"""
Campaign Editor for Icarus GD.json prospect saves.

Reads and modifies WorldTalentRecords and Rock Golem spawner actor blobs.

Option D — WorldTalentRecords (ambient spawning via WorldStats):
    editor.set_talent('GH_RG_B', False)

Option B — OwnerResolvePolicy (prevents blob-driven actor re-creation):
    editor.set_option_b(True)   # FindOrRespawn → FindOnly

Option C — RecordedNumSpawned (caps the spawner's counter):
    editor.set_option_c(True)   # set to 9999

Option A — Delete spawner blobs (removes actor state entries entirely):
    editor.delete_spawner_blobs()

Usage:
    from campaign_editor import CampaignEditor, CAMPAIGN_STAGES

    editor = CampaignEditor('path/to/GD.json')
    editor.load()
    editor.set_option_b(True)
    editor.set_talent('GH_RG_B', False)
    editor.save(backup=True)
"""

import json
import base64
import zlib
import struct
import shutil
import hashlib
from typing import List, Dict, Optional, Set

from ue4_properties import PropertySerializer, FPropertyTag


# ---------------------------------------------------------------------------
# Campaign stage definitions — all stages that set a WorldStat spawn flag
# ---------------------------------------------------------------------------

CAMPAIGN_STAGES: List[Dict] = [
    {
        'row':         'GH_RG_A',
        'label':       'Stage A',
        'effect':      'Desert Quarrite Spawning',
        'description': 'Juvenile Quarrites spawn in desert zones',
        'world_stat':  'WorldJuvenileRockGolemDesertSpawn',
    },
    {
        'row':         'GH_RG_B',
        'label':       'Stage B',
        'effect':      'World-Wide Quarrite Spawning',
        'description': 'Juvenile Quarrites spawn across the entire map',
        'world_stat':  'WorldJuvenileRockGolemWorldSpawn',
    },
    {
        'row':         'GH_RG_C',
        'label':       'Stage C  [Choice vs D]',
        'effect':      'Landsharks in Caves',
        'description': 'Landsharks begin appearing inside caves',
        'world_stat':  'WorldLandsharksAppearInCaves',
    },
    {
        'row':         'GH_RG_D',
        'label':       'Stage D  [Choice vs C]',
        'effect':      'Caveworms Outside Caves',
        'description': 'Caveworms escape caves and roam the surface',
        'world_stat':  'WorldCavewormsSpawnOutsideCaves',
    },
    {
        'row':         'GH_RG_C2',
        'label':       'Stage C2',
        'effect':      'Exotic Quarrite Spawning',
        'description': 'Exotic-infused Quarrites begin spawning (requires C)',
        'world_stat':  'WorldJuvenileRockGolemExoticSpawn',
    },
    {
        'row':         'GH_RG_O2',
        'label':       'Optional O2',
        'effect':      'Quarrite Explosive Weakness',
        'description': 'Quarrites gain weakness to explosive damage',
        'world_stat':  'WorldRockGolemExplosiveWeakness',
    },
    {
        'row':         'GH_RG_E',
        'label':       'Stage E  [Choice vs F]',
        'effect':      'Increased Quarrite Loot',
        'description': 'Quarrite loot table is improved',
        'world_stat':  'WorldJuvenileRockGolemLootIncreased',
    },
    {
        'row':         'GH_RG_F',
        'label':       'Stage F  [Choice vs E]',
        'effect':      'Reduced Boss Minions',
        'description': 'Fewer Quarrite minions in the final boss fight',
        'world_stat':  'WorldRockGolemMinionsReduced',
    },
]

# ---------------------------------------------------------------------------
# Binary constants
# ---------------------------------------------------------------------------

_WTML_COMPONENT      = b'/Script/Icarus.WorldTalentManagerRecorderComponent\x00'
_WORLD_TALENT_STRUCT = 'WorldTalentRecord'
_TOTAL_SIZE_POS      = 41   # offset of StateRecorderBlobs outer 'size' int32
_ARRAY_COUNT_POS     = 69   # offset of StateRecorderBlobs element count int32

# Blob start marker: every StateRecorderBlobs entry begins with this FPropertyTag name
# "OwnerResolvePolicy" = 18 chars + null = 19 bytes → FString length prefix = 0x13
_ORP_PROP_NAME = b'\x13\x00\x00\x00OwnerResolvePolicy\x00'

# Rock Golem spawner actor class names found in blob outer properties
_SPAWNER_CLASSES = [b'BP_Rock_Golem_Spawner_C', b'BP_Rock_Golem_Spawner_Drill_C']

