# Quarrite Campaign — Full Analysis

## What Is the Quarrite Campaign?

"Quarrite" is the in-game name for the **Rock Golem** creature.
The campaign is the Great Hunt story arc for this creature (`GH_RG_*` prefix = Great Hunt Rock Golem).
It runs on **Olympus** (`Terrain_016`). The talent tree is named `GreatHunt_RockGolem`.

---

## Full Campaign Structure

### Flow Diagram

```
GH_RG_A
  └─ GH_RG_B
       ├─ [Optional] GH_RG_O1  (after B, Quarrite Dens at GRID M6)
       └─ [Choice] ──────────────────────────────────────────────
            ├─ GH_RG_C  (save Mining Outpost Beta, rescue miners)
            │    ├─ [Optional] GH_RG_O2  (test weapons, GRID B14/C15)
            │    └─ GH_RG_C2  (observation outpost, collect armor samples)
            │         └─ [reroute] ──► GH_RG_E  ─┐
            │                                     ├─► GH_RG_Hunt (Final Boss)
            └─ GH_RG_D  (arctic exotic cluster)  │
                 └─ GH_RG_D2  (rebuild outpost)  │
                      └─ [Choice] ────────────────┤
                           ├─ GH_RG_F  ──────────►┘
                           └─ GH_RG_E  ──────────►┘
```

**Current save state:** `GH_RG_A` ✅ → `GH_RG_B` ✅ → *next stage not yet started*

### Stage Summary (from `D_GreatHunts.json` + `D_Quests.json`)

| Stage | Type | Quest Count | WorldStat Set On Completion | Key Activity |
|-------|------|-------------|----------------------------|--------------|
| **A** | Main | 10 | `WorldJuvenileRockGolemDesertSpawn` | Investigate miners, secure outpost, collapse burrow |
| **B** | Main | 22 | `WorldJuvenileRockGolemWorldSpawn` | Scan caves, clear caveworms, collapse 3 cave burrows |
| **O1** | Optional | 12 | *(none)* | Organic Analyzer, craft Drill Arrows |
| **C** | Choice | 20 | `WorldLandsharksAppearInCaves` | Rescue Biggs & Wedge from Outpost Beta |
| **D** | Choice | 14 | `WorldCavewormsSpawnOutsideCaves` | Arctic exotic cluster, kill Exotic Infused Quarrite |
| **O2** | Optional | 7 | `WorldRockGolemExplosiveWeakness` | Test weapon types on Quarrites |
| **C2** | Main (after C) | 30 | `WorldJuvenileRockGolemExoticSpawn` | Build obs outpost, collect 4 armor fragment variants |
| **D2** | Main (after D) | 29 | *(none)* | Rebuild destroyed Outpost Beta, kill Landshark |
| **E** | Choice | 24 | `WorldJuvenileRockGolemLootIncreased` | Restock outpost, rescue Voss & Harken from caves |
| **F** | Choice | 18 | `WorldRockGolemMinionsReduced` | ECHO device, track tunnels, scan Quarrites |
| **Hunt** | Final | 5 | *(none)* | Resonance Surveyor → enter den → kill UNSTABLE QUARRITE |

> **Choice nodes (MutuallyExclusive):** After B choose C **or** D (mutually exclusive). After D2 choose E **or** F. C2 and E/F all funnel into the final Hunt.

### WorldStats — What They Do

Each completed stage sets a persistent world-level stat flag that changes the game environment. These are stored in the `WorldTalentManager` (per-world) and in each player's Profile (per-player):

| Flag | Effect on the World |
|------|---------------------|
| `WorldJuvenileRockGolemDesertSpawn` (after A) | Quarrites start appearing in desert zones |
| `WorldJuvenileRockGolemWorldSpawn` (after B) | Quarrites spawn across the whole map (current state of this save) |
| `WorldLandsharksAppearInCaves` (after C) | Landsharks begin appearing in caves |
| `WorldCavewormsSpawnOutsideCaves` (after D) | Caveworms escape caves and roam outside |
| `WorldJuvenileRockGolemExoticSpawn` (after C2) | Exotic-infused Quarrites start spawning |
| `WorldRockGolemExplosiveWeakness` (after O2) | Quarrites gain explosive weakness |
| `WorldJuvenileRockGolemLootIncreased` (after E) | Quarrite loot table improves |
| `WorldRockGolemMinionsReduced` (after F) | Fewer Quarrite minions in the boss fight |

