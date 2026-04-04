# data/ — Icarus Game Data Tables

Exported Unreal Engine DataTable JSON files from Icarus PAK files.
The editor uses a small subset of these at runtime; the rest are present for
reference and future features.

---

## Common Schema

Every file shares the same wrapper:

```json
{
  "RowStruct": "/Script/Icarus.<StructType>",
  "Defaults":  { /* default field values */ },
  "Rows":      [ /* array of row objects */ ],
  "Columns":   [ /* key column names */ ],
  "GenerateEnum": true
}
```

Foreign-key references appear as:
```json
{ "RowName": "Some_Row", "DataTableName": "D_OtherTable" }
```

Localised strings appear as:
```
NSLOCTEXT("TableName", "Key-FieldName", "Display text")
```

`campaign_data.py` uses a regex helper `_extract_loctext()` to unwrap these.

---

## Files Used by the Editor

### `Prospects/D_ProspectList.json`

All playable prospect missions (regular, campaign, outpost, open world).

| Field | Description |
|-------|-------------|
| `Name` | Internal row name / talent key (e.g. `STYX_D_Expedition`, `GH_RG_A`) |
| `DropName` | NSLOCTEXT display name (e.g. `ZEPHYR`, `MISSING MINERS`) |
| `Description` | NSLOCTEXT one-line mission brief |
| `FlavourText` | NSLOCTEXT long lore text |
| `DifficultySetup` | Easy/Medium/Hard/Ironman difficulty overrides |
| `Terrain` | Reference to `D_Terrains` (map layout) |
| `bIsPersistent` | True for outpost sessions |
| `WorldStatList` | Array of `D_ProspectStats` references |

**Used by** `campaign_data.py`:
- `_load_prospects()` builds `PROSPECT_DISPLAY_NAMES`, `PROSPECT_DESCRIPTIONS`, and
  `REGULAR_MISSION_GROUPS` from this file.
- Campaign mission labels are resolved here (e.g. `GH_RG_A` → `MISSING MINERS`).

**Row name prefixes:**

| Prefix | Map / Category |
|--------|---------------|
| `Tier1_` – `Tier5_` | Olympus standard missions |
| `OLY_SQ_` | Olympus side quests |
| `STYX_` | Styx missions + side quests |
| `PRO_` | Prometheus missions + side quests |
| `ELY_` | Elysium missions + side quests |
| `GH_RG_` | Quarrite (Rock Golem) campaign |
| `GH_Ape_` | Gargantuan (Ape) campaign |
| `GH_IM_` | Rimetusk (Ice Mammoth) campaign |
| `Outpost` | Persistent outpost sessions (excluded from UI) |
| `OpenWorld_` | Open world sessions (excluded from UI) |
| `GreatHunt_` | Hunt archetype rows, not missions (excluded from UI) |

---

### `GreatHunt/D_GreatHunts.json`

Defines each individual Great Hunt mission (step) within a campaign.

