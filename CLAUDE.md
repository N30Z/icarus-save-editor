# Claude Instructions: Icarus Save Editor

## Project Overview

A full-featured desktop GUI (CustomTkinter) for editing Icarus save files, plus a legacy
command-line interface focused on mount editing.  The GUI covers characters, tech trees,
talents, workshop unlocks, inventory, mounts, prospect inventory, and campaign / prospect
mission completion.

## Architecture

```
gui_main.py               # GUI entry point — IcarusEditorApp (CTk window, topbar, tabs)
save_manager.py           # SaveManager: loads Characters.json, Profile.json, MetaInventory.json
character_editor.py       # CharacterEditor: XP, debt, account resources
profile_editor.py         # ProfileEditor: workshop unlocks + meta-resources (Profile.json Talents)
inventory_editor.py       # InventoryEditor: MetaInventory items
campaign_data.py          # Campaign + prospect mission defs (D_GreatHunts + D_ProspectList)
gd_inventory_editor.py    # GdInventoryEditor: player inventory inside a GD.json prospect save
game_items.py             # Item catalog for inventory tab

mount_cli.py              # Legacy CLI interface
mount_editor.py           # High-level API (MountEditor class)
mount_types.py            # Mount type definitions (MOUNT_TYPES dict)
ue4_properties.py         # Low-level UE4 binary parser (FPropertyTag, PropertySerializer)
test_cli.py               # Test suite

GUI/
  constants.py                  # Shared fonts (FONT_TITLE, FONT_NORMAL, FONT_SMALL, FONT_MONO, FONT_HEADER)
  prospect_manager.py           # ProspectManager: shared GD.json state (observer pattern)
  tab_character.py              # Character + Profile tab
  tab_techtree.py               # Tech Tree tab
  tab_talents.py                # Talents tab
  tab_workshop.py               # Workshop unlocks tab
  tab_inventory.py              # MetaInventory tab
  tab_mounts.py                 # Mounts tab
  tab_prospect_inventory.py     # Prospect Inventory tab
  tab_campaign.py               # Campaign + Prospect Missions tab

data/
  GreatHunt/
    D_GreatHunts.json     # Great Hunt mission definitions (row, type, conflicts)
  Prospects/
    D_ProspectList.json   # All prospect missions (display name, description)
  ... (other game data tables)
```

### Top Bar

```
[Icarus Save Editor] [Steam ID ▾] | [Prospect save ▾] [Browse…]  …  [Status]  [Save + Backup] [Save All]
```

- **Steam ID** dropdown: `find_steam_ids()` auto-detects accounts; switching reloads all editors.
- **Prospect save** dropdown: populated from `{steam_id}/Prospects/*.json` by `ProspectManager`.
  Selecting a file calls `ProspectManager.notify(path)` which fires all registered tab callbacks
  (both ProspectInventoryTab and CampaignTab).
- **Save All / Save + Backup**: persist Characters.json, Profile.json, MetaInventory.json,
  Mounts.json (optionally creating timestamped `.backup_*.json` files).

### ProspectManager (observer pattern)

`GUI/prospect_manager.py` — shared singleton per steam_id, passed to both
`ProspectInventoryTab` and `CampaignTab`.

```python
manager.register(callback)  # tabs subscribe
manager.notify(path)        # topbar fires this; calls every registered callback
manager.list_prospects()    # returns sorted .json filenames in Prospects folder
manager.current_path        # last-loaded path
```

### Campaign Tab Layout

The Campaign tab (`GUI/tab_campaign.py`) is a 50/50 vertical split:

**Left panel — Campaign Missions**
- Detects the active Great Hunt campaign from the loaded GD.json `ProspectDTKey`.
- Shows a checklist of campaign missions with: display name, internal row_name, type
  badge (Standard / Choice / Optional / Final), conflict indicators, and a description.
- Choice missions auto-uncheck their mutually-exclusive peers on toggle.
- Completion state is stored in `Profile.json` Talents as `{"RowName": "GH_RG_A", "Rank": 1}`.
- Buttons: Mark All, Clear All, Apply (writes to ProfileEditor; use Save All to persist).

**Right panel — Prospect Missions**
- Lists all regular (non-GH) prospect missions grouped by map: Olympus, Styx, Prometheus, Elysium.
- Each mission shows: display name, internal row_name, description.
- Same Profile.json Talents mechanism as campaign missions.
- Buttons: Mark All, Clear All, Apply.

### campaign_data.py

Loads two data files at import time (`_load_prospects()` runs first, then `_load()`):

