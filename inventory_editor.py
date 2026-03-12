#!/usr/bin/env python3
"""
Inventory Editor for Icarus Save Editor GUI

Wraps MetaInventory.json data with methods to read/write:
  - Item list (RowName, quantity, durability)
  - Repair items (restore durability to max)
  - Remove items
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# Max durability value used by the game (100% = 500000)
MAX_DURABILITY = 500_000


@dataclass
class InventoryItem:
    """Summary of a single MetaInventory item."""
    index: int
    row_name: str
    quantity: int
    durability: Optional[int]       # None if item has no durability
    max_durability: int = MAX_DURABILITY

    @property
    def durability_pct(self) -> Optional[float]:
        if self.durability is None:
            return None
        if self.max_durability <= 0:
            return 100.0
        return round(self.durability / self.max_durability * 100, 1)

    @property
    def display_name(self) -> str:
        """Human-readable name derived from RowName (strip prefix, format)."""
        name = self.row_name
        # Strip common prefixes
        for prefix in ('Meta_', 'Item_', 'D_'):
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        # Replace underscores with spaces
        return name.replace('_', ' ')


def _get_dynamic_prop(item: Dict, prop_type: str) -> Optional[int]:
    """Find a value in ItemDynamicData by PropertyType."""
    for entry in item.get('ItemDynamicData', []):
        if entry.get('PropertyType') == prop_type:
            return entry.get('Value')
    return None


def _set_dynamic_prop(item: Dict, prop_type: str, value: int) -> bool:
    """Set a value in ItemDynamicData by PropertyType. Returns True if found."""
    for entry in item.get('ItemDynamicData', []):
        if entry.get('PropertyType') == prop_type:
            entry['Value'] = value
            return True
    return False


class InventoryEditor:
    """
    Editor for MetaInventory.json.

    MetaInventory.json structure:
      {
        "InventoryID": "MetaInventoryID_Main",
        "Items": [
          {
            "ItemStaticData": {"RowName": "Meta_Bow_Shengong_Charlie", ...},
            "ItemDynamicData": [
              {"PropertyType": "ItemableStack", "Value": 1},
              {"PropertyType": "Durability", "Value": 450000},
              ...
            ],
            "DatabaseGUID": "...",
            ...
          },
          ...
        ]
      }
    """

    def __init__(self, data: Dict):
        self._data = data

    @property
    def _items_raw(self) -> List[Dict]:
        return self._data.get('Items', [])

    def get_items(self) -> List[InventoryItem]:
        """Return all items as InventoryItem summaries."""
        result = []
        for i, item in enumerate(self._items_raw):
            static = item.get('ItemStaticData', {})
            row_name = static.get('RowName', f'Item_{i}')
            quantity = _get_dynamic_prop(item, 'ItemableStack') or 1
            durability = _get_dynamic_prop(item, 'Durability')
            result.append(InventoryItem(
                index=i,
                row_name=row_name,
                quantity=quantity,
                durability=durability,
                max_durability=MAX_DURABILITY,
            ))
        return result

    def repair_item(self, index: int) -> bool:
        """Restore item at index to max durability. Returns True if item has durability."""
        items = self._items_raw
        if index < 0 or index >= len(items):
            return False
        return _set_dynamic_prop(items[index], 'Durability', MAX_DURABILITY)

    def repair_all(self) -> int:
        """Repair all items. Returns count of items repaired."""
        count = 0
        for item in self._items_raw:
            if _set_dynamic_prop(item, 'Durability', MAX_DURABILITY):
                count += 1
        return count

    def set_quantity(self, index: int, quantity: int) -> bool:
        """Set item stack quantity. Returns True if successful."""
        items = self._items_raw
        if index < 0 or index >= len(items):
            return False
        return _set_dynamic_prop(items[index], 'ItemableStack', max(1, quantity))

    def remove_item(self, index: int) -> bool:
        """Remove an item by index. Returns True if removed."""
        items = self._items_raw
        if index < 0 or index >= len(items):
            return False
        del items[index]
        return True

    def remove_items(self, indices: List[int]) -> int:
        """Remove multiple items by index (descending order to preserve indices)."""
        count = 0
        for i in sorted(set(indices), reverse=True):
            if self.remove_item(i):
                count += 1
        return count

    @property
    def item_count(self) -> int:
        return len(self._items_raw)
