"""
Game item data loader for Icarus save editor.

Loads item metadata from extracted game data tables:
  - data/Items/D_ItemsStatic.json     (master item list + trait references)
  - data/Traits/D_Itemable.json       (display name, max stack, weight)
  - data/Traits/D_Durable.json        (max durability)
  - data/Items/D_ItemTemplate.json    (override stack sizes from crafting)

Provides:
  - load_item_catalog()  → dict of ItemInfo by row name
  - get_all_item_names() → sorted list of valid item row names
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')


@dataclass
class ItemInfo:
    """Metadata for a single game item."""
    row_name: str           # e.g. 'Fiber', 'Stone_Axe'
    display_name: str       # e.g. 'Fiber', 'Stone Axe'
    max_stack: int          # 1 for tools/weapons, 100-1000 for resources
    max_durability: int     # 0 if not durable
    has_durability: bool    # True if item has Durable trait
    has_inventory: bool     # True if item has InventoryContainer (attachments)
    inventory_container: str  # InventoryContainer RowName (e.g. 'Knife_Attachment')
    weight: int             # item weight (×10 internal units)
    tags: List[str]         # gameplay tags for categorization


def _extract_nsloctext(s: str) -> str:
    """Extract display string from NSLOCTEXT(...) format."""
    if not s or 'NSLOCTEXT' not in s:
        return s or ''
    parts = s.split('"')
    if len(parts) >= 6:
        return parts[5]
    return s


def load_item_catalog() -> Dict[str, ItemInfo]:
    """Load all item metadata from game data files. Returns dict keyed by row name."""

    # 1. Load D_ItemsStatic (master item list)
    static_path = os.path.join(_DATA_DIR, 'Items', 'D_ItemsStatic.json')
    with open(static_path, 'r', encoding='utf-8') as f:
        static_data = json.load(f)

    # 2. Load D_Itemable (display name, max stack, weight)
    itemable_path = os.path.join(_DATA_DIR, 'Traits', 'D_Itemable.json')
    with open(itemable_path, 'r', encoding='utf-8') as f:
        itemable_data = json.load(f)
    itemable_lookup: Dict[str, dict] = {r['Name']: r for r in itemable_data['Rows']}

    # 3. Load D_Durable (max durability)
    durable_path = os.path.join(_DATA_DIR, 'Traits', 'D_Durable.json')
    with open(durable_path, 'r', encoding='utf-8') as f:
        durable_data = json.load(f)
    durable_lookup: Dict[str, dict] = {r['Name']: r for r in durable_data['Rows']}
    durable_default_max = durable_data.get('Defaults', {}).get('Max_Durability', 100)

    # 4. Load D_ItemTemplate (override stack sizes)
    template_path = os.path.join(_DATA_DIR, 'Items', 'D_ItemTemplate.json')
    template_stacks: Dict[str, int] = {}
    if os.path.exists(template_path):
        with open(template_path, 'r', encoding='utf-8') as f:
            template_data = json.load(f)
        for row in template_data.get('Rows', []):
            for dyn in row.get('ItemDynamicData', []):
                if dyn.get('PropertyType') == 'ItemableStack':
                    template_stacks[row['Name']] = dyn['Value']

    # Build catalog
    catalog: Dict[str, ItemInfo] = {}

    for item_row in static_data['Rows']:
        row_name = item_row['Name']

        # Resolve Itemable reference
        itemable_rn = item_row.get('Itemable', {}).get('RowName', '')
        itemable_info = itemable_lookup.get(itemable_rn, {})

        display_name = _extract_nsloctext(itemable_info.get('DisplayName', ''))
        if not display_name:
            display_name = row_name.replace('_', ' ')

        max_stack = itemable_info.get('MaxStack', 1)

        # Override from template if present
        if row_name in template_stacks:
            max_stack = template_stacks[row_name]

        weight = itemable_info.get('Weight', 0)

        # Resolve Durable reference
        durable_rn = item_row.get('Durable', {}).get('RowName', '')
        has_durability = bool(durable_rn)
        max_durability = 0
        if durable_rn and durable_rn in durable_lookup:
            max_durability = durable_lookup[durable_rn].get('Max_Durability', durable_default_max)
        elif durable_rn:
            max_durability = durable_default_max

        # InventoryContainer (attachments / ammo slots)
        inv_container_rn = item_row.get('InventoryContainer', {}).get('RowName', '')
        has_inventory = bool(inv_container_rn)

        # Tags
        tags = []
        for tag_entry in item_row.get('Manual_Tags', {}).get('GameplayTags', []):
            tags.append(tag_entry.get('TagName', ''))

        catalog[row_name] = ItemInfo(
            row_name=row_name,
            display_name=display_name,
            max_stack=max_stack,
            max_durability=max_durability,
            has_durability=has_durability,
            has_inventory=has_inventory,
            inventory_container=inv_container_rn,
            weight=weight,
            tags=tags,
        )

    return catalog


def get_all_item_names(catalog: Optional[Dict[str, ItemInfo]] = None) -> List[str]:
    """Return sorted list of all valid item row names."""
    if catalog is None:
        catalog = load_item_catalog()
    return sorted(catalog.keys())


# Singleton cache
_catalog_cache: Optional[Dict[str, ItemInfo]] = None

def get_catalog() -> Dict[str, ItemInfo]:
    """Get or load the item catalog (cached singleton)."""
    global _catalog_cache
    if _catalog_cache is None:
        _catalog_cache = load_item_catalog()
    return _catalog_cache