| Symbol | Description |
|--------|-------------|
| `CAMPAIGNS` | Dict of three GH campaigns; each has `missions` list with `row_name`, `label`, `description`, `type`, `forbidden` |
| `REGULAR_MISSION_GROUPS` | List of four map groups (Olympus/Styx/Prometheus/Elysium); each mission has `row_name`, `label`, `description` |
| `PROSPECT_DISPLAY_NAMES` | `{row_name: display_name}` for every row in D_ProspectList.json |
| `PROSPECT_DESCRIPTIONS` | `{row_name: description}` for every row in D_ProspectList.json |
| `detect_campaign(key)` | Returns campaign id from a ProspectDTKey string, or None |

Mission labels come from the `DropName` field (NSLOCTEXT-unwrapped), e.g. `GH_RG_A` → `MISSING MINERS`.
Descriptions come from the `Description` field, e.g. `INVESTIGATE THE DISTURBANCE AT THE MINING OUTPOST`.

Regular missions excluded: `Outpost*`, `OpenWorld*`, `GreatHunt_*`, `GH_*`.

---

## Data Flow (GUI)

1. **Load**: `SaveManager(steam_id).load_all()` reads Characters.json, Profile.json, MetaInventory.json.
2. **Editors** created: `CharacterEditor`, `ProfileEditor`, `InventoryEditor`, `MountEditor`, `ProspectManager`.
3. **Tabs** rebuilt: each tab receives the relevant editor(s) and renders current state.
4. **Prospect save**: user selects GD.json via topbar dropdown or Browse; `ProspectManager.notify()`
   fires `ProspectInventoryTab._on_manager_load()` and `CampaignTab._on_manager_load()`.
5. **Save**: `SaveManager.save_all(backup=)` writes back JSON files; `MountEditor.save()` handles Mounts.json.

## Data Flow (Mount CLI / Legacy)

1. `Mounts.json` contains array of mounts with `RecorderBlob` field
2. `RecorderBlob.BinaryData` is base64-decoded to raw bytes
3. `PropertySerializer.deserialize()` parses UE4 property tree
4. Modifications made to `FPropertyTag` objects
5. `PropertySerializer.serialize()` re-encodes with correct size headers
6. Updated bytes written back to JSON

### Key Classes

- **MountEditor**: User-facing API for load/save/modify operations
- **MountData**: Single mount with `properties` (List[FPropertyTag]) and `json_data` (dict)
- **FPropertyTag**: UE4 property with name, type, size, value
- **PropertySerializer**: Binary parse/serialize logic

---

## Critical Implementation Details

### UE4 Property Size Headers

The `size` field in properties is **critical**. It must exactly match the serialized byte length
of the value. The pattern:

```python
# Serialize to temp buffer first
temp = BytesIO()
value_size = serialize_value(temp, prop)

# THEN write the size
writer.write_int32(value_size)
writer.write(temp.getvalue())
```

Never calculate sizes upfront — always serialize first, then measure.

### Unique Mount IDs

Every mount needs unique identifiers across these properties:
- `ObjectFName`: `BP_Mount_Type_C_XXXXXXXXXX`
- `ActorPathName`: Contains the same ID
- `IcarusActorGUID`: The numeric ID

When cloning, generate new IDs in range `2147000000-2147483647` and check for collisions.

### Level System (CRITICAL)

Mount level is tracked in TWO places that must stay synchronized:

1. **JSON `MountLevel`** — The authoritative level value displayed in-game
2. **Binary `Experience`** — The XP value stored in properties

**IMPORTANT:** Setting `Experience` alone will NOT change the displayed level.
You MUST set `MountLevel` in JSON as well.

Use `set_mount_level(index, level)` which handles both automatically.

**Official XP Curve** (extracted from `C_MountExperienceGrowth.uasset`):

| Level | XP | Level | XP |
|-------|-----|-------|-----|
| 10 | 13,500 | 40 | 467,500 |
| 20 | 39,875 | **50 (MAX)** | **1,150,000** |
| 30 | 140,000 | | |

### Mount Type Transformation

Changing mount type requires updating:
1. `AISetupRowName` (e.g., `Mount_Horse` → `Mount_Tusker`)
2. `ActorClassName` (e.g., `BP_Mount_Horse_C` → `BP_Mount_Tusker_C`)
3. `ObjectFName` (replace blueprint prefix, keep ID)
4. `ActorPathName` (replace blueprint in path)
5. JSON `MountType` field

---

## Valid Mount Types

From `mount_types.py` — only these blueprints work in-game:

### IMPORTANT: Terrenus vs Horse Naming

The game has confusing naming for horse-like mounts:

| Save File Type | In-Game Name | Origin |
|----------------|--------------|--------|
| `Horse` / `Mount_Horse` | **Terrenus** | Wild alien creature (purple boar-horse hybrid), tamed on Icarus |
| `Horse_Standard` / `Mount_Horse_Standard_A*` | **Horse** | Actual Earth horse, unlocked via Workshop (3 color variants) |

### Full Mount Table

