#!/usr/bin/env python3
"""
Icarus Save Editor - GUI
========================

CustomTkinter-based desktop editor for Icarus save files.

Tabs:
  - Mounts     : List / edit all mounts (name, level, type, skin, clone, delete)
  - Character  : XP, XP Debt, Dead/Abandoned status (stats only)
  - Tech Tree  : Blueprint/crafting unlocks grouped by tier
  - Talents    : Character perk bonuses grouped by tree/subtree
  - Workshop   : Workshop unlocks (Profile.json Talents)
  - Inventory  : MetaInventory items (repair, remove)
  - Profile    : Credits, Exotics, Refund Tokens, Licences

Usage:
    python gui_main.py
"""

import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import List, Optional, Tuple
import customtkinter as ctk

from save_manager import SaveManager, find_steam_ids
from character_editor import CharacterEditor, TalentEntry
from profile_editor import ProfileEditor
from inventory_editor import InventoryEditor
from mount_editor import MountEditor, get_default_mounts_path
from mount_types import MOUNT_TYPES
from game_data import (
    classify_save_talents, TALENT_SUBTREES, TALENT_TREES, TALENT_PREFIXES,
    get_tech_catalog_for_tier, get_talent_catalog_for_subtree,
    format_stats, rowname_matches_catalog, find_talent_catalog_match,
    get_tech_tier_labels,
)


# ── Appearance ──────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

FONT_TITLE  = ("Segoe UI", 15, "bold")
FONT_NORMAL = ("Segoe UI", 13)
FONT_SMALL  = ("Segoe UI", 11)
FONT_MONO   = ("Consolas", 12)
FONT_HEADER = ("Consolas", 12, "bold")
PAD = {"padx": 8, "pady": 4}

# Tier sort order for display
_TIER_ORDER = ["Tier 1", "Tier 2", "Tier 3", "Tier 4",
               "Anvil", "Armor Bench", "Carpentry Bench", "Cement Mixer",
               "Chemistry Bench", "Glass Furnace", "Herbalism Bench",
               "Kitchen", "Mason Bench", "Mortar & Pestle", "Meat Processing",
               "Workshop", "Tier ?"]

# Talent subtree sort order
_SUBTREE_ORDER = [
    "Survival / Resources", "Survival / Exploration",
    "Survival / Hunting", "Survival / Cook / Farm",
    "Construction / Repairing", "Construction / Tools", "Construction / Building",
    "Combat / Bows", "Combat / Spears", "Combat / Blades", "Combat / Firearms",
    "Solo / Solo",
]


def _sort_key(label: str, order: list) -> int:
    try:
        return order.index(label)
    except ValueError:
        return len(order)


# ============================================================================
# Mounts Tab
# ============================================================================

