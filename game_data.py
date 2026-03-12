#!/usr/bin/env python3
"""
Icarus Game Data

Provides classification and display metadata for save file RowNames.

Data sourced from icarusbuilds.app (https://icarusbuilds.app/) which extracts
its data from the Icarus game PAK files.

Two separate in-game systems are stored in Characters.json Talents[]:
  - TECH TREE  : Blueprint/crafting unlocks (Stone_Knife, Crafting_Bench, ...)
  - TALENTS    : Character perk bonuses     (Bow_Accuracy, Solo_Stamina, ...)

Profile.json Talents[] stores:
  - WORKSHOP   : Meta-progression unlocks   (Workshop_Envirosuit, ...)
"""

import re
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Talent tree structure
# (tree_key, subtree_key) -> (tree_display, subtree_display)
# ---------------------------------------------------------------------------

TALENT_TREES = {
    's': 'Survival',
    't': 'Construction',
    'x': 'Combat',
    'z': 'Solo',
}

TALENT_SUBTREES = {
    'sr': ('Survival',      'Resources'),
    'se': ('Survival',      'Exploration'),
    'sh': ('Survival',      'Hunting'),
    'sc': ('Survival',      'Cook / Farm'),
    'tr': ('Construction',  'Repairing'),
    'tt': ('Construction',  'Tools'),
    'tb': ('Construction',  'Building'),
    'xb': ('Combat',        'Bows'),
    'xs': ('Combat',        'Spears'),
    'xx': ('Combat',        'Blades'),
    'xf': ('Combat',        'Firearms'),
    'za': ('Solo',          'Solo'),
}

# ---------------------------------------------------------------------------
# Tech tree tiers (Planetary)
# ---------------------------------------------------------------------------

TECH_TIERS = {
    't1base': 'Tier 1',
    't2base': 'Tier 2',
    't3base': 'Tier 3',
    't4base': 'Tier 4',
}

# Crafting bench keys (Workshop items at specific benches)
BENCH_TIER = {
    's_anvi': 'Anvil',
    's_armo': 'Armor Bench',
    's_carp': 'Carpentry Bench',
    's_ceme': 'Cement Mixer',
    's_chem': 'Chemistry Bench',
    's_glas': 'Glass Furnace',
    's_herb': 'Herbalism Bench',
    's_kitc': 'Kitchen',
    's_maso': 'Mason Bench',
    's_mort': 'Mortar & Pestle',
    's_mpro': 'Meat Processing',
}

# ---------------------------------------------------------------------------
# RowName → subtree prefix mappings for talent perks
# ---------------------------------------------------------------------------

# Maps RowName prefix → TALENT_SUBTREES key
TALENT_PREFIXES: list = [
    # Combat
    ('Bow_',           'xb'),
    ('Crossbow_',      'xb'),
    ('Spear_',         'xs'),
    ('Javelin_',       'xs'),
    ('Blade_',         'xx'),
    ('Sword_',         'xx'),
    ('Knife_Combat_',  'xx'),
    ('Axe_Combat_',    'xx'),
    ('Pistol_',        'xf'),
    ('Rifle_',         'xf'),
    ('Shotgun_',       'xf'),
    ('Firearm_',       'xf'),
    ('Gun_',           'xf'),
    # Survival
    ('Stalking_',      'sh'),
    ('Hunting_',       'sh'),
    ('Trap_',          'sh'),
    ('Gathering_',     'sh'),
    ('Genetics_',      'sh'),
    ('Solo_',          'za'),
    ('Resources_',     'sr'),
    ('Lumber_',        'sr'),
    ('Mining_',        'sr'),
    ('Exploration_',   'se'),
    ('Health_',        'se'),
    ('Oxygen_',        'se'),
    ('Swim_',          'se'),
    ('Cook_',          'sc'),
    ('Farm_',          'sc'),
    ('Cooking_',       'sc'),
    ('Food_',          'sc'),
    ('Produce_',       'sc'),
    ('Water_Trough',   'sc'),
    # Construction
    ('Building_',      'tb'),
    ('Fortification_', 'tb'),
    ('Construction_',  'tb'),
    ('Repair_',        'tr'),
    ('Tools_',         'tt'),
    ('Tool_',          'tt'),
    ('Talent_',        None),   # generic - will show as unknown subtree
]

# ---------------------------------------------------------------------------
# RowName normalization helpers
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    """Normalize a string for fuzzy matching."""
    return re.sub(r'[^a-z0-9]+', '_', s.lower()).strip('_')