# Option B: enum value strings (with null terminator, FString content only)
_FIND_OR_RESPAWN = b'EStateRecorderOwnerResolvePolicy::FindOrRespawn\x00'
_FIND_ONLY       = b'EStateRecorderOwnerResolvePolicy::FindOnly\x00'

# Option B: EnumProperty size field is at value_content_pos - 50
# (name_fstr:23 + type_fstr:17 + size:4 + idx:4 + enum_type_fstr:37 + hasguid:1 + fstr_len:4 = 90
#  counting from FPropertyTag start; offset from value_content = -(hasguid + fstr_len + enum_type_fstr + idx + size)
#  = -(1 + 4 + 37 + 4 + 4) = -50)
_B_SIZE_OFFSET = -50
_B_FSTR_OFFSET = -4   # FString length prefix is 4 bytes before value content

# Option C: RecordedNumSpawned value offset within its FPropertyTag
# name(19) + iVariable_fstr_len(4) + iVariable(10) + IntProperty_fstr_len(4) + IntProperty(12)
# + size(4) + array_idx(4) + hasguid(1) = 58
_C_RNS_PATTERN = b'RecordedNumSpawned\x00'
_C_VAL_OFFSET  = 58


# ---------------------------------------------------------------------------
# Editor
# ---------------------------------------------------------------------------

