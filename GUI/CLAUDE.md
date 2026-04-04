# GUI/ — Desktop Interface Modules

All GUI modules use **CustomTkinter** (`ctk`) — a modern dark-themed wrapper around
Tkinter. The root window is `IcarusEditorApp` in `gui_main.py`.

---

## Module Overview

| File | Class | Purpose |
|------|-------|---------|
| `constants.py` | — | Shared fonts, padding, sort helpers |
| `prospect_manager.py` | `ProspectManager` | Shared GD.json state (observer pattern) |
| `tab_catalog_base.py` | `_CatalogTab` | Abstract 3-panel catalog base (Tech Tree, Talents) |
| `tab_character.py` | `CharacterTab` | Character stats + account resources |
| `tab_techtree.py` | `TechTreeTab` | Blueprint / crafting unlock browser |
| `tab_talents.py` | `TalentsTab` | Character talent browser |
| `tab_workshop.py` | `WorkshopTab` | Workshop unlock manager |
| `tab_inventory.py` | `InventoryTab` | MetaInventory item editor |
| `tab_mounts.py` | `MountsTab` | Mount list and edit panel |
| `tab_prospect_inventory.py` | `ProspectInventoryTab` | In-session player inventory editor |
| `tab_campaign.py` | `CampaignTab` | Campaign + prospect mission completion |
| `tab_profile.py` | `ProfileTab` | Account resources (unused — merged into CharacterTab) |

---

## `constants.py`

Shared constants imported by every tab.

```python
FONT_TITLE  = ("Segoe UI", 15, "bold")
FONT_HEADER = ("Consolas", 12, "bold")
FONT_NORMAL = ("Segoe UI", 13)
FONT_SMALL  = ("Segoe UI", 11)
FONT_MONO   = ("Consolas", 12)
PAD         = 8
```

Also exports `_TIER_ORDER` and `_SUBTREE_ORDER` (dicts of label → sort index) and a
`_sort_key(label, order)` helper used by the catalog tabs.

---

## `prospect_manager.py` — `ProspectManager`

Shared state object passed to both `ProspectInventoryTab` and `CampaignTab`.
Implements the observer pattern so any component can trigger a file load
and all interested tabs react.

```python
manager = ProspectManager(steam_id)

# Tabs subscribe once at construction
manager.register(callback)           # callback(path: str) called on every load

# Top bar fires this when user picks a file
manager.notify(path)                 # stores path, fires all callbacks

# Helpers
manager.list_prospects()             # sorted .json filenames in Prospects/
manager.get_prospect_path(filename)  # full path for a filename
manager.current_path                 # last-loaded path (None if none yet)
```

The Prospects folder is `{steam_id_dir}/Prospects/` resolved via `save_manager.get_save_dir()`.

---

## `tab_catalog_base.py` — `_CatalogTab`

Abstract base class for 3-panel catalog-style tabs (Tech Tree and Talents).

**Layout:**
```
┌──────────────┬────────────────────────┬──────────────────────────┐
│  Categories  │  Item list             │  Detail panel            │
│  (left)      │  (scrollable, search)  │  (title, meta, desc,     │
│              │  ✓ = unlocked          │   Add / Remove button)   │
└──────────────┴────────────────────────┴──────────────────────────┘
```

**Abstract methods subclasses must implement:**

| Method | Returns | Purpose |
|--------|---------|---------|
| `_category_labels()` | `List[str]` | All category display names |
| `_category_count(label)` | `int` | Total items in category |
| `_unlocked_count(label)` | `int` | Items unlocked in save |
| `_load_catalog(label)` | `List[Any]` | Items for a category |
| `_is_save_unlocked(item)` | `(bool, str, int)` | is_unlocked, save_rowname, rank |
| `_detail_text(item, ...)` | `dict` | title / meta / desc / extra / rowname |
| `_add_rowname(item)` | `str` | RowName to write when user clicks Add |
| `_remove_rowname(item, save_rn)` | `str` | RowName to remove |

**Key public method:** `refresh()` — reloads category panel from current editor data.

---

## `tab_character.py` — `CharacterTab`

**Constructor:** `CharacterTab(master, char_editor, prof_editor, on_char_change)`

**Two-column layout:**

