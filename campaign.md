# Quarrite Campaign — GD.json Analysis

## What Is the Quarrite Campaign?

"Quarrite" is the in-game name for the **Rock Golem** creature (`GH_RG_*` prefix = Great Hunt Rock Golem).
The campaign is a multi-stage Great Hunt story arc that runs on Olympus (`Terrain_016`).

Available campaign stages (from `D_Quests.json`):

| Stage | Quest Key | Description |
|-------|-----------|-------------|
| A | `GH_RG_A` | First contact: miners disappear, find and secure the mining outpost |
| B | `GH_RG_B` | Cave investigation (caveworms warning) |
| C | `GH_RG_C` | *(not started in this save)* |
| C2 | `GH_RG_C2` | *(not started)* |
| D | `GH_RG_D` | *(not started)* |
| D2 | `GH_RG_D2` | *(not started)* |
| E | `GH_RG_E` | *(not started)* |

---

## Current Campaign State (This Save File)

**Prospect:** `Outpost006_Olympus` — Terrain_016, elapsed ~91 hours.

### Quest Manager (`IcarusQuestManagerRecorderComponent`, blob index 52)

| Field | Value | Meaning |
|-------|-------|---------|
| `QuestActorName` | `BPQ_GH_RG_B_C` | Active quest blueprint: Campaign B |
| `bMissionComplete` | `True` | B is complete |
| `bRunQuests` | `True` | Quest system is live |
| `FactionMissionName` | `None` | No faction mission attached |
| `DynamicQuestDifficulty` | `2` | Medium |

### World Talent Manager (`WorldTalentManagerRecorderComponent`, blob index 53)

Stores which campaign stages are "unlocked" at world level:

| Talent Row | Rank |
|------------|------|
| `GH_RG_A` | 1 |
| `GH_RG_B` | 1 |

> **Critical:** These world talent records are what drive map changes. When Rank 1 is set for a stage,
> the game places prebuilt structures and activates spawners for that stage.

### Per-Player Mission History (in `GameModeStateRecorderComponent`, blob index 45)

Tracked inside `MissionHistory` array, per player:

| Player (Steam ID) | `bMissionCompleted` | `CurrentMissionIndex` | Missions completed |
|-------------------|---------------------|-----------------------|--------------------|
| 76561198119356626 | **True** | 13 | `GH_RG_A`, `GH_RG_B` |
| 76561198162166460 | **True** | 13 | `GH_RG_A`, `GH_RG_B` |
| 76561199178830519 | False | 2 | partial |
| 76561198116205199 | False | 0 | — |

Mission end times (game-seconds):
- `GH_RG_A`: 292,406 s (~81 hours in)
- `GH_RG_B`: 296,987 s (~82 hours in)

---

## How the Campaign Changes the Map

The campaign affects the world through **three systems**, each stored independently:

### 1. Prebuilt Structures (`PrebuiltStructureRecorderComponent`)

Entire prefab areas placed by quest progression, stored as actor blobs with `OwnerResolvePolicy: FindOrRespawn`.

| Blob # | Structure Name | Contents |
|--------|----------------|----------|
| 2177 | `GH_RG_A_MiningOutpost` | Grid floors, notes, mining rails, carts, equipment, furniture, hitching posts |
| 2468 | `GH_RG_B_Cave` | Cave interior with props |
| 2513 | `GH_RG_B_Cave2` | Second cave |
| 2549 | `GH_RG_B_Cave3` | Third cave (furnace, crates, animal beds, hitching posts) |

All four structures use `FindOrRespawn` — if the actor is missing from the map, it gets recreated from the save data.

### 2. Rock Golem Spawners (`ActorStateRecorderComponent`, `FindOrRespawn`)

These actors control where and how many Quarrites spawn:

| Blob # | Actor | Location (UE4 units) | NumSpawned | bGeneratedRewards |
|--------|-------|----------------------|------------|-------------------|
| 2149 | `BP_Rock_Golem_Spawner_Drill_C` | (262094, -171599, -30423) | 2 | **True** |
| 2539 | `BP_Rock_Golem_Spawner_C` | (158151, -255770, -32144) | 2 | False |
| 2540 | `BP_Rock_Golem_Spawner_C` | (126073, -186515, -34391) | 2 | False |
| 2541 | `BP_Rock_Golem_Spawner_C` | (153673, -331125, -32341) | 1 | **True** |

Each spawner tracks two state variables:
- `RecordedNumSpawned` (IntVar) — how many Quarrites this spawner has already created
- `bGeneratedRewards` (BoolVar) — whether this spawner has paid out its loot

### 3. Den Entrance Teleport (`BaseLevelTeleportRecorderComponent`, blob index 44)

| Field | Value |
|-------|-------|
| `ObjectFName` | `BP_GH_DenEntrance_RockGolem_2` |
| `bTeleportActive` | False |
| `RemainingCooldown` | 0 |
| Location | (-238191, 263300, -34458) |

---

## Data Separation: World vs Per-Player

