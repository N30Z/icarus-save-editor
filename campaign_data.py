"""
Campaign mission definitions loaded from data/GreatHunt/D_GreatHunts.json.
Regular prospect mission definitions loaded from data/Prospects/D_ProspectList.json.

Provides the three Great Hunt campaigns, a helper to detect which campaign
a savegame.json prospect save belongs to, and grouped regular prospect missions.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

_DATA_PATH = Path(__file__).parent / "data" / "GreatHunt" / "D_GreatHunts.json"
_PROSPECT_LIST_PATH = Path(__file__).parent / "data" / "Prospects" / "D_ProspectList.json"
_TALENTS_PATH = Path(__file__).parent / "data" / "Talents" / "D_Talents.json"

# D_ProspectList row_name → D_Talents row_name (for Profile.json writes).
# e.g. "STYX_D_Expedition" → "Prospect_Styx_D_Expedition"
# Populated by _load_talent_keys() at import time.
PROSPECT_TALENT_KEYS: Dict[str, str] = {}

# Hunt archetype RowName  →  campaign id
_HUNT_TO_CAMPAIGN: Dict[str, str] = {
    'GreatHunt_RockGolem':  'quarrite',
    'GreatHunt_Ape':        'gargantuan',
    'GreatHunt_IceMammoth': 'rimetusk',
}

# Type → display color hint (consumed by the tab)
TYPE_COLORS: Dict[str, str] = {
    'Standard': '#4da6ff',
    'Choice':   '#e09b3d',
    'Optional': '#3bba6b',
    'Final':    '#e05252',
}

# Master campaign table; 'missions' list is populated by _load() at import time.
CAMPAIGNS: Dict[str, dict] = {
    'quarrite': {
        'name':         'Quarrite Campaign',
        'subtitle':     'Great Hunt: Rock Golem',
        'map':          'Olympus',
        'key_prefixes': ('GH_RG',),
        'missions':     [],
    },
    'gargantuan': {
        'name':         'Gargantuan Campaign',
        'subtitle':     'Great Hunt: Ape',
        'map':          'Styx',
        'key_prefixes': ('GH_Ape',),
        'missions':     [],
    },
    'rimetusk': {
        'name':         'Rimetusk Campaign',
        'subtitle':     'Great Hunt: Ice Mammoth',
        'map':          'Prometheus',
        'key_prefixes': ('GH_IM',),
        'missions':     [],
    },
}

# Prospect row_name → display name (e.g. "GH_RG_A" → "MISSING MINERS")
# Populated by _load_prospects() at import time.
PROSPECT_DISPLAY_NAMES: Dict[str, str] = {}

# Prospect row_name → short description (e.g. "GH_RG_A" → "INVESTIGATE THE DISTURBANCE...")
# Populated by _load_prospects() at import time.
PROSPECT_DESCRIPTIONS: Dict[str, str] = {}

# Regular (non-campaign) prospect missions grouped by map.
# Each group: {'name': str, 'color': str, 'missions': [{'row_name': str, 'label': str}, ...]}
# Populated by _load_prospects() at import time.
REGULAR_MISSION_GROUPS: List[Dict] = []

# Row name prefix → map name for regular (non-GH) prospects.
# Used by detect_map() and _load_prospects().
_PROSPECT_PREFIX_TO_MAP: Dict[str, str] = {
    'Tier':  'Olympus',
    'OLY_':  'Olympus',
    'STYX_': 'Styx',
    'PRO_':  'Prometheus',
    'ELY_':  'Elysium',
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_loctext(s: str) -> str:
    """Extract display text from NSLOCTEXT(...) or return the string as-is."""
    m = re.search(r'NSLOCTEXT\([^,]+,[^,]+,\s*"(.*?)"\)', s)
    return m.group(1) if m else s


def _format_label(name: str) -> str:
    """'Rock_Golem_C2' → 'Rock Golem C2'"""
    return name.replace('_', ' ')


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_talent_keys() -> None:
    """Build PROSPECT_TALENT_KEYS from D_Talents.json.

    Two passes:
    1. ExtraData.RowName → Name  (authoritative, where present)
    2. Pattern derivation for talents with no/wrong ExtraData:
       Prospect_OLY_X  → OLY_X
       Prospect_Styx_X → STYX_X
       Prospect_Pro_X  → PRO_X
       Prospect_ELY_X  → ELY_X
    """
    try:
        with open(_TALENTS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return

    # Pass 1: ExtraData-based mapping (most reliable)
    for row in data['Rows']:
        extra = row.get('ExtraData') or {}
        if extra.get('DataTableName') == 'D_ProspectList':
            prospect_key = extra.get('RowName', '')
            talent_key = row.get('Name', '')
            if prospect_key and talent_key:
                PROSPECT_TALENT_KEYS[prospect_key] = talent_key

    # Pass 2: Pattern-based fallback for missing entries
    _TALENT_PREFIX_TO_PROSPECT: Dict[str, str] = {
        'Prospect_OLY_':  'OLY_',
        'Prospect_Styx_': 'STYX_',
        'Prospect_Pro_':  'PRO_',
        'Prospect_ELY_':  'ELY_',
    }
    for row in data['Rows']:
        talent_key = row.get('Name', '')
        for t_prefix, p_prefix in _TALENT_PREFIX_TO_PROSPECT.items():
            if talent_key.startswith(t_prefix):
                prospect_key = p_prefix + talent_key[len(t_prefix):]
                if prospect_key not in PROSPECT_TALENT_KEYS:
                    PROSPECT_TALENT_KEYS[prospect_key] = talent_key
                break


def _load_prospects() -> None:
    """Load D_ProspectList.json to build display names and regular mission groups."""
    with open(_PROSPECT_LIST_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Row names to exclude from the regular missions panel
    _EXCLUDE_PREFIXES = (
        'Outpost',       # persistent outpost sessions
        'OpenWorld',     # open world sessions
        'GreatHunt_',    # hunt archetype rows, not missions
        'GH_',           # Great Hunt campaign missions (left panel)
    )

    # How to classify a row into a map group by name prefix
    _MAP_GROUPS_ORDER = ['Olympus', 'Styx', 'Prometheus', 'Elysium']
    _MAP_COLORS = {
        'Olympus':    '#3bba6b',
        'Styx':       '#e09b3d',
        'Prometheus': '#4da6ff',
        'Elysium':    '#9b59b6',
    }
    _PREFIX_TO_MAP = _PROSPECT_PREFIX_TO_MAP

    # Build display name lookup and collect regular missions
    _groups: Dict[str, List[Dict]] = {m: [] for m in _MAP_GROUPS_ORDER}

    for row in data['Rows']:
        name: str = row['Name']
        drop_name = _extract_loctext(row.get('DropName', name))
        description = _extract_loctext(row.get('Description', ''))
        PROSPECT_DISPLAY_NAMES[name] = drop_name
        if description:
            PROSPECT_DESCRIPTIONS[name] = description

        # Skip excluded prefixes
        if any(name.startswith(p) for p in _EXCLUDE_PREFIXES):
            continue

        # Classify into a map group
        map_group: Optional[str] = None
        for prefix, mg in _PREFIX_TO_MAP.items():
            if name.startswith(prefix):
                map_group = mg
                break

        if map_group is None:
            continue  # unknown / don't show

        _groups[map_group].append({
            'row_name':        name,
            'talent_row_name': PROSPECT_TALENT_KEYS.get(name, name),
            'label':           drop_name,
            'description':     description,
        })

    for map_name in _MAP_GROUPS_ORDER:
        missions = _groups[map_name]
        if missions:
            REGULAR_MISSION_GROUPS.append({
                'name':     map_name,
                'color':    _MAP_COLORS[map_name],
                'missions': missions,
            })


def _load() -> None:
    with open(_DATA_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for row in data['Rows']:
        hunt_key = row['Hunt']['RowName']
        campaign_id = _HUNT_TO_CAMPAIGN.get(hunt_key)
        if campaign_id is None:
            continue

        row_name = row['Prospect']['RowName']
        forbidden = [ft['RowName'] for ft in row.get('ForbiddenTalent', [])]

        # Prefer the display name from D_ProspectList if available; fall back to
        # the internal name formatted as a readable label.
        display = PROSPECT_DISPLAY_NAMES.get(row_name)
        label = display if display else _format_label(row['Name'])
        description = PROSPECT_DESCRIPTIONS.get(row_name, '')

        CAMPAIGNS[campaign_id]['missions'].append({
            'row_name':    row_name,          # talent key, e.g. GH_RG_A
            'name':        row['Name'],       # e.g. Rock_Golem_A
            'label':       label,             # e.g. MISSING MINERS
            'description': description,       # e.g. INVESTIGATE THE DISTURBANCE...
            'type':        row.get('Type', 'Standard'),
            'forbidden':   forbidden,
        })


# Run at import time — talent keys first, then prospect list, then campaigns.
_load_talent_keys()
_load_prospects()
_load()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def detect_map(prospect_key: str) -> Optional[str]:
    """
    Return the map name ('Olympus', 'Styx', 'Prometheus', 'Elysium') for a
    ProspectDTKey string, or None if it cannot be determined.

    Works for both campaign (GH_*) and regular prospect keys.
    """
    if not prospect_key:
        return None

    # Campaign keys → map via CAMPAIGNS table
    campaign_id = detect_campaign(prospect_key)
    if campaign_id:
        return CAMPAIGNS[campaign_id]['map']

    # Regular prospect keys → map via prefix table
    for prefix, map_name in _PROSPECT_PREFIX_TO_MAP.items():
        if prospect_key.startswith(prefix):
            return map_name

    return None


def detect_campaign(prospect_key: str) -> Optional[str]:
    """
    Return the campaign id ('quarrite', 'gargantuan', 'rimetusk') for the given
    ProspectDTKey string, or None if it cannot be determined.

    Detection order:
      1. Talent-key prefix  (GH_RG_*, GH_Ape_*, GH_IM_*)
      2. Map name substring (Olympus, Styx, Prometheus)
    """
    if not prospect_key:
        return None

    for campaign_id, info in CAMPAIGNS.items():
        for prefix in info['key_prefixes']:
            if prospect_key.startswith(prefix):
                return campaign_id

    key_lower = prospect_key.lower()
    if 'olympus' in key_lower:
        return 'quarrite'
    if 'styx' in key_lower:
        return 'gargantuan'
    if 'prometheus' in key_lower:
        return 'rimetusk'

    return None
