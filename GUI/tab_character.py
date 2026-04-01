"""Character + Profile tab for the Icarus Save Editor GUI.

Left column  – Character Stats  (XP, XP Debt, Dead/Abandoned)
Right column – Account Resources (Credits, Exotics, Refund Tokens, Licences)
"""

from tkinter import messagebox
from typing import Optional

import customtkinter as ctk

from character_editor import CharacterEditor
from profile_editor import ProfileEditor
from GUI.constants import FONT_TITLE, FONT_NORMAL, FONT_SMALL


class CharacterTab(ctk.CTkFrame):
    def __init__(self, master, char_editor: CharacterEditor,
                 prof_editor: Optional[ProfileEditor] = None,
                 on_char_change=None, **kwargs):
        super().__init__(master, **kwargs)
        self.char_editor = char_editor
        self.prof_editor = prof_editor
        self._on_char_change_cb = on_char_change
        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self._build_left()
        self._build_right()

    def _build_left(self):
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(16, 8), pady=16)
        left.columnconfigure(1, weight=1)

        ctk.CTkLabel(left, text="Character Stats", font=FONT_TITLE).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        # Character selector
        ctk.CTkLabel(left, text="Character", font=FONT_NORMAL).grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=8)
        self.char_var = ctk.StringVar()
        self.char_menu = ctk.CTkOptionMenu(left, variable=self.char_var, values=["–"],
                                           font=FONT_NORMAL, command=self._on_char_change,
                                           width=220)
        self.char_menu.grid(row=1, column=1, sticky="w", pady=8)

        # Name (read-only)
        ctk.CTkLabel(left, text="Name", font=FONT_NORMAL).grid(
            row=2, column=0, sticky="w", padx=(0, 8), pady=8)
        self.name_label = ctk.CTkLabel(left, text="–", font=FONT_NORMAL, anchor="w")
        self.name_label.grid(row=2, column=1, sticky="w", pady=8)

        # XP
        ctk.CTkLabel(left, text="XP", font=FONT_NORMAL).grid(
            row=3, column=0, sticky="w", padx=(0, 8), pady=8)
        self.xp_var = ctk.StringVar()
        ctk.CTkEntry(left, textvariable=self.xp_var, font=FONT_NORMAL, width=200).grid(
            row=3, column=1, sticky="w", pady=8)

        # XP Debt
        ctk.CTkLabel(left, text="XP Debt", font=FONT_NORMAL).grid(
            row=4, column=0, sticky="w", padx=(0, 8), pady=8)
        self.xp_debt_var = ctk.StringVar()
        ctk.CTkEntry(left, textvariable=self.xp_debt_var, font=FONT_NORMAL, width=200).grid(
            row=4, column=1, sticky="w", pady=8)

        # Dead / Abandoned
        ctk.CTkLabel(left, text="Status", font=FONT_NORMAL).grid(
            row=5, column=0, sticky="w", padx=(0, 8), pady=8)
        status_frame = ctk.CTkFrame(left, fg_color="transparent")
        status_frame.grid(row=5, column=1, sticky="w", pady=8)
        self.dead_var = ctk.BooleanVar()
        ctk.CTkCheckBox(status_frame, text="Dead", variable=self.dead_var,
                        font=FONT_NORMAL).pack(side="left", padx=(0, 16))
        self.abandoned_var = ctk.BooleanVar()
        ctk.CTkCheckBox(status_frame, text="Abandoned", variable=self.abandoned_var,
                        font=FONT_NORMAL).pack(side="left")

        ctk.CTkButton(left, text="Apply Stats", command=self._apply_stats, width=160).grid(
            row=6, column=0, columnspan=2, pady=(16, 4), sticky="w")

        self._char_status = ctk.CTkLabel(left, text="", font=FONT_SMALL, text_color="gray")
        self._char_status.grid(row=7, column=0, columnspan=2, sticky="w")

    def _build_right(self):
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 16), pady=16)
        right.columnconfigure(1, weight=1)

        ctk.CTkLabel(right, text="Account Resources", font=FONT_TITLE).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        if not self.prof_editor:
            ctk.CTkLabel(right, text="Profile.json not loaded.",
                         font=FONT_NORMAL, text_color="gray").grid(
                row=1, column=0, columnspan=2, sticky="w", pady=8)
            return

        self._res_vars = {}
        labels = {
            "Credits":  "Credits",
            "Exotics":  "Exotic Matter",
            "Refunds":  "Refund Tokens",
            "Licences": "Licences",
        }
        for r, (key, label) in enumerate(labels.items(), start=1):
            ctk.CTkLabel(right, text=label, font=FONT_NORMAL, anchor="w").grid(
                row=r, column=0, sticky="w", padx=(0, 8), pady=8)
            var = ctk.StringVar()
            self._res_vars[key] = var
            ctk.CTkEntry(right, textvariable=var, font=FONT_NORMAL, width=200).grid(
                row=r, column=1, sticky="w", pady=8)

        ctk.CTkButton(right, text="Apply Resources", command=self._apply_resources,
                      width=160).grid(row=10, column=0, columnspan=2, pady=(16, 4), sticky="w")

        self._res_status = ctk.CTkLabel(right, text="", font=FONT_SMALL, text_color="gray")
        self._res_status.grid(row=11, column=0, columnspan=2, sticky="w")

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self):
        # Character side
        if self.char_editor.character_count > 0:
            names = self.char_editor.get_character_names()
            self.char_menu.configure(values=names)
            self.char_var.set(names[0])
            self._load_current_char()

        # Resources side
        if self.prof_editor and hasattr(self, "_res_vars"):
            for key, var in self._res_vars.items():
                var.set(str(self.prof_editor.get_resource(key)))

    # ── Char helpers ──────────────────────────────────────────────────────────

    def _on_char_change(self, value):
        idx = self.char_menu.cget("values").index(value)
        self.char_editor.select(idx)
        self._load_current_char()
        if self._on_char_change_cb:
            self._on_char_change_cb()

    def _load_current_char(self):
        self.name_label.configure(text=self.char_editor.name or "–")
        self.xp_var.set(str(self.char_editor.xp))
        self.xp_debt_var.set(str(self.char_editor.xp_debt))
        self.dead_var.set(self.char_editor.is_dead)
        self.abandoned_var.set(self.char_editor.is_abandoned)

    def _apply_stats(self):
        try:
            self.char_editor.xp = int(self.xp_var.get())
            self.char_editor.xp_debt = int(self.xp_debt_var.get())
            self.char_editor.is_dead = self.dead_var.get()
            self.char_editor.is_abandoned = self.abandoned_var.get()
            self._char_status.configure(text="Stats updated (not yet saved).",
                                        text_color="#3bba6b")
        except ValueError as e:
            messagebox.showerror("Invalid Value", str(e))

    # ── Resources helpers ─────────────────────────────────────────────────────

    def _apply_resources(self):
        if not self.prof_editor or not hasattr(self, "_res_vars"):
            return
        try:
            for key, var in self._res_vars.items():
                self.prof_editor.set_resource(key, int(var.get()))
            self._res_status.configure(text="Resources updated (not yet saved).",
                                       text_color="#3bba6b")
        except ValueError as e:
            messagebox.showerror("Invalid Value", f"Please enter integers only.\n{e}")