class MountsTab(ctk.CTkFrame):
    def __init__(self, master, mount_editor: MountEditor, **kwargs):
        super().__init__(master, **kwargs)
        self.editor = mount_editor
        self._selected_idx: Optional[int] = None
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=2)
        self.rowconfigure(0, weight=1)

        # ── Left: mount list ──────────────────────────────────────────────
        left = ctk.CTkFrame(self)
        left.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="Mounts", font=FONT_TITLE).grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 4))

        self.list_box = tk.Listbox(
            left, bg="#2b2b2b", fg="white", selectbackground="#1f6aa5",
            font=FONT_MONO, activestyle="none", bd=0, highlightthickness=0,
            relief="flat"
        )
        self.list_box.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self.list_box.bind("<<ListboxSelect>>", self._on_select)

        btn_row = ctk.CTkFrame(left, fg_color="transparent")
        btn_row.grid(row=2, column=0, pady=4)
        ctk.CTkButton(btn_row, text="Clone", width=80, command=self._clone).pack(side="left", padx=4)
        ctk.CTkButton(btn_row, text="Delete", width=80, fg_color="#c0392b",
                      hover_color="#962d22", command=self._delete).pack(side="left", padx=4)

        # ── Right: edit panel ─────────────────────────────────────────────
        right = ctk.CTkScrollableFrame(self, label_text="Edit Mount")
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)
        right.columnconfigure(1, weight=1)

        def row_label(r, text):
            ctk.CTkLabel(right, text=text, font=FONT_NORMAL, anchor="w").grid(
                row=r, column=0, sticky="w", padx=(8, 4), pady=6)

        row_label(0, "Name")
        self.name_var = ctk.StringVar()
        ctk.CTkEntry(right, textvariable=self.name_var, font=FONT_NORMAL).grid(
            row=0, column=1, sticky="ew", padx=8, pady=6)

        row_label(1, "Level (1–50)")
        self.level_var = ctk.IntVar(value=1)
        ctk.CTkSlider(right, from_=1, to=50, number_of_steps=49,
                      variable=self.level_var, command=self._update_level_label).grid(
            row=1, column=1, sticky="ew", padx=8, pady=6)
        self.level_label = ctk.CTkLabel(right, text="1", font=FONT_NORMAL)
        self.level_label.grid(row=1, column=2, padx=4)

        row_label(2, "Type")
        type_keys = list(MOUNT_TYPES.keys())
        self.type_var = ctk.StringVar()
        self.type_menu = ctk.CTkOptionMenu(right, variable=self.type_var, values=type_keys,
                                           font=FONT_NORMAL)
        self.type_menu.grid(row=2, column=1, sticky="ew", padx=8, pady=6)

        row_label(3, "Skin")
        self.skin_var = ctk.StringVar(value="0 – Default")
        self.skin_menu = ctk.CTkOptionMenu(right, variable=self.skin_var,
                                           values=["0 – Default"], font=FONT_NORMAL)
        self.skin_menu.grid(row=3, column=1, sticky="ew", padx=8, pady=6)

        row_label(4, "Horse Variant")
        self.variant_var = ctk.StringVar(value="A3")
        ctk.CTkOptionMenu(right, variable=self.variant_var, values=["A1", "A2", "A3"],
                          font=FONT_NORMAL).grid(
            row=4, column=1, sticky="ew", padx=8, pady=6)
        self.variant_hint = ctk.CTkLabel(right,
            text="A1=Brown  A2=Black  A3=White  (Workshop Horse only)",
            font=FONT_SMALL, text_color="gray")
        self.variant_hint.grid(row=5, column=0, columnspan=3, sticky="w", padx=8)

        ctk.CTkButton(right, text="Reset Mount Talents", command=self._reset_talents,
                      fg_color="#7f6000", hover_color="#5c4700").grid(
            row=6, column=0, columnspan=3, padx=8, pady=(12, 4), sticky="ew")

        ctk.CTkButton(right, text="Apply Changes", command=self._apply,
                      font=FONT_TITLE).grid(
            row=7, column=0, columnspan=3, padx=8, pady=(4, 12), sticky="ew")

        self.status_label = ctk.CTkLabel(right, text="", font=FONT_SMALL, text_color="gray")
        self.status_label.grid(row=8, column=0, columnspan=3, padx=8)

    def refresh(self):
        if not self.editor.is_loaded:
            return
        self.list_box.delete(0, tk.END)
        for info in self.editor.list_mounts():
            self.list_box.insert(tk.END,
                f"{info.index:2d}  {info.name:<20} {info.mount_type:<14} Lv.{info.level}")
        self._selected_idx = None

    def _on_select(self, _event=None):
        sel = self.list_box.curselection()
        if not sel:
            return
        idx = sel[0]
        try:
            mount = self.editor.get_mount(idx)
        except IndexError:
            return
        self._selected_idx = idx
        self._populate(mount)

    def _populate(self, mount):
        self.name_var.set(mount.name)
        level = mount.level
        self.level_var.set(level)
        self.level_label.configure(text=str(level))
        self.type_var.set(mount.mount_type if mount.mount_type in MOUNT_TYPES else list(MOUNT_TYPES)[0])
        self._update_skin_options(mount.mount_type)

    def _update_level_label(self, value):
        self.level_label.configure(text=str(int(float(value))))

    def _update_skin_options(self, type_key: str):
        mt = MOUNT_TYPES.get(type_key)
        if mt and mt.skins:
            opts = [f"{s.index} – {s.name}" for s in mt.skins]
            self.skin_menu.configure(values=opts)
            self.skin_var.set(opts[0])
        else:
            self.skin_menu.configure(values=["N/A"])
            self.skin_var.set("N/A")

    def _apply(self):
        if self._selected_idx is None:
            return
        idx = self._selected_idx
        try:
            new_name = self.name_var.get().strip()
            if new_name:
                self.editor.set_mount_name(idx, new_name)

            new_level = int(self.level_var.get())
            self.editor.set_mount_level(idx, new_level)

            new_type = self.type_var.get()
            mount = self.editor.get_mount(idx)
            if new_type != mount.mount_type:
                self.editor.change_mount_type(idx, new_type)

            skin_str = self.skin_var.get()
            if skin_str and skin_str != "N/A" and "–" in skin_str:
                skin_idx = int(skin_str.split("–")[0].strip())
                try:
                    self.editor.set_cosmetic_skin(idx, skin_idx)
                except ValueError:
                    pass

            new_type_key = self.type_var.get()
            if new_type_key == "Horse":
                variant = self.variant_var.get()
                try:
                    self.editor.set_horse_variant(idx, variant)
                except ValueError:
                    pass

            self.status_label.configure(text="Changes applied (not yet saved).", text_color="#3bba6b")
            self.refresh()
            self.list_box.selection_set(idx)
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _clone(self):
        if self._selected_idx is None:
            messagebox.showinfo("Clone", "Select a mount first.")
            return
        name = simpledialog.askstring("Clone Mount", "Name for the cloned mount:")
        if not name:
            return
        try:
            new_idx = self.editor.clone_mount(self._selected_idx, name)
            self.refresh()
            self.list_box.selection_set(new_idx)
            self._selected_idx = new_idx
            self._on_select()
        except Exception as e:
            messagebox.showerror("Clone Error", str(e))

    def _delete(self):
        if self._selected_idx is None:
            messagebox.showinfo("Delete", "Select a mount first.")
            return
        mount = self.editor.get_mount(self._selected_idx)
        if not messagebox.askyesno("Delete Mount", f"Delete '{mount.name}'?"):
            return
        self.editor.delete_mount(self._selected_idx)
        self.refresh()

    def _reset_talents(self):
        if self._selected_idx is None:
            return
        n = self.editor.reset_mount_talents(self._selected_idx)
        self.status_label.configure(text=f"Reset {n} talent(s).", text_color="#e09b3d")


# ============================================================================
# Character Tab  (stats only — no talent list)
# ============================================================================