**These flags drive the ambient world spawning separate from the quest-placed spawner actors.**

---

## Creature Roster (from `D_EpicCreatures.json` + `D_AICreatureType.json`)

| Internal Name | In-Game Name | Notes |
|---------------|--------------|-------|
| `RockGolem` | **UNSTABLE QUARRITE** | Final boss |
| `RockGolemJr_A` | **Quarrite** | Standard juvenile |
| `RockGolemJr_D` | **Exotic Eater** | Arctic variant |
| `RockGolemJr_E` | **Aggressive Borer** | Appears in Stage E caves |
| `RockGolemJr_F` | **Quarrite Warden** | Guards tunnels in Stage F |
| `RockGolemJr_Exotic` | **Exotic Infused Quarrite** | Appears in C2 / D |
| `CaveWorm_RockGolem` | *(Caveworm variant)* | Displaced caveworms from campaign |

**Spawn types on Olympus** (from `D_AISpawnConfig.json`):
- `Juvenile_Rock_Golem` → rules: `Away_From_Dropships` + `Quarrite_Population` (pop limit 1)
- `Juvenile_Rock_Golem_Arctic` → rules: `Away_From_Dropships` + `QuarriteArctic__Population` (pop limit 1)

Population is controlled by blueprint filters:
- `BP_SpawnFilter_PopulationCheck_Quarrite_C`
- `BP_SpawnFilter_PopulationCheck_QuarriteArctic_C`

---

## Rewards & Unlockable Blueprints

Completing campaign stages grants `AccountFlags` that unlock blueprints in the talent tree:

| Blueprint | Talent Row | Where Crafted | Flag Required |
|-----------|------------|---------------|---------------|
| Rock Golem Grenade | `Rock_Golem_Grenade` | T3 Machine | `GrantedBlueprint_RG_Grenade` |
| Rock Golem Sledgehammer | `Rock_Golem_Sledgehammer` | T4 Fabricator / Anvil | `GrantedBlueprint_RG_Sledgehammer` |
| Rock Golem Gun | `Rock_Golem_Gun` | T4 Fabricator | `GrantedBlueprint_RG_Gun` |
| Rock Golem Attachment | `Rock_Golem_Attachment` | T4 / Alt Bench | `GrantedBlueprint_RG_Attachment` |
| Rock Golem Module | `Rock_Golem_Module` | T4 / Alt Bench | `GrantedBlueprint_RG_Module` |
| Quarrite Trophies | `Rock_Golem_Trophies` | T2 Crafting | `GrantedBlueprint_RG_Trophies` (level 20+) |

Blueprint flags are stored per-player in **Profile.json**, not in savegame.json.

---

## Achievements (from `D_Accolades.json`)

| Achievement | Steam ID | Display Name | Condition |
|-------------|----------|--------------|-----------|
| `DefeatQuarrite` | `ACH_KILL_ROCKGOLEM_BOSS` | **Fault Line** | Kill the Quarrite boss once |
| `DefeatQuarriteHard` | `ACH_KILL_ROCKGOLEM_BOSS_HARD` | **Rock and a Hard Place** | Kill boss on hardest difficulty |
| `CompleteQuarriteTree` | `ACH_COMPLETE_ROCKGOLEM_CAMPAIGN` | **Hero of the Mines** | Complete the Quarrite Campaign (any path) |
| `AllQuarriteMissionsDone` | `ACH_FULL_ROCKGOLEM_CAMPAIGN` | **Faultless Victory** | Complete ALL 11 stages (multiple playthroughs) |

