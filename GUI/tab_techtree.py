"""Tech Tree tab for the Icarus Save Editor GUI."""

from typing import Optional, Tuple

from character_editor import CharacterEditor
from game_data import (
    get_tech_catalog_for_tier, rowname_matches_catalog, get_tech_tier_labels,
)
from GUI.tab_catalog_base import _CatalogTab


class TechTreeTab(_CatalogTab):

    def _category_labels(self):
        return get_tech_tier_labels()

    def _category_count(self, label: str) -> int:
        return len(get_tech_catalog_for_tier(label))

    def _unlocked_count(self, label: str) -> int:
        catalog = get_tech_catalog_for_tier(label)
        return sum(1 for item in catalog
                   if any(rowname_matches_catalog(rn, item[1])
                          for rn in self._save_rownames))

    def _load_catalog(self, label: str) -> list:
        return get_tech_catalog_for_tier(label)
        # items: (site_key, row_name, title, desc, flavor)

    def _item_title(self, item) -> str:
        return item[2]  # title

    def _is_save_unlocked(self, item) -> Tuple[bool, Optional[str], int]:
        catalog_rn = item[1]
        for rn in self._save_rownames:
            if rowname_matches_catalog(rn, catalog_rn):
                return True, rn, 1
        return False, None, 0

    def _detail_text(self, item, is_unlocked, save_rn, rank) -> dict:
        site_key, catalog_rn, title, desc, flavor = item
        rn_display = save_rn if save_rn else catalog_rn
        return {
            'title':   title,
            'meta':    f"Site key: {site_key}",
            'desc':    desc,
            'extra':   flavor,
            'rowname': rn_display,
        }

    def _add_rowname(self, item) -> str:
        return item[1]  # catalog_row_name (title.replace(' ', '_'))
