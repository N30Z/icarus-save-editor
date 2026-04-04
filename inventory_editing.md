---
name: Inventory Editing — savegame.json Deep Knowledge
description: Everything learned about Icarus player inventory binary format, structure, and editing in savegame.json
type: project
---

# Inventory Editing — savegame.json

## File Location

```
savegame.json   — prospect / session save (NOT the same as Mounts.json)
```

savegame.json lives in a different directory from Mounts.json. The user picks any path; the CLI accepts it as a first argument.

---

## Binary Decoding Chain

```
savegame.json
  └─ ProspectBlob.BinaryBlob
       └─ base64 decode
            └─ zlib decompress
                 └─ UE4 property stream  (same format as Mounts.json, but with the extra compression layer)
```

The outer UE4 property stream starts with a single `StateRecorderBlobs` ArrayProperty that holds **all** world actors (2705 entries in a typical save).

### Outer size field

`binary[41:45]` = int32 total payload size of `StateRecorderBlobs`.
**Must be updated** by the delta when any BinaryData inside is resized.

---

## Finding Player State Blobs

Scan for the byte pattern:
```
b'/Script/Icarus.PlayerStateRecorderComponent\x00'
```

Each occurrence is followed (within ~500 bytes) by a `BinaryData` ArrayProperty of ByteProperty. That byte array IS the player state binary (UE4 property stream, no further compression).

### BinaryData header layout (from the 'B' of 'BinaryData\x00' minus 4 bytes)

| Offset from name-len | Field | Notes |
|----------------------|-------|-------|
| 0 | int32 name_len | = 11 |
| 4 | 'BinaryData\x00' | 11 bytes |
| 15 | int32 type_len | = 14 |
| 19 | 'ArrayProperty\x00' | 14 bytes |
| 33 | **int32 size** | = count + 4  ← patch on save |
| 37 | int32 arr_idx | always 0 |
| 41 | int32 inner_len | = 13 |
| 45 | 'ByteProperty\x00' | 13 bytes |
| 58 | byte HasGuid | always 0 |
| 59 | **int32 count** | byte count ← patch on save |
| 63 | [count bytes] | player state data ← replace on save |

---

## Player State Top-Level Properties

Parsed with `PropertySerializer` from `ue4_properties.py`. Key fields:

| Property | Type | Notes |
|----------|------|-------|
| `PlayerCharacterID` | StructProperty | Contains `PlayerID` (steam ID string) and `ChrSlot` (int) |
| `Location` | Vector | Player world position |
| `Health` | IntProperty | Current HP |
| `FoodLevel` | IntProperty | |
| `WaterLevel` | IntProperty | |
| `bIsAlive` | BoolProperty | |
| **`SavedInventories`** | ArrayProperty[6] | All inventory containers |

---

## SavedInventories Structure

`SavedInventories` is an **ArrayProperty of StructProperty** with typically 6 entries (one per inventory container).

Each entry has two sub-properties:
- `Slots` — ArrayProperty of StructProperty (`InventorySlotSaveData`), one element per occupied slot
- `InventoryID` — IntProperty

### Inventory ID mapping

| ID | In-game name | Typical slot range |
|----|-------------|-------------------|
| 2  | Equipment / Hotbar | 0–11 |
| 3  | Backpack (main) | 0–23 |
| 4  | Belt | 0–? |
| 5  | Armor / Cosmetics | 5–7 (equipment slot positions) |
| 11 | Unknown | |
| 12 | Unknown | |

**Empty slots are not stored.** Missing `Location` values = empty slots. To add an item, append a new slot entry.

---

## Inventory Slot Structure (`InventorySlotSaveData`)

```
Slot
├── Location          IntProperty      slot index (not necessarily 0-based consecutive)
├── ItemStaticData    NameProperty     item row name, e.g. 'Iron_Ingot', 'Wood_Bow'
├── ItemGuid          StrProperty      usually None/empty
├── ItemOwnerLookupId IntProperty      -1
├── DynamicData       ArrayProperty[N] struct=InventorySlotDynamicData
│     └── [each entry] DynamicData StructProperty
│           ├── Index  IntProperty
│           └── Value  IntProperty
├── AdditionalStats   ArrayProperty    struct=InventorySlotStatData
├── Alterations       ArrayProperty    struct=InventorySlotAlterationData
└── LivingItemSlots   ArrayProperty    struct=LivingItemSlotSaveData
```