def _build_tech_index() -> dict:
    """Build title→site_key lookup from assets/tech_data.json."""
    import json, os
    assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
    tech_path   = os.path.join(assets_dir, 'tech_data.json')
    tiers_path  = os.path.join(assets_dir, 'tech_tiers.json')
    if not os.path.exists(tech_path):
        return {}
    with open(tech_path) as f:
        tech = json.load(f)
    with open(tiers_path) as f:
        tiers = json.load(f)

    index = {}  # norm_title -> (site_key, tier_label, title)
    for site_key, node in tech.items():
        title = node.get('title', '')
        tier  = TECH_TIERS.get(tiers.get(site_key, ''), BENCH_TIER.get(tiers.get(site_key, ''), 'Workshop'))
        nk    = _norm(title)
        index[nk] = (site_key, tier, title)
        # Also index without trailing tier suffixes in title
        cleaned = re.sub(r'\s+(tier\s+)?\d+$', '', title, flags=re.I)
        if cleaned != title:
            index[_norm(cleaned)] = (site_key, tier, title)
    return index


# Build once on import
_TECH_INDEX: dict = _build_tech_index()


def classify_row_name(row_name: str) -> Tuple[str, Optional[str], str]:
    """
    Classify a Characters.json Talent RowName.

    Returns:
        (category, subtree_or_tier, display_label)
        category: 'tech' | 'talent' | 'unknown'
        subtree_or_tier: for tech = tier name; for talent = subtree key; else None
        display_label: human-readable category string
    """
    # 1. Try tech tree match by title normalization
    title_guess = row_name.replace('_', ' ')
    nk = _norm(title_guess)
    if nk in _TECH_INDEX:
        site_key, tier, title = _TECH_INDEX[nk]
        return ('tech', tier, tier)

    # 2. Try with trailing _T2/_T3/_T4 variants stripped
    cleaned = re.sub(r'_T[234]$|_v\d+$|_MK\d+$|_Tier\d+$', '', row_name)
    if cleaned != row_name:
        nk2 = _norm(cleaned.replace('_', ' '))
        if nk2 in _TECH_INDEX:
            _, tier, _ = _TECH_INDEX[nk2]
            return ('tech', tier, tier)

    # 3. Try talent prefix match
    for prefix, subtree_key in TALENT_PREFIXES:
        if row_name.startswith(prefix):
            if subtree_key and subtree_key in TALENT_SUBTREES:
                tree, sub = TALENT_SUBTREES[subtree_key]
                return ('talent', subtree_key, f'{tree} / {sub}')
            return ('talent', None, 'Talent (unclassified)')

    # 4. Heuristic: single-word or CamelCase names with no underscore are likely tech items
    if '_' not in row_name:
        return ('tech', 'unknown', 'Tier ?')

    return ('unknown', None, 'Unknown')


def get_tech_node_info(site_key: str) -> Optional[dict]:
    """Return tech node metadata (title, desc, flavor) by site key."""
    import json, os
    assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
    tech_path  = os.path.join(assets_dir, 'tech_data.json')
    if not os.path.exists(tech_path):
        return None
    with open(tech_path) as f:
        tech = json.load(f)
    return tech.get(site_key)


def get_talent_node_info(subtree_key: str, site_key: str) -> Optional[dict]:
    """Return talent node metadata (title, desc, stats) by subtree + site key."""
    import json, os
    assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
    path = os.path.join(assets_dir, 'talent_data.json')
    if not os.path.exists(path):
        return None
    with open(path) as f:
        talent_data = json.load(f)
    subtree = talent_data.get(subtree_key, {})
    return subtree.get(site_key)


# ---------------------------------------------------------------------------
# Full data caches (loaded once on import)
# ---------------------------------------------------------------------------

def _load_tech_data_full() -> dict:
    import json, os
    p = os.path.join(os.path.dirname(__file__), 'assets', 'tech_data.json')
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        return json.load(f)


def _load_talent_data_full() -> dict:
    import json, os
    p = os.path.join(os.path.dirname(__file__), 'assets', 'talent_data.json')
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        return json.load(f)


def _load_tech_tiers_full() -> dict:
    import json, os
    p = os.path.join(os.path.dirname(__file__), 'assets', 'tech_tiers.json')
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        return json.load(f)


_TECH_DATA_FULL:   dict = _load_tech_data_full()
_TALENT_DATA_FULL: dict = _load_talent_data_full()
_TECH_TIERS_FULL:  dict = _load_tech_tiers_full()


# ---------------------------------------------------------------------------
# Catalog functions
# ---------------------------------------------------------------------------

def get_tech_catalog_for_tier(tier_label: str) -> List[Tuple]:
    """
    Return all tech catalog items for a given tier label.

    Returns list of (site_key, row_name, title, desc, flavor) sorted by title.
    row_name is derived as title.replace(' ', '_').
    """
    tier_key = None
    for k, v in TECH_TIERS.items():
        if v == tier_label:
            tier_key = k
            break
    if tier_key is None:
        for k, v in BENCH_TIER.items():
            if v == tier_label:
                tier_key = k
                break
    if tier_key is None:
        return []

    result = []
    for site_key, tk in _TECH_TIERS_FULL.items():
        if tk == tier_key:
            node = _TECH_DATA_FULL.get(site_key, {})
            title = node.get('title', site_key)
            row_name = title.replace(' ', '_')
            result.append((site_key, row_name, title,
                           node.get('desc', ''), node.get('flavor', '')))
    return sorted(result, key=lambda x: x[2])


