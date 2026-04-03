"""Shared 3-panel catalog base class for Tech Tree and Talents tabs."""

import tkinter as tk
from typing import List, Optional, Tuple

import customtkinter as ctk

from character_editor import CharacterEditor
from GUI.constants import FONT_TITLE, FONT_NORMAL, FONT_SMALL, FONT_MONO, FONT_HEADER


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
