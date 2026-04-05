#!/usr/bin/env python3
"""
Icarus Save Editor - GUI
========================

CustomTkinter-based desktop editor for Icarus save files.

Tabs:
  - Character        : XP, XP Debt, Dead/Abandoned + Account Resources (merged)
  - Tech Tree        : Blueprint/crafting unlocks grouped by tier
  - Talents          : Character perk bonuses grouped by tree/subtree
  - Workshop         : Workshop unlocks (Profile.json Talents)
  - Inventory        : MetaInventory items (repair, remove)
  - Mounts           : List / edit all mounts (name, level, type, skin, clone, delete)
  - Prospect Inventory : In-session player inventory editor (savegame.json, shared save)
  - Campaign         : Rock Golem spawning controls (savegame.json, shared save)
  - Profile          : (merged into Character tab)

Usage:
    python gui_main.py
"""

from tkinter import messagebox
from typing import Optional
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from save_manager import SaveManager, find_steam_ids
from character_editor import CharacterEditor
from profile_editor import ProfileEditor
from inventory_editor import InventoryEditor
from mount_editor import MountEditor, get_default_mounts_path

from GUI.constants import FONT_TITLE, FONT_NORMAL, FONT_SMALL
from GUI.prospect_manager import ProspectManager
from GUI.tab_mounts import MountsTab
from GUI.tab_character import CharacterTab
from GUI.tab_techtree import TechTreeTab
from GUI.tab_talents import TalentsTab
from GUI.tab_workshop import WorkshopTab
from GUI.tab_inventory import InventoryTab
from GUI.tab_prospect_inventory import ProspectInventoryTab
from GUI.tab_campaign import CampaignTab


# ============================================================================
# Main Application
# ============================================================================

_ALL_TABS = ("Character", "Tech Tree", "Talents",
             "Workshop", "Inventory", "Mounts", "Prospect Inventory", "Campaign")


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
        self._prospect_manager: Optional[ProspectManager] = None

        self._char_tab: Optional[CharacterTab] = None
        self._tech_tab: Optional[TechTreeTab] = None
        self._talents_tab: Optional[TalentsTab] = None
        self._workshop_tab: Optional[WorkshopTab] = None
        self._inv_tab: Optional[InventoryTab] = None
        self._mounts_tab: Optional[MountsTab] = None
        self._prospect_inv_tab: Optional[ProspectInventoryTab] = None
        self._campaign_tab: Optional[CampaignTab] = None

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

        # Separator
        ctk.CTkLabel(top, text="|", text_color="#444", font=FONT_SMALL).pack(
            side="left", padx=2)

        # Prospect save selector (shared by Prospect Inventory + Campaign tabs)
        self._prospect_var = tk.StringVar(value="– select save –")
        self._prospect_menu = ctk.CTkOptionMenu(
            top, variable=self._prospect_var,
            values=["– select save –"], font=FONT_SMALL,
            command=self._on_prospect_change, width=200)
        self._prospect_menu.pack(side="left", padx=4, pady=8)

        ctk.CTkButton(top, text="Browse…", width=72,
                      command=self._browse_prospect).pack(side="left", padx=2, pady=8)

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

            # Shared prospect save manager (Prospects subfolder)
            self._prospect_manager = ProspectManager(steam_id)
            self._refresh_prospect_menu()

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

        # Character + Profile (merged, first tab)
        if self._char_editor:
            self._char_tab = CharacterTab(
                self.tabview.tab("Character"),
                char_editor=self._char_editor,
                prof_editor=self._prof_editor,
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

        # Mounts
        if self._mount_editor:
            self._mounts_tab = MountsTab(
                self.tabview.tab("Mounts"), self._mount_editor)
            self._mounts_tab.grid(row=0, column=0, sticky="nsew")
        else:
            ctk.CTkLabel(self.tabview.tab("Mounts"),
                         text="Mounts.json not found.", font=FONT_NORMAL).grid()
            self._mounts_tab = None

        # Prospect Inventory — shared ProspectManager
        self._prospect_inv_tab = ProspectInventoryTab(
            self.tabview.tab("Prospect Inventory"),
            prospect_manager=self._prospect_manager)
        self._prospect_inv_tab.grid(row=0, column=0, sticky="nsew")

        # Campaign — shared ProspectManager + prof_editor for mission completion
        self._campaign_tab = CampaignTab(
            self.tabview.tab("Campaign"),
            prospect_manager=self._prospect_manager,
            prof_editor=self._prof_editor)
        self._campaign_tab.grid(row=0, column=0, sticky="nsew")

    # ------------------------------------------------------------------
    # Prospect save (topbar)
    # ------------------------------------------------------------------

    def _refresh_prospect_menu(self):
        if not self._prospect_manager:
            return
        prospects = self._prospect_manager.list_prospects()
        if prospects:
            self._prospect_menu.configure(values=prospects)
            if self._prospect_manager.current_path:
                self._prospect_var.set(Path(self._prospect_manager.current_path).name)
            else:
                self._prospect_var.set(prospects[0])
        else:
            self._prospect_menu.configure(values=["– no saves found –"])
            self._prospect_var.set("– no saves found –")

    def _on_prospect_change(self, filename: str):
        if filename.startswith("–") or not self._prospect_manager:
            return
        path = self._prospect_manager.get_prospect_path(filename)
        self._prospect_manager.notify(path)

    def _browse_prospect(self):
        path = filedialog.askopenfilename(
            title="Open savegame.json (Prospect Save)",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if path and self._prospect_manager:
            self._prospect_manager.notify(path)
            fname = Path(path).name
            known = self._prospect_menu.cget("values")
            if fname in known:
                self._prospect_var.set(fname)

    def _on_char_change(self):
        """Called when Character tab changes the selected character."""
        if self._tech_tab:
            self._tech_tab.refresh()
        if self._talents_tab:
            self._talents_tab.refresh()

    def _refresh_all(self):
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
        if self._mounts_tab:
            self._mounts_tab.refresh()

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
