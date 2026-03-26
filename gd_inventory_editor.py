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
DYN_FILL_AMOUNT = 10  # current fill level (water, oxygen, etc.)
DYN_FILL_TYPE   = 11  # fill type: 2=water, 4=oxygen
DYN_LINKED_INV  = 13  # linked sub-inventory ID (pouches, armor upgrade slots)

# Fill type labels
FILL_TYPE_NAMES = {2: 'Water', 4: 'Oxygen'}

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
_INVSAVE_STRUCT       = 'InventorySaveData'


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


@dataclass
class ContainerManagerState:
    """
    IcarusContainerManagerRecorderComponent blob.

    Stores all sub-inventory contents for items that have container slots:
    pouches, weapon ammo slots, armor upgrade slots, etc.

    SavedInventoryContainers[i] describes container slot i (type/info).
    SavedInventories[i] holds the actual items in container slot i.

    Player slots reference this via DynamicData index 13 (DYN_LINKED_INV),
    which is the array index into SavedInventories.
    """
    bd_size_pos:  int
    bd_count_pos: int
    bd_data_pos:  int
    bd_data_len:  int
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


_KNOWN_DYN_INDICES = frozenset({
    DYN_DURABILITY, DYN_STACK_COUNT, DYN_MAX_STACK,
    DYN_FILL_AMOUNT, DYN_FILL_TYPE, DYN_LINKED_INV,
})


def _get_extra_dyn_values(slot: FPropertyTag) -> Dict[int, int]:
    """Return all DynamicData entries whose index is not in the known set."""
    dd_prop = next((p for p in slot.nested if p.name == 'DynamicData'), None)
    if not dd_prop:
        return {}
    result = {}
    for entry in dd_prop.nested:
        idx_p = next((p for p in entry.nested if p.name == 'Index'), None)
        val_p = next((p for p in entry.nested if p.name == 'Value'), None)
        if idx_p and val_p and idx_p.value not in _KNOWN_DYN_INDICES:
            result[idx_p.value] = val_p.value
    return result


