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
from tkinter import messagebox, simpledialog, filedialog
from typing import List, Optional, Tuple, Dict
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
from gd_inventory_editor import GdInventoryEditor, INVENTORY_NAMES, _get_dyn_value, DYN_DURABILITY, DYN_STACK_COUNT
from game_items import get_catalog, ItemInfo
from campaign_editor import CampaignEditor, CAMPAIGN_STAGES


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
# Prospect Inventory Tab  (GD.json — in-session player inventory)
# ============================================================================

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
    """GUI tab for editing player inventories in a GD.json prospect save."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
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

        # ── Top bar: file picker + player/inventory selectors ──
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        top.columnconfigure(4, weight=1)

        ctk.CTkLabel(top, text="Prospect Inventory", font=FONT_TITLE).grid(
            row=0, column=0, sticky="w", padx=(0, 12))

        ctk.CTkButton(top, text="Load GD.json", width=120,
                      command=self._pick_file).grid(row=0, column=1, padx=4)

        self._file_label = ctk.CTkLabel(top, text="No file loaded", font=FONT_SMALL,
                                         text_color="gray")
        self._file_label.grid(row=0, column=2, padx=8)

        # Player selector
        ctk.CTkLabel(top, text="Player:", font=FONT_NORMAL).grid(
            row=0, column=5, padx=(16, 4))
        self._player_var = ctk.StringVar(value="–")
        self._player_menu = ctk.CTkOptionMenu(top, variable=self._player_var,
                                               values=["–"], font=FONT_SMALL,
                                               command=self._on_player_change, width=180)
        self._player_menu.grid(row=0, column=6, padx=4)

        # Inventory selector
        ctk.CTkLabel(top, text="Inventory:", font=FONT_NORMAL).grid(
            row=0, column=7, padx=(12, 4))
        self._inv_var = ctk.StringVar(value="–")
        self._inv_menu = ctk.CTkOptionMenu(top, variable=self._inv_var,
                                            values=["–"], font=FONT_SMALL,
                                            command=self._on_inv_change, width=180)
        self._inv_menu.grid(row=0, column=8, padx=4)

        # ── Action bar ──
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=8, pady=4)
        actions.columnconfigure(6, weight=1)

        ctk.CTkButton(actions, text="Add Item", width=100,
                      command=self._add_item).grid(row=0, column=0, padx=4)
        ctk.CTkButton(actions, text="Clear Inventory", width=120,
                      fg_color="#c0392b", hover_color="#962d22",
                      command=self._clear_inventory).grid(row=0, column=1, padx=4)
        ctk.CTkButton(actions, text="Save GD.json", width=110,
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

        self._status_label = ctk.CTkLabel(actions, text="", font=FONT_SMALL,
                                           text_color="gray")
        self._status_label.grid(row=0, column=6, sticky="e", padx=8)

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

    # ── File loading ──────────────────────────────────────────────────

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Open GD.json (Prospect Save)",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return
        self._load_gd(path)

    def _load_gd(self, path: str):
        try:
            editor = GdInventoryEditor(path)
            editor.load()
            self._gd_editor = editor

            # Load item catalog (lazy)
            if not self._catalog:
                self._catalog = get_catalog()

            # Truncate display path
            display_path = path
            if len(display_path) > 60:
                display_path = "…" + display_path[-57:]
            self._file_label.configure(text=display_path)

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
            messagebox.showerror("Load Error", f"Failed to load GD.json:\n{e}")

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
            ctk.CTkLabel(self._grid_frame, text="Select a GD.json file, player, and inventory.",
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
            ("Durability", 90), ("", 200),
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
        """If the item has LivingItemSlots, render them as nested rows."""
        if not self._gd_editor or not self._current_steam_id:
            return

        # Find the actual slot FPropertyTag to inspect LivingItemSlots
        player = self._gd_editor.players.get(self._current_steam_id)
        if not player:
            return

        saved_inv = next((p for p in player.props if p.name == 'SavedInventories'), None)
        if not saved_inv:
            return

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

        # Check LivingItemSlots
        living = next((p for p in slot_prop.nested if p.name == 'LivingItemSlots'), None)
        if not living or not living.nested:
            return

        # Render nested items
        nested_frame = ctk.CTkFrame(parent_frame, fg_color="#1a2a3a")
        nested_frame.grid(row=1, column=0, columnspan=5, sticky="ew", padx=(50, 8), pady=(0, 4))
        nested_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(nested_frame, text="Attachments:", font=FONT_SMALL,
                     text_color="#7ecff4").grid(row=0, column=0, columnspan=4,
                                                 sticky="w", padx=8, pady=(4, 2))

        for i, sub_slot in enumerate(living.nested):
            sub_item = next((p for p in sub_slot.nested if p.name == 'ItemStaticData'), None)
            sub_loc = next((p for p in sub_slot.nested if p.name == 'Location'), None)

            if sub_item and sub_item.value:
                sub_name = sub_item.value
                sub_info = self._catalog.get(sub_name)
                sub_display = sub_info.display_name if sub_info else sub_name
                sub_dur = _get_dyn_value(sub_slot, DYN_DURABILITY)
                sub_count = _get_dyn_value(sub_slot, DYN_STACK_COUNT)

                loc_str = str(sub_loc.value) if sub_loc else "?"
                dur_str = f"Dur: {sub_dur}" if sub_dur is not None else ""
                count_str = f"x{sub_count}" if sub_count and sub_count > 1 else ""

                ctk.CTkLabel(nested_frame,
                    text=f"  [{loc_str}] {sub_display} ({sub_name}) {count_str} {dur_str}",
                    font=FONT_SMALL, text_color="#a0c0e0", anchor="w").grid(
                    row=i + 1, column=0, columnspan=4, sticky="w", padx=12, pady=1)

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

    # ── Save ──────────────────────────────────────────────────────────

    def _save_gd(self):
        if not self._gd_editor:
            self._status_label.configure(text="No file loaded.", text_color="#e09b3d")
            return
        try:
            self._gd_editor.save(backup=False)
            self._status_label.configure(text="Saved GD.json", text_color="#3bba6b")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _save_gd_backup(self):
        if not self._gd_editor:
            self._status_label.configure(text="No file loaded.", text_color="#e09b3d")
            return
        try:
            self._gd_editor.save(backup=True)
            self._status_label.configure(text="Saved GD.json (with backup)",
                                          text_color="#3bba6b")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))


# ============================================================================
# Campaign Tab
# ============================================================================

class CampaignTab(ctk.CTkFrame):
    """GUI tab for toggling ambient world spawning effects (GD.json campaign stages)."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self._ce: Optional[CampaignEditor] = None
        self._switches: Dict[str, ctk.CTkSwitch] = {}   # row_name → switch
        self._switch_vars: Dict[str, tk.BooleanVar] = {} # row_name → var
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # ── Top bar ──────────────────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        ctk.CTkLabel(top, text="Campaign Spawning", font=FONT_TITLE).pack(side="left", padx=(0, 16))

        ctk.CTkButton(top, text="Load GD.json", width=120,
                      command=self._pick_file).pack(side="left", padx=4)

        self._file_label = ctk.CTkLabel(top, text="No file loaded", font=FONT_SMALL,
                                         text_color="gray")
        self._file_label.pack(side="left", padx=8)

        # ── Action bar ───────────────────────────────────────────────────
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=8, pady=4)

        ctk.CTkButton(actions, text="Save GD.json", width=110,
                      fg_color="#1a6a1a", hover_color="#228b22",
                      command=self._save).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="Save + Backup", width=120,
                      fg_color="#1a6a1a", hover_color="#228b22",
                      command=self._save_backup).pack(side="left", padx=4)

        self._status_label = ctk.CTkLabel(actions, text="", font=FONT_SMALL, text_color="gray")
        self._status_label.pack(side="right", padx=8)

        # ── Toggle list ──────────────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(self, label_text="Ambient World Spawning Effects")
        scroll.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        scroll.columnconfigure(1, weight=1)

        note = ("Toggles control whether ambient world spawning is active.\n"
                "Campaign quest progress is NOT changed.")
        ctk.CTkLabel(scroll, text=note, font=FONT_SMALL, text_color="#aaa",
                     justify="left").grid(row=0, column=0, columnspan=3, sticky="w",
                                          padx=8, pady=(4, 12))

        for i, stage in enumerate(CAMPAIGN_STAGES, start=1):
            row_name = stage['row']

            var = tk.BooleanVar(value=False)
            self._switch_vars[row_name] = var

            sw = ctk.CTkSwitch(scroll, text="", variable=var, onvalue=True, offvalue=False,
                                width=50, state="disabled")
            sw.grid(row=i, column=0, padx=(8, 4), pady=6, sticky="w")
            self._switches[row_name] = sw

            # Effect label (bold) + description
            label_frame = ctk.CTkFrame(scroll, fg_color="transparent")
            label_frame.grid(row=i, column=1, sticky="w", padx=4)

            ctk.CTkLabel(label_frame,
                         text=f"{stage['label']}  —  {stage['effect']}",
                         font=FONT_NORMAL, anchor="w").pack(side="top", anchor="w")
            ctk.CTkLabel(label_frame, text=stage['description'],
                         font=FONT_SMALL, text_color="#aaa", anchor="w").pack(side="top", anchor="w")

            # Row name tag on the right
            ctk.CTkLabel(scroll, text=row_name, font=FONT_MONO,
                         text_color="#666").grid(row=i, column=2, padx=12, sticky="e")

        scroll.columnconfigure(2, weight=0)

    # ── File loading ──────────────────────────────────────────────────

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Open GD.json (Prospect Save)",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return
        self._load_gd(path)

    def _load_gd(self, path: str):
        try:
            ce = CampaignEditor(path)
            ce.load()
            self._ce = ce

            display_path = path if len(path) <= 60 else "…" + path[-57:]
            self._file_label.configure(text=display_path)

            active = ce.get_active_talents()
            for row_name, var in self._switch_vars.items():
                var.set(row_name in active)
                self._switches[row_name].configure(state="normal")

            self._status_label.configure(
                text=f"Loaded  ({len(active)} active stage(s))", text_color="#3bba6b")

        except Exception as exc:
            self._status_label.configure(text=f"Error: {exc}", text_color="#e05252")

    # ── Save ──────────────────────────────────────────────────────────

    def _save(self):
        self._do_save(backup=False)

    def _save_backup(self):
        self._do_save(backup=True)

    def _do_save(self, backup: bool):
        if not self._ce:
            self._status_label.configure(text="No file loaded.", text_color="#e09b3d")
            return
        try:
            for row_name, var in self._switch_vars.items():
                self._ce.set_talent(row_name, var.get())
            self._ce.save(backup=backup)
            active = self._ce.get_active_talents()
            self._status_label.configure(
                text=f"Saved  ({len(active)} active stage(s))", text_color="#3bba6b")
        except Exception as exc:
            self._status_label.configure(text=f"Error: {exc}", text_color="#e05252")


# ============================================================================
# Main Application
# ============================================================================

_ALL_TABS = ("Mounts", "Character", "Tech Tree", "Talents",
             "Workshop", "Inventory", "Prospect Inventory", "Campaign", "Profile")


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
        self._prospect_inv_tab: Optional[ProspectInventoryTab] = None
        self._campaign_tab: Optional[CampaignTab] = None
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

        # Prospect Inventory (GD.json — always available, uses file picker)
        self._prospect_inv_tab = ProspectInventoryTab(
            self.tabview.tab("Prospect Inventory"))
        self._prospect_inv_tab.grid(row=0, column=0, sticky="nsew")

        # Campaign (GD.json — always available, uses file picker)
        self._campaign_tab = CampaignTab(self.tabview.tab("Campaign"))
        self._campaign_tab.grid(row=0, column=0, sticky="nsew")

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
