"""Workshop tab for the Icarus Save Editor GUI."""

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from profile_editor import ProfileEditor
from GUI.constants import FONT_TITLE, FONT_NORMAL, FONT_SMALL, FONT_MONO


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
