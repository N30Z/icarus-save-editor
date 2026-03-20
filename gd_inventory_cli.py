#!/usr/bin/env python3
"""
GD.json Inventory Editor — Command-Line Interface

An independent editor for player inventories stored in a GD.json prospect save.
GD.json is located separately from Mounts.json and contains the full world state.

Usage:
    python gd_inventory_cli.py <GD.json> <command> [options]

Commands:
    list                         List all players and their item counts
    inventory <steam_id>         Show all inventories for a player
    items <steam_id> [inv_id]    Show items (optionally filtered by inventory ID)

    set <steam_id> <inv_id> <slot> <item> [count] [durability]
                                 Place or update an item in a slot

    add <steam_id> <inv_id> <item> [count] [durability]
                                 Add item to the next free slot

    remove <steam_id> <inv_id> <slot>
                                 Remove item from a slot

    clear <steam_id> <inv_id>    Remove ALL items from an inventory

    fill <steam_id> <inv_id> <item> [count] [start_slot] [num_slots]
                                 Fill consecutive empty slots with an item

Examples:
    # List all players
    python gd_inventory_cli.py GD.json list

    # Show backpack items for a player
    python gd_inventory_cli.py GD.json items 76561198116205199 3

    # Add 500 iron ingots to backpack slot 10
    python gd_inventory_cli.py GD.json set 76561198116205199 3 10 Iron_Ingot 500

    # Add item to first available slot
    python gd_inventory_cli.py GD.json add 76561198116205199 3 Iron_Ingot 200

    # Remove item from slot 10
    python gd_inventory_cli.py GD.json remove 76561198116205199 3 10

    # Clear the entire backpack
    python gd_inventory_cli.py GD.json clear 76561198116205199 3

Inventory IDs:
    2  = Equipment / Hotbar
    3  = Backpack (main inventory)
    4  = Belt
    5  = Armor / Cosmetics
"""

import sys
import os
import argparse

from gd_inventory_editor import GdInventoryEditor, INVENTORY_NAMES


def _fmt_inv(inv_id: int) -> str:
    return f"{inv_id} ({INVENTORY_NAMES.get(inv_id, '?')})"


def cmd_list(editor: GdInventoryEditor, args) -> None:
    players = editor.list_players()
    if not players:
        print("No players found in save.")
        return
    for p in players:
        inv_str = ", ".join(
            f"inv{iid}:{cnt}" for iid, cnt in sorted(p['inventories'].items())
        )
        print(f"  {p['steam_id']}  slot={p['char_slot']}  [{inv_str}]")


def cmd_inventory(editor: GdInventoryEditor, args) -> None:
    steam_id = args.steam_id
    invs = editor.get_inventories(steam_id)
    if not invs:
        print(f"No inventories found for {steam_id}")
        return
    print(f"Inventories for {steam_id}:")
    for inv in invs:
        print(f"  ID {inv['id']:2d}  {inv['name']:<22}  {inv['slot_count']} slots occupied")


def cmd_items(editor: GdInventoryEditor, args) -> None:
    steam_id = args.steam_id
    inv_id   = getattr(args, 'inv_id', None)

    items = editor.get_items(steam_id, inv_id)
    if not items:
        print("No items found.")
        return

    # Group by inventory
    by_inv: dict = {}
    for item in items:
        by_inv.setdefault(item['inv_id'], []).append(item)

    for iid, iitems in sorted(by_inv.items()):
        print(f"\n  {'-'*55}")
        print(f"  Inventory {_fmt_inv(iid)}")
        print(f"  {'-'*55}")
        print(f"  {'Slot':>4}  {'Item':<35}  {'Count':>6}  {'Durability':>10}")
        print(f"  {'-'*55}")
        for it in sorted(iitems, key=lambda x: x['location'] or 0):
            count_s = str(it['count']) if it['count'] is not None else "-"
            dur_s   = str(it['durability']) if it['durability'] is not None else "-"
            print(f"  {it['location']:>4}  {it['item']:<35}  {count_s:>6}  {dur_s:>10}")
    print()


def cmd_set(editor: GdInventoryEditor, args) -> None:
    editor.set_item(
        steam_id   = args.steam_id,
        inv_id     = args.inv_id,
        location   = args.slot,
        item_name  = args.item,
        count      = args.count,
        durability = args.durability,
    )
    dur_str = f"  durability={args.durability}" if args.durability is not None else ""
    print(f"Set slot {args.slot} in inventory {_fmt_inv(args.inv_id)}: "
          f"{args.item} x{args.count}{dur_str}")
    editor.save(backup=args.no_backup is False)


def cmd_add(editor: GdInventoryEditor, args) -> None:
    """Add item to the first free slot in the inventory."""
    steam_id = args.steam_id
    inv_id   = args.inv_id

    # Find occupied slot locations
    items = editor.get_items(steam_id, inv_id)
    used  = {it['location'] for it in items}

    # Find first free slot starting from 0
    slot = 0
    while slot in used:
        slot += 1

    editor.set_item(
        steam_id   = steam_id,
        inv_id     = inv_id,
        location   = slot,
        item_name  = args.item,
        count      = args.count,
        durability = args.durability,
    )
    print(f"Added {args.item} x{args.count} to slot {slot} in inventory {_fmt_inv(inv_id)}")
    editor.save(backup=args.no_backup is False)


