"""Talents tab for the Icarus Save Editor GUI."""

from tkinter import simpledialog
from typing import List, Optional, Tuple

from game_data import (
    get_talent_catalog_for_subtree, find_talent_catalog_match,
    format_stats, TALENT_PREFIXES,
)
from GUI.tab_catalog_base import _CatalogTab


# Ordered list of (subtree_key, display_label) for the category panel
_SUBTREE_DISPLAY: List[Tuple[str, str]] = [
    ('sr', 'Survival / Resources'),
    ('se', 'Survival / Exploration'),
    ('sh', 'Survival / Hunting'),
    ('sc', 'Survival / Cook & Farm'),
    ('tr', 'Construction / Repairing'),
    ('tt', 'Construction / Tools'),
    ('tb', 'Construction / Building'),
    ('xb', 'Combat / Bows'),
    ('xs', 'Combat / Spears'),
    ('xx', 'Combat / Blades'),
    ('xf', 'Combat / Firearms'),
    ('za', 'Solo'),
]
_SUBTREE_KEY_FOR_LABEL = {label: key for key, label in _SUBTREE_DISPLAY}


class TalentsTab(_CatalogTab):

    def _category_labels(self) -> List[str]:
        return [label for _, label in _SUBTREE_DISPLAY]

    def _category_count(self, label: str) -> int:
        key = _SUBTREE_KEY_FOR_LABEL.get(label, '')
        return len(get_talent_catalog_for_subtree(key))

    def _unlocked_count(self, label: str) -> int:
        key = _SUBTREE_KEY_FOR_LABEL.get(label, '')
        if not key:
            return 0
        return sum(
            1 for rn in self._save_rownames
            if any(rn.startswith(p) for p, sk in TALENT_PREFIXES if sk == key)
        )

    def _load_catalog(self, label: str) -> list:
        key = _SUBTREE_KEY_FOR_LABEL.get(label, '')
        return get_talent_catalog_for_subtree(key)
        # items: (site_key, title, desc, stats_str)

    def _item_title(self, item) -> str:
        return item[1]  # title

    def _is_save_unlocked(self, item) -> Tuple[bool, Optional[str], int]:
        site_key, title, desc, stats_str = item
        subtree_key = _SUBTREE_KEY_FOR_LABEL.get(self._selected_category or '', '')
        if not subtree_key:
            return False, None, 0

        # Filter save RowNames to this subtree
        subtree_rns = [
            rn for rn in self._save_rownames
            if any(rn.startswith(p) for p, sk in TALENT_PREFIXES if sk == subtree_key)
        ]
        for rn in subtree_rns:
            match = find_talent_catalog_match(rn, subtree_key)
            if match and match.get('site_key') == site_key:
                for t in self.editor.get_talents():
                    if t.row_name == rn:
                        return True, rn, t.rank
                return True, rn, 1
        return False, None, 0

    def _detail_text(self, item, is_unlocked, save_rn, rank) -> dict:
        site_key, title, desc, stats_str = item
        subtree_key = _SUBTREE_KEY_FOR_LABEL.get(self._selected_category or '', '')

        if is_unlocked and save_rn:
            rn_display = save_rn
        else:
            rn_display = f"(unknown — enter manually)"

        stats_formatted = format_stats(stats_str)

        rank_info = ""
        if rank > 0 and stats_str:
            parts = stats_str.split(';')
            max_rank = len(parts) - 1
            rank_info = f"Rank {rank} / {max_rank}"

        return {
            'title':   title,
            'meta':    rank_info,
            'desc':    desc,
            'extra':   stats_formatted,
            'rowname': rn_display,
        }

    def _add_rowname(self, item) -> str:
        # Can't reliably derive RowName for talents — prompt user
        site_key, title, desc, stats_str = item
        guess = title.replace(' ', '_').replace("'", "")
        result = simpledialog.askstring(
            "Add Talent",
            f"Enter RowName for:\n'{title}'\n\n"
            f"Hint: check your save file for the exact name.\n"
            f"Best guess:",
            initialvalue=guess,
        )
        return result or ""

    def _toggle_selected(self):
        if self._selected_list_idx is None:
            return
        idx = self._selected_list_idx
        if idx >= len(self._list_indices):
            return
        item, is_unlocked, save_rn, rank = self._list_indices[idx]

        if is_unlocked:
            rn = save_rn or ""
            if not rn:
                return
            self.editor.remove_talent(rn)
            self._status.configure(text=f"Removed '{rn}'", text_color="#e09b3d")
        else:
            rn = self._add_rowname(item)
            if not rn:
                return
            self.editor.add_talent(rn, rank=1)
            self._status.configure(text=f"Added '{rn}'", text_color="#4ade80")

        self._save_rownames = {t.row_name for t in self.editor.get_talents()}
        self._render_list()
        self._rebuild_cat_panel()