class CharacterTab(ctk.CTkFrame):
    def __init__(self, master, char_editor: CharacterEditor,
                 on_char_change=None, **kwargs):
        super().__init__(master, **kwargs)
        self.editor = char_editor
        self._on_char_change_cb = on_char_change  # optional external callback
        self._build()

    def _build(self):
        self.columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Character Stats", font=FONT_TITLE).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(16, 8))

        # Character selector
        ctk.CTkLabel(self, text="Character", font=FONT_NORMAL).grid(
            row=1, column=0, sticky="w", padx=(16, 8), pady=8)
        self.char_var = ctk.StringVar()
        self.char_menu = ctk.CTkOptionMenu(self, variable=self.char_var, values=["–"],
                                           font=FONT_NORMAL, command=self._on_char_change,
                                           width=220)
        self.char_menu.grid(row=1, column=1, sticky="w", padx=8, pady=8)

        # Name (read-only)
        ctk.CTkLabel(self, text="Name", font=FONT_NORMAL).grid(
            row=2, column=0, sticky="w", padx=(16, 8), pady=8)
        self.name_label = ctk.CTkLabel(self, text="–", font=FONT_NORMAL, anchor="w")
        self.name_label.grid(row=2, column=1, sticky="w", padx=8, pady=8)

        # XP
        ctk.CTkLabel(self, text="XP", font=FONT_NORMAL).grid(
            row=3, column=0, sticky="w", padx=(16, 8), pady=8)
        self.xp_var = ctk.StringVar()
        ctk.CTkEntry(self, textvariable=self.xp_var, font=FONT_NORMAL, width=200).grid(
            row=3, column=1, sticky="w", padx=8, pady=8)

        # XP Debt
        ctk.CTkLabel(self, text="XP Debt", font=FONT_NORMAL).grid(
            row=4, column=0, sticky="w", padx=(16, 8), pady=8)
        self.xp_debt_var = ctk.StringVar()
        ctk.CTkEntry(self, textvariable=self.xp_debt_var, font=FONT_NORMAL, width=200).grid(
            row=4, column=1, sticky="w", padx=8, pady=8)

        # Dead / Abandoned
        ctk.CTkLabel(self, text="Status", font=FONT_NORMAL).grid(
            row=5, column=0, sticky="w", padx=(16, 8), pady=8)
        status_frame = ctk.CTkFrame(self, fg_color="transparent")
        status_frame.grid(row=5, column=1, sticky="w", padx=8, pady=8)
        self.dead_var = ctk.BooleanVar()
        ctk.CTkCheckBox(status_frame, text="Dead", variable=self.dead_var,
                        font=FONT_NORMAL).pack(side="left", padx=(0, 16))
        self.abandoned_var = ctk.BooleanVar()
        ctk.CTkCheckBox(status_frame, text="Abandoned", variable=self.abandoned_var,
                        font=FONT_NORMAL).pack(side="left")

        ctk.CTkButton(self, text="Apply Stats", command=self._apply_stats, width=160).grid(
            row=6, column=0, columnspan=2, padx=16, pady=(16, 4), sticky="w")

        self.status_label = ctk.CTkLabel(self, text="", font=FONT_SMALL, text_color="gray")
        self.status_label.grid(row=7, column=0, columnspan=2, sticky="w", padx=16)

    def refresh(self):
        if self.editor.character_count == 0:
            return
        names = self.editor.get_character_names()
        self.char_menu.configure(values=names)
        self.char_var.set(names[0])
        self._load_current()

    def _on_char_change(self, value):
        idx = self.char_menu.cget("values").index(value)
        self.editor.select(idx)
        self._load_current()
        if self._on_char_change_cb:
            self._on_char_change_cb()

    def _load_current(self):
        self.name_label.configure(text=self.editor.name or "–")
        self.xp_var.set(str(self.editor.xp))
        self.xp_debt_var.set(str(self.editor.xp_debt))
        self.dead_var.set(self.editor.is_dead)
        self.abandoned_var.set(self.editor.is_abandoned)

    def _apply_stats(self):
        try:
            self.editor.xp = int(self.xp_var.get())
            self.editor.xp_debt = int(self.xp_debt_var.get())
            self.editor.is_dead = self.dead_var.get()
            self.editor.is_abandoned = self.abandoned_var.get()
            self.status_label.configure(text="Stats updated (not yet saved).",
                                        text_color="#3bba6b")
        except ValueError as e:
            messagebox.showerror("Invalid Value", str(e))


# ============================================================================
# Shared 3-panel catalog base
# ============================================================================

