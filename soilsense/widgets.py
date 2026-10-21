"""Reusable widgets: buttons, cards, KPI tiles, scrolling page, charts, tables."""
import tkinter as tk
from tkinter import ttk

import matplotlib

matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402

from . import theme as T  # noqa: E402

BUTTON_STYLES = {
    "primary": (T.EMERALD, T.TEXT, T.GREEN),
    "wheat": (T.WHEAT, T.ON_WHEAT, "#F0C75A"),
    "ghost": (T.SURFACE_2, T.TEXT, T.SURFACE_3),
    "danger": ("#7F1D1D", T.TEXT, "#991B1B"),
}


class Button(tk.Label):
    """Flat square button with hover and a disabled state."""

    def __init__(self, parent, text, command=None, kind="primary", padx=16, pady=8, font=None, **kw):
        self.bg, self.fg, self.hover = BUTTON_STYLES[kind]
        super().__init__(parent, text=text, bg=self.bg, fg=self.fg, padx=padx, pady=pady, cursor="hand2",
                         font=font or T.FONTS["mono_bold"], highlightthickness=1, highlightbackground="#000", **kw)
        self.command, self.enabled = command, True
        self.bind("<Enter>", lambda e: self.enabled and self.config(bg=self.hover))
        self.bind("<Leave>", lambda e: self.config(bg=self.bg if self.enabled else T.SURFACE_3))
        self.bind("<Button-1>", lambda e: self.enabled and self.command and self.command())

    def set_enabled(self, on, text=None):
        self.enabled = on
        self.config(bg=self.bg if on else T.SURFACE_3, fg=self.fg if on else T.MUTED, cursor="hand2" if on else "arrow")
        if text:
            self.config(text=text)


def card(parent, title=None, sub=None, **kw):
    """A bordered panel; returns (outer, body)."""
    outer = tk.Frame(parent, bg=T.SURFACE, highlightthickness=1, highlightbackground=T.BORDER, **kw)
    if title:
        head = tk.Frame(outer, bg=T.SURFACE)
        head.pack(fill="x", padx=16, pady=(14, 4))
        tk.Label(head, text=title.upper(), bg=T.SURFACE, fg=T.TEXT, font=T.FONTS["h3"]).pack(anchor="w")
        if sub:
            tk.Label(head, text=sub, bg=T.SURFACE, fg=T.MUTED, font=T.FONTS["small"]).pack(anchor="w")
    body = tk.Frame(outer, bg=T.SURFACE)
    body.pack(fill="both", expand=True, padx=16, pady=(4, 14))
    return outer, body


class Kpi(tk.Frame):
    """Deep-emerald stat tile like the website's."""

    def __init__(self, parent, label, unit=""):
        super().__init__(parent, bg=T.EMERALD_DARK, highlightthickness=2, highlightbackground=T.EMERALD)
        tk.Label(self, text=label.upper(), bg=T.EMERALD_DARK, fg="#A7F3D0", font=T.FONTS["mono_bold"]).pack(anchor="w", padx=14, pady=(12, 0))
        row = tk.Frame(self, bg=T.EMERALD_DARK)
        row.pack(anchor="w", padx=14)
        self.value = tk.Label(row, text="—", bg=T.EMERALD_DARK, fg=T.TEXT, font=T.FONTS["kpi"])
        self.value.pack(side="left")
        tk.Label(row, text=unit, bg=T.EMERALD_DARK, fg="#A7F3D0", font=T.FONTS["body"]).pack(side="left", padx=(4, 0), pady=(10, 0))
        self.foot = tk.Label(self, text="", bg=T.EMERALD_DARK, fg="#A7F3D0", font=T.FONTS["small"])
        self.foot.pack(anchor="w", padx=14, pady=(0, 12))

    def set(self, value, foot=""):
        self.value.config(text=value)
        self.foot.config(text=foot)


class ScrollPage(tk.Frame):
    """A vertically scrolling area; put content in .inner."""

    def __init__(self, parent):
        super().__init__(parent, bg=T.BG)
        self.canvas = tk.Canvas(self, bg=T.BG, highlightthickness=0)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=T.BG)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        _install_wheel(self.winfo_toplevel())

    def scroll(self, units):
        self.canvas.yview_scroll(units, "units")