| Field | Description |
|-------|-------------|
| `Name` | Internal step name (e.g. `Rock_Golem_A`) |
| `Hunt` | Reference to hunt archetype (maps to campaign id) |
| `Prospect` | Reference to `D_ProspectList` row (the mission's row_name) |
| `Type` | `Standard` / `Choice` / `Optional` / `Final` |
| `ForbiddenTalent` | Array of mutually-exclusive mission row_names |
| `WorldStats` | Array of stat modifier references |

**Hunt → Campaign mapping** (hardcoded in `campaign_data.py`):

| Hunt RowName | Campaign |
|-------------|----------|
| `GreatHunt_RockGolem` | `quarrite` |
| `GreatHunt_Ape` | `gargantuan` |
| `GreatHunt_IceMammoth` | `rimetusk` |

**Used by** `campaign_data._load()` to populate `CAMPAIGNS[id]['missions']`.

---

### `Items/D_ItemsStatic.json`

Master item catalog — one row per item, each row containing references to
trait tables that describe its actual properties.

| Field | Description |
|-------|-------------|
| `Meshable` | Visual mesh reference |
| `Itemable` | Display name, stack size, weight (→ `D_Itemable`) |
| `Durable` | Durability values (→ `D_Durable`) |
| `Fillable` | Fill resource type + max capacity (→ `D_Fillable`) |
| `Inventory` | Has inventory container (→ `D_Inventory`) |
| … | Many other optional trait references |

**Used by** `game_items.load_item_catalog()` (joined with trait tables below).

---

### `Traits/D_Itemable.json`

Display names and stack sizes for all items.

| Field | Description |
|-------|-------------|
| `DisplayName` | NSLOCTEXT player-visible name |
| `MaxStack` | Maximum stack count |
| `Weight` | Item weight |
| `Description` | NSLOCTEXT description |

---

### `Traits/D_Durable.json`

Durability values for weapons, tools, and armour.

| Field | Description |
|-------|-------------|
| `Max_Durability` | Maximum durability value |
| `DurabilityTooltipText` | NSLOCTEXT tooltip |

---

### `Traits/D_Fillable.json`

Defines items that store resources (water, oxygen, biofuel).

| Field | Description |
|-------|-------------|
| `ResourceTypes` | Array of resource type references |
| `MaximumStoredUnits` | Maximum fill capacity |

---

### `Items/D_ItemTemplate.json`

Per-item overrides for stack sizes and initial dynamic data.

| Field | Description |
|-------|-------------|
| `ItemDynamicData` | Array of `{PropertyType, Value}` pairs |

**Used by** `game_items.load_item_catalog()` to override `MaxStack` from D_Itemable.

---

## Directory Reference

Directories not currently used by the editor but available for extension:

| Directory | Contents |
|-----------|----------|
| `AI/` | Creature and mount definitions (`D_Mounts.json`, `D_Saddles.json`, `D_AISetup.json`, Great Hunt creature info, tame modifiers) |
| `Armour/` | Armour set stats and tier data |
| `Attachments/` | Weapon attachment definitions |
| `Blueprints/` | Tech tree unlock structure |
| `Building/` | Buildable structures, skins, stability |
| `Challenges/` | Achievement and challenge definitions |
| `Character/` | Starting stats, growth curves |
| `Config/` | Game configuration tables |
| `Crafting/` | Crafting recipes and material costs |
| `Currency/` | In-game currency definitions |
| `DLC/` | DLC content unlock tables |
| `Damage/` | Damage type modifiers |
| `Experience/` | XP curves (including `C_MountExperienceGrowth`) |
| `Farming/` | Crop and farming data |
| `Fish/` | Fishing data |
| `Flags/` | Player and world flag definitions |
| `GreatHunt/` | Great Hunt mission data (used — see above) |
| `Horde/` | Horde event definitions |
| `Inventory/` | Inventory slot and container configs |
| `Items/` | Item catalog (used — see above) |
| `LivingItems/` | Weapon attachments / living item slots |
| `MetaResource/` | Workshop meta-resource definitions |
| `MetaWorkshop/` | Workshop product definitions |
| `Modifiers/` | Stat modifier definitions |
| `Perks/` | Perk and buff definitions |
| `Prospects/` | Mission list (used — see above) |
| `Quests/` | Quest definitions |
| `Resources/` | Resource types and conversions |
| `Rulesets/` | Game mode ruleset tables |
| `Scaling/` | Creature and loot scaling |
| `Spawn/` | Creature spawn tables |
| `Stats/` | Player and creature stat tables |
| `Talents/` | Talent tree, rank, and archetype data (`D_Talents.json`, `D_TalentTrees.json`, `D_TalentRanks.json`, `D_TalentArchetypes.json`) |
| `Tools/` | Weapon/tool stats, ammo types, firearm data |
| `Traits/` | Item trait tables (used — see above) |
| `UI/` | UI-related data tables |
| `Vehicles/` | Vehicle definitions |
| `Weather/` | Weather events and prospect forecasts |
| `World/` | World generation and biome data |

---

## Adding Support for a New Data File

1. Check the file's `RowStruct` to understand the schema.
2. Use `_extract_loctext()` from `campaign_data.py` for any NSLOCTEXT string fields.
3. Follow-up foreign keys via `RowName` + `DataTableName` to join related tables.
4. Load at module level (like `campaign_data._load_prospects()`) or lazily cache
   behind a function (like `game_items.get_catalog()`).
