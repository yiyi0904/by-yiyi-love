"""配色与 ttk 主题（支持蓝色 / 白色两套风格，可在设置里切换）。"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

FONT_FAMILY = "Microsoft YaHei UI"

# --------------------------------------------------------------------------
# 两套配色
# --------------------------------------------------------------------------
DARK = {
    "BG": "#0e1117",
    "PANEL": "#161a24",
    "PANEL_ALT": "#1d2230",
    "PANEL_HI": "#242b3b",
    "FIELD": "#11151d",
    "BORDER": "#2a3244",
    "BORDER_SOFT": "#222938",
    "TEXT": "#eaeefb",
    "TEXT_DIM": "#98a3bd",
    "TEXT_FAINT": "#6b7690",
    "ACCENT": "#4d8dff",
    "ACCENT_2": "#7a6bff",
    "ACCENT_HOVER": "#6aa2ff",
    "ACCENT_DARK": "#2f6ce0",
    "GLOW": "#1f3a6b",
    "SUCCESS": "#3ddc97",
    "WARN": "#ffb454",
    "DANGER": "#ff6b81",
    "DANGER_DARK": "#d94b66",
    "ON_ACCENT": "#ffffff",
    "SHADOW": "#0a0c12",
}

LIGHT = {
    "BG": "#eef1f7",
    "PANEL": "#ffffff",
    "PANEL_ALT": "#f1f4fa",
    "PANEL_HI": "#e2e8f4",
    "FIELD": "#ffffff",
    "BORDER": "#d3daea",
    "BORDER_SOFT": "#e4e9f3",
    "TEXT": "#1b2130",
    "TEXT_DIM": "#5c6678",
    "TEXT_FAINT": "#8b94a8",
    "ACCENT": "#2f6fe0",
    "ACCENT_2": "#6d5cf0",
    "ACCENT_HOVER": "#4a86ef",
    "ACCENT_DARK": "#2359c0",
    "GLOW": "#bcd4ff",
    "SUCCESS": "#119a66",
    "WARN": "#b8791a",
    "DANGER": "#d8455f",
    "DANGER_DARK": "#b52f49",
    "ON_ACCENT": "#ffffff",
    "SHADOW": "#c9d2e6",
}

PALETTES = {"dark": DARK, "light": LIGHT}
THEME_LABELS = {"dark": "蓝色风格", "light": "白色风格"}

_current = "dark"


def palette_name() -> str:
    return _current


def is_light() -> bool:
    return _current == "light"


def set_palette(name: str) -> None:
    """切换配色：把选中的颜色写进模块全局，后续创建的控件即使用新配色。"""
    global _current
    palette = PALETTES.get(name) or DARK
    _current = name if name in PALETTES else "dark"
    globals().update(palette)


# 初始化默认（蓝色）配色，保证模块级常量可用
set_palette("dark")


def fonts() -> dict[str, tkfont.Font]:
    base = tkfont.Font(family=FONT_FAMILY, size=10)
    return {
        "base": base,
        "small": tkfont.Font(family=FONT_FAMILY, size=9),
        "bold": tkfont.Font(family=FONT_FAMILY, size=10, weight="bold"),
        "title": tkfont.Font(family=FONT_FAMILY, size=15, weight="bold"),
        "subtitle": tkfont.Font(family=FONT_FAMILY, size=11, weight="bold"),
        "mono": tkfont.Font(family="Consolas", size=9),
    }


def apply_theme(root: tk.Misc) -> dict[str, tkfont.Font]:
    """按当前配色重建 ttk 样式。"""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:  # pragma: no cover
        pass

    f = fonts()
    root.option_add("*Font", f["base"])
    root.configure(bg=BG)

    style.configure(".", background=BG, foreground=TEXT, fieldbackground=FIELD,
                    bordercolor=BORDER, lightcolor=PANEL, darkcolor=PANEL,
                    font=f["base"], focuscolor=PANEL)
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("Alt.TFrame", background=PANEL_ALT)
    style.configure("TLabel", background=BG, foreground=TEXT, font=f["base"])
    style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
    style.configure("Dim.TLabel", background=PANEL, foreground=TEXT_DIM, font=f["small"])
    style.configure("Title.TLabel", background=BG, foreground=TEXT, font=f["title"])
    style.configure("Sub.TLabel", background=PANEL, foreground=TEXT, font=f["subtitle"])

    style.configure(
        "TButton",
        background=PANEL_ALT,
        foreground=TEXT,
        borderwidth=0,
        focuscolor=PANEL_ALT,
        padding=(12, 7),
        font=f["base"],
    )
    style.map(
        "TButton",
        background=[("pressed", BORDER), ("active", BORDER), ("disabled", PANEL)],
        foreground=[("disabled", TEXT_FAINT)],
    )

    style.configure(
        "TEntry",
        fieldbackground=FIELD,
        foreground=TEXT,
        insertcolor=TEXT,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=6,
    )
    style.map("TEntry", bordercolor=[("focus", ACCENT)])
    style.configure(
        "TCombobox",
        fieldbackground=FIELD,
        background=PANEL_ALT,
        foreground=TEXT,
        arrowcolor=TEXT_DIM,
        bordercolor=BORDER,
        padding=4,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", FIELD)],
        foreground=[("readonly", TEXT)],
        bordercolor=[("focus", ACCENT)],
    )
    root.option_add("*TCombobox*Listbox.background", PANEL)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", ON_ACCENT)

    style.configure(
        "TCheckbutton",
        background=PANEL,
        foreground=TEXT,
        focuscolor=PANEL,
        indicatorcolor=FIELD,
        padding=2,
    )
    style.map(
        "TCheckbutton",
        background=[("active", PANEL)],
        indicatorcolor=[("selected", ACCENT), ("active", PANEL_ALT)],
        foreground=[("active", TEXT)],
    )

    style.configure(
        "Treeview",
        background=PANEL,
        fieldbackground=PANEL,
        foreground=TEXT,
        bordercolor=BORDER,
        rowheight=27,
        font=f["base"],
    )
    style.configure(
        "Treeview.Heading",
        background=PANEL_ALT,
        foreground=TEXT_DIM,
        relief="flat",
        padding=(8, 6),
        font=f["small"],
    )
    style.map(
        "Treeview.Heading",
        background=[("active", PANEL_HI)],
        foreground=[("active", TEXT)],
    )
    style.map(
        "Treeview",
        background=[("selected", ACCENT)],
        foreground=[("selected", ON_ACCENT)],
    )
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    style.configure(
        "Vertical.TScrollbar",
        background=PANEL_ALT,
        troughcolor=BG,
        bordercolor=BG,
        arrowcolor=TEXT_DIM,
        width=10,
    )
    style.map("Vertical.TScrollbar", background=[("active", BORDER)])
    style.configure(
        "Horizontal.TScrollbar",
        background=PANEL_ALT,
        troughcolor=BG,
        bordercolor=BG,
        arrowcolor=TEXT_DIM,
    )

    style.configure("TSeparator", background=BORDER)
    style.configure("Vertical.TPanedwindow", background=BG)
    style.configure("TPanedwindow", background=BG)

    return f
