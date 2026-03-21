"""
GD.json Player Inventory Editor for Icarus.

Parses and modifies player inventories stored in the ProspectBlob binary stream.

Usage:
    from gd_inventory_editor import GdInventoryEditor

    editor = GdInventoryEditor('path/to/GD.json')
    editor.load()

    # List players
    for p in editor.list_players():
        print(p)

    # View items
    for item in editor.get_items('76561198000000000'):
        print(item)

    # Add item to backpack (inventory ID 3)
    editor.set_item('76561198000000000', inv_id=3, location=5, item_name='Iron_Ingot', count=100)

    # Remove item
    editor.remove_item('76561198000000000', inv_id=3, location=5)

    editor.save(backup=True)
"""

import json
import base64
import zlib
import struct
import shutil
import os
import hashlib
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from copy import deepcopy

from ue4_properties import PropertySerializer, FPropertyTag


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# DynamicData index meanings (from game data analysis)
DYN_DURABILITY  = 6   # item durability / health value
DYN_STACK_COUNT = 7   # stack count (quantity)
DYN_MAX_STACK   = 9   # max stack size

# Known inventory IDs
INVENTORY_NAMES = {
    2:  "Equipment/Hotbar",
    3:  "Backpack",
    4:  "Belt",
    5:  "Armor/Cosmetics",
    11: "Inventory-11",
    12: "Inventory-12",
}

# Struct type names used when building new slots from scratch
_SLOT_STRUCT          = 'InventorySlotSaveData'
_DYNDATA_STRUCT       = 'InventorySlotDynamicData'
_ADDSTATS_STRUCT      = 'InventorySlotStatData'
_ALTERATIONS_STRUCT   = 'InventorySlotAlterationData'
_LIVING_STRUCT        = 'LivingItemSlotSaveData'


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PlayerState:
    """Player state blob loaded from the GD.json binary stream."""
    steam_id:    str
    char_slot:   int

    # Positions in the OUTER binary (for patching on save)
    bd_size_pos:  int   # position of BinaryData ArrayProperty 'size' field
    bd_count_pos: int   # position of BinaryData byte count (int32)
    bd_data_pos:  int   # position where BinaryData content starts
    bd_data_len:  int   # current byte length of BinaryData content

    # Parsed property tree
    props: List[FPropertyTag] = field(default_factory=list)
    dirty: bool = False


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _get_dyn_value(slot: FPropertyTag, index: int) -> Optional[int]:
    """Read a DynamicData entry value by index."""
    dd_prop = next((p for p in slot.nested if p.name == 'DynamicData'), None)
    if not dd_prop:
        return None
    for entry in dd_prop.nested:
        idx_p = next((p for p in entry.nested if p.name == 'Index'), None)
        val_p = next((p for p in entry.nested if p.name == 'Value'), None)
        if idx_p and val_p and idx_p.value == index:
            return val_p.value
    return None


def _set_dyn_value(slot: FPropertyTag, index: int, value: int) -> None:
    """Set (or create) a DynamicData entry by index."""
    dd_prop = next((p for p in slot.nested if p.name == 'DynamicData'), None)
    if not dd_prop:
        return
    for entry in dd_prop.nested:
        idx_p = next((p for p in entry.nested if p.name == 'Index'), None)
        val_p = next((p for p in entry.nested if p.name == 'Value'), None)
        if idx_p and idx_p.value == index:
            if val_p:
                val_p.value = value
            return
    # Not found – create new entry
    new_entry = FPropertyTag(
        name='DynamicData', type_name='StructProperty',
        struct_type=_DYNDATA_STRUCT,
        nested=[
            FPropertyTag('Index', 'IntProperty', value=index),
            FPropertyTag('Value', 'IntProperty', value=value),
        ]
    )
    dd_prop.nested.append(new_entry)


