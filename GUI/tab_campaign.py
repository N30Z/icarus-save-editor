"""Campaign tab — Mission completed toggle list.

Detects the campaign from the loaded GD.json (via ProspectManager), then
shows a checklist of missions whose completion state is stored as Talents in
Profile.json (via ProfileEditor).

Supported campaigns:
  - Quarrite Campaign   (Olympus)
  - Gargantuan Campaign (Styx)
  - Rimetusk Campaign   (Prometheus)
"""

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Dict, List, Optional

import customtkinter as ctk

from campaign_data import CAMPAIGNS, TYPE_COLORS, detect_campaign
from profile_editor import ProfileEditor
from GUI.constants import FONT_TITLE, FONT_NORMAL, FONT_SMALL, FONT_MONO, FONT_HEADER
from GUI.prospect_manager import ProspectManager


class CampaignTab(ctk.CTkFrame):
    """GUI tab: campaign mission completion toggles."""

    def __init__(self, master, prospect_manager: ProspectManager,
                 prof_editor: Optional[ProfileEditor] = None, **kwargs):
        super().__init__(master, **kwargs)
        self._manager = prospect_manager
        self._manager.register(self._on_manager_load)
        self._prof_editor = prof_editor

        self._current_campaign_id: Optional[str] = None
        self._check_vars: Dict[str, tk.BooleanVar] = {}   # row_name → BooleanVar

        self._build()
        self._refresh_prospect_list()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # ── Top bar: file selector ────────────────────────────────────────
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))

        ctk.CTkLabel(top, text="Campaign Missions", font=FONT_TITLE).pack(
            side="left", padx=(0, 12))

        self._prospect_var = tk.StringVar(value="– select save –")
        self._prospect_menu = ctk.CTkOptionMenu(
            top, variable=self._prospect_var,
            values=["– select save –"], font=FONT_SMALL,
            command=self._on_prospect_change, width=220)
        self._prospect_menu.pack(side="left", padx=4)

        ctk.CTkButton(top, text="Browse…", width=80,
                      command=self._browse_file).pack(side="left", padx=4)

        self._file_label = ctk.CTkLabel(top, text="No file loaded", font=FONT_SMALL,
                                         text_color="gray")
        self._file_label.pack(side="left", padx=8)

        # ── Action bar ────────────────────────────────────────────────────
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", padx=8, pady=4)

        ctk.CTkButton(actions, text="Mark All", width=90,
                      command=self._mark_all).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="Clear All", width=90,
                      fg_color="#5a2a2a", hover_color="#7a3a3a",
                      command=self._clear_all).pack(side="left", padx=4)
        ctk.CTkButton(actions, text="Apply to Profile", width=130,
                      fg_color="#1a6a1a", hover_color="#228b22",
                      command=self._apply).pack(side="left", padx=(16, 4))

        self._status_label = ctk.CTkLabel(actions, text="", font=FONT_SMALL, text_color="gray")
        self._status_label.pack(side="right", padx=8)

        # ── Scrollable mission list ───────────────────────────────────────
        self._scroll = ctk.CTkScrollableFrame(self, label_text="Campaign Missions")
        self._scroll.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._scroll.columnconfigure(0, weight=1)

        ctk.CTkLabel(self._scroll,
                     text="Load a prospect save to detect the campaign and list missions.",
                     font=FONT_NORMAL, text_color="gray").pack(padx=16, pady=16)

    # ── Prospect list helpers ─────────────────────────────────────────────────

    def _refresh_prospect_list(self):
        prospects = self._manager.list_prospects()
        if prospects:
            self._prospect_menu.configure(values=prospects)
            if self._manager.current_path:
                self._prospect_var.set(Path(self._manager.current_path).name)
        else:
            self._prospect_menu.configure(values=["– no saves found –"])
            self._prospect_var.set("– no saves found –")

    def _on_prospect_change(self, filename: str):
        if filename.startswith("–"):
            return
        self._manager.notify(self._manager.get_prospect_path(filename))

    def _browse_file(self):
        path = filedialog.askopenfilename(
            title="Open GD.json (Prospect Save)",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")],
        )
        if path:
            self._manager.notify(path)

    def _on_manager_load(self, path: str):
        self._load_gd(path)

    # ── File loading ──────────────────────────────────────────────────────────

    def _load_gd(self, path: str):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                gd_data = json.load(f)

            prospect_key = gd_data.get('ProspectInfo', {}).get('ProspectDTKey', '')

            # Sync dropdown selection
            fname = Path(path).name
            known = self._prospect_menu.cget("values")
            if fname in known:
                self._prospect_var.set(fname)

            display_path = path if len(path) <= 60 else "…" + path[-57:]
            self._file_label.configure(text=display_path)

            campaign_id = detect_campaign(prospect_key)
            self._current_campaign_id = campaign_id
            self._rebuild_mission_list(campaign_id, prospect_key)

        except Exception as exc:
            self._status_label.configure(text=f"Error: {exc}", text_color="#e05252")

    # ── Mission list ──────────────────────────────────────────────────────────

    def _rebuild_mission_list(self, campaign_id: Optional[str], prospect_key: str):
        for w in self._scroll.winfo_children():
            w.destroy()
        self._check_vars.clear()

        if not campaign_id:
            ctk.CTkLabel(
                self._scroll,
                text=(f"Could not determine campaign for prospect '{prospect_key}'.\n\n"
                      "Only GD.json files for the three Great Hunt campaigns\n"
                      "(Olympus / Styx / Prometheus) are supported."),
                font=FONT_NORMAL, text_color="#e09b3d", justify="left",
            ).pack(padx=16, pady=16)
            self._scroll.configure(label_text="Campaign Missions — unknown map")
            return

        campaign = CAMPAIGNS[campaign_id]
        missions: List[dict] = campaign['missions']

        # ── Campaign header ───────────────────────────────────────────────
        hdr = ctk.CTkFrame(self._scroll, fg_color="#1a1a2e")
        hdr.pack(fill="x", padx=4, pady=(4, 2))
        ctk.CTkLabel(hdr, text=campaign['name'], font=FONT_TITLE,
                     text_color="#4da6ff").pack(side="left", padx=12, pady=6)
        ctk.CTkLabel(hdr, text=campaign['subtitle'], font=FONT_NORMAL,
                     text_color="#888").pack(side="left", padx=4, pady=6)
        ctk.CTkLabel(hdr, text=f"Map: {campaign['map']}  |  key: {prospect_key}",
                     font=FONT_SMALL, text_color="#555").pack(side="right", padx=12, pady=6)

        if not self._prof_editor:
            ctk.CTkLabel(self._scroll,
                         text="Profile.json not loaded — cannot show mission completion.",
                         font=FONT_NORMAL, text_color="#e09b3d").pack(padx=16, pady=12)
            return

        # ── Column header ──────────────────────────────────────────────────
        col_hdr = ctk.CTkFrame(self._scroll, fg_color="#1e1e1e")
        col_hdr.pack(fill="x", padx=4, pady=(4, 2))
        col_hdr.columnconfigure(1, weight=1)
        for col, (txt, w) in enumerate([
            ("Done", 52), ("Mission", 0), ("Type", 82), ("Conflicts with", 0),
        ]):
            kw = {"width": w} if w else {}
            ctk.CTkLabel(col_hdr, text=txt, font=FONT_SMALL, text_color="gray",
                         anchor="w", **kw).grid(row=0, column=col, padx=(8, 4), pady=3,
                                                sticky="w")

        # ── One row per mission ────────────────────────────────────────────
        for i, m in enumerate(missions):
            row_name = m['row_name']
            is_done = self._prof_editor.has_workshop_unlock(row_name)
            var = tk.BooleanVar(value=is_done)
            self._check_vars[row_name] = var

            bg = "#242424" if i % 2 == 0 else "#2a2a2a"
            row_f = ctk.CTkFrame(self._scroll, fg_color=bg)
            row_f.pack(fill="x", padx=4, pady=1)
            row_f.columnconfigure(1, weight=1)

            # Checkbox
            ctk.CTkCheckBox(
                row_f, text="", variable=var, width=52,
                command=lambda rn=row_name: self._on_toggle(rn),
            ).grid(row=0, column=0, padx=(8, 4), pady=6, sticky="w")

            # Mission label + row_name (small)
            name_f = ctk.CTkFrame(row_f, fg_color="transparent")
            name_f.grid(row=0, column=1, sticky="ew", padx=4)
            ctk.CTkLabel(name_f, text=m['label'], font=FONT_NORMAL,
                         anchor="w").pack(side="left")
            ctk.CTkLabel(name_f, text=f"  {row_name}", font=FONT_MONO,
                         text_color="#555", anchor="w").pack(side="left")

            # Type badge
            type_color = TYPE_COLORS.get(m['type'], '#888')
            ctk.CTkLabel(row_f, text=m['type'], font=FONT_SMALL, width=82,
                         text_color=type_color, anchor="w").grid(
                row=0, column=2, padx=4, pady=6, sticky="w")

            # Conflicts
            if m['forbidden']:
                # Strip common GH_XX_ prefix for readability
                short = []
                for rn in m['forbidden']:
                    # e.g. GH_RG_D → D,  GH_Ape_E → E
                    parts = rn.split('_')
                    short.append(parts[-1] if len(parts) >= 3 else rn)
                ctk.CTkLabel(row_f, text="⊗ " + ", ".join(short),
                             font=FONT_SMALL, text_color="#e09b3d", anchor="w").grid(
                    row=0, column=3, padx=4, pady=6, sticky="w")

        self._update_status()
        self._scroll.configure(label_text=f"Campaign Missions  —  {campaign['name']}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _on_toggle(self, row_name: str):
        """When a Choice mission is checked, auto-uncheck its forbidden peers."""
        if not self._current_campaign_id:
            return
        var = self._check_vars.get(row_name)
        if not var or not var.get():
            self._update_status()
            return
        # Find mission entry and uncheck any forbidden peer
        missions = CAMPAIGNS[self._current_campaign_id]['missions']
        for m in missions:
            if m['row_name'] == row_name:
                for forb in m['forbidden']:
                    peer = self._check_vars.get(forb)
                    if peer:
                        peer.set(False)
                break
        self._update_status()

    def _update_status(self):
        if not self._check_vars:
            return
        done = sum(1 for v in self._check_vars.values() if v.get())
        total = len(self._check_vars)
        if done == total:
            self._status_label.configure(text=f"All {total} missions selected",
                                         text_color="#3bba6b")
        else:
            self._status_label.configure(
                text=f"{done}/{total} selected — click 'Apply to Profile' to save",
                text_color="#e09b3d")

    def _mark_all(self):
        for var in self._check_vars.values():
            var.set(True)
        self._update_status()

    def _clear_all(self):
        for var in self._check_vars.values():
            var.set(False)
        self._update_status()

    # ── Apply ──────────────────────────────────────────────────────────────────

    def _apply(self):
        if not self._prof_editor:
            self._status_label.configure(text="Profile.json not loaded.", text_color="#e09b3d")
            return
        if not self._check_vars:
            self._status_label.configure(text="No missions loaded.", text_color="#e09b3d")
            return

        added = removed = 0
        for row_name, var in self._check_vars.items():
            want = var.get()
            have = self._prof_editor.has_workshop_unlock(row_name)
            if want and not have:
                self._prof_editor.add_workshop_unlock(row_name, rank=1)
                added += 1
            elif not want and have:
                self._prof_editor.remove_workshop_unlock(row_name)
                removed += 1

        self._status_label.configure(
            text=f"Applied: +{added} completed, -{removed} removed.  Use 'Save All' to persist.",
            text_color="#3bba6b")
