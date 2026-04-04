"""Prospect Inventory tab for the Icarus Save Editor GUI."""

import json
import tkinter as tk
from tkinter import messagebox, filedialog
from typing import Dict, List, Optional

import customtkinter as ctk

from gd_inventory_editor import (GdInventoryEditor, INVENTORY_NAMES,
                                  _get_dyn_value, DYN_DURABILITY, DYN_STACK_COUNT,
                                  DYN_MAX_STACK, DYN_LINKED_INV, DYN_FILL_AMOUNT)
from game_items import get_catalog, ItemInfo
from GUI.constants import FONT_TITLE, FONT_NORMAL, FONT_SMALL, FONT_MONO, FONT_HEADER
from GUI.prospect_manager import ProspectManager


# Inventory slot counts per ID (base game defaults)
_INV_SLOT_COUNTS = {
    2: 12,   # Equipment/Hotbar
    3: 24,   # Backpack (can vary with backpack item)
    4: 4,    # Belt
    5: 10,   # Armor/Cosmetics
    11: 1,
    12: 1,
}

# Minimum search length for item dropdown
_MIN_SEARCH_LEN = 3


class _ItemSearchPopup(ctk.CTkToplevel):
    """Dropdown-style popup with a search bar for selecting items.

    Only shows results when the search bar has >= 3 characters.
    """

    def __init__(self, parent, catalog: Dict[str, ItemInfo],
                 callback, x: int, y: int):
        super().__init__(parent)
        self.catalog = catalog
        self.callback = callback
        self._sorted_names = sorted(catalog.keys())

        self.title("Select Item")
        self.geometry(f"460x420+{x}+{y}")
        self.resizable(False, True)
        self.transient(parent)
        self.grab_set()

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # Search entry
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter())
        search = ctk.CTkEntry(self, textvariable=self._search_var,
                              placeholder_text="Type at least 3 letters to search…",
                              font=FONT_NORMAL)
        search.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        search.focus_set()

        # Results listbox
        lf = ctk.CTkFrame(self)
        lf.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 4))
        lf.rowconfigure(0, weight=1)
        lf.columnconfigure(0, weight=1)

        self._listbox = tk.Listbox(
            lf, bg="#1e1e1e", fg="#d0d0d0", selectbackground="#1f4f8a",
            selectforeground="white", font=FONT_MONO,
            bd=0, highlightthickness=0, relief="flat", activestyle="none",
        )
        self._listbox.grid(row=0, column=0, sticky="nsew")
        sb = tk.Scrollbar(lf, orient="vertical", command=self._listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self._listbox.configure(yscrollcommand=sb.set)
        self._listbox.bind("<Double-Button-1>", self._on_select)
        self._listbox.bind("<Return>", self._on_select)

        # Info label
        self._info = ctk.CTkLabel(self, text="", font=FONT_SMALL,
                                   text_color="gray", anchor="w")
        self._info.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 4))

        # Select button
        ctk.CTkButton(self, text="Select", command=self._on_select).grid(
            row=3, column=0, padx=8, pady=(0, 8), sticky="ew")

        self._visible_names: List[str] = []
        self._filter()

        # Close on Escape
        self.bind("<Escape>", lambda _: self.destroy())

    def _filter(self):
        q = self._search_var.get().strip()
        self._listbox.delete(0, tk.END)
        self._visible_names.clear()

        if len(q) < _MIN_SEARCH_LEN:
            self._info.configure(text=f"Type at least {_MIN_SEARCH_LEN} characters…")
            return

        q_lower = q.lower()
        for name in self._sorted_names:
            info = self.catalog[name]
            # Search in both row name and display name
            if q_lower in name.lower() or q_lower in info.display_name.lower():
                stack_str = f"x{info.max_stack}" if info.max_stack > 1 else ""
                dur_str = f" Dur:{info.max_durability}" if info.has_durability else ""
                self._listbox.insert(tk.END,
                    f"{info.display_name:<30} {stack_str:>6}{dur_str}")
                self._visible_names.append(name)

        self._info.configure(text=f"{len(self._visible_names)} matches")

    def _on_select(self, _event=None):
        sel = self._listbox.curselection()
        if not sel or sel[0] >= len(self._visible_names):
            return
        name = self._visible_names[sel[0]]
        self.callback(name)
        self.destroy()


