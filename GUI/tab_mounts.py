"""Mounts tab for the Icarus Save Editor GUI."""

import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Optional

import customtkinter as ctk

from mount_editor import MountEditor
from mount_types import MOUNT_TYPES
from GUI.constants import FONT_TITLE, FONT_NORMAL, FONT_SMALL, FONT_MONO


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