def get_talent_catalog_for_subtree(subtree_key: str) -> List[Tuple]:
    """
    Return all talent catalog items for a given subtree key.

    Returns list of (site_key, title, desc, stats_str) sorted by title.
    """
    subtree = _TALENT_DATA_FULL.get(subtree_key, {})
    result = []
    for site_key, node in subtree.items():
        result.append((site_key, node.get('title', site_key),
                       node.get('desc', ''), node.get('stats', '')))
    return sorted(result, key=lambda x: x[1])


def format_stats(stats_str: str) -> str:
    """
    Format '+{0}% Foo Bar;5;10;20' → '+5% Foo Bar  →  +10% Foo Bar  →  +20% Foo Bar'
    """
    if not stats_str:
        return ''
    parts = stats_str.split(';')
    if len(parts) < 2:
        return stats_str
    template, values = parts[0], parts[1:]
    return '  →  '.join(template.replace('{0}', v) for v in values)


def rowname_matches_catalog(save_rn: str, catalog_rn: str) -> bool:
    """
    Check if a save RowName corresponds to a catalog tech node.
    Handles suffix variants like _T3, _T4, _v2, _MK2.
    """
    if save_rn == catalog_rn:
        return True
    stripped = re.sub(r'_T[234]$|_T\d+$|_v\d+$|_MK\d+$|_Tier\d+$|_\d+$', '', save_rn)
    return stripped == catalog_rn


def find_talent_catalog_match(row_name: str, subtree_key: str) -> Optional[Dict]:
    """
    Fuzzy-match a save talent RowName to its catalog node.
    Returns dict with site_key/title/desc/stats, or None.
    """
    # Strip the known prefix for this subtree
    prefix_used = ''
    for p, sk in TALENT_PREFIXES:
        if row_name.startswith(p) and sk == subtree_key:
            prefix_used = p
            break

    remainder = row_name[len(prefix_used):]
    # Remove trailing digits / underscore-numbers
    remainder = re.sub(r'[_\d]+$', '', remainder)
    remainder = remainder.replace('_', ' ').lower().strip()
    if not remainder:
        return None

    query_words = set(remainder.split())
    subtree = _TALENT_DATA_FULL.get(subtree_key, {})

    best_score, best_key = 0, None
    for site_key, node in subtree.items():
        title_w = set(node.get('title', '').lower().split())
        desc_w  = set(node.get('desc',  '').lower().split())
        score = (len(query_words & title_w) * 3 +
                 len(query_words & desc_w))
        if score > best_score:
            best_score, best_key = score, site_key

    if best_score > 0 and best_key:
        node = subtree[best_key]
        return {
            'site_key': best_key,
            'title':    node.get('title', ''),
            'desc':     node.get('desc',  ''),
            'stats':    node.get('stats', ''),
        }
    return None


def get_tech_tier_labels() -> List[str]:
    """Return all tier labels that have at least one catalog item."""
    from collections import Counter
    label_map = {**{k: v for k, v in TECH_TIERS.items()},
                 **{k: v for k, v in BENCH_TIER.items()}}
    tier_counts: dict = {}
    for site_key, tier_key in _TECH_TIERS_FULL.items():
        label = label_map.get(tier_key, 'Workshop')
        tier_counts[label] = tier_counts.get(label, 0) + 1
    # Return in canonical order, filtered to those with items
    result = [t for t in (list(TECH_TIERS.values()) + list(BENCH_TIER.values()))
              if t in tier_counts]
    # De-duplicate while preserving order
    seen = set()
    return [t for t in result if not (t in seen or seen.add(t))]  # type: ignore


def classify_save_talents(talents: list) -> dict:
    """
    Classify a list of TalentEntry objects into tech and talent groups.

    Returns:
        {
          'tech':    { tier_label: [(row_name, rank), ...], ... },
          'talent':  { 'Tree/Sub': [(row_name, rank), ...], ... },
          'unknown': [(row_name, rank), ...],
        }
    """
    tech_groups:    dict = {}
    talent_groups:  dict = {}
    unknown_list:   list = []

    for entry in talents:
        cat, sub_or_tier, label = classify_row_name(entry.row_name)
        if cat == 'tech':
            tech_groups.setdefault(label, []).append((entry.row_name, entry.rank))
        elif cat == 'talent':
            talent_groups.setdefault(label, []).append((entry.row_name, entry.rank))
        else:
            unknown_list.append((entry.row_name, entry.rank))

    return {
        'tech': tech_groups,
        'talent': talent_groups,
        'unknown': unknown_list,
    }
