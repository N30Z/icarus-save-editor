"""Campaign tab — split view: campaign missions (left) + regular missions (right).

Left panel
----------
Detects the active campaign from the loaded savegame.json (via ProspectManager) and
shows a completion checklist.  Campaign detection relies on the ProspectDTKey
stored inside the file.

Right panel
-----------
Lists all regular prospect missions (Olympus / Styx / Prometheus / Elysium)
grouped by map.  Completion state is read from / written to the same
Profile.json Talents array used by the campaign panel.

Supported campaigns (left panel):
  - Quarrite Campaign   (Olympus)
  - Gargantuan Campaign (Styx)
  - Rimetusk Campaign   (Prometheus)
"""

import json
import tkinter as tk
from pathlib import Path
from typing import Dict, List, Optional

import customtkinter as ctk

from campaign_data import CAMPAIGNS, REGULAR_MISSION_GROUPS, TYPE_COLORS, detect_campaign
from profile_editor import ProfileEditor
from GUI.constants import FONT_TITLE, FONT_NORMAL, FONT_SMALL, FONT_MONO, FONT_HEADER
from GUI.prospect_manager import ProspectManager


class CampaignTab(ctk.CTkFrame):
    """GUI tab: campaign mission completion toggles (left) + regular missions (right)."""

    def __init__(self, master, prospect_manager: ProspectManager,
                 prof_editor: Optional[ProfileEditor] = None, **kwargs):
        super().__init__(master, **kwargs)
        self._manager = prospect_manager
        self._manager.register(self._on_manager_load)
        self._prof_editor = prof_editor

        self._current_campaign_id: Optional[str] = None
        # row_name → BooleanVar for campaign missions
        self._campaign_vars: Dict[str, tk.BooleanVar] = {}
        # row_name → BooleanVar for regular missions
        self._regular_vars: Dict[str, tk.BooleanVar] = {}

        self._build()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        # ── Left panel: Campaign Missions ─────────────────────────────────
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(8, 4), pady=8)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        # Action bar
        left_actions = ctk.CTkFrame(left, fg_color="transparent")
        left_actions.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        ctk.CTkLabel(left_actions, text="Campaign Missions",
                     font=FONT_TITLE).pack(side="left", padx=(0, 12))
        ctk.CTkButton(left_actions, text="Mark All", width=80,
                      command=self._campaign_mark_all).pack(side="left", padx=2)
        ctk.CTkButton(left_actions, text="Clear All", width=80,
                      fg_color="#5a2a2a", hover_color="#7a3a3a",
                      command=self._campaign_clear_all).pack(side="left", padx=2)
        ctk.CTkButton(left_actions, text="Apply", width=80,
                      fg_color="#1a6a1a", hover_color="#228b22",
                      command=self._campaign_apply).pack(side="left", padx=(12, 2))

        self._campaign_status = ctk.CTkLabel(left_actions, text="", font=FONT_SMALL,
                                              text_color="gray")
        self._campaign_status.pack(side="right", padx=4)

        # Scrollable mission list
        self._campaign_scroll = ctk.CTkScrollableFrame(left, label_text="Campaign Missions")
        self._campaign_scroll.grid(row=1, column=0, sticky="nsew")
        self._campaign_scroll.columnconfigure(0, weight=1)

        ctk.CTkLabel(self._campaign_scroll,
                     text="Load a prospect save (top bar) to detect the campaign.",
                     font=FONT_NORMAL, text_color="gray").pack(padx=16, pady=16)

        # ── Divider ───────────────────────────────────────────────────────
        ctk.CTkFrame(self, width=2, fg_color="#333").grid(
            row=0, column=0, sticky="ns", padx=(0, 0))

        # ── Right panel: Regular Missions ─────────────────────────────────
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=8)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        # Action bar
        right_actions = ctk.CTkFrame(right, fg_color="transparent")
        right_actions.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        ctk.CTkLabel(right_actions, text="Prospect Missions",
                     font=FONT_TITLE).pack(side="left", padx=(0, 12))
        ctk.CTkButton(right_actions, text="Mark All", width=80,
                      command=self._regular_mark_all).pack(side="left", padx=2)
        ctk.CTkButton(right_actions, text="Clear All", width=80,
                      fg_color="#5a2a2a", hover_color="#7a3a3a",
                      command=self._regular_clear_all).pack(side="left", padx=2)
        ctk.CTkButton(right_actions, text="Apply", width=80,
                      fg_color="#1a6a1a", hover_color="#228b22",
                      command=self._regular_apply).pack(side="left", padx=(12, 2))

        self._regular_status = ctk.CTkLabel(right_actions, text="", font=FONT_SMALL,
                                             text_color="gray")
        self._regular_status.pack(side="right", padx=4)

        # Scrollable mission list
        self._regular_scroll = ctk.CTkScrollableFrame(right, label_text="Prospect Missions")
        self._regular_scroll.grid(row=1, column=0, sticky="nsew")
        self._regular_scroll.columnconfigure(0, weight=1)

        self._build_regular_missions()

    # ── Regular missions (right panel) ────────────────────────────────────────

    def _build_regular_missions(self):
        """Populate the regular missions panel from REGULAR_MISSION_GROUPS."""
        for w in self._regular_scroll.winfo_children():
            w.destroy()
        self._regular_vars.clear()

        if not self._prof_editor:
            ctk.CTkLabel(self._regular_scroll,
                         text="Profile.json not loaded.",
                         font=FONT_NORMAL, text_color="#e09b3d").pack(padx=16, pady=12)
            return

        row_idx = 0
        for group in REGULAR_MISSION_GROUPS:
            # Group header
            hdr = ctk.CTkFrame(self._regular_scroll, fg_color="#1a1a2e")
            hdr.pack(fill="x", padx=4, pady=(6, 2))
            ctk.CTkLabel(hdr, text=group['name'], font=FONT_HEADER,
                         text_color=group['color']).pack(side="left", padx=12, pady=5)

            for m in group['missions']:
                row_name = m['row_name']
                is_done = self._prof_editor.has_workshop_unlock(row_name)
                var = tk.BooleanVar(value=is_done)
                self._regular_vars[row_name] = var

                bg = "#242424" if row_idx % 2 == 0 else "#2a2a2a"
                row_f = ctk.CTkFrame(self._regular_scroll, fg_color=bg)
                row_f.pack(fill="x", padx=4, pady=1)
                row_f.columnconfigure(1, weight=1)

                ctk.CTkCheckBox(
                    row_f, text="", variable=var, width=36,
                    command=self._update_regular_status,
                ).grid(row=0, column=0, rowspan=2, padx=(8, 4), pady=5, sticky="nw")

                # Top line: name + row_name
                top_line = ctk.CTkFrame(row_f, fg_color="transparent")
                top_line.grid(row=0, column=1, sticky="ew", padx=4, pady=(5, 0))
                ctk.CTkLabel(top_line, text=m['label'], font=FONT_NORMAL,
                             anchor="w").pack(side="left")
                ctk.CTkLabel(top_line, text=f"  {row_name}", font=FONT_MONO,
                             text_color="#555", anchor="w").pack(side="left")

                # Description line
                if m.get('description'):
                    ctk.CTkLabel(row_f, text=m['description'], font=FONT_SMALL,
                                 text_color="#666", anchor="w").grid(
                        row=1, column=1, sticky="ew", padx=4, pady=(0, 5))

                row_idx += 1

        self._update_regular_status()

    def refresh_regular_missions(self):
        """Re-read completion state for all regular missions (call after prof_editor swap)."""
        for row_name, var in self._regular_vars.items():
            if self._prof_editor:
                var.set(self._prof_editor.has_workshop_unlock(row_name))
        self._update_regular_status()

    # ── ProspectManager callback ───────────────────────────────────────────────

    def _on_manager_load(self, path: str):
        self._load_gd(path)

    # ── File loading ──────────────────────────────────────────────────────────

    def _load_gd(self, path: str):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                gd_data = json.load(f)

            prospect_key = gd_data.get('ProspectInfo', {}).get('ProspectDTKey', '')
            campaign_id = detect_campaign(prospect_key)
            self._current_campaign_id = campaign_id
            self._rebuild_campaign_list(campaign_id, prospect_key)

        except Exception as exc:
            self._campaign_status.configure(text=f"Error: {exc}", text_color="#e05252")

    # ── Campaign mission list (left panel) ────────────────────────────────────

    def _rebuild_campaign_list(self, campaign_id: Optional[str], prospect_key: str):
        for w in self._campaign_scroll.winfo_children():
            w.destroy()
        self._campaign_vars.clear()

        if not campaign_id:
            ctk.CTkLabel(
                self._campaign_scroll,
                text=(f"Could not determine campaign for prospect '{prospect_key}'.\n\n"
                      "Only savegame.json files for the three Great Hunt campaigns\n"
                      "(Olympus / Styx / Prometheus) are supported."),
                font=FONT_NORMAL, text_color="#e09b3d", justify="left",
            ).pack(padx=16, pady=16)
            self._campaign_scroll.configure(label_text="Campaign Missions — unknown map")
            return

        campaign = CAMPAIGNS[campaign_id]
        missions: List[dict] = campaign['missions']

        # Campaign header
        hdr = ctk.CTkFrame(self._campaign_scroll, fg_color="#1a1a2e")
        hdr.pack(fill="x", padx=4, pady=(4, 2))
        ctk.CTkLabel(hdr, text=campaign['name'], font=FONT_TITLE,
                     text_color="#4da6ff").pack(side="left", padx=12, pady=6)
        ctk.CTkLabel(hdr, text=campaign['subtitle'], font=FONT_NORMAL,
                     text_color="#888").pack(side="left", padx=4, pady=6)
        ctk.CTkLabel(hdr, text=f"Map: {campaign['map']}  |  key: {prospect_key}",
                     font=FONT_SMALL, text_color="#555").pack(side="right", padx=12, pady=6)

        if not self._prof_editor:
            ctk.CTkLabel(self._campaign_scroll,
                         text="Profile.json not loaded — cannot show mission completion.",
                         font=FONT_NORMAL, text_color="#e09b3d").pack(padx=16, pady=12)
            return

        # Column header
        col_hdr = ctk.CTkFrame(self._campaign_scroll, fg_color="#1e1e1e")
        col_hdr.pack(fill="x", padx=4, pady=(4, 2))
        col_hdr.columnconfigure(1, weight=1)
        for col, (txt, w) in enumerate([
            ("Done", 48), ("Mission", 0), ("Type", 82), ("Conflicts with", 0),
        ]):
            kw = {"width": w} if w else {}
            ctk.CTkLabel(col_hdr, text=txt, font=FONT_SMALL, text_color="gray",
                         anchor="w", **kw).grid(row=0, column=col, padx=(8, 4), pady=3,
                                                sticky="w")

        # One row per mission
        for i, m in enumerate(missions):
            row_name = m['row_name']
            is_done = self._prof_editor.has_workshop_unlock(row_name)
            var = tk.BooleanVar(value=is_done)
            self._campaign_vars[row_name] = var

            bg = "#242424" if i % 2 == 0 else "#2a2a2a"
            row_f = ctk.CTkFrame(self._campaign_scroll, fg_color=bg)
            row_f.pack(fill="x", padx=4, pady=1)
            row_f.columnconfigure(1, weight=1)

            ctk.CTkCheckBox(
                row_f, text="", variable=var, width=48,
                command=lambda rn=row_name: self._on_campaign_toggle(rn),
            ).grid(row=0, column=0, rowspan=2, padx=(8, 4), pady=6, sticky="nw")

            # Top line: name + row_name
            top_line = ctk.CTkFrame(row_f, fg_color="transparent")
            top_line.grid(row=0, column=1, sticky="ew", padx=4, pady=(5, 0))
            ctk.CTkLabel(top_line, text=m['label'], font=FONT_NORMAL,
                         anchor="w").pack(side="left")
            ctk.CTkLabel(top_line, text=f"  {row_name}", font=FONT_MONO,
                         text_color="#555", anchor="w").pack(side="left")

            # Description line
            if m.get('description'):
                ctk.CTkLabel(row_f, text=m['description'], font=FONT_SMALL,
                             text_color="#666", anchor="w").grid(
                    row=1, column=1, columnspan=3, sticky="ew", padx=4, pady=(0, 5))

            type_color = TYPE_COLORS.get(m['type'], '#888')
            ctk.CTkLabel(row_f, text=m['type'], font=FONT_SMALL, width=82,
                         text_color=type_color, anchor="w").grid(
                row=0, column=2, padx=4, pady=(5, 0), sticky="nw")

            if m['forbidden']:
                short = []
                for rn in m['forbidden']:
                    parts = rn.split('_')
                    short.append(parts[-1] if len(parts) >= 3 else rn)
                ctk.CTkLabel(row_f, text="⊗ " + ", ".join(short),
                             font=FONT_SMALL, text_color="#e09b3d", anchor="w").grid(
                    row=0, column=3, padx=4, pady=(5, 0), sticky="nw")

        self._update_campaign_status()
        self._campaign_scroll.configure(label_text=f"Campaign — {campaign['name']}")

    # ── Campaign helpers ──────────────────────────────────────────────────────

    def _on_campaign_toggle(self, row_name: str):
        if not self._current_campaign_id:
            return
        var = self._campaign_vars.get(row_name)
        if not var or not var.get():
            self._update_campaign_status()
            return
        missions = CAMPAIGNS[self._current_campaign_id]['missions']
        for m in missions:
            if m['row_name'] == row_name:
                for forb in m['forbidden']:
                    peer = self._campaign_vars.get(forb)
                    if peer:
                        peer.set(False)
                break
        self._update_campaign_status()

    def _update_campaign_status(self):
        if not self._campaign_vars:
            self._campaign_status.configure(text="")
            return
        done = sum(1 for v in self._campaign_vars.values() if v.get())
        total = len(self._campaign_vars)
        if done == total:
            self._campaign_status.configure(text=f"All {total} done",
                                             text_color="#3bba6b")
        else:
            self._campaign_status.configure(text=f"{done}/{total}",
                                             text_color="#e09b3d")

    def _campaign_mark_all(self):
        for var in self._campaign_vars.values():
            var.set(True)
        self._update_campaign_status()

    def _campaign_clear_all(self):
        for var in self._campaign_vars.values():
            var.set(False)
        self._update_campaign_status()

    def _campaign_apply(self):
        if not self._prof_editor:
            self._campaign_status.configure(text="Profile.json not loaded.",
                                             text_color="#e09b3d")
            return
        if not self._campaign_vars:
            self._campaign_status.configure(text="No missions loaded.",
                                             text_color="#e09b3d")
            return
        added = removed = 0
        for row_name, var in self._campaign_vars.items():
            want = var.get()
            have = self._prof_editor.has_workshop_unlock(row_name)
            if want and not have:
                self._prof_editor.add_workshop_unlock(row_name, rank=1)
                added += 1
            elif not want and have:
                self._prof_editor.remove_workshop_unlock(row_name)
                removed += 1
        self._campaign_status.configure(
            text=f"+{added} / -{removed}  — Save All to persist",
            text_color="#3bba6b")

    # ── Regular mission helpers ───────────────────────────────────────────────

    def _update_regular_status(self):
        if not self._regular_vars:
            self._regular_status.configure(text="")
            return
        done = sum(1 for v in self._regular_vars.values() if v.get())
        total = len(self._regular_vars)
        if done == total:
            self._regular_status.configure(text=f"All {total} done",
                                            text_color="#3bba6b")
        else:
            self._regular_status.configure(text=f"{done}/{total}",
                                            text_color="#e09b3d")

    def _regular_mark_all(self):
        for var in self._regular_vars.values():
            var.set(True)
        self._update_regular_status()

    def _regular_clear_all(self):
        for var in self._regular_vars.values():
            var.set(False)
        self._update_regular_status()

    def _regular_apply(self):
        if not self._prof_editor:
            self._regular_status.configure(text="Profile.json not loaded.",
                                            text_color="#e09b3d")
            return
        if not self._regular_vars:
            self._regular_status.configure(text="No missions.", text_color="#e09b3d")
            return
        added = removed = 0
        for row_name, var in self._regular_vars.items():
            want = var.get()
            have = self._prof_editor.has_workshop_unlock(row_name)
            if want and not have:
                self._prof_editor.add_workshop_unlock(row_name, rank=1)
                added += 1
            elif not want and have:
                self._prof_editor.remove_workshop_unlock(row_name)
                removed += 1
        self._regular_status.configure(
            text=f"+{added} / -{removed}  — Save All to persist",
            text_color="#3bba6b")
