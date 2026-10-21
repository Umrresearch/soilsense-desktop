"""Colours and fonts — the same dark emerald + wheat look as the website."""
from tkinter import font as tkfont, ttk

BG = "#0D0F0D"
SURFACE = "#161916"
SURFACE_2 = "#1F231F"
SURFACE_3 = "#2A2F2A"
BORDER = "#2F352F"
TEXT = "#ECE7DA"
TEXT_2 = "#B9B4A6"
MUTED = "#8F8B80"
EMERALD = "#047857"
EMERALD_DARK = "#064E3B"
EMERALD_LIGHT = "#34D399"
GREEN = "#10B981"
WHEAT = "#E0B341"
ON_WHEAT = "#1A1406"
WARNING = "#FB923C"
DANGER = "#F87171"
INFO = "#60A5FA"
SERIES = {"SOIL_MOISTURE": "#3987E5", "TEMPERATURE": "#D95926", "HUMIDITY": "#199E70"}
PRIORITY = {"CRITICAL": DANGER, "HIGH": WARNING, "MEDIUM": WHEAT, "LOW": INFO}

FONTS = {}


def _family(root, wanted):
    have = set(tkfont.families(root))
    return next((f for f in wanted if f in have), "TkDefaultFont")


def setup(root):
    sans = _family(root, ["Segoe UI", "Inter", "Helvetica Neue", "Arial", "DejaVu Sans"])
    display = _family(root, ["Bahnschrift", "Segoe UI Semibold", "Arial Narrow", "DejaVu Sans Condensed", sans])
    mono = _family(root, ["Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Courier New"])
    FONTS.update(
        body=(sans, 10), small=(sans, 9), bold=(sans, 10, "bold"),
        h1=(display, 22, "bold"), h2=(display, 15, "bold"), h3=(display, 12, "bold"),
        kpi=(display, 26, "bold"), mono=(mono, 9), mono_bold=(mono, 9, "bold"), brand=(display, 16, "bold"),
    )
    root.configure(bg=BG)
    root.option_add("*Font", FONTS["body"])

    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=BG, foreground=TEXT, fieldbackground=SURFACE_2, bordercolor=BORDER,
                lightcolor=BORDER, darkcolor=BORDER, troughcolor=SURFACE, font=FONTS["body"])
    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background=SURFACE)
    s.configure("TLabel", background=BG, foreground=TEXT)
    s.configure("TCombobox", fieldbackground=SURFACE_2, background=SURFACE_2, foreground=TEXT, arrowcolor=WHEAT,
                padding=6, bordercolor=BORDER)
    s.map("TCombobox", fieldbackground=[("readonly", SURFACE_2)], foreground=[("readonly", TEXT)],
          selectbackground=[("readonly", SURFACE_2)], selectforeground=[("readonly", TEXT)])
    root.option_add("*TCombobox*Listbox.background", SURFACE_2)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", EMERALD)
    s.configure("Treeview", background=SURFACE, fieldbackground=SURFACE, foreground=TEXT, rowheight=30,
                bordercolor=BORDER, borderwidth=0, font=FONTS["body"])
    s.configure("Treeview.Heading", background=SURFACE_2, foreground=MUTED, relief="flat",
                font=FONTS["mono_bold"], padding=6)
    s.map("Treeview", background=[("selected", EMERALD_DARK)], foreground=[("selected", TEXT)])
    s.map("Treeview.Heading", background=[("active", SURFACE_3)])
    s.configure("Vertical.TScrollbar", background=SURFACE_2, troughcolor=BG, bordercolor=BG, arrowcolor=MUTED)
    s.configure("TSpinbox", fieldbackground=SURFACE_2, foreground=TEXT, arrowcolor=WHEAT, padding=5)