def cmd_remove(editor: GdInventoryEditor, args) -> None:
    removed = editor.remove_item(args.steam_id, args.inv_id, args.slot)
    if removed:
        print(f"Removed item from slot {args.slot} in inventory {_fmt_inv(args.inv_id)}")
        editor.save(backup=args.no_backup is False)
    else:
        print(f"Slot {args.slot} in inventory {args.inv_id} was already empty.")


def cmd_clear(editor: GdInventoryEditor, args) -> None:
    removed = editor.clear_inventory(args.steam_id, args.inv_id)
    if removed:
        print(f"Cleared {removed} items from inventory {_fmt_inv(args.inv_id)}")
        editor.save(backup=args.no_backup is False)
    else:
        print(f"Inventory {args.inv_id} was already empty.")


def cmd_fill(editor: GdInventoryEditor, args) -> None:
    """Fill consecutive slots with an item."""
    steam_id   = args.steam_id
    inv_id     = args.inv_id
    item       = args.item
    count      = args.count
    start      = getattr(args, 'start_slot', 0) or 0
    num        = getattr(args, 'num_slots', 10) or 10

    for slot in range(start, start + num):
        editor.set_item(steam_id, inv_id, slot, item, count, args.durability)
    print(f"Filled slots {start}–{start+num-1} with {item} x{count}")
    editor.save(backup=args.no_backup is False)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='gd_inventory_cli.py',
        description='Icarus GD.json inventory editor',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument('gd_file', help='Path to GD.json')
    p.add_argument('--no-backup', action='store_true',
                   help='Skip creating a .backup file before saving')

    sub = p.add_subparsers(dest='command')

    # list
    sub.add_parser('list', help='List all players')

    # inventory
    inv_p = sub.add_parser('inventory', help='Show inventories for a player')
    inv_p.add_argument('steam_id')

    # items
    items_p = sub.add_parser('items', help='Show items for a player')
    items_p.add_argument('steam_id')
    items_p.add_argument('inv_id', type=int, nargs='?',
                         help='Inventory ID to filter (omit for all)')

    # set
    set_p = sub.add_parser('set', help='Set or update an item in a slot')
    set_p.add_argument('steam_id')
    set_p.add_argument('inv_id',    type=int)
    set_p.add_argument('slot',      type=int, help='Slot location index')
    set_p.add_argument('item',      help='Item row name, e.g. Iron_Ingot')
    set_p.add_argument('count',     type=int, nargs='?', default=1)
    set_p.add_argument('durability',type=int, nargs='?', default=None)

    # add
    add_p = sub.add_parser('add', help='Add item to first free slot')
    add_p.add_argument('steam_id')
    add_p.add_argument('inv_id',    type=int)
    add_p.add_argument('item',      help='Item row name')
    add_p.add_argument('count',     type=int, nargs='?', default=1)
    add_p.add_argument('durability',type=int, nargs='?', default=None)

    # remove
    rem_p = sub.add_parser('remove', help='Remove item from a slot')
    rem_p.add_argument('steam_id')
    rem_p.add_argument('inv_id',    type=int)
    rem_p.add_argument('slot',      type=int)

    # clear
    clr_p = sub.add_parser('clear', help='Clear all items from an inventory')
    clr_p.add_argument('steam_id')
    clr_p.add_argument('inv_id',    type=int)

    # fill
    fill_p = sub.add_parser('fill', help='Fill consecutive slots with an item')
    fill_p.add_argument('steam_id')
    fill_p.add_argument('inv_id',      type=int)
    fill_p.add_argument('item',        help='Item row name')
    fill_p.add_argument('count',       type=int, nargs='?', default=1)
    fill_p.add_argument('start_slot',  type=int, nargs='?', default=0)
    fill_p.add_argument('num_slots',   type=int, nargs='?', default=10)
    fill_p.add_argument('--durability',type=int, default=None,
                        help='Durability value for tool/weapon items')

    return p


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

COMMANDS = {
    'list':      cmd_list,
    'inventory': cmd_inventory,
    'items':     cmd_items,
    'set':       cmd_set,
    'add':       cmd_add,
    'remove':    cmd_remove,
    'clear':     cmd_clear,
    'fill':      cmd_fill,
}


def main() -> None:
    parser = build_parser()
    args   = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    gd_path = args.gd_file
    if not os.path.isfile(gd_path):
        print(f"Error: file not found: {gd_path}", file=sys.stderr)
        sys.exit(1)

    print(f"[+] Loading {gd_path} …")
    editor = GdInventoryEditor(gd_path)
    editor.load()
    print(f"    {len(editor.players)} player(s) found")

    fn = COMMANDS.get(args.command)
    if fn:
        fn(editor, args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