class CampaignEditor:
    """
    Read and modify campaign-related data in a GD.json prospect save.

    Supports:
      Option A — Delete spawner actor blobs entirely
      Option B — Toggle OwnerResolvePolicy FindOrRespawn ↔ FindOnly
      Option C — Toggle RecordedNumSpawned 0 ↔ 9999
      Option D — Toggle WorldTalentRecords entries (ambient spawning)
    """

    def __init__(self, gd_path: str):
        self.gd_path = gd_path
        self._ps = PropertySerializer()
        self.binary: bytes = b''

        # WorldTalentManager BinaryData patch positions (Option D)
        self._bd_size_pos:  int = 0
        self._bd_count_pos: int = 0
        self._bd_data_pos:  int = 0
        self._bd_data_len:  int = 0
        self._props: List[FPropertyTag] = []

        # Spawner blob metadata (Options A/B/C)
        self._spawner_blobs: List[Dict] = []   # {start, end}

        self.loaded: bool = False

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self) -> None:
        with open(self.gd_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        compressed = base64.b64decode(raw['ProspectBlob']['BinaryBlob'])
        self.binary = zlib.decompress(compressed)
        self._parse_talent_manager()
        self._find_spawner_blobs()
        self.loaded = True

    def _parse_talent_manager(self) -> None:
        d = self.binary
        pos = d.find(_WTML_COMPONENT)
        if pos == -1:
            raise ValueError("WorldTalentManagerRecorderComponent not found in GD.json")

        bd_name_pos = d.find(b'BinaryData\x00', pos, pos + 500)
        if bd_name_pos == -1:
            raise ValueError("BinaryData not found near WorldTalentManager")

        p = bd_name_pos - 4
        name_len = struct.unpack_from('<i', d, p)[0]; p += 4 + name_len
        type_len = struct.unpack_from('<i', d, p)[0]; p += 4 + type_len
        self._bd_size_pos = p; p += 4
        p += 4
        inner_len = struct.unpack_from('<i', d, p)[0]; p += 4 + inner_len
        hg = d[p]; p += 1
        if hg:
            p += 16
        self._bd_count_pos = p
        bd_count = struct.unpack_from('<i', d, p)[0]; p += 4
        self._bd_data_pos = p
        self._bd_data_len = bd_count

        bd_bytes = d[self._bd_data_pos:self._bd_data_pos + bd_count]
        self._props = self._ps.deserialize(bd_bytes)

    def _find_spawner_blobs(self) -> None:
        """Locate all Rock Golem spawner actor state blobs by scanning ORP property starts."""
        d = self.binary

        # Every StateRecorderBlobs entry starts with an OwnerResolvePolicy FPropertyTag.
        # Finding all these start positions lets us determine exact blob boundaries.
        all_starts: List[int] = []
        pos = 0
        while True:
            p = d.find(_ORP_PROP_NAME, pos)
            if p == -1:
                break
            all_starts.append(p)
            pos = p + 1
        all_starts.sort()

        # FString length prefix for "ComponentClassName\x00" (18 chars + null = 19 → 0x13)
        _COMP_CLASS_PROP = b'\x13\x00\x00\x00ComponentClassName\x00'

        self._spawner_blobs = []
        for i, start in enumerate(all_starts):
            end = all_starts[i + 1] if i + 1 < len(all_starts) else len(d)
            seg = d[start:end]

            # Only inspect the outer property section (before ComponentClassName+BinaryData).
            # Spawner class names may also appear deep inside BinaryData of adjacent blobs.
            comp_pos = seg.find(_COMP_CLASS_PROP)
            outer_seg = seg[:comp_pos] if comp_pos != -1 else seg[:600]

            for sc in _SPAWNER_CLASSES:
                if sc in outer_seg:
                    self._spawner_blobs.append({'start': start, 'end': end})
                    break

    # ------------------------------------------------------------------
    # Option D — WorldTalentRecords (ambient spawning)
    # ------------------------------------------------------------------

    def get_active_talents(self) -> Set[str]:
        """Return the set of RowNames currently present in WorldTalentRecords."""
        wtr = next((p for p in self._props if p.name == 'WorldTalentRecords'), None)
        if not wtr:
            return set()
        result = set()
        for entry in wtr.nested:
            rn = next((p for p in entry.nested if p.name == 'RowName'), None)
            if rn and rn.value:
                result.add(rn.value)
        return result

    def set_talent(self, row_name: str, active: bool) -> None:
        """Add or remove a talent row in WorldTalentRecords."""
        wtr = next((p for p in self._props if p.name == 'WorldTalentRecords'), None)
        if not wtr:
            return

        existing = next(
            (e for e in wtr.nested
             if any(p.name == 'RowName' and p.value == row_name for p in e.nested)),
            None
        )

        if active and not existing:
            wtr.nested.append(FPropertyTag(
                name='WorldTalentRecords',
                type_name='StructProperty',
                struct_type=_WORLD_TALENT_STRUCT,
                nested=[
                    FPropertyTag('RowName', 'StrProperty', value=row_name),
                    FPropertyTag('Rank',    'IntProperty', value=1),
                ]
            ))
        elif not active and existing:
            wtr.nested.remove(existing)

    # ------------------------------------------------------------------
    # Option B — OwnerResolvePolicy (blob re-creation)
    # ------------------------------------------------------------------

    def get_option_b_state(self) -> bool:
        """Return True if ALL spawner blobs currently have FindOnly (Option B active)."""
        if not self._spawner_blobs:
            return False
        for blob in self._spawner_blobs:
            seg = self.binary[blob['start']:blob['end']]
            if _FIND_OR_RESPAWN in seg:
                return False
        return True

    def set_option_b(self, enabled: bool) -> None:
        """
        enabled=True:  FindOrRespawn → FindOnly   (prevents actor re-creation)
        enabled=False: FindOnly → FindOrRespawn   (restores default)
        """
        old_val = _FIND_OR_RESPAWN if enabled else _FIND_ONLY
        new_val = _FIND_ONLY       if enabled else _FIND_OR_RESPAWN

        old_size = struct.pack('<i', 4 + len(old_val))   # EnumProperty size field
        new_size = struct.pack('<i', 4 + len(new_val))
        old_flen = struct.pack('<i', len(old_val))        # FString length prefix
        new_flen = struct.pack('<i', len(new_val))

        delta_per = len(new_val) - len(old_val)

        # Collect all absolute positions of old_val within spawner blob ranges
        positions: List[int] = []
        for blob in self._spawner_blobs:
            seg = self.binary[blob['start']:blob['end']]
            p = 0
            while True:
                q = seg.find(old_val, p)
                if q == -1:
                    break
                positions.append(blob['start'] + q)
                p = q + 1

        if not positions:
            return

        # Apply replacements in reverse position order (high → low) so earlier
        # offsets remain valid after each variable-length substitution.
        d = bytearray(self.binary)
        for abs_pos in sorted(positions, reverse=True):
            size_pos = abs_pos + _B_SIZE_OFFSET
            flen_pos = abs_pos + _B_FSTR_OFFSET
            val_end  = abs_pos + len(old_val)

            d[size_pos:size_pos + 4] = new_size
            d[flen_pos:flen_pos + 4] = new_flen
            d[abs_pos:val_end]       = new_val

        # Update outer StateRecorderBlobs total size
        total_delta = delta_per * len(positions)
        if total_delta != 0:
            old_total = struct.unpack_from('<i', bytes(d), _TOTAL_SIZE_POS)[0]
            d[_TOTAL_SIZE_POS:_TOTAL_SIZE_POS + 4] = struct.pack('<i', old_total + total_delta)

        self.binary = bytes(d)
        self._find_spawner_blobs()

    # ------------------------------------------------------------------
    # Option C — RecordedNumSpawned (spawn cap)
    # ------------------------------------------------------------------

    def get_option_c_state(self) -> bool:
        """Return True if any spawner blob has RecordedNumSpawned >= 9999."""
        for blob in self._spawner_blobs:
            seg = self.binary[blob['start']:blob['end']]
            p = 0
            while True:
                q = seg.find(_C_RNS_PATTERN, p)
                if q == -1:
                    break
                val_offset = q + _C_VAL_OFFSET
                if val_offset + 4 <= len(seg):
                    val = struct.unpack_from('<i', seg, val_offset)[0]
                    if val >= 9999:
                        return True
                p = q + 1
        return False

    def set_option_c(self, enabled: bool) -> None:
        """
        enabled=True:  set RecordedNumSpawned = 9999
        enabled=False: reset RecordedNumSpawned = 0
        """
        target = struct.pack('<i', 9999 if enabled else 0)
        d = bytearray(self.binary)

        for blob in self._spawner_blobs:
            seg = self.binary[blob['start']:blob['end']]
            p = 0
            while True:
                q = seg.find(_C_RNS_PATTERN, p)
                if q == -1:
                    break
                abs_val_pos = blob['start'] + q + _C_VAL_OFFSET
                d[abs_val_pos:abs_val_pos + 4] = target
                p = q + 1

        self.binary = bytes(d)

    # ------------------------------------------------------------------
    # Option A — Delete spawner blobs
    # ------------------------------------------------------------------

    def get_spawner_count(self) -> int:
        """Return the number of spawner actor state blobs currently in the save."""
        return len(self._spawner_blobs)

    def delete_spawner_blobs(self) -> None:
        """
        Remove all Rock Golem spawner actor state blobs from StateRecorderBlobs.
        This is irreversible — save a backup first.
        """
        if not self._spawner_blobs:
            return

        d = bytearray(self.binary)
        total_removed = 0

        # Delete in reverse position order so earlier offsets stay valid
        for blob in sorted(self._spawner_blobs, key=lambda b: b['start'], reverse=True):
            start, end = blob['start'], blob['end']
            del d[start:end]
            total_removed += end - start

        # Decrement StateRecorderBlobs element count
        old_count = struct.unpack_from('<i', bytes(d), _ARRAY_COUNT_POS)[0]
        d[_ARRAY_COUNT_POS:_ARRAY_COUNT_POS + 4] = struct.pack(
            '<i', old_count - len(self._spawner_blobs))

        # Update outer size field
        old_total = struct.unpack_from('<i', bytes(d), _TOTAL_SIZE_POS)[0]
        d[_TOTAL_SIZE_POS:_TOTAL_SIZE_POS + 4] = struct.pack(
            '<i', old_total - total_removed)

        self.binary = bytes(d)
        self._spawner_blobs = []   # blobs are gone

    # ------------------------------------------------------------------
    # Save (applies Option D WorldTalentRecords changes + writes file)
    # ------------------------------------------------------------------

    def save(self, backup: bool = True) -> None:
        """
        Re-serialize WorldTalentRecords into BinaryData, compress, and write GD.json.
        Options A/B/C changes are applied directly to self.binary before this call
        via their respective set_* methods.
        """
        if backup:
            shutil.copy2(self.gd_path, self.gd_path + '.backup')

        new_bd    = self._ps.serialize(self._props, add_trailing=False)
        new_count = len(new_bd)
        old_count = self._bd_data_len
        delta     = new_count - old_count

        binary = bytearray(self.binary)

        # Patch WorldTalentManager BinaryData size and content
        binary[self._bd_size_pos:self._bd_size_pos + 4] = struct.pack('<i', new_count + 4)
        binary[self._bd_count_pos:self._bd_count_pos + 4] = struct.pack('<i', new_count)
        binary[self._bd_data_pos:self._bd_data_pos + old_count] = new_bd

        # Update outer StateRecorderBlobs total size (if WorldTalentRecords changed)
        if delta != 0:
            old_total = struct.unpack_from('<i', bytes(binary), _TOTAL_SIZE_POS)[0]
            binary[_TOTAL_SIZE_POS:_TOTAL_SIZE_POS + 4] = struct.pack('<i', old_total + delta)

        new_binary = bytes(binary)
        compressed = zlib.compress(new_binary, level=6)
        b64_blob   = base64.b64encode(compressed).decode('ascii')

        with open(self.gd_path, 'r', encoding='utf-8') as f:
            gd_data = json.load(f)
        blob = gd_data['ProspectBlob']
        blob['BinaryBlob'] = b64_blob
        blob['Hash'] = hashlib.sha1(new_binary).hexdigest()
        blob['TotalLength'] = len(compressed)
        blob['DataLength'] = len(compressed)
        with open(self.gd_path, 'w', encoding='utf-8') as f:
            json.dump(gd_data, f, separators=(',', ':'), ensure_ascii=False)

        # Update internal state so further saves work correctly
        self._bd_data_len = new_count
        self.binary = new_binary