def _install_wheel(root):
    """Bind the mouse wheel ONCE for the whole app; scroll whichever ScrollPage is under the pointer."""
    if getattr(root, "_wheel_installed", False):
        return
    root._wheel_installed = True

    def handler(e, units=None):
        if units is None:
            units = int(-e.delta / 40) if abs(e.delta) >= 40 else (-1 if e.delta > 0 else 1)
        try:
            w = root.winfo_containing(e.x_root, e.y_root)
        except (KeyError, tk.TclError):
            return
        while w is not None:
            if isinstance(w, ttk.Treeview):
                return                                   # let tables scroll themselves
            if isinstance(w, ScrollPage):
                w.scroll(units)
                return
            w = getattr(w, "master", None)

    root.bind_all("<MouseWheel>", handler)
    root.bind_all("<Button-4>", lambda e: handler(e, -3))
    root.bind_all("<Button-5>", lambda e: handler(e, 3))


def _make_canvas(fig, parent):
    """FigureCanvasTkAgg, minus the handlers matplotlib attaches to the main window.

    For every chart, matplotlib binds <MouseWheel> and <Destroy> on the *toplevel* window.
    Those callbacks outlive the chart, so each logout/login would leave a few behind (a slow
    leak). We don't use matplotlib's wheel/close events, so remove them straight away.
    """
    root = parent.winfo_toplevel()
    before = set(root._tclCommands or [])
    saved = {seq: root.bind(seq) for seq in ("<MouseWheel>", "<Destroy>")}
    canvas = FigureCanvasTkAgg(fig, master=parent)
    for seq, script in saved.items():
        root.bind(seq, script)                     # put the window's own bindings back exactly
    for name in [c for c in (root._tclCommands or []) if c not in before]:
        root.deletecommand(name)                   # free matplotlib's Python callbacks
    return canvas


class Chart:
    """A matplotlib figure styled for the dark theme, embedded in Tk."""

    def __init__(self, parent, height=2.6, width=6.0):
        self.fig = Figure(figsize=(width, height), dpi=100, facecolor=T.SURFACE)
        self.ax = self.fig.add_subplot(111)
        self.canvas = _make_canvas(self.fig, parent)
        self.widget = self.canvas.get_tk_widget()
        self.widget.configure(bg=T.SURFACE, highlightthickness=0)
        self.style()

    def style(self):
        ax = self.ax
        ax.set_facecolor(T.SURFACE)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(T.BORDER)
        ax.tick_params(colors=T.MUTED, labelsize=8)
        ax.grid(axis="y", color=T.BORDER, linewidth=0.6, alpha=0.7)
        ax.set_axisbelow(True)

    def clear(self):
        self.ax.clear()
        self.style()

    def empty(self, text="No data for this period"):
        self.clear()
        self.ax.text(0.5, 0.5, text, ha="center", va="center", color=T.MUTED, transform=self.ax.transAxes)
        self.ax.set_xticks([]); self.ax.set_yticks([])
        self.draw()

    def draw(self):
        self.fig.tight_layout(pad=1.0)
        self.canvas.draw_idle()


def table(parent, columns, height=8):
    """Treeview with headings; columns = [(key, heading, width, anchor), ...]."""
    tv = ttk.Treeview(parent, columns=[c[0] for c in columns], show="headings", height=height)
    for key, head, width, anchor in columns:
        tv.heading(key, text=head.upper(), anchor=anchor)
        tv.column(key, width=width, anchor=anchor, stretch=True)
    tv.tag_configure("odd", background=T.SURFACE_2)
    return tv


def fill_table(tv, rows):
    tv.delete(*tv.get_children())
    for i, values in enumerate(rows):
        tv.insert("", "end", values=values, tags=("odd",) if i % 2 else ())


def badge(parent, text, color, bg=None):
    return tk.Label(parent, text=f" {text} ", bg=color, fg="#000", font=T.FONTS["mono_bold"], padx=4)


def fmt_num(v, d=1, default="—"):
    if v is None:
        return default
    v = float(v)
    return f"{v:,.{d}f}" if d else f"{v:,.0f}"


def fmt_litres(l):
    l = float(l or 0)
    if l >= 1e6:
        return f"{l / 1e6:.2f} ML"
    if l >= 1e3:
        return f"{l / 1e3:,.0f} kL"
    return f"{l:,.0f} L"


def time_ago(dt):
    if dt is None:
        return "never"
    from datetime import datetime, timezone
    s = (datetime.now(timezone.utc) - dt).total_seconds()
    if s < 90:
        return "just now"
    if s < 3600:
        return f"{int(s // 60)} min ago"
    if s < 86400:
        return f"{int(s // 3600)} h ago"
    return f"{int(s // 86400)} d ago"