`AllQuarriteMissionsDone` requires: A, B, C, C2, D, D2, E, F, Hunt, O1, O2 — all 11 in any run combination.

---

## Current Save State (savegame.json)

**Prospect:** `Outpost006_Olympus` (Terrain_016), ~91 hours elapsed.
**Completed:** Stage A (at ~81h) and Stage B (at ~82h).
**Active quest actor:** `BPQ_GH_RG_B_C` — `bMissionComplete: True`.

### WorldTalentRecords (active world stat flags in this save)

| Talent | Rank | Means |
|--------|------|-------|
| `GH_RG_A` | 1 | Desert Quarrite spawning enabled |
| `GH_RG_B` | 1 | World-wide Quarrite spawning enabled ← **active** |

C, D, C2, D2, E, F, Hunt, O1, O2 — **not unlocked** in this save.

---

## How Campaign Progress Is Stored

| Data | Location | Scope |
|------|----------|-------|
| WorldStat flags (which stages completed) | `WorldTalentManagerRecorderComponent` in savegame.json | World/server |
| Active quest blueprint | `IcarusQuestManagerRecorderComponent` in savegame.json | World/server |
| `bMissionComplete`, `CurrentMissionIndex` | `GameModeStateRecorderComponent.PlayerRewards[]` in savegame.json | Per player (partial echo) |
| Full per-player mission history log | `GameModeStateRecorderComponent.MissionHistory[]` in savegame.json | Shared world log |
| Personal campaign progress, choice history | **Profile.json** per Steam ID | Per player |
| Blueprint unlock flags (`GrantedBlueprint_RG_*`) | **Profile.json** per Steam ID | Per player |
| Steam achievements | Steam / Profile.json | Per player |

---

## Spawning System — How It Works

There are **two independent spawning systems** in play:

### 1. Ambient World Spawning (WorldStat-driven)

Triggered by the `WorldStat` flags set on stage completion. These use the `D_AISpawnConfig.json` / `D_AISpawnRules.json` pipeline:
- Quarrites spawn on the map based on biome heatmap and population limits
- Population cap: 1 per spawn rule (controlled by blueprint filter)
- **Not stored as individual actor blobs** — the spawn system recreates them each session from the config

### 2. Quest-Placed Spawner Actors (blob-driven)

Specific `BP_Rock_Golem_Spawner_*` actors placed by quest scripts and persisted in `StateRecorderBlobs`:

| Blob # | Actor | Type | NumSpawned | bGeneratedRewards |
|--------|-------|------|------------|-------------------|
| 2149 | `BP_Rock_Golem_Spawner_Drill_C_2147453878` | Drill site (Stage A) | 2 | ✅ True |
| 2539 | `BP_Rock_Golem_Spawner_C_2147445025` | Cave spawner (Stage B) | 2 | ❌ False |
| 2540 | `BP_Rock_Golem_Spawner_C_2147445018` | Cave spawner (Stage B) | 2 | ❌ False |
| 2541 | `BP_Rock_Golem_Spawner_C_2147445011` | Cave spawner (Stage B) | 1 | ✅ True |

All use `OwnerResolvePolicy: FindOrRespawn` — recreated on map load if missing.

### 3. Prebuilt Structure Actors (blob-driven)

Map set-pieces placed by quest progression, also `FindOrRespawn`:

| Blob # | Structure | Stage |
|--------|-----------|-------|
| 2177 | `GH_RG_A_MiningOutpost` | A |
| 2468 | `GH_RG_B_Cave` | B |
| 2513 | `GH_RG_B_Cave2` | B |
| 2549 | `GH_RG_B_Cave3` | B |

---

## Removing Spawning Without Changing Campaign Progress

### The Problem

- **Ambient spawning** (system 1) is driven by `WorldTalentRecords` → cannot stop it without removing the world talent entries, which would reset campaign progress.
- **Spawner actors** (system 2) use `FindOrRespawn` → they recreate themselves every map load.

### Options

#### Option A — Delete Spawner Blobs (blob indices 2149, 2539, 2540, 2541)

