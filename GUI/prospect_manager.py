"""Shared prospect save state for ProspectInventory and Campaign tabs."""

from pathlib import Path
from typing import Callable, List, Optional

from save_manager import get_save_dir


class ProspectManager:
    """Manages the currently-loaded savegame.json path shared between tabs.

    Both ProspectInventoryTab and CampaignTab hold a reference to the same
    instance.  When either tab loads a file (via dropdown or Browse), it
    calls ``notify(path)`` which updates the stored path and fires every
    registered callback so the other tab can reload its own editor.
    """

    def __init__(self, steam_id: str):
        self._steam_id = steam_id
        self._path: Optional[str] = None
        self._callbacks: List[Callable[[str], None]] = []

    # ── Registration ─────────────────────────────────────────────────────────

    def register(self, callback: Callable[[str], None]) -> None:
        """Register a function to call whenever a new file is loaded.

        The callback receives the full file path as its only argument.
        """
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    # ── Prospects directory ───────────────────────────────────────────────────

    def get_prospects_dir(self) -> Optional[Path]:
        """Return the Prospects directory for the current steam_id, or None."""
        d = get_save_dir(self._steam_id) / "Prospects"
        return d if d.exists() else None

    def list_prospects(self) -> List[str]:
        """Return sorted list of .json filenames inside the Prospects folder."""
        d = self.get_prospects_dir()
        if not d:
            return []
        return sorted(f.name for f in d.glob("*.json"))

    def get_prospect_path(self, filename: str) -> str:
        """Return the full path string for a filename inside Prospects."""
        return str(get_save_dir(self._steam_id) / "Prospects" / filename)

    # ── Load notification ────────────────────────────────────────────────────

    def notify(self, path: str) -> None:
        """Record *path* as current and fire all registered callbacks."""
        self._path = path
        for cb in self._callbacks:
            try:
                cb(path)
            except Exception:
                pass  # individual tab errors must not stop other tabs

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def current_path(self) -> Optional[str]:
        return self._path

    @property
    def steam_id(self) -> str:
        return self._steam_id
