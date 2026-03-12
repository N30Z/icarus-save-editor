#!/usr/bin/env python3
"""
Profile Editor for Icarus Save Editor GUI

Wraps Profile.json data with methods to read/write:
  - MetaResources: Credits, Exotics (Exotic1), Refund Tokens (Refund), Licences (Licence)
  - Workshop Unlocks (Talents array in Profile.json)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


# MetaRow keys used in Profile.json MetaResources array
RESOURCE_KEYS = {
    'Credits':  'Credits',
    'Exotics':  'Exotic1',
    'Refunds':  'Refund',
    'Licences': 'Licence',
}


@dataclass
class WorkshopEntry:
    """A single workshop unlock."""
    row_name: str
    rank: int = 1


class ProfileEditor:
    """
    Editor for Profile.json.

    Profile.json is standard (not double-wrapped) JSON with structure:
      {
        "UserID": "...",
        "MetaResources": [{"MetaRow": "Credits", "Count": 0}, ...],
        "Talents": [{"RowName": "Workshop_Envirosuit", "Rank": 1}, ...],
        "UnlockedFlags": [...],
        "NextChrSlot": 1,
        "DataVersion": 4
      }
    """

    def __init__(self, data: Dict):
        self._data = data

    # ------------------------------------------------------------------
    # MetaResources
    # ------------------------------------------------------------------

    def _find_resource(self, meta_row: str) -> Optional[Dict]:
        for entry in self._data.get('MetaResources', []):
            if entry.get('MetaRow') == meta_row:
                return entry
        return None

    def get_resource(self, label: str) -> int:
        """Get resource count by label (Credits, Exotics, Refunds, Licences)."""
        meta_row = RESOURCE_KEYS.get(label, label)
        entry = self._find_resource(meta_row)
        return entry.get('Count', 0) if entry else 0

    def set_resource(self, label: str, count: int) -> None:
        """Set resource count by label. Creates the entry if it doesn't exist."""
        meta_row = RESOURCE_KEYS.get(label, label)
        entry = self._find_resource(meta_row)
        if entry is not None:
            entry['Count'] = max(0, int(count))
        else:
            self._data.setdefault('MetaResources', []).append({
                'MetaRow': meta_row,
                'Count': max(0, int(count))
            })

    def get_all_resources(self) -> Dict[str, int]:
        """Return all resource counts keyed by label."""
        return {label: self.get_resource(label) for label in RESOURCE_KEYS}

    # ------------------------------------------------------------------
    # Workshop Unlocks (Profile Talents)
    # ------------------------------------------------------------------

    def get_workshop_unlocks(self) -> List[WorkshopEntry]:
        """Return all workshop unlocks."""
        result = []
        for entry in self._data.get('Talents', []):
            if isinstance(entry, dict):
                row = entry.get('RowName', '')
                rank = entry.get('Rank', 1)
                if row:
                    result.append(WorkshopEntry(row_name=row, rank=rank))
        return result

    def has_workshop_unlock(self, row_name: str) -> bool:
        return any(
            t.get('RowName') == row_name
            for t in self._data.get('Talents', [])
        )

    def add_workshop_unlock(self, row_name: str, rank: int = 1) -> bool:
        """Add a workshop unlock. Returns True if added, False if already present."""
        if self.has_workshop_unlock(row_name):
            return False
        self._data.setdefault('Talents', []).append({'RowName': row_name, 'Rank': rank})
        return True

    def remove_workshop_unlock(self, row_name: str) -> bool:
        """Remove a workshop unlock. Returns True if found and removed."""
        talents = self._data.get('Talents', [])
        original_len = len(talents)
        self._data['Talents'] = [
            t for t in talents if t.get('RowName') != row_name
        ]
        return len(self._data['Talents']) < original_len

    def set_workshop_unlocks(self, entries: List[WorkshopEntry]) -> None:
        """Replace the entire workshop unlock list."""
        self._data['Talents'] = [
            {'RowName': e.row_name, 'Rank': e.rank} for e in entries
        ]

    def clear_workshop_unlocks(self) -> int:
        """Remove all workshop unlocks. Returns count removed."""
        count = len(self._data.get('Talents', []))
        self._data['Talents'] = []
        return count
