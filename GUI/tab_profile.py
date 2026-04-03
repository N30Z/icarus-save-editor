"""Profile tab for the Icarus Save Editor GUI."""

from tkinter import messagebox

import customtkinter as ctk

from profile_editor import ProfileEditor
from GUI.constants import FONT_TITLE, FONT_NORMAL, FONT_SMALL


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
