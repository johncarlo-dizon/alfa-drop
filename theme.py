import tkinter as tk
from tkinter import ttk

# Light palette
BG = "#f3f4f8"
CARD = "#ffffff"
BORDER = "#dfe2ec"
TEXT = "#1f2330"
MUTED = "#6a7088"
FIELD = "#ffffff"
ACCENT = "#6d4aff"
ACCENT_DARK = "#5937e6"
ACCENT_SOFT = "#ece8ff"
SUCCESS = "#1e9e5a"
SUCCESS_DARK = "#17804a"
DANGER = "#d6405a"
DANGER_DARK = "#b32e47"
WARNING = "#b57a14"
GHOST = "#eceef5"
GHOST_HOVER = "#e0e3ef"
DISABLED_BG = "#e6e8f0"
GROUP_BG = "#f1f2f8"

FONT = ("Segoe UI", 10)
FONT_BOLD = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_TITLE = ("Segoe UI", 18, "bold")
FONT_MONO = ("Consolas", 9)


def _button(style, name, bg, hover, fg="white", padding=(14, 7), font=FONT_BOLD):
    style.configure(name, background=bg, foreground=fg, bordercolor=bg, lightcolor=bg,
                    darkcolor=bg, borderwidth=0, focusthickness=0, focuscolor=bg,
                    padding=padding, font=font, relief="flat")
    style.map(name,
              background=[("disabled", DISABLED_BG), ("pressed", hover), ("active", hover)],
              bordercolor=[("disabled", DISABLED_BG), ("active", hover)],
              lightcolor=[("disabled", DISABLED_BG), ("active", hover)],
              darkcolor=[("disabled", DISABLED_BG), ("active", hover)],
              foreground=[("disabled", MUTED)])


def apply_style(root):
    s = ttk.Style(root)
    try:
        s.theme_use("clam")
    except tk.TclError:
        pass
    root.configure(bg=BG)

    s.configure(".", font=FONT, background=BG, foreground=TEXT, bordercolor=BORDER)
    s.configure("TFrame", background=BG)
    s.configure("Card.TFrame", background=CARD)
    s.configure("TLabel", background=BG, foreground=TEXT)
    s.configure("Card.TLabel", background=CARD, foreground=TEXT)
    s.configure("CardTitle.TLabel", background=CARD, foreground=TEXT, font=FONT_BOLD)
    s.configure("Hint.TLabel", background=CARD, foreground=MUTED, font=FONT_SMALL)
    s.configure("Title.TLabel", background=BG, foreground=ACCENT, font=FONT_TITLE)
    s.configure("Subtitle.TLabel", background=BG, foreground=MUTED)

    _button(s, "Accent.TButton", ACCENT, ACCENT_DARK)
    _button(s, "Success.TButton", SUCCESS, SUCCESS_DARK, padding=(14, 10))
    _button(s, "Danger.TButton", DANGER, DANGER_DARK, padding=(14, 10))
    _button(s, "Ghost.TButton", GHOST, GHOST_HOVER, fg=TEXT, font=FONT)
    _button(s, "Small.TButton", GHOST, GHOST_HOVER, fg=TEXT, padding=(8, 4), font=FONT_SMALL)

    s.configure("TEntry", fieldbackground=FIELD, bordercolor=BORDER, lightcolor=BORDER,
                darkcolor=BORDER, padding=6)
    s.map("TEntry", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
          darkcolor=[("focus", ACCENT)])
    s.configure("TSpinbox", fieldbackground=FIELD, bordercolor=BORDER, lightcolor=BORDER,
                darkcolor=BORDER, arrowsize=14, padding=4)
    s.map("TSpinbox", bordercolor=[("focus", ACCENT)], lightcolor=[("focus", ACCENT)],
          darkcolor=[("focus", ACCENT)])

    s.configure("Card.TCheckbutton", background=CARD, foreground=TEXT, focuscolor=CARD,
                indicatorbackground="#ffffff", indicatorforeground="#ffffff")
    s.map("Card.TCheckbutton",
          background=[("active", CARD)],
          indicatorbackground=[("selected", ACCENT), ("disabled", DISABLED_BG)],
          foreground=[("disabled", MUTED)])

    s.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
                rowheight=26, borderwidth=0, font=FONT)
    s.map("Treeview", background=[("selected", ACCENT_SOFT)], foreground=[("selected", TEXT)])
    s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    s.configure("Horizontal.TProgressbar", troughcolor="#e4e7f0", background=ACCENT,
                bordercolor="#e4e7f0", lightcolor=ACCENT, darkcolor=ACCENT, thickness=10)

    for orient in ("Vertical", "Horizontal"):
        s.configure(f"{orient}.TScrollbar", background="#c9cde0", troughcolor=BG,
                    bordercolor=BG, arrowcolor=MUTED, relief="flat", borderwidth=0, gripcount=0)
        s.map(f"{orient}.TScrollbar", background=[("active", ACCENT), ("pressed", ACCENT)])