def _slot_to_dict(slot: FPropertyTag, inv_id: int) -> Optional[Dict]:
    """Convert a slot FPropertyTag to a plain dict for display."""
    item_prop = next((p for p in slot.nested if p.name == 'ItemStaticData'), None)
    loc_prop  = next((p for p in slot.nested if p.name == 'Location'), None)
    if not item_prop or not item_prop.value:
        return None
    d = {
        'inv_id':        inv_id,
        'location':      loc_prop.value if loc_prop else None,
        'item':          item_prop.value,
        'count':         _get_dyn_value(slot, DYN_STACK_COUNT),
        'durability':    _get_dyn_value(slot, DYN_DURABILITY),
        'fill_amount':   _get_dyn_value(slot, DYN_FILL_AMOUNT),
        'fill_type':     _get_dyn_value(slot, DYN_FILL_TYPE),
        'linked_inv_id': _get_dyn_value(slot, DYN_LINKED_INV),
    }
    extra = _get_extra_dyn_values(slot)
    if extra:
        d['dyn_data_extra'] = extra
    return d


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

    _TOTAL_SIZE_POS = 41    # offset of StateRecorderBlobs outer ArrayProperty 'size' int32
    _PROTO_SIZE_POS = 115   # offset of prototype StructProperty 'size' int32 (= total element data)

    def __init__(self, gd_path: str):
        self.gd_path = gd_path
        self.binary:  Optional[bytes] = None
        self.players: Dict[str, PlayerState] = {}
        self.container_manager: Optional[ContainerManagerState] = None
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
        self.container_manager = None
        self._find_player_state_blobs()
        self._find_container_manager_blob()

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

    def _find_container_manager_blob(self) -> None:
        """
        Locate and parse the IcarusContainerManagerRecorderComponent binary blob.

        This component stores all sub-inventory contents for portable containers
        (pouches, weapon ammo slots, armor upgrade slots).  Player slots reference
        it via DYN_LINKED_INV (DynamicData index 13), which is the ARRAY INDEX
        into ContainerManager.SavedInventories (not an inventory ID).
        """
        d = self.binary
        pat = b'/Script/Icarus.IcarusContainerManagerRecorderComponent\x00'
        pos = d.find(pat)
        if pos == -1:
            return

        bd_name_pos = d.find(b'BinaryData\x00', pos, pos + 500)
        if bd_name_pos == -1:
            return

        p = bd_name_pos - 4
        try:
            name_len = struct.unpack_from('<i', d, p)[0]; p += 4
            p += name_len
            type_len = struct.unpack_from('<i', d, p)[0]; p += 4
            p += type_len
            bd_size_pos = p
            bd_size = struct.unpack_from('<i', d, p)[0]; p += 4
            p += 4
            inner_len = struct.unpack_from('<i', d, p)[0]; p += 4
            p += inner_len
            hg = d[p]; p += 1
            if hg: p += 16
            bd_count_pos = p
            bd_count = struct.unpack_from('<i', d, p)[0]; p += 4
            bd_data_pos = p
        except Exception:
            return

        if bd_size != bd_count + 4:
            return
        if not (10 < bd_count < 10_000_000):
            return

        try:
            props = self._ps.deserialize(d[bd_data_pos:bd_data_pos + bd_count])
        except Exception:
            return

        self.container_manager = ContainerManagerState(
            bd_size_pos=bd_size_pos,
            bd_count_pos=bd_count_pos,
            bd_data_pos=bd_data_pos,
            bd_data_len=bd_count,
            props=props,
        )

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def _container_array_pos(self, inventory_index: int) -> int:
        """
        Find the array position in SavedInventories/SavedInventoryContainers that
        corresponds to the given InventoryIndex value.

        DYN_LINKED_INV stores an InventoryIndex (logical ID), NOT a direct array
        position.  The SavedInventoryContainers list can have gaps in InventoryIndex
        values when containers have been dynamically added across multiple players.

        Returns -1 if not found.
        """
        if not self.container_manager:
            return -1
        sic = next(
            (p for p in self.container_manager.props
             if p.name == 'SavedInventoryContainers'),
            None)
        if not sic:
            return -1
        for pos, entry in enumerate(sic.nested):
            ii_p = next((p for p in entry.nested if p.name == 'InventoryIndex'), None)
            if ii_p and ii_p.value == inventory_index:
                return pos
        return -1

    def get_container_items(self, inventory_index: int) -> List[Dict]:
        """
        Return items from the container slot with the given InventoryIndex.

        inventory_index is the DYN_LINKED_INV (DynamicData index 13) value from
        a player's inventory slot — it is the logical InventoryIndex stored in
        SavedInventoryContainers, NOT a direct array position.

        Returns an empty list if no ContainerManager was found or the index is
        not registered.
        """
        pos = self._container_array_pos(inventory_index)
        if pos == -1:
            return []
        if not self.container_manager:
            return []
        saved_inv = next(
            (p for p in self.container_manager.props if p.name == 'SavedInventories'),
            None)
        if not saved_inv or pos >= len(saved_inv.nested):
            return []
        entry = saved_inv.nested[pos]
        slots_p = next((p for p in entry.nested if p.name == 'Slots'), None)
        if not slots_p:
            return []
        result = []
        for slot in slots_p.nested:
            d = _slot_to_dict(slot, inventory_index)
            if d:
                result.append(d)
        return result

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
                 durability: Optional[int] = None,
                 fill_amount: Optional[int] = None) -> None:
        """
        Place an item at a specific slot location.
        If the slot already exists it is updated; otherwise a new slot is added.

        Args:
            steam_id:    Target player steam ID.
            inv_id:      Inventory ID (2=hotbar, 3=backpack, 5=armor).
            location:    Slot index within the inventory.
            item_name:   Game item row name (e.g. 'Iron_Ingot', 'Assault_Rifle').
            count:       Stack size / quantity.
            durability:  Item durability value (omit for non-tool items).
            fill_amount: Fill level for fillable items (water, oxygen, etc.).
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
            if fill_amount is not None:
                _set_dyn_value(slot, DYN_FILL_AMOUNT, fill_amount)
        else:
            # Create new slot
            if slots_prop is None:
                raise ValueError(f"Inventory {inv_id} not found for player {steam_id}")
            new_slot = _make_new_slot(location, item_name, count, durability)
            if fill_amount is not None:
                _set_dyn_value(new_slot, DYN_FILL_AMOUNT, fill_amount)
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
        dirty_players = [p for p in self.players.values() if p.dirty]
        dirty_cm = self.container_manager and self.container_manager.dirty
        if not dirty_players and not dirty_cm:
            print("No changes to save.")
            return

        if backup:
            bak = self.gd_path + '.backup'
            shutil.copy2(self.gd_path, bak)
            print(f"Backup saved to {bak}")

        # Build new binary with all changes applied.
        # Collect all dirty blobs (players + container manager) sorted by position
        # so that offset adjustments accumulate correctly.
        binary = bytearray(self.binary)
        total_delta = 0

        # Build list of (bd_data_pos, blob_state) for all dirty blobs
        dirty_blobs = []
        for player in dirty_players:
            dirty_blobs.append(player)
        if dirty_cm:
            dirty_blobs.append(self.container_manager)
        dirty_blobs.sort(key=lambda b: b.bd_data_pos)

        for blob in dirty_blobs:
            if isinstance(blob, ContainerManagerState):
                new_bd = self._ps.serialize(blob.props, add_trailing=True)
            else:
                new_bd = self._ps.serialize(blob.props, add_trailing=True)
            new_count = len(new_bd)
            old_count = blob.bd_data_len
            delta     = new_count - old_count

            size_pos  = blob.bd_size_pos  + total_delta
            count_pos = blob.bd_count_pos + total_delta
            data_pos  = blob.bd_data_pos  + total_delta

            binary[size_pos:size_pos + 4] = struct.pack('<i', new_count + 4)
            binary[count_pos:count_pos + 4] = struct.pack('<i', new_count)
            binary[data_pos:data_pos + old_count] = new_bd

            total_delta += delta

        # Update outer StateRecorderBlobs size fields if content length changed.
        # Both the ArrayProperty 'size' (pos 41) and the prototype tag 'size' (pos 115)
        # represent the total element data and must be kept in sync.
        if total_delta != 0:
            for pos in (self._TOTAL_SIZE_POS, self._PROTO_SIZE_POS):
                old_val = struct.unpack_from('<i', bytes(binary), pos)[0]
                binary[pos:pos + 4] = struct.pack('<i', old_val + total_delta)

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

        # Mark blobs as clean.
        for blob in dirty_blobs:
            blob.dirty = False

    def export_inventory(self, steam_id: str, inv_id: int) -> Dict:
        """Export a player inventory to a portable dict (for saving to a JSON file)."""
        inv_name = INVENTORY_NAMES.get(inv_id, f'Inventory-{inv_id}')
        return {
            'type': 'icarus_prospect_inventory',
            'version': 1,
            'inventory_id': inv_id,
            'inventory_name': inv_name,
            'items': self._export_items_with_living(steam_id, inv_id),
        }

    def _export_items_with_living(self, steam_id: str, inv_id: int) -> List[Dict]:
        """Return items for an inventory with living_slots_bin / container_items for slots that have them."""
        player = self.players.get(steam_id)
        if not player:
            return []
        saved_inv = next((pp for pp in player.props if pp.name == 'SavedInventories'), None)
        if not saved_inv:
            return []
        items = []
        for entry in saved_inv.nested:
            iid_p = next((pp for pp in entry.nested if pp.name == 'InventoryID'), None)
            if not iid_p or iid_p.value != inv_id:
                continue
            slot_p = next((pp for pp in entry.nested if pp.name == 'Slots'), None)
            if not slot_p:
                break
            for slot in slot_p.nested:
                d = _slot_to_dict(slot, inv_id)
                if not d:
                    continue
                # Weapon modifications: serialise LivingItemSlots as binary blob
                living = next((p for p in slot.nested if p.name == 'LivingItemSlots'), None)
                if living and living.nested:
                    binary = self._ps.serialize([living], add_trailing=False)
                    d['living_slots_bin'] = base64.b64encode(binary).decode('ascii')
                # Pouch / upgrade-slot contents: stored in ContainerManager by array index
                container_idx = d.get('linked_inv_id')
                if container_idx is not None:
                    d['container_items'] = self.get_container_items(container_idx)
                items.append(d)
            break
        return items

    def _get_linked_inventory_items(self, saved_inv: FPropertyTag,
                                     linked_inv_id: int) -> List[Dict]:
        """
        Compatibility shim: look up container items via ContainerManager.

        The linked_inv_id is the DYN_LINKED_INV value (ContainerManager array index).
        """
        return self.get_container_items(linked_inv_id)

    def import_inventory(self, steam_id: str, inv_id: int,
                         data: Dict, merge: bool = False) -> int:
        """
        Import items from an exported inventory dict.

        Args:
            steam_id: Target player steam ID.
            inv_id:   Target inventory ID.
            data:     Dict produced by export_inventory().
            merge:    If True, skip slots that are already occupied.
                      If False, clear the inventory first.
        Returns:
            Number of items imported.
        """
        if not merge:
            self.clear_inventory(steam_id, inv_id)

        used_slots: set = set()
        if merge:
            existing = self.get_items(steam_id, inv_id)
            used_slots = {it['location'] for it in existing}

        items_data = data.get('items', [])
        count = 0
        for entry in items_data:
            location = entry.get('location')
            item_name = entry.get('item', '')
            item_count = max(1, entry.get('count', 1) or 1)
            durability = entry.get('durability')

            if location is None or not item_name:
                continue
            if merge and location in used_slots:
                continue

            try:
                self.set_item(steam_id, inv_id, location, item_name,
                              count=item_count, durability=durability)
            except Exception:
                pass
            else:
                player = self.players[steam_id]
                living_bin = entry.get('living_slots_bin')
                if living_bin:
                    self._restore_living_slots(player, inv_id, location, living_bin)
                # Container items (pouches, armor upgrade slots) via ContainerManager
                container_items = entry.get('container_items')
                container_idx = entry.get('linked_inv_id')
                # Restore extra DynamicData indices not handled by set_item
                extra_dyn = entry.get('dyn_data_extra')
                if extra_dyn:
                    slot, _, _ = self._find_slot(player, inv_id, location)
                    if slot:
                        for idx, val in extra_dyn.items():
                            _set_dyn_value(slot, int(idx), val)
                if container_items is not None and container_idx is not None:
                    # Re-stamp DYN_LINKED_INV on the (re-)created slot so the
                    # game and GUI can find the ContainerManager entry.
                    slot, _, _ = self._find_slot(player, inv_id, location)
                    if slot:
                        _set_dyn_value(slot, DYN_LINKED_INV, container_idx)
                    self._restore_container_items(container_idx, container_items)
                count += 1

        return count

    def _restore_living_slots(self, player: PlayerState, inv_id: int,
                               location: int, b64: str) -> None:
        """Restore LivingItemSlots on a slot from a base64-encoded binary blob."""
        slot, _, _ = self._find_slot(player, inv_id, location)
        if not slot:
            return
        binary = base64.b64decode(b64)
        props = self._ps.deserialize(binary)
        restored = next((p for p in props if p.name == 'LivingItemSlots'), None)
        if not restored:
            return
        living = next((p for p in slot.nested if p.name == 'LivingItemSlots'), None)
        if living is not None:
            living.nested = restored.nested
            if restored.struct_type:
                living.struct_type = restored.struct_type
            if restored.elem_name:
                living.elem_name = restored.elem_name
        else:
            slot.nested.append(restored)

    def _restore_container_items(self, inventory_index: int,
                                  items: List[Dict]) -> None:
        """
        Write items to the ContainerManager slot with the given InventoryIndex.

        inventory_index is the DYN_LINKED_INV value (logical InventoryIndex),
        not a direct array position.  The slot must already exist in the
        ContainerManager.  Items are replaced (not merged).
        """
        if not self.container_manager:
            return
        pos = self._container_array_pos(inventory_index)
        if pos == -1:
            return
        saved_inv = next(
            (p for p in self.container_manager.props if p.name == 'SavedInventories'),
            None)
        if not saved_inv or pos >= len(saved_inv.nested):
            return
        entry = saved_inv.nested[pos]
        slots_p = next((p for p in entry.nested if p.name == 'Slots'), None)
        if slots_p is None:
            return
        slots_p.nested.clear()
        for item_entry in items:
            loc = item_entry.get('location')
            iname = item_entry.get('item', '')
            if loc is None or not iname:
                continue
            cnt = max(1, item_entry.get('count', 1) or 1)
            dur = item_entry.get('durability')
            fill = item_entry.get('fill_amount')
            new_slot = _make_new_slot(loc, iname, cnt, dur)
            if fill is not None:
                _set_dyn_value(new_slot, DYN_FILL_AMOUNT, fill)
            extra_dyn = item_entry.get('dyn_data_extra')
            if extra_dyn:
                for idx, val in extra_dyn.items():
                    _set_dyn_value(new_slot, int(idx), val)
            slots_p.nested.append(new_slot)
        self.container_manager.dirty = True

    def export_all_inventories(self, steam_id: str) -> Dict:
        """Export all inventories for a player to a portable dict."""
        inventories = []
        for inv in self.get_inventories(steam_id):
            inv_id = inv['id']
            inventories.append({
                'inventory_id': inv_id,
                'inventory_name': inv['name'],
                'items': self._export_items_with_living(steam_id, inv_id),
            })
        return {
            'type': 'icarus_player_inventories',
            'version': 1,
            'steam_id': steam_id,
            'inventories': inventories,
        }

    def import_all_inventories(self, steam_id: str, data: Dict,
                               merge: bool = False) -> int:
        """
        Import all inventories from an exported player inventories dict.

        Each inventory in the file is matched by inventory_id and imported
        into the same slot on the target player. Unknown inventory IDs are
        silently skipped.

        Args:
            steam_id: Target player steam ID.
            data:     Dict produced by export_all_inventories().
            merge:    If True, skip slots that are already occupied.
                      If False, clear each matching inventory first.
        Returns:
            Total number of items imported across all inventories.
        """
        known_ids = {inv['id'] for inv in self.get_inventories(steam_id)}
        total = 0
        for inv_block in data.get('inventories', []):
            inv_id = inv_block.get('inventory_id')
            if inv_id not in known_ids:
                continue
            total += self.import_inventory(steam_id, inv_id, inv_block, merge=merge)
        return total

    def update_living_item(self, steam_id: str, inv_id: int, slot_location: int,
                           sub_location: int, count: Optional[int] = None,
                           durability: Optional[int] = None) -> bool:
        """
        Update count and/or durability of an item inside a LivingItemSlots container.

        Args:
            steam_id:      Player steam ID.
            inv_id:        Inventory ID.
            slot_location: Location of the parent slot (the pouch/weapon).
            sub_location:  Location of the item inside the parent's LivingItemSlots.
            count:         New stack count (or None to leave unchanged).
            durability:    New durability (or None to leave unchanged).
        Returns:
            True if the sub-slot was found and updated.
        """
        player = self.players.get(steam_id)
        if not player:
            return False
        slot, _, _ = self._find_slot(player, inv_id, slot_location)
        if not slot:
            return False
        living = next((p for p in slot.nested if p.name == 'LivingItemSlots'), None)
        if not living:
            return False
        for sub in living.nested:
            loc_p = next((p for p in sub.nested if p.name == 'Location'), None)
            if loc_p and loc_p.value == sub_location:
                if count is not None:
                    _set_dyn_value(sub, DYN_STACK_COUNT, count)
                if durability is not None:
                    _set_dyn_value(sub, DYN_DURABILITY, durability)
                player.dirty = True
                return True
        return False

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