*Left — Character Stats* (from `CharacterEditor`):
- Character selector dropdown
- Name (read-only)
- XP entry
- XP Debt entry
- Dead / Abandoned checkboxes
- Apply button → writes to `CharacterEditor`, fires `on_char_change()`

*Right — Account Resources* (from `ProfileEditor`):
- Credits, Exotic Matter, Refund Tokens, Licences entries
- Apply button → writes to `ProfileEditor`

`on_char_change` callback is wired in `gui_main.py` to refresh `TechTreeTab` and
`TalentsTab` when the selected character changes.

---

## `tab_techtree.py` — `TechTreeTab`

**Constructor:** `TechTreeTab(master, char_editor)`

Extends `_CatalogTab`. Categories are tech tiers: `Tier 1` through `Tier 4` plus
workshop bench tiers (`Anvil`, `Concrete Bench`, etc.).

- Catalog items loaded via `game_data.get_tech_catalog_for_tier(label)`.
- Unlock check uses `game_data.rowname_matches_catalog(save_rn, catalog_rn)` for
  fuzzy matching (normalises case and underscores).
- Detail panel shows: title, crafting site key, description, flavour text, RowName.
- Add/Remove writes directly to `CharacterEditor.add_talent()` / `remove_talent()`.

---

## `tab_talents.py` — `TalentsTab`

**Constructor:** `TalentsTab(master, char_editor)`

Extends `_CatalogTab`. Categories are talent subtrees: `Survival/Resources`,
`Combat/Bows`, etc.

- Catalog items loaded via `game_data.get_talent_catalog_for_subtree(key)`.
- Detail panel shows: title, rank info, description, formatted stats, RowName.
- **Note:** RowNames cannot always be reliably derived from titles, so clicking
  Add prompts the user via `simpledialog.askstring()` with a best-guess pre-filled.

---

## `tab_workshop.py` — `WorkshopTab`

**Constructor:** `WorkshopTab(master, prof_editor)`

Simple searchable list of Profile.json Talents entries (workshop unlocks).

- Loads from `ProfileEditor.get_workshop_unlocks()`.
- Search entry filters displayed rows in real time.
- Buttons: **Add** (manual RowName entry), **Remove Selected**, **Clear All**.
- Status label shows count and last action.

> Workshop unlocks and campaign/mission completions live in the **same**
> `Profile.json → Talents` array. They are distinguished only by RowName prefix
> (`Workshop_*` vs `GH_*` vs `STYX_*` etc.).

---

## `tab_inventory.py` — `InventoryTab`

**Constructor:** `InventoryTab(master, inv_editor)`

Edits `MetaInventory.json` (workshop personal inventory — not in-session items).

- Listbox columns: `#`, `Item`, `Qty`, `Durability %`.
- Buttons: **Repair All**, **Remove Selected**.
- Per-item actions: **Repair**, **Remove**.
- **Export All** / **Import All**: JSON round-trip with `type: "icarus_meta_inventory"`.
  Import has merge option (append vs replace).

---

## `tab_mounts.py` — `MountsTab`

**Constructor:** `MountsTab(master, mount_editor)`

**Two-column layout:**

*Left — Mount list:*
- Listbox: index, name, type, level.
- Buttons: **Clone**, **Delete**.

*Right — Edit panel* (for selected mount):
- Name entry.
- Level slider (1–50).
- Type dropdown (from `MOUNT_TYPES`).
- Skin index dropdown (type-dependent options).
- Variant dropdown (A1/A2/A3, only for Workshop Horse).
- Buttons: **Reset Talents**, **Apply**.

Apply calls the relevant `MountEditor` setters; changes are in-memory until
**Save All** in the top bar.

---

## `tab_prospect_inventory.py` — `ProspectInventoryTab`

**Constructor:** `ProspectInventoryTab(master, prospect_manager)`

The most complex tab (~350 lines). Edits player inventories inside the active
`GD.json` prospect save via `GdInventoryEditor`.

**Registers with `ProspectManager`** → reloads when any component selects a new file.

**Top bar:** Player selector → Inventory selector.

**Action bar:** Add Item, Clear Inventory, Save GD.json, Save + Backup, Debug toggle,
Export All, Import All.

