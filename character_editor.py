#!/usr/bin/env python3
"""
Character Editor for Icarus Save Editor GUI

Wraps Characters.json data with methods to read/write:
  - XP and XP Debt
  - Dead / Abandoned status
  - Tech Tree (Talents array: RowName + Rank)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TalentEntry:
    """A single tech tree / talent unlock."""
    row_name: str
    rank: int = 1


class CharacterEditor:
    """
    Editor for a single character's data (from Characters.json).

    Characters.json is double-wrapped: the outer JSON has key "Characters.json"
    whose value is a JSON string. SaveManager handles the unwrapping; this class
    receives the inner dict directly.

    The inner data is a list of character objects (one per character slot).
    This editor operates on one character at a time (by ChrSlot or list index).
    """

    def __init__(self, data: Any):
        """
        Args:
            data: Unwrapped Characters.json data. May be a list of characters
                  or a single character dict depending on game version.
        """
        # Normalise: always work with a list
        if isinstance(data, list):
            self._characters: List[Dict] = data
        elif isinstance(data, dict):
            # Some versions store a single character at top level
            self._characters = [data]
        else:
            self._characters = []

        self._current_index: int = 0

    # ------------------------------------------------------------------
    # Character selection
    # ------------------------------------------------------------------

    @property
    def character_count(self) -> int:
        return len(self._characters)

    def get_character_names(self) -> List[str]:
        """Return display names for all characters."""
        names = []
        for i, c in enumerate(self._characters):
            name = c.get('CharacterName', f'Character {i}')
            slot = c.get('ChrSlot', i)
            names.append(f"[{slot}] {name}")
        return names

    def select(self, index: int) -> None:
        """Select character by list index."""
        if 0 <= index < len(self._characters):
            self._current_index = index

    @property
    def _char(self) -> Dict:
        if not self._characters:
            return {}
        return self._characters[self._current_index]

    # ------------------------------------------------------------------
    # Basic stats
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._char.get('CharacterName', '')

    @property
    def xp(self) -> int:
        return self._char.get('XP', 0)

    @xp.setter
    def xp(self, value: int) -> None:
        self._char['XP'] = max(0, int(value))

    @property
    def xp_debt(self) -> int:
        return self._char.get('XP_Debt', 0)

    @xp_debt.setter
    def xp_debt(self, value: int) -> None:
        self._char['XP_Debt'] = max(0, int(value))

    @property
    def is_dead(self) -> bool:
        return bool(self._char.get('IsDead', False))

    @is_dead.setter
    def is_dead(self, value: bool) -> None:
        self._char['IsDead'] = bool(value)

    @property
    def is_abandoned(self) -> bool:
        return bool(self._char.get('IsAbandoned', False))

    @is_abandoned.setter
    def is_abandoned(self, value: bool) -> None:
        self._char['IsAbandoned'] = bool(value)

    # ------------------------------------------------------------------
    # Tech Tree (Talents)
    # ------------------------------------------------------------------

    def get_talents(self) -> List[TalentEntry]:
        """Return all unlocked tech tree talents."""
        raw = self._char.get('Talents', [])
        result = []
        for entry in raw:
            if isinstance(entry, dict):
                row = entry.get('RowName', '')
                rank = entry.get('Rank', 1)
                if row:
                    result.append(TalentEntry(row_name=row, rank=rank))
        return result

    def set_talents(self, talents: List[TalentEntry]) -> None:
        """Replace the entire talents list."""
        self._char['Talents'] = [
            {'RowName': t.row_name, 'Rank': t.rank} for t in talents
        ]

    def add_talent(self, row_name: str, rank: int = 1) -> bool:
        """
        Add or update a talent.

        Returns True if added, False if updated existing.
        """
        talents = self._char.setdefault('Talents', [])
        for entry in talents:
            if entry.get('RowName') == row_name:
                entry['Rank'] = rank
                return False
        talents.append({'RowName': row_name, 'Rank': rank})
        return True

    def remove_talent(self, row_name: str) -> bool:
        """Remove a talent by RowName. Returns True if found and removed."""
        talents = self._char.get('Talents', [])
        original_len = len(talents)
        self._char['Talents'] = [
            t for t in talents if t.get('RowName') != row_name
        ]
        return len(self._char['Talents']) < original_len

    def has_talent(self, row_name: str) -> bool:
        return any(t.get('RowName') == row_name for t in self._char.get('Talents', []))

    def get_talent_rank(self, row_name: str) -> Optional[int]:
        for t in self._char.get('Talents', []):
            if t.get('RowName') == row_name:
                return t.get('Rank', 1)
        return None

    def unlock_all_talents(self, known_talents: List[str]) -> int:
        """Unlock all talents from a known list. Returns count added."""
        added = 0
        for row_name in known_talents:
            if self.add_talent(row_name, rank=1):
                added += 1
        return added

    def clear_all_talents(self) -> int:
        """Remove all talents. Returns count removed."""
        count = len(self._char.get('Talents', []))
        self._char['Talents'] = []
        return count

    # ------------------------------------------------------------------
    # Raw data access (for SaveManager)
    # ------------------------------------------------------------------

    def get_raw_data(self) -> Any:
        """Return the underlying data structure (for saving)."""
        return self._characters