class _CatalogTab(ctk.CTkFrame):
    """
    Three-panel visual catalog:
      Left   — category selector with unlocked/total counts
      Middle — scrollable item list (catalog + save status)
      Right  — detail panel for selected item + Add/Remove button
    """

    def __init__(self, master, char_editor: CharacterEditor, **kwargs):
        super().__init__(master, **kwargs)
        self.editor = char_editor
        self._save_rownames: set = set()      # all RowNames currently in save
        self._catalog_items: list = []        # (key, row_name_or_none, title, ...)
        self._list_indices: list = []         # parallel to listbox; each entry is
                                              # (catalog_item_tuple, is_unlocked, save_rn)
        self._selected_category: Optional[str] = None
        self._build()

    # ── abstract interface ──────────────────────────────────────────────

    def _category_labels(self) -> List[str]:
        """Ordered list of category labels to show in left panel."""
        raise NotImplementedError

    def _category_count(self, label: str) -> int:
        """Total catalog items for this category."""
        raise NotImplementedError

    def _unlocked_count(self, label: str) -> int:
        """How many catalog items are unlocked in the save."""
        raise NotImplementedError

    def _load_catalog(self, label: str) -> list:
        """Return catalog rows for a category. Row format varies by subclass."""
        raise NotImplementedError

    def _is_save_unlocked(self, catalog_row) -> Tuple[bool, Optional[str], int]:
        """
        Check if catalog_row is in the save.
        Returns (is_unlocked, matched_save_rowname, rank).
        """
        raise NotImplementedError

    def _detail_text(self, catalog_row, is_unlocked: bool,
                     save_rn: Optional[str], rank: int) -> dict:
        """Return dict with keys: title, meta, desc, extra, rowname."""
        raise NotImplementedError

    def _add_rowname(self, catalog_row) -> str:
        """RowName to add when user clicks Add for this catalog item."""
        raise NotImplementedError

    def _remove_rowname(self, catalog_row, save_rn: Optional[str]) -> str:
        """RowName to remove."""
        return save_rn or self._add_rowname(catalog_row)

    # ── build UI ───────────────────────────────────────────────────────

    def _build(self):
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=3)
        self.columnconfigure(2, weight=2)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)

        # ── Left: category selector ──────────────────────────────────
        self._cat_frame = ctk.CTkScrollableFrame(self, width=180)
        self._cat_frame.grid(row=0, column=0, rowspan=2, sticky="nsew",
                             padx=(8, 4), pady=8)
        self._cat_frame.columnconfigure(0, weight=1)
        self._cat_buttons: dict = {}

        # ── Middle: item listbox ─────────────────────────────────────
        mid = ctk.CTkFrame(self)
        mid.grid(row=0, column=1, sticky="nsew", padx=4, pady=8)
        mid.rowconfigure(2, weight=1)
        mid.columnconfigure(0, weight=1)

        self._mid_title = ctk.CTkLabel(mid, text="Select a category →",
                                       font=FONT_TITLE, anchor="w")
        self._mid_title.grid(row=0, column=0, columnspan=2, sticky="ew",
                              padx=8, pady=(8, 2))

        self._mid_counts = ctk.CTkLabel(mid, text="", font=FONT_SMALL,
                                         text_color="gray", anchor="w")
        self._mid_counts.grid(row=1, column=0, columnspan=2, sticky="ew",
                               padx=8, pady=(0, 4))

        lf = ctk.CTkFrame(mid)
        lf.grid(row=2, column=0, sticky="nsew", padx=(4, 0), pady=(0, 4))
        lf.rowconfigure(0, weight=1)
        lf.columnconfigure(0, weight=1)

        self._listbox = tk.Listbox(
            lf, bg="#1e1e1e", fg="#d0d0d0", selectbackground="#1f4f8a",
            selectforeground="white", font=FONT_MONO,
            bd=0, highlightthickness=0, relief="flat",
            activestyle="none",
        )
        self._listbox.grid(row=0, column=0, sticky="nsew")
        sb = tk.Scrollbar(lf, orient="vertical", command=self._listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self._listbox.configure(yscrollcommand=sb.set)
        self._listbox.bind("<<ListboxSelect>>", self._on_item_select)

        search_row = ctk.CTkFrame(mid, fg_color="transparent")
        search_row.grid(row=3, column=0, columnspan=2, sticky="ew",
                        padx=4, pady=(0, 4))
        search_row.columnconfigure(0, weight=1)
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._render_list())
        ctk.CTkEntry(search_row, textvariable=self._search_var,
                     placeholder_text="Filter items…",
                     font=FONT_NORMAL).grid(row=0, column=0, sticky="ew")

        # ── Right: detail panel ──────────────────────────────────────
        right = ctk.CTkScrollableFrame(self, width=280)
        right.grid(row=0, column=2, sticky="nsew", padx=(4, 8), pady=8)
        right.columnconfigure(0, weight=1)

        self._det_title  = ctk.CTkLabel(right, text="", font=FONT_TITLE,
                                         wraplength=250, justify="left", anchor="nw")
        self._det_title.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 2))

        self._det_meta   = ctk.CTkLabel(right, text="", font=FONT_SMALL,
                                         text_color="gray", anchor="nw")
        self._det_meta.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 6))

        ctk.CTkFrame(right, height=1, fg_color="#3a3a3a").grid(
            row=2, column=0, sticky="ew", padx=8)

        self._det_desc   = ctk.CTkLabel(right, text="", font=FONT_SMALL,
                                         wraplength=250, justify="left", anchor="nw",
                                         text_color="#c8c8c8")
        self._det_desc.grid(row=3, column=0, sticky="ew", padx=8, pady=(6, 4))

        self._det_extra  = ctk.CTkLabel(right, text="", font=FONT_SMALL,
                                         wraplength=250, justify="left", anchor="nw",
                                         text_color="#7ecff4")
        self._det_extra.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 4))

        ctk.CTkFrame(right, height=1, fg_color="#3a3a3a").grid(
            row=5, column=0, sticky="ew", padx=8)

        self._det_rn_label = ctk.CTkLabel(right, text="RowName", font=FONT_SMALL,
                                           text_color="gray", anchor="w")
        self._det_rn_label.grid(row=6, column=0, sticky="ew", padx=8, pady=(6, 0))

        self._det_rowname = ctk.CTkLabel(right, text="", font=FONT_MONO,
                                          wraplength=250, justify="left", anchor="nw")
        self._det_rowname.grid(row=7, column=0, sticky="ew", padx=8, pady=(0, 8))

        self._det_status  = ctk.CTkLabel(right, text="", font=FONT_SMALL, anchor="w")
        self._det_status.grid(row=8, column=0, sticky="ew", padx=8, pady=2)

        self._toggle_btn = ctk.CTkButton(right, text="", font=FONT_NORMAL,
                                          command=self._toggle_selected)
        self._toggle_btn.grid(row=9, column=0, sticky="ew", padx=8, pady=(4, 8))
        self._toggle_btn.configure(state="disabled")

        # ── Bottom status bar ────────────────────────────────────────
        self._status = ctk.CTkLabel(self, text="", font=FONT_SMALL, text_color="gray")
        self._status.grid(row=1, column=1, columnspan=2, sticky="w", padx=12, pady=(0, 6))

        self._selected_list_idx: Optional[int] = None

    # ── category panel ─────────────────────────────────────────────────

    def _rebuild_cat_panel(self):
        for w in self._cat_frame.winfo_children():
            w.destroy()
        self._cat_buttons.clear()

        for label in self._category_labels():
            total     = self._category_count(label)
            unlocked  = self._unlocked_count(label)
            is_sel    = (label == self._selected_category)
            fg = "#1a4a7a" if is_sel else "transparent"

            btn = ctk.CTkButton(
                self._cat_frame,
                text=f"{label}\n{unlocked} / {total}",
                font=FONT_SMALL, anchor="w", height=46,
                fg_color=fg, hover_color="#1a4a7a",
                command=lambda lbl=label: self._select_category(lbl),
            )
            btn.grid(sticky="ew", padx=4, pady=2)
            self._cat_buttons[label] = btn

    def _select_category(self, label: str):
        self._selected_category = label
        # Update button highlights
        for lbl, btn in self._cat_buttons.items():
            btn.configure(fg_color="#1a4a7a" if lbl == label else "transparent")
        self._catalog_items = self._load_catalog(label)
        self._search_var.set("")
        self._render_list()
        self._clear_detail()

    # ── item list ──────────────────────────────────────────────────────

    def _render_list(self):
        q = self._search_var.get().lower()
        self._listbox.delete(0, tk.END)
        self._list_indices.clear()

        for item in self._catalog_items:
            title = self._item_title(item)
            if q and q not in title.lower():
                continue
            is_unlocked, save_rn, rank = self._is_save_unlocked(item)
            if is_unlocked:
                prefix = "✓"
                rank_str = f" [R{rank}]" if rank > 1 else ""
                fg = "#4ade80"   # green
            else:
                prefix = " "
                rank_str = ""
                fg = "#808080"   # gray

            text = f" {prefix}  {title}{rank_str}"
            self._listbox.insert(tk.END, text)
            self._listbox.itemconfig(tk.END, fg=fg)
            self._list_indices.append((item, is_unlocked, save_rn, rank))

        # Update middle header counts
        if self._selected_category:
            total    = len(self._catalog_items)
            unlocked = sum(1 for _, iu, _, _ in self._list_indices if iu)
            shown    = len(self._list_indices)
            extra    = f"  (filtered: {shown})" if q else ""
            self._mid_title.configure(text=self._selected_category)
            self._mid_counts.configure(
                text=f"{unlocked} unlocked  /  {total} in catalog{extra}")

    def _item_title(self, item) -> str:
        """Extract display title from a catalog row."""
        raise NotImplementedError

    def _on_item_select(self, _event=None):
        sel = self._listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self._list_indices):
            return
        self._selected_list_idx = idx
        item, is_unlocked, save_rn, rank = self._list_indices[idx]
        info = self._detail_text(item, is_unlocked, save_rn, rank)

        self._det_title.configure(text=info.get('title', ''))
        self._det_meta.configure(text=info.get('meta', ''))
        self._det_desc.configure(text=info.get('desc', ''))
        self._det_extra.configure(text=info.get('extra', ''))
        self._det_rowname.configure(text=info.get('rowname', ''))

        if is_unlocked:
            self._det_status.configure(text="✓  Unlocked in your save",
                                        text_color="#4ade80")
            self._toggle_btn.configure(text="Remove from save",
                                        fg_color="#7a1a1a", hover_color="#9a2a2a",
                                        state="normal")
        else:
            self._det_status.configure(text="  Not in your save",
                                        text_color="#808080")
            self._toggle_btn.configure(text="Add to save",
                                        fg_color="#1a4a7a", hover_color="#2a6ab0",
                                        state="normal")

    def _clear_detail(self):
        for lbl in (self._det_title, self._det_meta, self._det_desc,
                    self._det_extra, self._det_rowname, self._det_status):
            lbl.configure(text="")
        self._toggle_btn.configure(state="disabled", text="")
        self._selected_list_idx = None

    # ── add / remove ───────────────────────────────────────────────────

    def _toggle_selected(self):
        if self._selected_list_idx is None:
            return
        idx = self._selected_list_idx
        if idx >= len(self._list_indices):
            return
        item, is_unlocked, save_rn, rank = self._list_indices[idx]

        if is_unlocked:
            rn = self._remove_rowname(item, save_rn)
            self.editor.remove_talent(rn)
            self._status.configure(text=f"Removed '{rn}'", text_color="#e09b3d")
        else:
            rn = self._add_rowname(item)
            self.editor.add_talent(rn, rank=1)
            self._status.configure(text=f"Added '{rn}'", text_color="#4ade80")

        self._save_rownames = {t.row_name for t in self.editor.get_talents()}
        self._render_list()
        self._rebuild_cat_panel()
        # Re-select same row if still visible
        for i, (it, _, _, _) in enumerate(self._list_indices):
            if it is item:
                self._listbox.selection_set(i)
                self._on_item_select()
                break

    # ── refresh ────────────────────────────────────────────────────────

    def refresh(self):
        self._save_rownames = {t.row_name for t in self.editor.get_talents()}
        self._rebuild_cat_panel()
        if self._selected_category:
            self._catalog_items = self._load_catalog(self._selected_category)
            self._render_list()


