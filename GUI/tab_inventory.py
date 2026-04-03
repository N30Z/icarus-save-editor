"""Inventory tab for the Icarus Save Editor GUI."""

import json
import tkinter as tk
from tkinter import messagebox, filedialog

import customtkinter as ctk

from inventory_editor import InventoryEditor
from GUI.constants import FONT_TITLE, FONT_NORMAL, FONT_SMALL, FONT_MONO


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
        ctk.CTkButton(header, text="Export", width=80,
                      fg_color="#1a5276", hover_color="#1a3a5c",
                      command=self._export_inventory).grid(row=0, column=5, padx=4)
        ctk.CTkButton(header, text="Import", width=80,
                      fg_color="#1a5276", hover_color="#1a3a5c",
                      command=self._import_inventory).grid(row=0, column=6, padx=4)

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

    def _export_inventory(self):
        path = filedialog.asksaveasfilename(
            title="Export Workshop Inventory",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
            initialfile="meta_inventory_export.json",
        )
        if not path:
            return
        try:
            data = self.editor.export_inventory()
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.status_label.configure(
                text=f"Exported {len(data['items'])} item(s) to file.", text_color="#3bba6b")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _import_inventory(self):
        path = filedialog.askopenfilename(
            title="Import Workshop Inventory",
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

        if data.get('type') != 'icarus_meta_inventory':
            if not messagebox.askyesno(
                    "Wrong File Type",
                    "This file does not look like a Workshop Inventory export.\n"
                    "Import anyway?"):
                return

        merge = messagebox.askyesnocancel(
            "Import Mode",
            "Yes  = Merge  (keep existing items, append new ones)\n"
            "No   = Replace (clear all existing items first)\n"
            "Cancel = Abort")
        if merge is None:
            return

        try:
            n = self.editor.import_inventory(data, merge=merge)
            self.refresh()
            mode_str = "merged" if merge else "replaced"
            self.status_label.configure(
                text=f"Imported {n} item(s) ({mode_str}). Click Save All to persist.",
                text_color="#3bba6b")
        except Exception as e:
            messagebox.showerror("Import Error", str(e))

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