def _slot_to_dict(slot: FPropertyTag, inv_id: int) -> Optional[Dict]:
    """Convert a slot FPropertyTag to a plain dict for display."""
    item_prop = next((p for p in slot.nested if p.name == 'ItemStaticData'), None)
    loc_prop  = next((p for p in slot.nested if p.name == 'Location'), None)
    if not item_prop or not item_prop.value:
        return None
    return {
        'inv_id':    inv_id,
        'location':  loc_prop.value if loc_prop else None,
        'item':      item_prop.value,
        'count':     _get_dyn_value(slot, DYN_STACK_COUNT),
        'durability': _get_dyn_value(slot, DYN_DURABILITY),
    }


def _make_new_slot(location: int, item_name: str, count: int = 1,
                   durability: Optional[int] = None) -> FPropertyTag:
    """Build a minimal InventorySlotSaveData FPropertyTag from scratch."""
    dyn_entries = []

    if durability is not None:
        dyn_entries.append(FPropertyTag(
            'DynamicData', 'StructProperty', struct_type=_DYNDATA_STRUCT,
            nested=[
                FPropertyTag('Index', 'IntProperty', value=DYN_DURABILITY),
                FPropertyTag('Value', 'IntProperty', value=durability),
            ]
        ))

    dyn_entries.append(FPropertyTag(
        'DynamicData', 'StructProperty', struct_type=_DYNDATA_STRUCT,
        nested=[
            FPropertyTag('Index', 'IntProperty', value=DYN_STACK_COUNT),
            FPropertyTag('Value', 'IntProperty', value=count),
        ]
    ))

    return FPropertyTag(
        name='Slots', type_name='StructProperty',
        struct_type=_SLOT_STRUCT,
        nested=[
            FPropertyTag('Location',         'IntProperty',  value=location),
            FPropertyTag('ItemStaticData',    'NameProperty', value=item_name),
            FPropertyTag('ItemGuid',          'StrProperty',  value=None),
            FPropertyTag('ItemOwnerLookupId', 'IntProperty',  value=-1),
            FPropertyTag('DynamicData', 'ArrayProperty',
                         inner_type='StructProperty', struct_type=_DYNDATA_STRUCT,
                         elem_name='DynamicData', nested=dyn_entries),
            FPropertyTag('AdditionalStats', 'ArrayProperty',
                         inner_type='StructProperty', struct_type=_ADDSTATS_STRUCT,
                         elem_name='AdditionalStats', nested=[]),
            FPropertyTag('Alterations', 'ArrayProperty',
                         inner_type='StructProperty', struct_type=_ALTERATIONS_STRUCT,
                         elem_name='Alterations', nested=[]),
            FPropertyTag('LivingItemSlots', 'ArrayProperty',
                         inner_type='StructProperty', struct_type=_LIVING_STRUCT,
                         elem_name='LivingItemSlots', nested=[]),
        ]
    )


# ---------------------------------------------------------------------------
# Main editor class
# ---------------------------------------------------------------------------