# ============================================================================
# Tech Tree Tab
# ============================================================================

class TechTreeTab(_CatalogTab):

    def _category_labels(self) -> List[str]:
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


# ============================================================================
# Talents Tab
# ============================================================================

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


# ============================================================================
# Workshop Tab
# ============================================================================

class WorkshopTab(ctk.CTkFrame):
    def __init__(self, master, prof_editor: ProfileEditor, **kwargs):
        super().__init__(master, **kwargs)
        self.editor = prof_editor
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        header.columnconfigure(1, weight=1)

        ctk.CTkLabel(header, text="Workshop Unlocks", font=FONT_TITLE).grid(
            row=0, column=0, sticky="w")

        self.count_label = ctk.CTkLabel(header, text="", font=FONT_SMALL, text_color="gray")
        self.count_label.grid(row=0, column=1, sticky="e", padx=8)

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self._filter)
        ctk.CTkEntry(header, textvariable=self.search_var, placeholder_text="Filter…",
                     font=FONT_NORMAL, width=200).grid(row=0, column=2, padx=4)

        list_frame = ctk.CTkFrame(self)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            list_frame, bg="#2b2b2b", fg="white", selectbackground="#1f6aa5",
            font=FONT_MONO, bd=0, highlightthickness=0, relief="flat",
            selectmode=tk.EXTENDED
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        sb = tk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=sb.set)

        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.grid(row=2, column=0, sticky="ew", padx=8, pady=8)
        ctrl.columnconfigure(0, weight=1)

        add_row = ctk.CTkFrame(ctrl, fg_color="transparent")
        add_row.grid(row=0, column=0, sticky="ew", pady=4)
        add_row.columnconfigure(0, weight=1)
        self.add_var = ctk.StringVar()
        ctk.CTkEntry(add_row, textvariable=self.add_var,
                     placeholder_text="RowName  e.g. Workshop_Envirosuit",
                     font=FONT_NORMAL).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ctk.CTkButton(add_row, text="Add", width=60, command=self._add).grid(row=0, column=1)

        btn_row = ctk.CTkFrame(ctrl, fg_color="transparent")
        btn_row.grid(row=1, column=0, sticky="ew", pady=4)
        ctk.CTkButton(btn_row, text="Remove Selected", command=self._remove).pack(
            side="left", padx=(0, 8))
        ctk.CTkButton(btn_row, text="Clear All", fg_color="#c0392b",
                      hover_color="#962d22", command=self._clear_all).pack(side="left")

        self.status_label = ctk.CTkLabel(ctrl, text="", font=FONT_SMALL, text_color="gray")
        self.status_label.grid(row=2, column=0, sticky="w")

        self._all_entries: list = []

    def refresh(self):
        self._all_entries = self.editor.get_workshop_unlocks()
        self._render(self._all_entries)

    def _render(self, entries):
        self.listbox.delete(0, tk.END)
        for e in entries:
            self.listbox.insert(tk.END, f"Rank {e.rank}  {e.row_name}")
        self.count_label.configure(text=f"{len(self._all_entries)} unlocks")

    def _filter(self, *_):
        q = self.search_var.get().lower()
        filtered = [e for e in self._all_entries if q in e.row_name.lower()]
        self.listbox.delete(0, tk.END)
        for e in filtered:
            self.listbox.insert(tk.END, f"Rank {e.rank}  {e.row_name}")

    def _add(self):
        row_name = self.add_var.get().strip()
        if not row_name:
            return
        added = self.editor.add_workshop_unlock(row_name)
        self.add_var.set("")
        self._all_entries = self.editor.get_workshop_unlocks()
        self._filter()
        self.status_label.configure(
            text=f"Added '{row_name}'" if added else f"'{row_name}' already unlocked",
            text_color="#3bba6b" if added else "#e09b3d")

    def _remove(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        q = self.search_var.get().lower()
        visible = [e for e in self._all_entries if q in e.row_name.lower()]
        for i in sel:
            if i < len(visible):
                self.editor.remove_workshop_unlock(visible[i].row_name)
        self._all_entries = self.editor.get_workshop_unlocks()
        self._filter()

    def _clear_all(self):
        if not messagebox.askyesno("Clear Workshop", "Remove ALL workshop unlocks?"):
            return
        n = self.editor.clear_workshop_unlocks()
        self._all_entries = []
        self._render([])
        self.status_label.configure(text=f"Cleared {n} unlocks.", text_color="#e09b3d")


# ============================================================================
# Inventory Tab
# ============================================================================

class InventoryTab(ctk.CTkFrame):
    def __init__(self, master, inv_editor: InventoryEditor, **kwargs):
        super().__init__(master, **kwargs)
        self.editor = inv_editor
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        header.columnconfigure(2, weight=1)

        ctk.CTkLabel(header, text="Workshop Inventory", font=FONT_TITLE).grid(
            row=0, column=0, sticky="w")
        self.count_label = ctk.CTkLabel(header, text="", font=FONT_SMALL, text_color="gray")
        self.count_label.grid(row=0, column=1, padx=12)

        ctk.CTkButton(header, text="Repair All", width=100, command=self._repair_all).grid(
            row=0, column=3, padx=4)
        ctk.CTkButton(header, text="Remove Selected", width=130,
                      fg_color="#c0392b", hover_color="#962d22",
                      command=self._remove_selected).grid(row=0, column=4, padx=4)

        cols_frame = ctk.CTkFrame(self, fg_color="#1e1e1e")
        cols_frame.grid(row=1, column=0, sticky="ew", padx=8)
        for col, text in enumerate(["#", "Item", "Qty", "Durability"]):
            ctk.CTkLabel(cols_frame, text=text, font=FONT_SMALL, anchor="w",
                         text_color="gray").grid(row=0, column=col, padx=8, pady=2, sticky="w")

        list_frame = ctk.CTkFrame(self)
        list_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=4)
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            list_frame, bg="#2b2b2b", fg="white", selectbackground="#1f6aa5",
            font=FONT_MONO, bd=0, highlightthickness=0, relief="flat",
            selectmode=tk.EXTENDED
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        sb = tk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=sb.set)

        ctrl = ctk.CTkFrame(self, fg_color="transparent")
        ctrl.grid(row=3, column=0, sticky="ew", padx=8, pady=4)
        ctk.CTkButton(ctrl, text="Repair Selected", command=self._repair_selected).pack(
            side="left", padx=(0, 8))
        self.status_label = ctk.CTkLabel(ctrl, text="", font=FONT_SMALL, text_color="gray")
        self.status_label.pack(side="left")

        self._items = []

    def refresh(self):
        self._items = self.editor.get_items()
        self._render()

    def _render(self):
        self.listbox.delete(0, tk.END)
        for item in self._items:
            dur = f"{item.durability_pct:.0f}%" if item.durability_pct is not None else "N/A"
            self.listbox.insert(tk.END,
                f"{item.index:3d}  {item.display_name:<36}  {item.quantity:>3}  {dur:>8}")
        self.count_label.configure(text=f"{len(self._items)} items")

    def _repair_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        for i in sel:
            if i < len(self._items):
                self.editor.repair_item(self._items[i].index)
        self.refresh()
        self.status_label.configure(text=f"Repaired {len(sel)} item(s).", text_color="#3bba6b")

    def _repair_all(self):
        n = self.editor.repair_all()
        self.refresh()
        self.status_label.configure(text=f"Repaired {n} item(s).", text_color="#3bba6b")

    def _remove_selected(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        indices = [self._items[i].index for i in sel if i < len(self._items)]
        if not messagebox.askyesno("Remove Items", f"Remove {len(indices)} item(s)?"):
            return
        self.editor.remove_items(indices)
        self.refresh()
        self.status_label.configure(text=f"Removed {len(indices)} item(s).",
                                    text_color="#e09b3d")


# ============================================================================
# Profile Tab
# ============================================================================

class ProfileTab(ctk.CTkFrame):
    def __init__(self, master, prof_editor: ProfileEditor, **kwargs):
        super().__init__(master, **kwargs)
        self.editor = prof_editor
        self._build()

    def _build(self):
        self.columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Account Resources", font=FONT_TITLE).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(16, 8))

        self._vars = {}
        labels = {
            "Credits":  "Credits",
            "Exotics":  "Exotic Matter",
            "Refunds":  "Refund Tokens",
            "Licences": "Licences",
        }
        for r, (key, label) in enumerate(labels.items(), start=1):
            ctk.CTkLabel(self, text=label, font=FONT_NORMAL, anchor="w").grid(
                row=r, column=0, sticky="w", padx=(16, 8), pady=8)
            var = ctk.StringVar()
            self._vars[key] = var
            ctk.CTkEntry(self, textvariable=var, font=FONT_NORMAL, width=200).grid(
                row=r, column=1, sticky="w", padx=8, pady=8)

        ctk.CTkButton(self, text="Apply Resources", command=self._apply).grid(
            row=10, column=0, columnspan=2, padx=16, pady=(16, 4), sticky="w")

        self.status_label = ctk.CTkLabel(self, text="", font=FONT_SMALL, text_color="gray")
        self.status_label.grid(row=11, column=0, columnspan=2, sticky="w", padx=16)

    def refresh(self):
        for key, var in self._vars.items():
            var.set(str(self.editor.get_resource(key)))

    def _apply(self):
        try:
            for key, var in self._vars.items():
                val = int(var.get())
                self.editor.set_resource(key, val)
            self.status_label.configure(text="Resources updated (not yet saved).",
                                        text_color="#3bba6b")
        except ValueError as e:
            messagebox.showerror("Invalid Value", f"Please enter integers only.\n{e}")


# ============================================================================
# Main Application
# ============================================================================

_ALL_TABS = ("Mounts", "Character", "Tech Tree", "Talents",
             "Workshop", "Inventory", "Profile")


class IcarusEditorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Icarus Save Editor")
        self.geometry("1200x750")
        self.minsize(1000, 640)

        self._save_manager: Optional[SaveManager] = None
        self._mount_editor: Optional[MountEditor] = None
        self._char_editor: Optional[CharacterEditor] = None
        self._prof_editor: Optional[ProfileEditor] = None
        self._inv_editor: Optional[InventoryEditor] = None

        self._mounts_tab: Optional[MountsTab] = None
        self._char_tab: Optional[CharacterTab] = None
        self._tech_tab: Optional[TechTreeTab] = None
        self._talents_tab: Optional[TalentsTab] = None
        self._workshop_tab: Optional[WorkshopTab] = None
        self._inv_tab: Optional[InventoryTab] = None
        self._prof_tab: Optional[ProfileTab] = None

        self._build_ui()
        self._auto_load()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        top = ctk.CTkFrame(self, height=50, fg_color="#1a1a2e")
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(2, weight=1)

        ctk.CTkLabel(top, text="Icarus Save Editor", font=FONT_TITLE,
                     text_color="#4da6ff").pack(side="left", padx=16)

        self.steam_var = ctk.StringVar()
        self.steam_menu = ctk.CTkOptionMenu(top, variable=self.steam_var,
                                             values=["Loading…"], font=FONT_SMALL,
                                             command=self._on_steam_change, width=160)
        self.steam_menu.pack(side="left", padx=8, pady=8)

        ctk.CTkButton(top, text="Save All", width=90, command=self._save_all).pack(
            side="right", padx=8, pady=8)
        ctk.CTkButton(top, text="Save + Backup", width=120,
                      command=self._save_with_backup).pack(side="right", padx=4, pady=8)

        self.status_bar = ctk.CTkLabel(top, text="", font=FONT_SMALL, text_color="#aaa")
        self.status_bar.pack(side="right", padx=16)

        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

        for tab_name in _ALL_TABS:
            self.tabview.add(tab_name)
            self.tabview.tab(tab_name).rowconfigure(0, weight=1)
            self.tabview.tab(tab_name).columnconfigure(0, weight=1)

    # ------------------------------------------------------------------
    # Load logic
    # ------------------------------------------------------------------

    def _auto_load(self):
        steam_ids = find_steam_ids()
        if not steam_ids:
            self._set_status("No Icarus save data found.")
            return
        self.steam_menu.configure(values=steam_ids)
        self.steam_var.set(steam_ids[0])
        self._load(steam_ids[0])

    def _on_steam_change(self, value: str):
        self._load(value)

    def _load(self, steam_id: str):
        self._set_status(f"Loading {steam_id}…")
        try:
            mgr = SaveManager(steam_id)
            warnings = mgr.load_all()
            self._save_manager = mgr

            try:
                me = MountEditor(steam_id=steam_id)
                me.load()
                self._mount_editor = me
            except FileNotFoundError:
                self._mount_editor = None
                warnings.append("Mounts.json not found")

            if mgr.characters_data is not None:
                self._char_editor = CharacterEditor(mgr.characters_data)
            else:
                self._char_editor = None

            if mgr.profile_data is not None:
                self._prof_editor = ProfileEditor(mgr.profile_data)
            else:
                self._prof_editor = None

            if mgr.inventory_data is not None:
                self._inv_editor = InventoryEditor(mgr.inventory_data)
            else:
                self._inv_editor = None

            self._build_tabs()
            self._refresh_all()

            msg = f"Loaded {steam_id}"
            if warnings:
                msg += f"  ({'; '.join(warnings)})"
            self._set_status(msg)

        except Exception as e:
            messagebox.showerror("Load Error", str(e))
            self._set_status(f"Error: {e}")

    def _build_tabs(self):
        for tab_name in _ALL_TABS:
            for w in self.tabview.tab(tab_name).winfo_children():
                w.destroy()

        # Mounts
        if self._mount_editor:
            self._mounts_tab = MountsTab(
                self.tabview.tab("Mounts"), self._mount_editor)
            self._mounts_tab.grid(row=0, column=0, sticky="nsew")
        else:
            ctk.CTkLabel(self.tabview.tab("Mounts"),
                         text="Mounts.json not found.", font=FONT_NORMAL).grid()
            self._mounts_tab = None

        # Character (stats only)
        if self._char_editor:
            self._char_tab = CharacterTab(
                self.tabview.tab("Character"), self._char_editor,
                on_char_change=self._on_char_change)
            self._char_tab.grid(row=0, column=0, sticky="nsew")
        else:
            ctk.CTkLabel(self.tabview.tab("Character"),
                         text="Characters.json not found.", font=FONT_NORMAL).grid()
            self._char_tab = None

        # Tech Tree
        if self._char_editor:
            self._tech_tab = TechTreeTab(
                self.tabview.tab("Tech Tree"), self._char_editor)
            self._tech_tab.grid(row=0, column=0, sticky="nsew")
        else:
            ctk.CTkLabel(self.tabview.tab("Tech Tree"),
                         text="Characters.json not found.", font=FONT_NORMAL).grid()
            self._tech_tab = None

        # Talents
        if self._char_editor:
            self._talents_tab = TalentsTab(
                self.tabview.tab("Talents"), self._char_editor)
            self._talents_tab.grid(row=0, column=0, sticky="nsew")
        else:
            ctk.CTkLabel(self.tabview.tab("Talents"),
                         text="Characters.json not found.", font=FONT_NORMAL).grid()
            self._talents_tab = None

        # Workshop
        if self._prof_editor:
            self._workshop_tab = WorkshopTab(
                self.tabview.tab("Workshop"), self._prof_editor)
            self._workshop_tab.grid(row=0, column=0, sticky="nsew")
        else:
            ctk.CTkLabel(self.tabview.tab("Workshop"),
                         text="Profile.json not found.", font=FONT_NORMAL).grid()
            self._workshop_tab = None

        # Inventory
        if self._inv_editor:
            self._inv_tab = InventoryTab(
                self.tabview.tab("Inventory"), self._inv_editor)
            self._inv_tab.grid(row=0, column=0, sticky="nsew")
        else:
            ctk.CTkLabel(self.tabview.tab("Inventory"),
                         text="MetaInventory.json not found.", font=FONT_NORMAL).grid()
            self._inv_tab = None

        # Profile
        if self._prof_editor:
            self._prof_tab = ProfileTab(
                self.tabview.tab("Profile"), self._prof_editor)
            self._prof_tab.grid(row=0, column=0, sticky="nsew")
        else:
            ctk.CTkLabel(self.tabview.tab("Profile"),
                         text="Profile.json not found.", font=FONT_NORMAL).grid()
            self._prof_tab = None

    def _on_char_change(self):
        """Called when Character tab changes the selected character."""
        if self._tech_tab:
            self._tech_tab.refresh()
        if self._talents_tab:
            self._talents_tab.refresh()

    def _refresh_all(self):
        if self._mounts_tab:
            self._mounts_tab.refresh()
        if self._char_tab:
            self._char_tab.refresh()
        if self._tech_tab:
            self._tech_tab.refresh()
        if self._talents_tab:
            self._talents_tab.refresh()
        if self._workshop_tab:
            self._workshop_tab.refresh()
        if self._inv_tab:
            self._inv_tab.refresh()
        if self._prof_tab:
            self._prof_tab.refresh()

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def _save_all(self):
        self._do_save(backup=False)

    def _save_with_backup(self):
        self._do_save(backup=True)

    def _do_save(self, backup: bool):
        if not self._save_manager:
            messagebox.showinfo("Save", "No data loaded.")
            return
        try:
            results = self._save_manager.save_all(backup=backup)
            if self._mount_editor and self._mount_editor.is_loaded:
                self._mount_editor.save(backup=backup)
            saved = [f for f, _ in results]
            if self._mount_editor:
                saved.append("Mounts.json")
            self._set_status(f"Saved: {', '.join(saved)}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _set_status(self, msg: str):
        self.status_bar.configure(text=msg)


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    app = IcarusEditorApp()
    app.mainloop()