class ProspectInventoryTab(ctk.CTkFrame):
    """GUI tab for editing player inventories in a savegame.json prospect save."""

    def __init__(self, master, prospect_manager: ProspectManager, **kwargs):
        super().__init__(master, **kwargs)
        self._manager = prospect_manager
        self._manager.register(self._on_manager_load)

        self._gd_editor: Optional[GdInventoryEditor] = None
        self._catalog: Dict[str, ItemInfo] = {}
        self._current_steam_id: Optional[str] = None
        self._current_inv_id: Optional[int] = None
        self._items: List[dict] = []       # items from get_items()
        self._slot_widgets: list = []      # slot frame widgets for the grid
        self._selected_slot_idx: Optional[int] = None  # index into _items

        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # ── Top bar: player/inventory selectors ──
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        top.columnconfigure(3, weight=1)

        ctk.CTkLabel(top, text="Prospect Inventory", font=FONT_TITLE).grid(
            row=0, column=0, sticky="w", padx=(0, 12))

        # Player selector
        ctk.CTkLabel(top, text="Player:", font=FONT_NORMAL).grid(
            row=0, column=1, padx=(16, 4))
        self._player_var = ctk.StringVar(value="–")
        self._player_menu = ctk.CTkOptionMenu(top, variable=self._player_var,
                                               values=["–"], font=FONT_SMALL,
                                               command=self._on_player_change, width=180)
        self._player_menu.grid(row=0, column=2, padx=4)

        # Inventory selector
        ctk.CTkLabel(top, text="Inventory:", font=FONT_NORMAL).grid(
            row=0, column=4, padx=(12, 4))
        self._inv_var = ctk.StringVar(value="–")
        self._inv_menu = ctk.CTkOptionMenu(top, variable=self._inv_var,
                                            values=["–"], font=FONT_SMALL,
                                            command=self._on_inv_change, width=180)
        self._inv_menu.grid(row=0, column=5, padx=4)

        # ── Action bar ──
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        actions.columnconfigure(8, weight=1)

        ctk.CTkButton(actions, text="Add Item", width=100,
                      command=self._add_item).grid(row=0, column=0, padx=4)
        ctk.CTkButton(actions, text="Clear Inventory", width=120,
                      fg_color="#c0392b", hover_color="#962d22",
                      command=self._clear_inventory).grid(row=0, column=1, padx=4)
        ctk.CTkButton(actions, text="Save savegame.json", width=110,
                      fg_color="#1a6a1a", hover_color="#228b22",
                      command=self._save_gd).grid(row=0, column=2, padx=4)
        ctk.CTkButton(actions, text="Save + Backup", width=120,
                      fg_color="#1a6a1a", hover_color="#228b22",
                      command=self._save_gd_backup).grid(row=0, column=3, padx=4)

        self._debug_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(actions, text="Experimental / Debug",
                        variable=self._debug_var, font=FONT_SMALL,
                        text_color="#e09b3d",
                        command=self._on_debug_toggle).grid(row=0, column=4, padx=(16, 4))

        ctk.CTkButton(actions, text="Export All", width=90,
                      fg_color="#1a5276", hover_color="#1a3a5c",
                      command=self._export_inventory).grid(row=0, column=5, padx=(16, 4))
        ctk.CTkButton(actions, text="Import All", width=90,
                      fg_color="#1a5276", hover_color="#1a3a5c",
                      command=self._import_inventory).grid(row=0, column=6, padx=4)

        self._status_label = ctk.CTkLabel(actions, text="", font=FONT_SMALL,
                                           text_color="gray")
        self._status_label.grid(row=0, column=8, sticky="e", padx=8)

        # ── Inventory grid (scrollable) ──
        self._grid_frame = ctk.CTkScrollableFrame(self, label_text="Inventory Slots")
        self._grid_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._grid_frame.columnconfigure(0, weight=1)

    # ── Debug mode ─────────────────────────────────────────────────

    _DEBUG_COUNT_LIMIT = 999999
    _DEBUG_DUR_LIMIT   = 9999999

    @property
    def _debug_mode(self) -> bool:
        return self._debug_var.get()

    def _on_debug_toggle(self):
        mode = "ON" if self._debug_mode else "OFF"
        self._status_label.configure(
            text=f"Experimental/Debug mode {mode}. "
                 + ("Count/durability limits raised." if self._debug_mode
                    else "Normal limits restored."),
            text_color="#e09b3d" if self._debug_mode else "gray")
        self._render_slots()

    def _on_manager_load(self, path: str):
        """Called by ProspectManager when any tab loads a file."""
        self._load_gd(path)

    # ── File loading ──────────────────────────────────────────────────

    def _load_gd(self, path: str):
        try:
            editor = GdInventoryEditor(path)
            editor.load()
            self._gd_editor = editor

            # Load item catalog (lazy)
            if not self._catalog:
                self._catalog = get_catalog()

            # Populate player selector
            players = editor.list_players()
            if not players:
                self._status_label.configure(text="No players found in save.",
                                              text_color="#e09b3d")
                return

            player_ids = [p['steam_id'] for p in players]
            self._player_menu.configure(values=player_ids)
            self._player_var.set(player_ids[0])
            self._current_steam_id = player_ids[0]
            self._populate_inventories()

            self._status_label.configure(
                text=f"Loaded {len(players)} player(s)", text_color="#3bba6b")

        except Exception as e:
            messagebox.showerror("Load Error", f"Failed to load savegame.json:\n{e}")

    def _on_player_change(self, value: str):
        self._current_steam_id = value
        self._populate_inventories()

    def _populate_inventories(self):
        if not self._gd_editor or not self._current_steam_id:
            return
        invs = self._gd_editor.get_inventories(self._current_steam_id)
        if not invs:
            self._inv_menu.configure(values=["–"])
            self._inv_var.set("–")
            self._current_inv_id = None
            self._render_slots()
            return

        labels = []
        for inv in invs:
            label = f"{inv['id']} - {inv['name']} ({inv['slot_count']} items)"
            labels.append(label)

        self._inv_menu.configure(values=labels)
        self._inv_var.set(labels[0])
        self._current_inv_id = invs[0]['id']
        self._render_slots()

    def _on_inv_change(self, value: str):
        # Parse inv ID from label: "3 - Backpack (5 items)"
        try:
            self._current_inv_id = int(value.split(" - ")[0])
        except (ValueError, IndexError):
            self._current_inv_id = None
        self._render_slots()

    # ── Slot rendering ────────────────────────────────────────────────

    def _render_slots(self):
        """Render the inventory slot grid."""
        # Clear existing
        for w in self._grid_frame.winfo_children():
            w.destroy()
        self._slot_widgets.clear()
        self._items.clear()

        if not self._gd_editor or not self._current_steam_id or self._current_inv_id is None:
            ctk.CTkLabel(self._grid_frame, text="Select a savegame.json file, player, and inventory.",
                         font=FONT_NORMAL, text_color="gray").grid(padx=16, pady=16)
            return

        items = self._gd_editor.get_items(self._current_steam_id, self._current_inv_id)
        self._items = sorted(items, key=lambda x: x['location'] or 0)

        max_slots = _INV_SLOT_COUNTS.get(self._current_inv_id, 24)

        # Build a location -> item map
        loc_map = {it['location']: it for it in self._items}

        # Header row
        header = ctk.CTkFrame(self._grid_frame, fg_color="#1a1a2e")
        header.grid(row=0, column=0, sticky="ew", padx=2, pady=(0, 4))
        header.columnconfigure(1, weight=1)
        for col, (text, w) in enumerate([
            ("Slot", 50), ("Item", 260), ("Count", 70),
            ("Durability", 90), ("", 200), ("Fill", 130),
        ]):
            ctk.CTkLabel(header, text=text, font=FONT_HEADER, width=w,
                         anchor="w").grid(row=0, column=col, padx=6, pady=4)

        # Slot rows
        for slot_idx in range(max_slots):
            item = loc_map.get(slot_idx)
            self._build_slot_row(slot_idx, item, row_num=slot_idx + 1)

    def _build_slot_row(self, slot_idx: int, item: Optional[dict], row_num: int):
        """Build a single slot row widget."""
        row_frame = ctk.CTkFrame(self._grid_frame,
                                  fg_color="#2a2a2a" if row_num % 2 == 0 else "#242424")
        row_frame.grid(row=row_num, column=0, sticky="ew", padx=2, pady=1)
        row_frame.columnconfigure(1, weight=1)

        # Slot number
        ctk.CTkLabel(row_frame, text=str(slot_idx), font=FONT_MONO, width=50,
                     anchor="center").grid(row=0, column=0, padx=4, pady=4)

        if item:
            item_name = item['item']
            catalog_info = self._catalog.get(item_name)
            display_name = catalog_info.display_name if catalog_info else item_name

            # Item name (clickable to change)
            item_btn = ctk.CTkButton(
                row_frame, text=f"{display_name}  ({item_name})",
                font=FONT_MONO, width=260, anchor="w",
                fg_color="transparent", hover_color="#3a3a4a",
                text_color="#4da6ff",
                command=lambda s=slot_idx: self._change_item(s),
            )
            item_btn.grid(row=0, column=1, padx=4, pady=4, sticky="w")

            # Count
            count_val = item.get('count') or 1
            max_stack = catalog_info.max_stack if catalog_info else 9999
            count_var = ctk.StringVar(value=str(count_val))
            count_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
            count_frame.grid(row=0, column=2, padx=4, pady=4)
            count_entry = ctk.CTkEntry(count_frame, textvariable=count_var,
                                        font=FONT_MONO, width=70)
            count_entry.pack(side="left")
            count_entry.bind("<FocusOut>",
                lambda _e, s=slot_idx, v=count_var: self._update_count(s, v))
            count_entry.bind("<Return>",
                lambda _e, s=slot_idx, v=count_var: self._update_count(s, v))
            if self._debug_mode and max_stack > 1:
                ctk.CTkLabel(count_frame, text=f"/ {self._DEBUG_COUNT_LIMIT}",
                             font=FONT_SMALL, text_color="#e09b3d").pack(side="left", padx=2)

            # Durability (number input, not slider)
            dur_val = item.get('durability')
            if dur_val is not None:
                max_dur = catalog_info.max_durability if catalog_info else dur_val
                dur_var = ctk.StringVar(value=str(dur_val))
                dur_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
                dur_frame.grid(row=0, column=3, padx=4, pady=4)
                dur_entry = ctk.CTkEntry(dur_frame, textvariable=dur_var,
                                          font=FONT_MONO, width=70)
                dur_entry.pack(side="left")
                dur_entry.bind("<FocusOut>",
                    lambda _e, s=slot_idx, v=dur_var: self._update_durability(s, v))
                dur_entry.bind("<Return>",
                    lambda _e, s=slot_idx, v=dur_var: self._update_durability(s, v))
                if max_dur > 0:
                    if self._debug_mode:
                        ctk.CTkLabel(dur_frame, text=f"/ {self._DEBUG_DUR_LIMIT}",
                                     font=FONT_SMALL, text_color="#e09b3d").pack(side="left", padx=4)
                    else:
                        ctk.CTkLabel(dur_frame, text=f"/ {max_dur}",
                                     font=FONT_SMALL, text_color="gray").pack(side="left", padx=4)
            else:
                ctk.CTkLabel(row_frame, text="–", font=FONT_MONO, width=90,
                             text_color="gray").grid(row=0, column=3, padx=4, pady=4)

            # Action buttons
            btn_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
            btn_frame.grid(row=0, column=4, padx=4, pady=4)

            if catalog_info and catalog_info.has_durability and dur_val is not None:
                ctk.CTkButton(btn_frame, text="Max Dur", width=70,
                              font=FONT_SMALL, fg_color="#7f6000", hover_color="#5c4700",
                              command=lambda s=slot_idx: self._max_durability(s)).pack(
                    side="left", padx=2)

            ctk.CTkButton(btn_frame, text="Remove", width=70,
                          font=FONT_SMALL, fg_color="#c0392b", hover_color="#962d22",
                          command=lambda s=slot_idx: self._remove_slot(s)).pack(
                side="left", padx=2)

            # Show attachment indicator if item has InventoryContainer
            if catalog_info and catalog_info.has_inventory:
                ctk.CTkLabel(btn_frame, text="[has attachments]",
                             font=FONT_SMALL, text_color="#7ecff4").pack(
                    side="left", padx=6)

            # Fill amount (water, oxygen, biofuel, etc.)
            fill_val = item.get('fill_amount')
            if (catalog_info and catalog_info.fill_resource_type
                    and fill_val is not None):
                max_fill = catalog_info.max_fill
                fill_var = ctk.StringVar(value=str(fill_val))
                fill_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
                fill_frame.grid(row=0, column=5, padx=4, pady=4)
                ctk.CTkLabel(fill_frame,
                             text=f"{catalog_info.fill_resource_type}:",
                             font=FONT_SMALL, text_color="#7ecff4").pack(side="left")
                fill_entry = ctk.CTkEntry(fill_frame, textvariable=fill_var,
                                          font=FONT_MONO, width=70)
                fill_entry.pack(side="left", padx=(2, 0))
                fill_entry.bind("<FocusOut>",
                    lambda _e, s=slot_idx, v=fill_var, mf=max_fill:
                        self._update_fill_amount(s, v, mf))
                fill_entry.bind("<Return>",
                    lambda _e, s=slot_idx, v=fill_var, mf=max_fill:
                        self._update_fill_amount(s, v, mf))
                if max_fill > 0:
                    ctk.CTkLabel(fill_frame, text=f"/ {max_fill}",
                                 font=FONT_SMALL, text_color="gray").pack(
                        side="left", padx=(2, 4))
                    ctk.CTkButton(fill_frame, text="Max", width=45,
                                  font=FONT_SMALL,
                                  fg_color="#005f5f", hover_color="#004545",
                                  command=lambda s=slot_idx, mf=max_fill:
                                      self._max_fill_amount(s, mf)).pack(side="left")

            # --- Nested inventory (attachments / LivingItemSlots) ---
            self._render_nested_inventory(row_frame, slot_idx, item, row_num)

        else:
            # Empty slot
            ctk.CTkLabel(row_frame, text="(empty)", font=FONT_MONO, width=260,
                         text_color="#555555", anchor="w").grid(
                row=0, column=1, padx=4, pady=4, sticky="w")
            ctk.CTkButton(row_frame, text="Set Item", width=80, font=FONT_SMALL,
                          command=lambda s=slot_idx: self._set_new_item(s)).grid(
                row=0, column=4, padx=4, pady=4)

    def _render_nested_inventory(self, parent_frame, slot_idx: int,
                                  item: dict, row_num: int):
        """
        Render sub-items for a slot that has attachments or pouch contents.

        Handles two storage mechanisms:
        - LivingItemSlots: weapon attachments (stored directly on the slot)
        - Linked inventory: pouch/upgrade-slot contents (separate SavedInventories entry
          pointed to by DynamicData index 13)
        """
        if not self._gd_editor or not self._current_steam_id:
            return

        player = self._gd_editor.players.get(self._current_steam_id)
        if not player:
            return

        saved_inv = next((p for p in player.props if p.name == 'SavedInventories'), None)
        if not saved_inv:
            return

        # Find the slot FPropertyTag in the current inventory
        slot_prop = None
        for entry in saved_inv.nested:
            iid_p = next((p for p in entry.nested if p.name == 'InventoryID'), None)
            if not iid_p or iid_p.value != self._current_inv_id:
                continue
            slots_p = next((p for p in entry.nested if p.name == 'Slots'), None)
            if not slots_p:
                continue
            for s in slots_p.nested:
                loc_p = next((p for p in s.nested if p.name == 'Location'), None)
                if loc_p and loc_p.value == slot_idx:
                    slot_prop = s
                    break
            break

        if not slot_prop:
            return

        # ── Weapon attachments (LivingItemSlots) ──────────────────────────
        living = next((p for p in slot_prop.nested if p.name == 'LivingItemSlots'), None)
        living_sub_slots = living.nested if living else []

        # ── Pouch / upgrade-slot contents (ContainerManager by array index) ──
        linked_inv_id = _get_dyn_value(slot_prop, DYN_LINKED_INV)
        linked_items: List[Dict] = []
        if linked_inv_id is not None:
            linked_items = self._gd_editor.get_container_items(linked_inv_id)

        if not living_sub_slots and not linked_items:
            return

        # ── Outer container ────────────────────────────────────────────────
        nested_frame = ctk.CTkFrame(parent_frame, fg_color="#162030")
        nested_frame.grid(row=1, column=0, columnspan=6, sticky="ew",
                          padx=(50, 8), pady=(0, 6))
        nested_frame.columnconfigure(1, weight=1)

        header_f = ctk.CTkFrame(nested_frame, fg_color="#0d1a2a")
        header_f.grid(row=0, column=0, columnspan=6, sticky="ew", padx=2, pady=(2, 0))
        label = "Contents" if linked_items else "Attachments"
        if living_sub_slots and linked_items:
            label = "Contents / Attachments"
        ctk.CTkLabel(header_f, text=label,
                     font=FONT_SMALL, text_color="#7ecff4").pack(side="left", padx=8, pady=3)

        row_offset = 1

        # ── Render LivingItemSlots (attachments) ──────────────────────────
        for i, sub_slot in enumerate(living_sub_slots):
            sub_item_p = next((p for p in sub_slot.nested if p.name == 'ItemStaticData'), None)
            sub_loc_p  = next((p for p in sub_slot.nested if p.name == 'Location'), None)
            if not sub_item_p or not sub_item_p.value:
                continue

            sub_name    = sub_item_p.value
            sub_loc     = sub_loc_p.value if sub_loc_p else i
            sub_info    = self._catalog.get(sub_name)
            sub_display = sub_info.display_name if sub_info else sub_name
            sub_dur     = _get_dyn_value(sub_slot, DYN_DURABILITY)
            sub_count   = _get_dyn_value(sub_slot, DYN_STACK_COUNT) or 1
            max_stack   = (sub_info.max_stack if sub_info else 9999) or 9999
            max_dur     = (sub_info.max_durability if sub_info and sub_info.has_durability
                           else 0)

            row_f = ctk.CTkFrame(nested_frame,
                                  fg_color="#1e2e40" if i % 2 == 0 else "#19263a")
            row_f.grid(row=row_offset + i, column=0, columnspan=6,
                       sticky="ew", padx=2, pady=1)
            row_f.columnconfigure(1, weight=1)

            ctk.CTkLabel(row_f, text=str(sub_loc), font=FONT_MONO, width=30,
                         text_color="#7ecff4", anchor="center").grid(
                row=0, column=0, padx=(8, 4), pady=3)
            ctk.CTkLabel(row_f,
                text=f"{sub_display}  ({sub_name})",
                font=FONT_SMALL, text_color="#c8e0f4", anchor="w").grid(
                row=0, column=1, padx=4, pady=3, sticky="w")

            if max_stack > 1:
                cnt_var = ctk.StringVar(value=str(sub_count))
                cnt_entry = ctk.CTkEntry(row_f, textvariable=cnt_var,
                                          font=FONT_MONO, width=60)
                cnt_entry.grid(row=0, column=2, padx=4, pady=3)
                cnt_entry.bind("<FocusOut>",
                    lambda _e, sid=slot_idx, sloc=sub_loc, v=cnt_var, ms=max_stack:
                        self._update_living_count(sid, sloc, v, ms))
                cnt_entry.bind("<Return>",
                    lambda _e, sid=slot_idx, sloc=sub_loc, v=cnt_var, ms=max_stack:
                        self._update_living_count(sid, sloc, v, ms))
            else:
                ctk.CTkLabel(row_f, text="1", font=FONT_MONO, width=60,
                             text_color="gray").grid(row=0, column=2, padx=4, pady=3)

            if sub_dur is not None and max_dur > 0:
                dur_var = ctk.StringVar(value=str(sub_dur))
                dur_frame = ctk.CTkFrame(row_f, fg_color="transparent")
                dur_frame.grid(row=0, column=3, padx=4, pady=3)
                dur_entry = ctk.CTkEntry(dur_frame, textvariable=dur_var,
                                          font=FONT_MONO, width=70)
                dur_entry.pack(side="left")
                dur_entry.bind("<FocusOut>",
                    lambda _e, sid=slot_idx, sloc=sub_loc, v=dur_var, md=max_dur:
                        self._update_living_dur(sid, sloc, v, md))
                dur_entry.bind("<Return>",
                    lambda _e, sid=slot_idx, sloc=sub_loc, v=dur_var, md=max_dur:
                        self._update_living_dur(sid, sloc, v, md))
                ctk.CTkLabel(dur_frame, text=f"/ {max_dur}",
                             font=FONT_SMALL, text_color="gray").pack(
                    side="left", padx=(2, 0))
                ctk.CTkButton(row_f, text="Max", width=45, font=FONT_SMALL,
                              fg_color="#7f6000", hover_color="#5c4700",
                              command=lambda sid=slot_idx, sloc=sub_loc, md=max_dur:
                                  self._max_living_dur(sid, sloc, md)).grid(
                    row=0, column=4, padx=(2, 8), pady=3)
            else:
                ctk.CTkLabel(row_f, text="–", font=FONT_MONO, width=70,
                             text_color="#444").grid(row=0, column=3, padx=4, pady=3)

        row_offset += len(living_sub_slots)

        # ── Render linked inventory items (pouch / upgrade slot) ───────────
        for i, sub_item in enumerate(linked_items):
            sub_name  = sub_item.get('item', '')
            sub_loc   = sub_item.get('location', i)
            sub_count = sub_item.get('count') or 1
            sub_dur   = sub_item.get('durability')
            sub_fill  = sub_item.get('fill_amount')
            sub_info  = self._catalog.get(sub_name)
            sub_display = sub_info.display_name if sub_info else sub_name
            max_stack = (sub_info.max_stack if sub_info else 9999) or 9999
            max_dur   = (sub_info.max_durability if sub_info and sub_info.has_durability
                         else 0)
            fill_type  = sub_info.fill_resource_type if sub_info else ''
            max_fill   = sub_info.max_fill if sub_info else 0

            row_f = ctk.CTkFrame(nested_frame,
                                  fg_color="#1e3020" if i % 2 == 0 else "#192a1a")
            row_f.grid(row=row_offset + i, column=0, columnspan=6,
                       sticky="ew", padx=2, pady=1)
            row_f.columnconfigure(1, weight=1)

            ctk.CTkLabel(row_f, text=str(sub_loc), font=FONT_MONO, width=30,
                         text_color="#7ecff4", anchor="center").grid(
                row=0, column=0, padx=(8, 4), pady=3)
            ctk.CTkLabel(row_f,
                text=f"{sub_display}  ({sub_name})",
                font=FONT_SMALL, text_color="#c8e0f4", anchor="w").grid(
                row=0, column=1, padx=4, pady=3, sticky="w")

            if max_stack > 1:
                cnt_var = ctk.StringVar(value=str(sub_count))
                cnt_entry = ctk.CTkEntry(row_f, textvariable=cnt_var,
                                          font=FONT_MONO, width=60)
                cnt_entry.grid(row=0, column=2, padx=4, pady=3)
                cnt_entry.bind("<FocusOut>",
                    lambda _e, lid=linked_inv_id, sloc=sub_loc, v=cnt_var, ms=max_stack:
                        self._update_linked_count(lid, sloc, v, ms))
                cnt_entry.bind("<Return>",
                    lambda _e, lid=linked_inv_id, sloc=sub_loc, v=cnt_var, ms=max_stack:
                        self._update_linked_count(lid, sloc, v, ms))
            else:
                ctk.CTkLabel(row_f, text="1", font=FONT_MONO, width=60,
                             text_color="gray").grid(row=0, column=2, padx=4, pady=3)

            if sub_dur is not None and max_dur > 0:
                dur_var = ctk.StringVar(value=str(sub_dur))
                dur_frame = ctk.CTkFrame(row_f, fg_color="transparent")
                dur_frame.grid(row=0, column=3, padx=4, pady=3)
                dur_entry = ctk.CTkEntry(dur_frame, textvariable=dur_var,
                                          font=FONT_MONO, width=70)
                dur_entry.pack(side="left")
                dur_entry.bind("<FocusOut>",
                    lambda _e, lid=linked_inv_id, sloc=sub_loc, v=dur_var, md=max_dur:
                        self._update_linked_dur(lid, sloc, v, md))
                dur_entry.bind("<Return>",
                    lambda _e, lid=linked_inv_id, sloc=sub_loc, v=dur_var, md=max_dur:
                        self._update_linked_dur(lid, sloc, v, md))
                ctk.CTkLabel(dur_frame, text=f"/ {max_dur}",
                             font=FONT_SMALL, text_color="gray").pack(
                    side="left", padx=(2, 0))
                ctk.CTkButton(row_f, text="Max", width=45, font=FONT_SMALL,
                              fg_color="#7f6000", hover_color="#5c4700",
                              command=lambda lid=linked_inv_id, sloc=sub_loc, md=max_dur:
                                  self._max_linked_dur(lid, sloc, md)).grid(
                    row=0, column=4, padx=(2, 8), pady=3)
            else:
                ctk.CTkLabel(row_f, text="–", font=FONT_MONO, width=70,
                             text_color="#444").grid(row=0, column=3, padx=4, pady=3)

            # Fill amount for fillable sub-items (e.g. canteen in a pouch)
            if fill_type and sub_fill is not None:
                fill_var = ctk.StringVar(value=str(sub_fill))
                fill_frame = ctk.CTkFrame(row_f, fg_color="transparent")
                fill_frame.grid(row=0, column=5, padx=4, pady=3)
                ctk.CTkLabel(fill_frame, text=f"{fill_type}:",
                             font=FONT_SMALL, text_color="#7ecff4").pack(side="left")
                fill_entry = ctk.CTkEntry(fill_frame, textvariable=fill_var,
                                           font=FONT_MONO, width=60)
                fill_entry.pack(side="left", padx=(2, 0))
                fill_entry.bind("<FocusOut>",
                    lambda _e, lid=linked_inv_id, sloc=sub_loc, v=fill_var, mf=max_fill:
                        self._update_linked_fill(lid, sloc, v, mf))
                fill_entry.bind("<Return>",
                    lambda _e, lid=linked_inv_id, sloc=sub_loc, v=fill_var, mf=max_fill:
                        self._update_linked_fill(lid, sloc, v, mf))
                if max_fill > 0:
                    ctk.CTkLabel(fill_frame, text=f"/ {max_fill}",
                                 font=FONT_SMALL, text_color="gray").pack(
                        side="left", padx=(2, 4))
                    ctk.CTkButton(fill_frame, text="Max", width=40,
                                  font=FONT_SMALL,
                                  fg_color="#005f5f", hover_color="#004545",
                                  command=lambda lid=linked_inv_id, sloc=sub_loc, mf=max_fill:
                                      self._max_linked_fill(lid, sloc, mf)).pack(side="left")

    # ── Living slot (pouch / attachment) actions ──────────────────────

    def _update_living_count(self, slot_idx: int, sub_loc: int,
                             var: ctk.StringVar, max_stack: int):
        if not self._gd_editor or not self._current_steam_id or self._current_inv_id is None:
            return
        try:
            count = max(1, int(var.get()))
            if not self._debug_mode and max_stack > 0:
                count = min(count, max_stack)
            var.set(str(count))
        except ValueError:
            return
        self._gd_editor.update_living_item(
            self._current_steam_id, self._current_inv_id,
            slot_idx, sub_loc, count=count)
        self._status_label.configure(
            text=f"Slot {slot_idx} [{sub_loc}]: count = {count}", text_color="#3bba6b")

    def _update_living_dur(self, slot_idx: int, sub_loc: int,
                           var: ctk.StringVar, max_dur: int):
        if not self._gd_editor or not self._current_steam_id or self._current_inv_id is None:
            return
        try:
            dur = max(0, int(var.get()))
            if not self._debug_mode and max_dur > 0:
                dur = min(dur, max_dur)
            var.set(str(dur))
        except ValueError:
            return
        self._gd_editor.update_living_item(
            self._current_steam_id, self._current_inv_id,
            slot_idx, sub_loc, durability=dur)
        self._status_label.configure(
            text=f"Slot {slot_idx} [{sub_loc}]: durability = {dur}", text_color="#3bba6b")

    def _max_living_dur(self, slot_idx: int, sub_loc: int, max_dur: int):
        if not self._gd_editor or not self._current_steam_id or self._current_inv_id is None:
            return
        dur = self._DEBUG_DUR_LIMIT if self._debug_mode else max_dur
        self._gd_editor.update_living_item(
            self._current_steam_id, self._current_inv_id,
            slot_idx, sub_loc, durability=dur)
        self._status_label.configure(
            text=f"Slot {slot_idx} [{sub_loc}]: durability set to max ({dur})",
            text_color="#3bba6b")
        self._render_slots()

    # ── Linked inventory (pouch / upgrade-slot) actions ───────────────

    def _update_linked_count(self, linked_inv_id: int, sub_loc: int,
                              var: ctk.StringVar, max_stack: int):
        if not self._gd_editor:
            return
        try:
            count = max(1, int(var.get()))
            if not self._debug_mode and max_stack > 0:
                count = min(count, max_stack)
            var.set(str(count))
        except ValueError:
            return
        items = self._gd_editor.get_container_items(linked_inv_id)
        target = next((it for it in items if it['location'] == sub_loc), None)
        if target:
            self._gd_editor._restore_container_items(
                linked_inv_id,
                [{**it, 'count': count} if it['location'] == sub_loc else it
                 for it in items])
        self._status_label.configure(
            text=f"Container {linked_inv_id} slot {sub_loc}: count = {count}",
            text_color="#3bba6b")

    def _update_linked_dur(self, linked_inv_id: int, sub_loc: int,
                            var: ctk.StringVar, max_dur: int):
        if not self._gd_editor:
            return
        try:
            dur = max(0, int(var.get()))
            if not self._debug_mode and max_dur > 0:
                dur = min(dur, max_dur)
            var.set(str(dur))
        except ValueError:
            return
        items = self._gd_editor.get_container_items(linked_inv_id)
        self._gd_editor._restore_container_items(
            linked_inv_id,
            [{**it, 'durability': dur} if it['location'] == sub_loc else it
             for it in items])
        self._status_label.configure(
            text=f"Container {linked_inv_id} slot {sub_loc}: durability = {dur}",
            text_color="#3bba6b")

    def _max_linked_dur(self, linked_inv_id: int, sub_loc: int, max_dur: int):
        if not self._gd_editor:
            return
        dur = self._DEBUG_DUR_LIMIT if self._debug_mode else max_dur
        items = self._gd_editor.get_container_items(linked_inv_id)
        self._gd_editor._restore_container_items(
            linked_inv_id,
            [{**it, 'durability': dur} if it['location'] == sub_loc else it
             for it in items])
        self._status_label.configure(
            text=f"Container {linked_inv_id} slot {sub_loc}: durability = max ({dur})",
            text_color="#3bba6b")
        self._render_slots()

    def _update_linked_fill(self, linked_inv_id: int, sub_loc: int,
                             var: ctk.StringVar, max_fill: int):
        if not self._gd_editor:
            return
        try:
            fill = max(0, int(var.get()))
            if max_fill > 0:
                fill = min(fill, max_fill)
            var.set(str(fill))
        except ValueError:
            return
        items = self._gd_editor.get_container_items(linked_inv_id)
        self._gd_editor._restore_container_items(
            linked_inv_id,
            [{**it, 'fill_amount': fill} if it['location'] == sub_loc else it
             for it in items])
        self._status_label.configure(
            text=f"Container {linked_inv_id} slot {sub_loc}: fill = {fill}",
            text_color="#3bba6b")

    def _max_linked_fill(self, linked_inv_id: int, sub_loc: int, max_fill: int):
        if not self._gd_editor:
            return
        items = self._gd_editor.get_container_items(linked_inv_id)
        self._gd_editor._restore_container_items(
            linked_inv_id,
            [{**it, 'fill_amount': max_fill} if it['location'] == sub_loc else it
             for it in items])
        self._status_label.configure(
            text=f"Container {linked_inv_id} slot {sub_loc}: fill = max ({max_fill})",
            text_color="#3bba6b")
        self._render_slots()

    def _update_fill_amount(self, slot_idx: int, var: ctk.StringVar, max_fill: int):
        """Update fill amount for a main inventory slot."""
        if not self._gd_editor or not self._current_steam_id or self._current_inv_id is None:
            return
        try:
            fill = max(0, int(var.get()))
            if max_fill > 0:
                fill = min(fill, max_fill)
            var.set(str(fill))
        except ValueError:
            return
        item = next((it for it in self._items if it['location'] == slot_idx), None)
        if item is None:
            return
        self._gd_editor.set_item(
            self._current_steam_id, self._current_inv_id, slot_idx,
            item['item'], count=item.get('count') or 1,
            durability=item.get('durability'), fill_amount=fill)
        self._status_label.configure(
            text=f"Slot {slot_idx}: fill = {fill}", text_color="#3bba6b")

    def _max_fill_amount(self, slot_idx: int, max_fill: int):
        """Set fill to max for a main inventory slot."""
        if not self._gd_editor or not self._current_steam_id or self._current_inv_id is None:
            return
        item = next((it for it in self._items if it['location'] == slot_idx), None)
        if item is None:
            return
        self._gd_editor.set_item(
            self._current_steam_id, self._current_inv_id, slot_idx,
            item['item'], count=item.get('count') or 1,
            durability=item.get('durability'), fill_amount=max_fill)
        self._status_label.configure(
            text=f"Slot {slot_idx}: fill = max ({max_fill})", text_color="#3bba6b")
        self._render_slots()

    # ── Item actions ──────────────────────────────────────────────────

    def _change_item(self, slot_idx: int):
        """Open item search popup to change the item in a slot."""
        if not self._catalog:
            return
        x = self.winfo_rootx() + 200
        y = self.winfo_rooty() + 100
        _ItemSearchPopup(self, self._catalog,
                         lambda name: self._do_change_item(slot_idx, name), x, y)

    def _do_change_item(self, slot_idx: int, item_name: str):
        if not self._gd_editor or not self._current_steam_id or self._current_inv_id is None:
            return
        catalog_info = self._catalog.get(item_name)
        dur = catalog_info.max_durability if catalog_info and catalog_info.has_durability else None
        count = 1

        self._gd_editor.set_item(
            self._current_steam_id, self._current_inv_id, slot_idx,
            item_name, count=count, durability=dur)
        self._status_label.configure(
            text=f"Changed slot {slot_idx} to {item_name}", text_color="#3bba6b")
        self._render_slots()

    def _set_new_item(self, slot_idx: int):
        """Set an item in an empty slot via search popup."""
        if not self._catalog:
            return
        x = self.winfo_rootx() + 200
        y = self.winfo_rooty() + 100
        _ItemSearchPopup(self, self._catalog,
                         lambda name: self._do_set_new_item(slot_idx, name), x, y)

    def _do_set_new_item(self, slot_idx: int, item_name: str):
        if not self._gd_editor or not self._current_steam_id or self._current_inv_id is None:
            return
        catalog_info = self._catalog.get(item_name)
        dur = catalog_info.max_durability if catalog_info and catalog_info.has_durability else None
        count = 1

        self._gd_editor.set_item(
            self._current_steam_id, self._current_inv_id, slot_idx,
            item_name, count=count, durability=dur)
        self._status_label.configure(
            text=f"Set slot {slot_idx} to {item_name}", text_color="#3bba6b")
        self._render_slots()

    def _update_count(self, slot_idx: int, var: ctk.StringVar):
        """Update item count from entry field."""
        if not self._gd_editor or not self._current_steam_id or self._current_inv_id is None:
            return
        try:
            count = int(var.get())
            if count < 1:
                count = 1
        except ValueError:
            return

        # Find current item at this slot
        item = next((it for it in self._items if it['location'] == slot_idx), None)
        if not item:
            return

        # Enforce limits
        if not self._debug_mode:
            catalog_info = self._catalog.get(item['item'])
            max_stack = catalog_info.max_stack if catalog_info else 9999
            if max_stack > 0 and count > max_stack:
                count = max_stack
                var.set(str(count))
        else:
            if count > self._DEBUG_COUNT_LIMIT:
                count = self._DEBUG_COUNT_LIMIT
                var.set(str(count))

        dur = item.get('durability')
        self._gd_editor.set_item(
            self._current_steam_id, self._current_inv_id, slot_idx,
            item['item'], count=count, durability=dur)
        self._status_label.configure(
            text=f"Slot {slot_idx}: count = {count}", text_color="#3bba6b")

    def _update_durability(self, slot_idx: int, var: ctk.StringVar):
        """Update item durability from entry field."""
        if not self._gd_editor or not self._current_steam_id or self._current_inv_id is None:
            return
        try:
            dur = int(var.get())
            if dur < 0:
                dur = 0
        except ValueError:
            return

        item = next((it for it in self._items if it['location'] == slot_idx), None)
        if not item:
            return

        # Enforce limits
        if not self._debug_mode:
            catalog_info = self._catalog.get(item['item'])
            max_dur = catalog_info.max_durability if catalog_info and catalog_info.has_durability else dur
            if max_dur > 0 and dur > max_dur:
                dur = max_dur
                var.set(str(dur))
        else:
            if dur > self._DEBUG_DUR_LIMIT:
                dur = self._DEBUG_DUR_LIMIT
                var.set(str(dur))

        count = item.get('count') or 1
        self._gd_editor.set_item(
            self._current_steam_id, self._current_inv_id, slot_idx,
            item['item'], count=count, durability=dur)
        self._status_label.configure(
            text=f"Slot {slot_idx}: durability = {dur}", text_color="#3bba6b")

    def _max_durability(self, slot_idx: int):
        """Set durability to max for a slot (debug mode uses raised limit)."""
        item = next((it for it in self._items if it['location'] == slot_idx), None)
        if not item:
            return
        catalog_info = self._catalog.get(item['item'])
        if not catalog_info or not catalog_info.has_durability:
            return
        max_dur = self._DEBUG_DUR_LIMIT if self._debug_mode else catalog_info.max_durability
        count = item.get('count') or 1
        self._gd_editor.set_item(
            self._current_steam_id, self._current_inv_id, slot_idx,
            item['item'], count=count, durability=max_dur)
        self._status_label.configure(
            text=f"Slot {slot_idx}: durability set to max ({max_dur})", text_color="#3bba6b")
        self._render_slots()

    def _remove_slot(self, slot_idx: int):
        """Remove item from a slot."""
        if not self._gd_editor or not self._current_steam_id or self._current_inv_id is None:
            return
        self._gd_editor.remove_item(self._current_steam_id, self._current_inv_id, slot_idx)
        self._status_label.configure(
            text=f"Removed item from slot {slot_idx}", text_color="#e09b3d")
        self._render_slots()

    def _add_item(self):
        """Add item to first free slot via search popup."""
        if not self._gd_editor or not self._current_steam_id or self._current_inv_id is None:
            self._status_label.configure(text="Load a file first.", text_color="#e09b3d")
            return
        if not self._catalog:
            return

        # Find first free slot
        items = self._gd_editor.get_items(self._current_steam_id, self._current_inv_id)
        used = {it['location'] for it in items}
        max_slots = _INV_SLOT_COUNTS.get(self._current_inv_id, 24)
        free_slot = None
        for i in range(max_slots):
            if i not in used:
                free_slot = i
                break
        if free_slot is None:
            self._status_label.configure(text="Inventory is full!", text_color="#e09b3d")
            return

        x = self.winfo_rootx() + 200
        y = self.winfo_rooty() + 100
        _ItemSearchPopup(self, self._catalog,
                         lambda name: self._do_set_new_item(free_slot, name), x, y)

    def _clear_inventory(self):
        """Clear all items from the current inventory."""
        if not self._gd_editor or not self._current_steam_id or self._current_inv_id is None:
            return
        if not messagebox.askyesno("Clear Inventory",
                f"Remove ALL items from {INVENTORY_NAMES.get(self._current_inv_id, 'this inventory')}?"):
            return
        n = self._gd_editor.clear_inventory(self._current_steam_id, self._current_inv_id)
        self._status_label.configure(text=f"Cleared {n} items.", text_color="#e09b3d")
        self._render_slots()

    # ── Import / Export ───────────────────────────────────────────────

    def _export_inventory(self):
        if not self._gd_editor or not self._current_steam_id:
            self._status_label.configure(text="Load a file first.", text_color="#e09b3d")
            return
        path = filedialog.asksaveasfilename(
            title="Export All Inventories",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            initialfile=f"inventories_{self._current_steam_id}.json",
        )
        if not path:
            return
        try:
            data = self._gd_editor.export_all_inventories(self._current_steam_id)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            total = sum(len(inv['items']) for inv in data['inventories'])
            n_invs = len(data['inventories'])
            self._status_label.configure(
                text=f"Exported {total} item(s) across {n_invs} inventories.",
                text_color="#3bba6b")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _import_inventory(self):
        if not self._gd_editor or not self._current_steam_id:
            self._status_label.configure(text="Load a file first.", text_color="#e09b3d")
            return
        path = filedialog.askopenfilename(
            title="Import All Inventories",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror("Import Error", f"Could not read file:\n{e}")
            return

        if data.get('type') != 'icarus_player_inventories':
            if not messagebox.askyesno(
                    "Wrong File Type",
                    "This file does not look like a full player inventories export.\n"
                    "Import anyway?"):
                return

        merge = messagebox.askyesnocancel(
            "Import Mode",
            "Yes  = Merge  (keep existing items, skip occupied slots)\n"
            "No   = Replace (clear each inventory first, then import)\n"
            "Cancel = Abort")
        if merge is None:
            return

        try:
            n = self._gd_editor.import_all_inventories(
                self._current_steam_id, data, merge=merge)
            mode_str = "merged" if merge else "replaced"
            self._status_label.configure(
                text=f"Imported {n} item(s) across all inventories ({mode_str}). Save savegame.json to persist.",
                text_color="#3bba6b")
            self._render_slots()
        except Exception as e:
            messagebox.showerror("Import Error", str(e))

    # ── Save ──────────────────────────────────────────────────────────

    def _save_gd(self):
        if not self._gd_editor:
            self._status_label.configure(text="No file loaded.", text_color="#e09b3d")
            return
        try:
            self._gd_editor.save(backup=False)
            self._status_label.configure(text="Saved savegame.json", text_color="#3bba6b")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _save_gd_backup(self):
        if not self._gd_editor:
            self._status_label.configure(text="No file loaded.", text_color="#e09b3d")
            return
        try:
            self._gd_editor.save(backup=True)
            self._status_label.configure(text="Saved savegame.json (with backup)",
                                          text_color="#3bba6b")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))