Remove the four actor blobs from `StateRecorderBlobs`. Campaign data (QuestManager, WorldTalentManager, MissionHistory) is untouched.

**Risk:** If the world talent system re-places spawners dynamically on load, they come back.

#### Option B — Change OwnerResolvePolicy: FindOrRespawn → FindOnly

In each spawner blob, change:
```
OwnerResolvePolicy: FindOrRespawn  →  FindOnly
```
With `FindOnly` the engine skips creating the actor if it's not already in the live level.
The blob stays in the save file (campaign integrity intact), but no actor is spawned.

**Best for:** Stopping blob-driven re-creation while keeping save file coherent.
**Does not affect:** Ambient world spawning driven by WorldStats.

#### Option C — Max Out RecordedNumSpawned

Set `RecordedNumSpawned` to a large value (e.g., `9999`) on each spawner blob.
If the spawner blueprint checks `RecordedNumSpawned >= MaxSpawns` before spawning, this prevents new creatures.

**Risk:** Unknown whether the spawner blueprint uses this cap or ignores it for continuous population management.

#### Option D — Remove WorldTalentRecords (stops ambient spawning, minor progress impact)

Remove `GH_RG_B` (and/or `GH_RG_A`) from `WorldTalentManagerRecorderComponent.WorldTalentRecords`.

**Effect:** Ambient Quarrite world spawning stops. However, the campaign mission history and quest completion remain intact — only the world-state "which stages are active" resets.
**Risk:** If the game re-adds the talent records from per-player Profile data on reconnect, they come back.

### Recommended Combined Approach

To stop **both** spawning systems with minimal side effects:

1. **Option B** on all 4 spawner blobs (change `OwnerResolvePolicy` to `FindOnly`)
2. **Option C** on all 4 spawner blobs (set `RecordedNumSpawned = 9999`)
3. Leave `WorldTalentRecords`, `QuestManager`, `MissionHistory` **completely untouched**

Ambient Quarrite spawning (WorldStat-driven) will continue unless WorldTalentRecords are also cleared. That is a separate decision.

---

## All Quest Descriptions by Stage

### Stage A — Investigate the Mining Outpost (10 quests)

| Quest | Description |
|-------|-------------|
| `GH_RG_A` | *Quarrite Campaign* — starts dialogue `GH_RG_A_INTRO` |
| `GH_RG_A_Miners` | Investigate the Disappearance of the Miners |
| `GH_RG_A_Miners_Travel` | Travel to Mining Outpost Alpha — GRID: N5 |
| `GH_RG_A_Miners_Explore` | Inspect the Drill Site to Find Out What Was Unearthed |
| `GH_RG_A_Secure` | Secure the Outpost |
| `GH_RG_A_Secure_Creature` | Defeat the Strange Creature *(Use Pickaxe for bonus damage)* |
| `GH_RG_A_Secure_Eliminate` | Collapse the Quarrite Burrow in the Center of the Outpost |
| `GH_RG_A_Secure_Creatures` | Eliminate any remaining Quarrites |
| `GH_RG_A_Discover` | Uncover the Purpose of the Miners' Operation |
| `GH_RG_A_Discover_Search` | Search the Outpost for Records *(Notes and Audio Logs)* |

### Stage B — Search the Caves (22 quests)