| Key | Blueprint | AI Setup | Rideable |
|-----|-----------|----------|----------|
| Terrenus | BP_Mount_Horse_C | Mount_Horse | Yes |
| Horse | BP_Mount_Horse_Standard_C | Mount_Horse_Standard_A1/A2/A3 | Yes |
| Moa | BP_Mount_Moa_C | Mount_Moa | Yes |
| ArcticMoa | BP_Mount_Arctic_Moa_C | Mount_Arctic_Moa | Yes |
| Buffalo | BP_Mount_Buffalo_C | Mount_Buffalo | Yes |
| Tusker | BP_Mount_Tusker_C | Mount_Tusker | Yes |
| Zebra | BP_Mount_Zebra_C | Mount_Zebra | Yes |
| WoolyZebra | BP_Mount_Wooly_Zebra_C | Mount_Zebra_Shaggy | Yes |
| SwampBird | BP_Mount_SwampBird_C | Mount_SwampBird | Yes |
| WoollyMammoth | BP_Mount_WoollyMammoth_C | Mount_WoollyMammoth | Yes |
| BluebackDaisy | BP_Mount_Blueback_Daisy_C | Mount_Blueback_Daisy | No (companion) |
| MiniHippo | BP_Mount_MiniHippo_Quest_C | Mount_MiniHippo | No (companion) |

**Broken**: `BP_Mount_Blueback_C` (1 HP), `BP_Mount_Raptor_C` (doesn't exist), `BP_Mount_Slinker_C` (doesn't exist)

### Workshop Horse Variants

Workshop horses are unlocked via talents in Profile.json (all variants have identical stats):
- `Workshop_Creature_Horse_A1` — Brown horse
- `Workshop_Creature_Horse_A2` — Black horse
- `Workshop_Creature_Horse_A3` — White horse

Each creates a mount with `AISetupRowName: Mount_Horse_Standard_A*` where * is the variant number.
The color is baked into the AI setup, not stored as `CosmeticSkinIndex`.
Stats: HP 1440, Stamina 373, Speed 805, Sprint 1518, Carry 220kg.

> Note: A1/A2/A3 definitions are in server-side data tables, not game PAK files.

---

## Cosmetic Skins

Skins are stored in `IntVariables` array as `CosmeticSkinIndex`.

**Note:** `CosmeticSkinIndex` applies to wild-tamed mounts (like Terrenus).
Workshop horses use A1/A2/A3 variants via `AISetupRowName` instead.

### Terrenus Skins (Verified In-Game)

| Index | Appearance |
|-------|------------|
| 0 | Default — Orange and white coat |
| 1 | Brown — Solid brown coat |
| 2 | Brown & White — Brown and white patterned coat |
| 3-9 | Unknown — need in-game verification |

---

## File Locations

```
%LocalAppData%\Icarus\Saved\PlayerData\{SteamID}\
├── Mounts.json
├── Profile.json
├── Characters.json          (double-wrapped JSON — outer shell is a JSON string)
├── MetaInventory.json
└── Prospects\
    └── {ProspectName}.json  (GD.json prospect saves)
```

## Complete Schema

See **[SCHEMA.md](SCHEMA.md)** for full documentation of all 40+ JSON and binary properties, including:
- Core identity fields (name, type, GUID)
- Stats (XP, health, stamina, food, water)
- Cosmetic variables (`CosmeticSkinIndex`, `bIsWildTame`)
- Behaviour states (combat, movement, grazing)
- Inventory, talents, transforms

---

## Testing Changes

1. Close Icarus completely
2. Make modifications with backup=True
3. Launch game and check
4. If mount missing: blueprint invalid or ID collision
5. Restore from `.backup_*.json` if needed

## Code Style

- Python 3.8+ standard library only (no external deps; GUI uses `customtkinter`)
- Type hints on all functions
- Dataclasses for data structures
- Keep backwards compatibility with existing save files

---

## Common Tasks

### Add New Mount Type

1. Find blueprint name in PAK files (search for `BP_Mount_`)
2. Test in-game by manually setting properties
3. If works, add to `MOUNT_TYPES` in `mount_types.py`

### Debug Serialization Issues

1. Compare `len(original_bytes)` vs `len(re_serialized_bytes)`
2. Use hex dump to find divergence point
3. Check size fields match actual content length
4. Verify string null terminators included in length

### Find Property in Mount

```python
from mount_editor import MountEditor, find_property

editor = MountEditor(steam_id='...')
editor.load()
mount = editor.get_mount(0)

# Find by name
prop = find_property(mount.properties, 'MountName')

# Find nested
health = find_property(mount.properties, 'CharacterRecord.CurrentHealth')
```

### Add a New Campaign Mission Group (Regular Missions)

Edit `campaign_data.py` → `_load_prospects()`:
1. Add a new entry to `_PREFIX_TO_MAP` mapping a name prefix to a group name.
2. Add the group name to `_MAP_GROUPS_ORDER` and `_MAP_COLORS`.
The missions will be collected automatically from D_ProspectList.json.
