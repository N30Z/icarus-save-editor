"""
Campaign mission definitions loaded from data/GreatHunt/D_GreatHunts.json.

Provides the three Great Hunt campaigns and a helper to detect which campaign
a GD.json prospect save belongs to.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

_DATA_PATH = Path(__file__).parent / "data" / "GreatHunt" / "D_GreatHunts.json"

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


def _format_label(name: str) -> str:
    """'Rock_Golem_C2' → 'Rock Golem C2'"""
    return name.replace('_', ' ')


def _load() -> None:
    with open(_DATA_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for row in data['Rows']:
        hunt_key = row['Hunt']['RowName']
        campaign_id = _HUNT_TO_CAMPAIGN.get(hunt_key)
        if campaign_id is None:
            continue

        forbidden = [ft['RowName'] for ft in row.get('ForbiddenTalent', [])]

        CAMPAIGNS[campaign_id]['missions'].append({
            'row_name': row['Prospect']['RowName'],          # talent key, e.g. GH_RG_A
            'name':     row['Name'],                          # e.g. Rock_Golem_A
            'label':    _format_label(row['Name']),           # e.g. Rock Golem A
            'type':     row.get('Type', 'Standard'),          # Standard/Choice/Optional/Final
            'forbidden': forbidden,                           # mutually-exclusive talent keys
        })


_load()


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