### DynamicData index meanings (confirmed from in-game data)

| Index | Meaning | Example values |
|-------|---------|----------------|
| 0–5 | Unknown stats | usually 0 |
| 6 | **Durability** | Wood_Bow=4150, Stone_Pickaxe=16600, Stone_Axe=4900 |
| 7 | **Stack count** | 100, 500, 1 |
| 9 | Max stack size | 10000 for Stick |
| 13 | Unknown | 7 for Wood_Bow |

### Minimal slot for a resource item (no durability)

```python
DynamicData = [{ Index=7, Value=<count> }]
AdditionalStats = []   # empty but prototype tag still written
Alterations     = []
LivingItemSlots = []
```

### Slot for a tool/weapon (with durability)

```python
DynamicData = [
    { Index=0..5, Value=0 },   # stat slots (present in existing items)
    { Index=7, Value=1 },      # stack count = 1
    { Index=6, Value=<dur> },  # durability
    { Index=13, Value=7 },     # unknown extra
]
AdditionalStats = [{ Index=-1, Name='ToolType_Enum', Value=<type_id> }]
Alterations     = [{ Name='Durability_2' }]
```

---

## Empty Array Serialization (Important)

Even arrays with **count=0** have a **prototype tag** written before the element data:
```
int32 count=0
[prototype StructProperty tag: name + 'StructProperty' + size=0 + arr_idx + struct_name + 16-byte GUID + 0x00]
```

When creating new empty arrays from scratch, `elem_name` and `struct_type` MUST be set:

| Array field | elem_name | struct_type |
|-------------|-----------|-------------|
| DynamicData | `'DynamicData'` | `'InventorySlotDynamicData'` |
| AdditionalStats | `'AdditionalStats'` | `'InventorySlotStatData'` |
| Alterations | `'Alterations'` | `'InventorySlotAlterationData'` |
| LivingItemSlots | `'LivingItemSlots'` | `'LivingItemSlotSaveData'` |

The `inner_type` for all of these must be `'StructProperty'` (NOT the struct type name — that was a bug to avoid).

---

## Round-Trip Verified

`PropertySerializer.deserialize()` → modify → `PropertySerializer.serialize()` produces **byte-exact output** for unmodified data (verified: 49712 bytes in = 49712 bytes out for a full player state).

---

## Patching the Outer Binary on Save

```python
delta = len(new_bd_bytes) - old_bd_len

# 1. Update BinaryData 'size' field  (= new_count + 4)
binary[bd_size_pos : bd_size_pos+4]  = struct.pack('<i', new_count + 4)

# 2. Update BinaryData byte count
binary[bd_count_pos : bd_count_pos+4] = struct.pack('<i', new_count)

# 3. Replace content bytes
binary[bd_data_pos : bd_data_pos + old_bd_len] = new_bd_bytes

# 4. Update outer StateRecorderBlobs total size at binary[41:45]
old_total = struct.unpack_from('<i', bytes(binary), 41)[0]
binary[41:45] = struct.pack('<i', old_total + delta)
```

Multiple players: sort by `bd_data_pos` ascending and accumulate `total_delta` to adjust positions.

---

## Known Item Row Names (sampled from player save)

Resources: `Stick`, `Fiber`, `Stone`, `Wood`, `Fur`, `Leather`, `bone`, `raw_meat`, `Gamey_Meat`, `Berry`, `Pumpkin`, `Coffee`, `Wheat`, `Dirt`, `Spoiled_Meat`, `Spoiled_Plants`
Crafted: `Stone_Arrow`, `Wood_Floor`, `Waterskin`, `Iron_Ingot`, `Steel`
Tools: `Wood_Bow`, `Bone_Knife`, `Stone_Pickaxe`, `Stone_Axe`, `Stone_Shovel`
Armor: `EnviroSuit`
Cosmetics: `Skin_Head_Male_05`, `Spacesuit_Cap_Male_03`
Special: `Player_Fist` (always present, cannot be removed)

For the full item list, browse game PAK files or look up `ItemDTKey` row names.

---

## Files Created

| File | Purpose |
|------|---------|
| `gd_inventory_editor.py` | `GdInventoryEditor` class — load / modify / save |
| `gd_inventory_cli.py` | CLI: list, inventory, items, set, add, remove, clear, fill |

Both files are fully independent from the mount editor and accept any savegame.json path.