| Data | Where stored | Scope |
|------|-------------|-------|
| Active quest blueprint | `IcarusQuestManagerRecorderComponent.QuestActorName` | World |
| `bMissionComplete` | `IcarusQuestManagerRecorderComponent` | World |
| World talent unlocks | `WorldTalentManagerRecorderComponent.WorldTalentRecords` | World |
| Spawner state (`RecordedNumSpawned`, `bGeneratedRewards`) | Each spawner actor blob | World |
| Prebuilt structures | `PrebuiltStructureRecorderComponent` | World |
| `bMissionCompleted` per player | `GameModeStateRecorderComponent.PlayerRewards[N]` | Per player |
| `CurrentMissionIndex` per player | `GameModeStateRecorderComponent.PlayerRewards[N]` | Per player |
| Mission history log | `GameModeStateRecorderComponent.MissionHistory` | World (shared) |

**Campaign progress** lives in three world-level records (`QuestManager`, `WorldTalentManager`, `GameModeState`) and is replicated per-player only in `bMissionCompleted` / `CurrentMissionIndex`.
**Spawning** lives entirely in the individual spawner actor blobs.

These two systems are **independent** — the spawner blobs do not reference the quest/talent records directly.

---

## How to Remove Spawning Without Changing Campaign Progress

### The Problem

All four Rock Golem spawner actors use `OwnerResolvePolicy: FindOrRespawn`.
This means: every time the server loads this prospect, if the spawner actor is not found on the map, the engine re-creates it from the saved blob.
The spawner blueprint then resumes spawning Quarrites based on its internal logic and `RecordedNumSpawned`.

### Option A — Delete the Spawner Blobs (Recommended if game doesn't re-add them)

Remove the four spawner actor entries from `StateRecorderBlobs` entirely:

- Blob index **2149** (`BP_Rock_Golem_Spawner_Drill_C_2147453878`)
- Blob index **2539** (`BP_Rock_Golem_Spawner_C_2147445025`)
- Blob index **2540** (`BP_Rock_Golem_Spawner_C_2147445018`)
- Blob index **2541** (`BP_Rock_Golem_Spawner_C_2147445011`)

**Leaves untouched:** QuestManager, WorldTalentManager, all mission history, prebuilt structures.

**Risk:** If the `WorldTalentManager` triggers the game to re-add spawners dynamically at load time (outside the save file), they will come back. This is the main unknown.

### Option B — Change OwnerResolvePolicy to FindOnly (Safer for persistence)

For each of the four spawner blobs, change:

```
OwnerResolvePolicy: FindOrRespawn  →  FindOnly
```

With `FindOnly`, if the actor is not found in the live level, the engine **skips** recreating it — the blob record stays in the save file (campaign data intact), but no actor is spawned.

**Advantage:** The blob entries remain, so the save file still looks "complete" to any campaign-progress checks.
**Disadvantage:** If the engine spawns these actors from a different code path (e.g., triggered by `WorldTalentRecords`), this won't help.

### Option C — Max Out RecordedNumSpawned

Set `RecordedNumSpawned` to a very large value (e.g., `9999`) on each spawner:

```
IntVar: RecordedNumSpawned = 9999
```

If the spawner blueprint has an internal `MaxSpawns` threshold it checks before spawning, this will prevent any new spawns while keeping the actors present in the world.
Campaign progress is completely unchanged.

**Risk:** Unknown whether `MaxSpawns` exists and what the cap is. If the spawner ignores `RecordedNumSpawned` for ongoing population management, this won't work.

### Option D — Set bGeneratedRewards + RecordedNumSpawned Together

Combine C with setting `bGeneratedRewards = True` on all spawners:

```
BoolVar: bGeneratedRewards = True
IntVar:  RecordedNumSpawned = 9999
```

Currently two spawners already have `bGeneratedRewards = False` (2539 and 2540). If the reward flag gates spawning activity, enabling it may stop the cycle.

---

## Recommended Approach

**Start with Option B (FindOnly)** because:
- It's fully reversible (just change the string back)
- The blob stays in the file so campaign validation is unaffected
- It directly targets the `FindOrRespawn` mechanism that drives actor recreation

**If Option B doesn't work** (game overrides it with dynamic spawning), try **Option C** (max RecordedNumSpawned) on top.

**Do not modify** any of the following — they hold campaign progress:
- `WorldTalentManagerRecorderComponent.WorldTalentRecords`
- `IcarusQuestManagerRecorderComponent` (QuestActorName, bMissionComplete)
- `GameModeStateRecorderComponent` (MissionHistory, PlayerRewards)

---

## Field Reference for Spawner Blobs

Each spawner actor blob (`ActorStateRecorderComponent`) has this structure:

```
ActorStateRecorderVersion: 3
ActorTransform: { Rotation, Translation, Scale3D }
SavedInventories: [...]        ← loot contents (drill spawner only)
FLODComponentData: { ... }
IcarusActorGUID: <int>
ObjectFName: BP_Rock_Golem_Spawner_*_C_<id>
Modifiers: []
EnergyTraitRecord: { bActive: false }
WaterTraitRecord:  { bActive: false }
GeneratorTraitRecord: { bActive: false }
ResourceComponentRecord: { bDeviceActive: true, ... }
IntVariables:
  - VariableName: RecordedNumSpawned
    iVariable: <int>            ← ★ CONTROL POINT
BoolVariables:
  - VariableName: bGeneratedRewards
    bVariable: <bool>           ← ★ CONTROL POINT
NameVariables: []
OwnerResolvePolicy: FindOrRespawn  ← ★ CONTROL POINT
ActorClassName: BP_Rock_Golem_Spawner_*_C
ActorPathName: /Game/Maps/Terrain_016_OLY/...
```