class GdInventoryEditor:
    """
    Read and modify player inventories stored in a GD.json prospect save.

    Workflow:
        editor = GdInventoryEditor('/path/to/GD.json')
        editor.load()
        # ... make changes ...
        editor.save(backup=True)
    """

    _TOTAL_SIZE_POS = 41    # offset of StateRecorderBlobs outer 'size' int32

    def __init__(self, gd_path: str):
        self.gd_path = gd_path
        self.binary:  Optional[bytes] = None
        self.players: Dict[str, PlayerState] = {}
        self._ps = PropertySerializer()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load GD.json, decompress the prospect blob, and parse player states."""
        with open(self.gd_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        compressed = base64.b64decode(raw['ProspectBlob']['BinaryBlob'])
        self.binary = zlib.decompress(compressed)
        self.players = {}
        self._find_player_state_blobs()

    def _find_player_state_blobs(self) -> None:
        """Scan the binary for PlayerStateRecorderComponent entries."""
        d = self.binary
        pat = b'/Script/Icarus.PlayerStateRecorderComponent\x00'
        pos = 0
        while True:
            pos = d.find(pat, pos)
            if pos == -1:
                break
            state = self._parse_blob_at(d, pos)
            if state:
                self.players[state.steam_id] = state
            pos += len(pat)

    def _parse_blob_at(self, d: bytes, pat_pos: int) -> Optional[PlayerState]:
        """
        Parse the PlayerState blob whose ComponentClassName FString ends at pat_pos.
        Returns a PlayerState or None on parse failure.
        """
        # Find the BinaryData ArrayProperty (ByteProperty array) nearby
        bd_name_pos = d.find(b'BinaryData\x00', pat_pos, pat_pos + 500)
        if bd_name_pos == -1:
            return None

        # The FString length field is 4 bytes before the string content.
        p = bd_name_pos - 4
        try:
            # name FString
            name_len = struct.unpack_from('<i', d, p)[0]; p += 4
            p += name_len                                   # skip 'BinaryData\x00'
            # type FString
            type_len = struct.unpack_from('<i', d, p)[0]; p += 4
            p += type_len                                   # skip 'ArrayProperty\x00'
            # size field
            bd_size_pos = p
            bd_size = struct.unpack_from('<i', d, p)[0]; p += 4
            # array index
            p += 4
            # inner type FString
            inner_len = struct.unpack_from('<i', d, p)[0]; p += 4
            p += inner_len                                  # skip 'ByteProperty\x00'
            # HasGuid byte
            hg = d[p]; p += 1
            if hg: p += 16
            # count (number of bytes)
            bd_count_pos = p
            bd_count = struct.unpack_from('<i', d, p)[0]; p += 4
            bd_data_pos  = p
        except Exception:
            return None

        # Sanity checks
        if bd_size != bd_count + 4:
            return None
        if not (100 < bd_count < 10_000_000):
            return None

        # Parse properties from the BinaryData bytes
        bd_bytes = d[bd_data_pos:bd_data_pos + bd_count]
        try:
            props = self._ps.deserialize(bd_bytes)
        except Exception:
            return None

        # Extract steam ID
        steam_id  = None
        char_slot = 0
        pcid = next((pp for pp in props if pp.name == 'PlayerCharacterID'), None)
        if pcid:
            pid_p  = next((pp for pp in pcid.nested if pp.name == 'PlayerID'),  None)
            slot_p = next((pp for pp in pcid.nested if pp.name == 'ChrSlot'),   None)
            if pid_p:
                steam_id = pid_p.value
            if slot_p:
                char_slot = slot_p.value or 0

        if not steam_id:
            return None

        return PlayerState(
            steam_id=steam_id,
            char_slot=char_slot,
            bd_size_pos=bd_size_pos,
            bd_count_pos=bd_count_pos,
            bd_data_pos=bd_data_pos,
            bd_data_len=bd_count,
            props=props,
        )

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def list_players(self) -> List[Dict]:
        """Return a list of players found in the save."""
        result = []
        for steam_id, p in self.players.items():
            inv_summary = {}
            saved_inv = next((pp for pp in p.props if pp.name == 'SavedInventories'), None)
            if saved_inv:
                for entry in saved_inv.nested:
                    iid_p  = next((pp for pp in entry.nested if pp.name == 'InventoryID'), None)
                    slot_p = next((pp for pp in entry.nested if pp.name == 'Slots'), None)
                    if iid_p and slot_p:
                        items = sum(1 for s in slot_p.nested
                                    if any(pp.name == 'ItemStaticData' and pp.value
                                           for pp in s.nested))
                        inv_summary[iid_p.value] = items
            result.append({
                'steam_id':       steam_id,
                'char_slot':      p.char_slot,
                'inventories':    inv_summary,
            })
        return result

    def get_inventories(self, steam_id: str) -> List[Dict]:
        """Return metadata for each inventory of a player."""
        player = self.players.get(steam_id)
        if not player:
            return []
        saved_inv = next((pp for pp in player.props if pp.name == 'SavedInventories'), None)
        if not saved_inv:
            return []
        result = []
        for entry in saved_inv.nested:
            iid_p  = next((pp for pp in entry.nested if pp.name == 'InventoryID'), None)
            slot_p = next((pp for pp in entry.nested if pp.name == 'Slots'), None)
            inv_id = iid_p.value if iid_p else -1
            result.append({
                'id':         inv_id,
                'name':       INVENTORY_NAMES.get(inv_id, f'Inventory-{inv_id}'),
                'slot_count': len(slot_p.nested) if slot_p else 0,
            })
        return result

    def get_items(self, steam_id: str, inv_id: Optional[int] = None) -> List[Dict]:
        """Return all items for a player (optionally filtered by inventory ID)."""
        player = self.players.get(steam_id)
        if not player:
            return []
        saved_inv = next((pp for pp in player.props if pp.name == 'SavedInventories'), None)
        if not saved_inv:
            return []
        items = []
        for entry in saved_inv.nested:
            iid_p = next((pp for pp in entry.nested if pp.name == 'InventoryID'), None)
            if not iid_p:
                continue
            eid = iid_p.value
            if inv_id is not None and eid != inv_id:
                continue
            slot_p = next((pp for pp in entry.nested if pp.name == 'Slots'), None)
            if not slot_p:
                continue
            for slot in slot_p.nested:
                d = _slot_to_dict(slot, eid)
                if d:
                    items.append(d)
        return items

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    def set_item(self, steam_id: str, inv_id: int, location: int,
                 item_name: str, count: int = 1,
                 durability: Optional[int] = None) -> None:
        """
        Place an item at a specific slot location.
        If the slot already exists it is updated; otherwise a new slot is added.

        Args:
            steam_id:   Target player steam ID.
            inv_id:     Inventory ID (2=hotbar, 3=backpack, 5=armor).
            location:   Slot index within the inventory.
            item_name:  Game item row name (e.g. 'Iron_Ingot', 'Assault_Rifle').
            count:      Stack size / quantity.
            durability: Item durability value (omit for non-tool items).
        """
        player = self.players.get(steam_id)
        if not player:
            raise KeyError(f"Player {steam_id!r} not found")

        slot, slots_prop, _ = self._find_slot(player, inv_id, location)

        if slot:
            # Update existing slot
            item_p = next((p for p in slot.nested if p.name == 'ItemStaticData'), None)
            if item_p:
                item_p.value = item_name
            _set_dyn_value(slot, DYN_STACK_COUNT, count)
            if durability is not None:
                _set_dyn_value(slot, DYN_DURABILITY, durability)
        else:
            # Create new slot
            if slots_prop is None:
                raise ValueError(f"Inventory {inv_id} not found for player {steam_id}")
            new_slot = _make_new_slot(location, item_name, count, durability)
            slots_prop.nested.append(new_slot)

        player.dirty = True

    def remove_item(self, steam_id: str, inv_id: int, location: int) -> bool:
        """
        Remove an item from the given slot.
        Returns True if found and removed, False if slot was already empty.
        """
        player = self.players.get(steam_id)
        if not player:
            raise KeyError(f"Player {steam_id!r} not found")

        slot, slots_prop, _ = self._find_slot(player, inv_id, location)
        if slot is None:
            return False

        slots_prop.nested.remove(slot)
        player.dirty = True
        return True

    def clear_inventory(self, steam_id: str, inv_id: int) -> int:
        """
        Remove ALL items from an inventory.
        Returns the number of slots removed.
        """
        player = self.players.get(steam_id)
        if not player:
            raise KeyError(f"Player {steam_id!r} not found")

        saved_inv = next((pp for pp in player.props if pp.name == 'SavedInventories'), None)
        if not saved_inv:
            return 0

        removed = 0
        for entry in saved_inv.nested:
            iid_p = next((pp for pp in entry.nested if pp.name == 'InventoryID'), None)
            if not iid_p or iid_p.value != inv_id:
                continue
            slot_p = next((pp for pp in entry.nested if pp.name == 'Slots'), None)
            if slot_p:
                removed = len(slot_p.nested)
                slot_p.nested.clear()
                player.dirty = True
        return removed

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(self, backup: bool = True) -> None:
        """
        Re-serialize dirty players and write changes back to GD.json.
        Patches the binary stream in-memory, updates size fields, and
        re-compresses the ProspectBlob.

        Args:
            backup: If True, copy the original file to GD.json.backup first.
        """
        dirty = [p for p in self.players.values() if p.dirty]
        if not dirty:
            print("No changes to save.")
            return

        if backup:
            bak = self.gd_path + '.backup'
            shutil.copy2(self.gd_path, bak)
            print(f"Backup saved to {bak}")

        # Build new binary with all changes applied.
        # Process players sorted by ascending bd_data_pos so position adjustments
        # accumulate correctly.
        binary = bytearray(self.binary)
        total_delta = 0

        for player in sorted(dirty, key=lambda p: p.bd_data_pos):
            new_bd = self._ps.serialize(player.props, add_trailing=True)
            new_count = len(new_bd)
            old_count = player.bd_data_len
            delta     = new_count - old_count

            # Adjust for any patches applied before this player.
            size_pos  = player.bd_size_pos  + total_delta
            count_pos = player.bd_count_pos + total_delta
            data_pos  = player.bd_data_pos  + total_delta

            # Patch size field (payload size = count + 4)
            binary[size_pos:size_pos + 4] = struct.pack('<i', new_count + 4)
            # Patch count field
            binary[count_pos:count_pos + 4] = struct.pack('<i', new_count)
            # Replace byte array content
            binary[data_pos:data_pos + old_count] = new_bd

            total_delta += delta

        # Update outer StateRecorderBlobs 'size' field if content length changed.
        if total_delta != 0:
            tsp = self._TOTAL_SIZE_POS
            old_total = struct.unpack_from('<i', bytes(binary), tsp)[0]
            binary[tsp:tsp + 4] = struct.pack('<i', old_total + total_delta)

        # Re-compress and update GD.json.
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
        blob['UncompressedLength'] = len(new_binary)
        with open(self.gd_path, 'w', encoding='utf-8') as f:
            json.dump(gd_data, f, separators=(',', ':'), ensure_ascii=False)

        print(f"Saved to {self.gd_path} "
              f"(binary delta: {total_delta:+d} bytes, "
              f"compressed: {len(compressed):,} bytes)")

        # Mark players as clean and update positions for subsequent saves.
        # (Reload is safest for further edits; warn accordingly.)
        for player in dirty:
            player.dirty = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_slot(self, player: PlayerState, inv_id: int,
                   location: int):
        """
        Locate the (slot FPropertyTag, slots_array FPropertyTag, entry FPropertyTag)
        for a given player / inventory / slot-location.
        Returns (slot, slots_array, entry) — slot may be None if not found.
        """
        saved_inv = next((pp for pp in player.props if pp.name == 'SavedInventories'), None)
        if not saved_inv:
            return None, None, None

        for entry in saved_inv.nested:
            iid_p = next((pp for pp in entry.nested if pp.name == 'InventoryID'), None)
            if not iid_p or iid_p.value != inv_id:
                continue
            slot_p = next((pp for pp in entry.nested if pp.name == 'Slots'), None)
            if slot_p is None:
                return None, None, entry
            for slot in slot_p.nested:
                loc_p = next((pp for pp in slot.nested if pp.name == 'Location'), None)
                if loc_p and loc_p.value == location:
                    return slot, slot_p, entry
            # Inventory found but slot not at this location
            return None, slot_p, entry

        return None, None, None
