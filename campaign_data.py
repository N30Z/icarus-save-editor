"""
Campaign mission definitions loaded from data/GreatHunt/D_GreatHunts.json.
Regular prospect mission definitions loaded from data/Prospects/D_ProspectList.json.

Provides the three Great Hunt campaigns, a helper to detect which campaign
a GD.json prospect save belongs to, and grouped regular prospect missions.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Optional

_DATA_PATH = Path(__file__).parent / "data" / "GreatHunt" / "D_GreatHunts.json"
_PROSPECT_LIST_PATH = Path(__file__).parent / "data" / "Prospects" / "D_ProspectList.json"

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

# Regular (non-campaign) prospect missions grouped by map.
# Each group: {'name': str, 'color': str, 'missions': [{'row_name': str, 'label': str}, ...]}
# Populated by _load_prospects() at import time.
REGULAR_MISSION_GROUPS: List[Dict] = []


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
    _PREFIX_TO_MAP: Dict[str, str] = {
        'Tier':     'Olympus',
        'OLY_':     'Olympus',
        'STYX_':    'Styx',
        'PRO_':     'Prometheus',
        'ELY_':     'Elysium',
    }

    # Build display name lookup and collect regular missions
    _groups: Dict[str, List[Dict]] = {m: [] for m in _MAP_GROUPS_ORDER}

    for row in data['Rows']:
        name: str = row['Name']
        drop_name = _extract_loctext(row.get('DropName', name))
        PROSPECT_DISPLAY_NAMES[name] = drop_name

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
            'row_name': name,
            'label':    drop_name,
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

        CAMPAIGNS[campaign_id]['missions'].append({
            'row_name': row_name,          # talent key, e.g. GH_RG_A
            'name':     row['Name'],       # e.g. Rock_Golem_A
            'label':    label,             # e.g. MISSING MINERS
            'type':     row.get('Type', 'Standard'),
            'forbidden': forbidden,
        })


# Run at import time — prospect list first so campaign labels can use it.
_load_prospects()
_load()


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

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