| Quest | Description |
|-------|-------------|
| `GH_RG_B` | *Quarrite Campaign* — ⚠️ Caveworms driven from caves, will appear throughout |
| `GH_RG_B_Prepare` | Acquire Equipment to Help Locate Nearby Caves |
| `GH_RG_B_Prepare_Craft` | Unlock, Craft and pick up a Cave Scanner *(T3 Machining Bench)* |
| `GH_RG_B_Area` | Search Nearby Caves, Close Quarrite Burrows |
| `GH_RG_B_Area_Cave` | Check Caves in GRID: L4 |
| `GH_RG_B_Area_Cave_Caveworm` | Clear Caveworms by the Cave Entrance |
| `GH_RG_B_Area_Cave_Survivors` | Search Miners Cabin for Survivors and Notes |
| `GH_RG_B_Area_Cave_Spawner` | Block the Quarrite Burrow further in the Cave *(Pickaxe)* |
| `GH_RG_B_Area_Cave2` | Check Caves in GRID: K5 |
| `GH_RG_B_Area_Cave2_Spawner` | Block the Quarrite Burrow Near the Cave |
| `GH_RG_B_Area_Cave2_Salvage` | Salvage Mining Equipment, Deliver to Sinotai Pod |
| `GH_RG_B_Area_Cave2_Salvage_Cart` | Mining Carts |
| `GH_RG_B_Area_Cave2_Salvage_Pick` | Pickaxes |
| `GH_RG_B_Area_Cave2_Salvage_Coal` | Coal |
| `GH_RG_B_Area_Cave2_Salvage_Light` | Lights |
| `GH_RG_B_Area_Cave3` | Check Caves in GRID: L2 |
| `GH_RG_B_Area_Cave3_Worms` | Clear Caveworms by Cave Entrance |
| `GH_RG_B_Area_Cave3_Shark` | Defeat the Emerged Landshark |
| `GH_RG_B_Area_Cave3_Spawner` | Block the Quarrite Burrow further in the Cave |
| `GH_RG_B_Eliminate` | Eliminate Displaced Threats in the Area |
| `GH_RG_B_Eliminate_Caveworms` | Cull Displaced Caveworms |
| `GH_RG_B_Eliminate_TeenageCaveworms` | Eliminate Adolescent Caveworms |

### Stage O1 — Optional: Develop Drill Arrows (12 quests, available after B)

Location: GRID M6. Requires Organic Analyzer (Fabricator, needs power). Crafts Drill Arrows (T3 Forge).

### Stage C — Save Outpost Beta [Choice vs D] (20 quests)

Location: GRID F8. Rescue **Drill Chief Biggs** and **Excavator Wedge** using HEAL + Stasis Bags. Defend against Quarrites, Caveworms, Landshark.

### Stage D — Arctic Exotic Cluster [Choice vs C] (14 quests)

Central Arctic. Use Radar to find cluster → fight Exotic Infused Quarrite → find exotic shards → **choice: give to Norex or keep for yourself** (convert via Bio-Cleaner).

### Stage O2 — Optional: Test Weapons (7 quests, available after C)

Location: GRID B14/C15. Test Poison, Explosive, Projectile, and Pickaxe kills on Quarrites.

### Stage C2 — Observation Outpost (30 quests, requires C)

Location: GRID B13. Build T3 outpost → craft Binoculars + Taxidermy Knife + Grenades → collect 4 Quarrite Armor Fragment variants (Oxite, Copper, Gold, Exotic) → defeat **Exotic Infused Quarrite** → convert fragment via Bio-Cleaner.

### Stage D2 — Rebuild Outpost Beta (29 quests, requires D)

Discover Outpost Beta was destroyed. Rebuild Barracks, Storage, Farm (Glasshouse), Workshop. Deploy Mini-Thumper → kill Caveworms to draw out Landshark → defeat Landshark.

### Stage E — Recover Personnel [Choice vs F] (24 quests)

Restock Outpost Beta. Rescue **Foreman Voss** (GRID F7) and **Technician Harken** (GRID B6) from caves. Defeat Aggressive Borer and Stygian Landshark. Use Stasis Bags.

### Stage F — Track the Tunnels [Choice vs E] (18 quests)

Use **BEAST device** to scan Quarrites (GRID F10) → calibrate **ECHO device** → follow tunnels to 4 locations (SD-I10, SD-K14, SD-G13, SD-D14) → defeat **Quarrite Wardens** → cull Caveworms and young Quarrites.

### Final Hunt (5 quests, requires C2 + E or F)

Use **Resonance Surveyor** to find seismic source → enter Quarrite Burrow → defeat **THE UNSTABLE QUARRITE** *(use Pickaxe for bonus damage on armor)*.
