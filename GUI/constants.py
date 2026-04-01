"""Shared UI constants for the Icarus Save Editor GUI."""

import customtkinter as ctk

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