**Slot grid** (scrollable):

| Column | Content |
|--------|---------|
| Slot | Slot index |
| Item | Clickable item name (opens `_ItemSearchPopup`) or "(empty)" + Set button |
| Count | Editable integer entry |
| Durability | Editable float entry + "/max" label |
| Actions | Max Dur, Remove, attachment indicator |
| Fill Amount | Editable float + Max button (fillable items only) |

**Nested inventory:** Weapon attachments (`LivingItemSlots`) and linked
`SavedInventory` pouches are rendered as indented sub-rows beneath the parent slot.

**Debug mode:** Raises count limit to 999,999 and durability limit to 9,999,999.
Enabled via the "Experimental / Debug" checkbox; affects all validation in
`_update_count()` and `_update_durability()`.

**`_ItemSearchPopup`** (inner `CTkToplevel`):
- Requires ≥ 3 characters to show results (prevents overwhelming the list).
- Searches both display name and RowName.
- Single-click selection calls callback and closes popup.

**Save flow:** "Save GD.json" and "Save + Backup" write only the prospect file;
they are independent of the main **Save All** in the top bar.

---

## `tab_campaign.py` — `CampaignTab`

**Constructor:** `CampaignTab(master, prospect_manager, prof_editor)`

**Registers with `ProspectManager`** → rebuilds left panel when a GD.json is loaded.

**Two-column layout (50/50):**

*Left — Campaign Missions:*
- Detects active campaign from `ProspectInfo.ProspectDTKey` in loaded GD.json.
- Renders missions from `campaign_data.CAMPAIGNS[id]['missions']`.
- Each row: checkbox, display name, internal RowName (gray), type badge (coloured),
  conflict indicator (`⊗ X`), description (second line, dim gray).
- Choice missions auto-uncheck `ForbiddenTalent` peers on toggle (`_on_campaign_toggle`).
- Buttons: **Mark All**, **Clear All**, **Apply**.

*Right — Prospect Missions:*
- Renders all groups from `campaign_data.REGULAR_MISSION_GROUPS` (Olympus / Styx /
  Prometheus / Elysium).
- Each row: checkbox, display name, RowName (gray), description (second line).
- Buttons: **Mark All**, **Clear All**, **Apply**.

**Apply** writes to `ProfileEditor` Talents via `add_workshop_unlock` / `remove_workshop_unlock`.
Changes are in-memory until **Save All** in the top bar.

**`refresh_regular_missions()`** — public method to re-read completion state after
a `prof_editor` swap (not currently called automatically; available for future use).

---

## `tab_profile.py` — `ProfileTab` *(unused)*

Standalone account resources editor (Credits, Exotics, Refund Tokens, Licences).
Superseded by the right panel of `CharacterTab`. Kept for reference; not
instantiated by `gui_main.py`.

---

## Cross-Tab Wiring (gui_main.py)

```
IcarusEditorApp._load(steam_id)
  ├─ Creates: SaveManager, CharacterEditor, ProfileEditor,
  │           InventoryEditor, MountEditor, ProspectManager
  │
  ├─ Topbar prospect dropdown → ProspectManager.notify(path)
  │     └─ Callbacks: ProspectInventoryTab, CampaignTab
  │
  ├─ Steam ID change → _load() again → rebuild all tabs
  │
  └─ CharacterTab on_char_change → TechTreeTab.refresh() + TalentsTab.refresh()
```

**Important:** `CharacterEditor.Talents` (per-character XP/blueprint unlocks) and
`ProfileEditor.Talents` (account-wide workshop/mission unlocks) are **different arrays
in different files**, but both use the same `{RowName, Rank}` structure.

---

## Common Patterns

### Refresh cycle
Every tab exposes a `refresh()` method. `gui_main._refresh_all()` calls all of them
after a steam ID change. Individual tabs handle their own partial refreshes internally.

### Apply → Save All
Tabs write to in-memory editor objects on Apply. Nothing is written to disk until
**Save All** or **Save + Backup** in the top bar (or "Save GD.json" in
ProspectInventoryTab for the prospect save specifically).

### Status labels
Every tab has a `_status_label` (right-aligned, small font) for feedback.
Gray = idle/count, orange = pending/warning, green = success.
