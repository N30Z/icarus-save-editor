#!/usr/bin/env python3
"""
Save Manager for Icarus Save Editor GUI

Handles discovery, loading, saving, and backup of all Icarus save files:
  - Mounts.json       (via MountEditor)
  - Characters.json   (double-wrapped JSON)
  - Profile.json      (standard JSON)
  - MetaInventory.json (standard JSON)
"""

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PLAYER_DATA_PATH = Path(os.path.expandvars(r'%LOCALAPPDATA%\Icarus\Saved\PlayerData'))

SAVE_FILES = ['Mounts.json', 'Characters.json', 'Profile.json', 'MetaInventory.json']

# Files that use double-wrapped JSON (outer JSON contains a key whose value is a JSON string)
DOUBLE_WRAPPED = {'Characters.json', 'AssociatedProspects_Slot_0.json'}


def find_steam_ids() -> List[str]:
    """Find all Steam ID directories in the Icarus PlayerData folder."""
    if not PLAYER_DATA_PATH.exists():
        return []
    return [
        d.name for d in PLAYER_DATA_PATH.iterdir()
        if d.is_dir() and d.name.isdigit()
    ]


def get_save_dir(steam_id: str) -> Path:
    """Get the save directory for a given Steam ID."""
    return PLAYER_DATA_PATH / steam_id


def load_json(path: Path) -> Any:
    """Load a JSON file, handling double-wrapped format if needed.

    Characters.json uses a double-wrapped list format:
      {"Characters.json": ["{...char json...}", "{...char json...}"]}
    Each element in the list is a JSON-serialized character dict.
    We parse them and return a plain list of dicts.
    """
    with open(path, 'r', encoding='utf-8') as f:
        outer = json.load(f)

    if path.name in DOUBLE_WRAPPED:
        key = path.name
        if key in outer:
            inner = outer[key]
            # List of JSON strings (one per character / slot)
            if isinstance(inner, list):
                return [json.loads(item) if isinstance(item, str) else item
                        for item in inner]
            # Single JSON string (older format)
            if isinstance(inner, str):
                parsed = json.loads(inner)
                return parsed if isinstance(parsed, list) else [parsed]
        return outer

    return outer


def save_json(path: Path, data: Any, backup: bool = True) -> Optional[Path]:
    """
    Save data to a JSON file, optionally creating a backup first.

    For double-wrapped files (Characters.json), re-wraps each character
    dict back into a JSON string inside the outer list.

    Returns the backup path if created, else None.
    """
    backup_path = None
    if backup and path.exists():
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = path.with_suffix(f'.backup_{timestamp}.json')
        shutil.copy(path, backup_path)

    if path.name in DOUBLE_WRAPPED:
        # Re-wrap: each character dict becomes a compact JSON string
        chars = data if isinstance(data, list) else [data]
        inner_list = [json.dumps(c, separators=(',', ':')) for c in chars]
        outer = {path.name: inner_list}
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(outer, f, indent='\t')
    else:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent='\t')

    return backup_path


class SaveManager:
    """
    Central manager for all Icarus save files.

    Owns the raw data for Characters.json, Profile.json, MetaInventory.json.
    MountEditor owns its own Mounts.json data.
    """

    def __init__(self, steam_id: str):
        self.steam_id = steam_id
        self.save_dir = get_save_dir(steam_id)

        self.characters_data: Optional[Any] = None
        self.profile_data: Optional[Dict] = None
        self.inventory_data: Optional[Dict] = None

        self._loaded = False

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def path(self, filename: str) -> Path:
        return self.save_dir / filename

    def load_all(self) -> List[str]:
        """
        Load all supported save files.

        Returns a list of warnings (files that couldn't be loaded).
        """
        warnings = []

        for filename in ('Characters.json', 'Profile.json', 'MetaInventory.json'):
            p = self.path(filename)
            try:
                data = load_json(p)
                if filename == 'Characters.json':
                    self.characters_data = data
                elif filename == 'Profile.json':
                    self.profile_data = data
                elif filename == 'MetaInventory.json':
                    self.inventory_data = data
            except FileNotFoundError:
                warnings.append(f"{filename} not found")
            except (json.JSONDecodeError, KeyError) as e:
                warnings.append(f"{filename} parse error: {e}")

        self._loaded = True
        return warnings

    def save_all(self, backup: bool = True) -> List[Tuple[str, str]]:
        """
        Save all loaded data back to disk.

        Returns list of (filename, backup_path_or_empty) tuples.
        """
        results = []

        saves = [
            ('Characters.json', self.characters_data),
            ('Profile.json', self.profile_data),
            ('MetaInventory.json', self.inventory_data),
        ]

        for filename, data in saves:
            if data is None:
                continue
            p = self.path(filename)
            backup_path = save_json(p, data, backup=backup)
            results.append((filename, str(backup_path) if backup_path else ''))

        return results

    def save_file(self, filename: str, backup: bool = True) -> Optional[str]:
        """Save a single file by name."""
        data_map = {
            'Characters.json': self.characters_data,
            'Profile.json': self.profile_data,
            'MetaInventory.json': self.inventory_data,
        }
        data = data_map.get(filename)
        if data is None:
            return None
        p = self.path(filename)
        backup_path = save_json(p, data, backup=backup)
        return str(backup_path) if backup_path else ''
