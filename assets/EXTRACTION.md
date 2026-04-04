# Icon Extraction

Icarus game textures are stored in UE4 PAK files and must be extracted with umodel.
This document covers how icons are located, extracted, and where they land.

---

## Tools

| Tool | Path |
|------|------|
| umodel (64-bit) | `assets/umodel_win32/umodel_64.exe` |
| Extraction script | `extract_icons.py` (project root) |

umodel download: https://www.gildor.org/en/projects/umodel

---

## Game Files

```
C:\Program Files (x86)\Steam\steamapps\common\Icarus\Icarus\Content\Paks\
    pakchunk0-WindowsNoEditor.pak        (9 257 files — main chunk)
    pakchunk0_s1-WindowsNoEditor.pak     (5 999 files — BLD assets)
    pakchunk0_s10-WindowsNoEditor.pak    …
    …                                    (33 PAK files total, 166 075 assets)
```

---

## Asset Path Format

In-game paths follow the Unreal `/Game/…` convention.
umodel drops the `/Game/` prefix:

| Context | Example |
|---------|---------|
| JSON data file | `/Game/Assets/2DArt/UI/Items/Item_Icons/Resources/ITEM_Fibre` |
| umodel `-pkg=` argument | `Assets/2DArt/UI/Items/Item_Icons/Resources/ITEM_Fibre` |
| Exported PNG | `assets/icons/Game/Assets/2DArt/UI/Items/Item_Icons/Resources/ITEM_Fibre.png` |

---

## Relevant Icon Directories

All paths extracted from `data/relevant.json` sources are listed in `data/icon_paths.json`.

| Directory | Count | Source |
|-----------|------:|--------|
| `2DArt/UI/Items/Item_Icons/` | 2 971 | `Traits/D_Itemable.json` |
| `2DArt/UI/Talents/` | 557 | `Talents/D_Talents.json` |
| `2DArt/UI/ProspectSelect/Images/` | 120 | `Prospects/D_ProspectList.json` |
| `2DArt/UI/Icons/` | ~100 | `Talents/D_TalentTrees.json`, `D_TalentArchetypes.json`, `D_TalentRanks.json` |
| `2DArt/UI/FieldGuide/` | ~40 | `Talents/D_Talents.json` |
| **Total unique** | **3 587** | |

---

## Extraction Command (single asset)

```bat
assets\umodel_win32\umodel_64.exe ^
  -export -png -nooverwrite ^
  -game=ue4.27 ^
  -path="C:\Program Files (x86)\Steam\steamapps\common\Icarus\Icarus\Content\Paks" ^
  -out="assets\icons" ^
  -pkg=Assets/2DArt/UI/Items/Item_Icons/Resources/ITEM_Fibre
```

Key flags:

| Flag | Purpose |
|------|---------|
| `-game=ue4.27` | Skips format auto-detection — reduces load time from ~15s to ~0s per asset |
| `-pkg=` | Use instead of a bare argument; prevents hyphens in asset names being parsed as flags |
| `-nooverwrite` | Safe to re-run; skips already-exported files |
| `-png` | Export as PNG instead of TGA |

---

## Bulk Extraction Script

```
python extract_icons.py [--workers=N] [--dry-run]
```

- Reads `data/icon_paths.json` (`_all` key)
- Converts `/Game/…` paths to umodel `Assets/…` format
- Runs umodel in parallel (default 8 workers)
- Reports progress every 50 completions with ETA
- Writes failures to `extract_icons_failures.txt`

Typical run: **~150 seconds** for 3 587 icons at 8 workers.

---

## Known Issues

**Hyphens in asset names** — umodel interprets leading hyphens as flags when the
package is passed as a bare argument. Always use `-pkg=<name>` (the script does this).

Affected assets (as of extraction 2026-04-04):
- `Assets/2DArt/UI/Icons/FactionMissionTypes/icon-factionmission-recovery`
- `Assets/2DArt/UI/Icons/FactionMissionTypes/icon-factionmission-recoveryalt`
- `Assets/2DArt/UI/Items/Item_Icons/Deployables/T_ITEM_Homestead_Shutter-2`

---

## Updating data/ JSON Tables

Game data tables are stored in a separate `data.pak` and extracted with **UnrealPak**
(bundled with IcarusModEditor).

```
python update_data.py [--dry-run]
```

- Extracts `data.pak` to a temp directory via `UnrealPak.exe … -Extract`
- Copies only **new or changed** files into `data/`, re-formats them with 4-space indent
- `--dry-run` shows what would change without writing anything
- Typical result: ~18 updated, ~269 unchanged per game patch

Tools:

| Tool | Path |
|------|------|
| UnrealPak | `assets/UnrealPak/Engine/Binaries/Win64/UnrealPak.exe` |
| data.pak | `C:\Program Files (x86)\Steam\steamapps\common\Icarus\Icarus\Content\Data\data.pak` |

The pak uses a build-machine mount point (`C:/BA/work/…/Temp/Data/`) — the script
locates the real root by searching for `DataTableMetadata.json` inside the extract.

---

## Output Layout

```
assets/
  icons/
    Game/
      Assets/
        2DArt/
          UI/
            Items/Item_Icons/      ← item icons (PNG)
            Talents/               ← talent tree icons (PNG)
            ProspectSelect/Images/ ← mission card images (PNG)
            Icons/                 ← misc UI icons (PNG)
            FieldGuide/            ← bestiary / field guide images (PNG)
  umodel_win32/
    umodel_64.exe
  EXTRACTION.md                    ← this file
```
