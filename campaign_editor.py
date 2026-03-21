"""
Campaign Editor for Icarus GD.json prospect saves.

Reads and modifies WorldTalentRecords in WorldTalentManagerRecorderComponent
to toggle ambient world spawning effects from Great Hunt campaigns.

Usage:
    from campaign_editor import CampaignEditor, CAMPAIGN_STAGES

    editor = CampaignEditor('path/to/GD.json')
    editor.load()

    active = editor.get_active_talents()   # {'GH_RG_A', 'GH_RG_B'}

    editor.set_talent('GH_RG_B', False)   # disable world-wide Quarrite spawning
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

_WTML_COMPONENT    = b'/Script/Icarus.WorldTalentManagerRecorderComponent\x00'
_WORLD_TALENT_STRUCT = 'WorldTalentRecord'
_TOTAL_SIZE_POS    = 41   # offset of StateRecorderBlobs outer 'size' int32


# ---------------------------------------------------------------------------
# Editor
# ---------------------------------------------------------------------------

class CampaignEditor:
    """Read and modify WorldTalentRecords in a GD.json prospect save."""

    def __init__(self, gd_path: str):
        self.gd_path = gd_path
        self._ps = PropertySerializer()
        self.binary: bytes = b''

        self._bd_size_pos:  int = 0
        self._bd_count_pos: int = 0
        self._bd_data_pos:  int = 0
        self._bd_data_len:  int = 0

        self._props: List[FPropertyTag] = []
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
        # name FString
        name_len = struct.unpack_from('<i', d, p)[0]; p += 4 + name_len
        # type FString
        type_len = struct.unpack_from('<i', d, p)[0]; p += 4 + type_len
        # size field
        self._bd_size_pos = p; p += 4
        # array index
        p += 4
        # inner type FString
        inner_len = struct.unpack_from('<i', d, p)[0]; p += 4 + inner_len
        # HasGuid byte
        hg = d[p]; p += 1
        if hg:
            p += 16
        # count
        self._bd_count_pos = p
        bd_count = struct.unpack_from('<i', d, p)[0]; p += 4
        self._bd_data_pos = p
        self._bd_data_len = bd_count

        bd_bytes = d[self._bd_data_pos:self._bd_data_pos + bd_count]
        self._props = self._ps.deserialize(bd_bytes)

    # ------------------------------------------------------------------
    # Read API
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

    def get_prospect_name(self) -> str:
        """Return the ProspectMapName from the binary, or empty string."""
        pmn = next((p for p in self._props if p.name == 'ProspectMapName'), None)
        return pmn.value if pmn and pmn.value else ''

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

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
    # Save
    # ------------------------------------------------------------------

    def save(self, backup: bool = True) -> None:
        """Re-serialize the WorldTalentManager blob and write back to GD.json."""
        if backup:
            shutil.copy2(self.gd_path, self.gd_path + '.backup')

        new_bd    = self._ps.serialize(self._props, add_trailing=False)
        new_count = len(new_bd)
        old_count = self._bd_data_len
        delta     = new_count - old_count

        binary = bytearray(self.binary)

        # Patch BinaryData size field (payload = count + 4)
        binary[self._bd_size_pos:self._bd_size_pos + 4] = struct.pack('<i', new_count + 4)
        # Patch byte count
        binary[self._bd_count_pos:self._bd_count_pos + 4] = struct.pack('<i', new_count)
        # Replace payload
        binary[self._bd_data_pos:self._bd_data_pos + old_count] = new_bd

        # Update outer StateRecorderBlobs size field
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

        # Update internal state
        self._bd_data_len = new_count
        self.binary = new_binary
