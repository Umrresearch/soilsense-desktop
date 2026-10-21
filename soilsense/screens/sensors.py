"""Live sensors — one chart per sensor type, threshold lines, and a BST-powered hover read-out."""
import tkinter as tk
from tkinter import ttk

import matplotlib.dates as mdates

from .. import db, theme as T
from ..ds import BST
from ..widgets import Button, Chart, ScrollPage, card, fmt_num, time_ago
from .base import Screen

PERIODS = [("24 h", 24), ("7 days", 168), ("30 days", 720)]
META = {"SOIL_MOISTURE": ("Soil moisture", "%"), "TEMPERATURE": ("Temperature", "°C"), "HUMIDITY": ("Humidity", "%")}


class SensorsScreen(Screen):
    title = "Live sensors"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.hours, self.field_id, self.fields = 168, None, []
        self.trees, self.heights = {}, {}                 # sensor type → BST of (time → value)

        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=20, pady=(16, 6))
        tk.Label(bar, text="FIELD", bg=T.BG, fg=T.MUTED, font=T.FONTS["mono_bold"]).pack(side="left")
        self.combo = ttk.Combobox(bar, state="readonly", width=34)
        self.combo.pack(side="left", padx=(8, 20))
        self.combo.bind("<<ComboboxSelected>>", self.pick_field)
        tk.Label(bar, text="PERIOD", bg=T.BG, fg=T.MUTED, font=T.FONTS["mono_bold"]).pack(side="left")
        self.period_btns = {}
        for label, h in PERIODS:
            b = Button(bar, label.upper(), lambda h=h: self.set_period(h), kind="ghost", padx=10, pady=5)
            b.pack(side="left", padx=(8 if h == 24 else 2, 0))
            self.period_btns[h] = b

        self.status = tk.Frame(self, bg=T.BG)
        self.status.pack(fill="x", padx=20, pady=(4, 0))

        page = ScrollPage(self)
        page.pack(fill="both", expand=True)
        self.charts, self.readouts = {}, {}
        for kind, (label, unit) in META.items():
            c, body = card(page.inner, label, f"Averaged readings ({unit}). Move the mouse over the chart to read a value.")
            c.pack(fill="x", padx=20, pady=6)
            self.readouts[kind] = tk.Label(body, text="", bg=T.SURFACE, fg=T.WHEAT, font=T.FONTS["mono_bold"], anchor="w")
            self.readouts[kind].pack(fill="x")
            ch = Chart(body, height=2.3)
            ch.widget.pack(fill="both", expand=True)
            ch.canvas.mpl_connect("motion_notify_event", lambda e, k=kind: self.hover(k, e))
            self.charts[kind] = ch
        self._mark_period()

    def refresh(self, field_id=None):
        if field_id:
            self.field_id = field_id
        fid = self.farmer_id
        self.run(db.sensors_fields, fid, done=self._got_fields, key="fields")

    def _got_fields(self, res):
        self.fields, self.t = res
        self.combo["values"] = [f"{f['field_name']}  ({f['field_id']})" for f in self.fields]
        ids = [f["field_id"] for f in self.fields]
        if self.field_id not in ids:
            self.field_id = ids[0] if ids else None
        if self.field_id:
            self.combo.current(ids.index(self.field_id))
            self.load()

    def pick_field(self, _e=None):
        self.field_id = self.fields[self.combo.current()]["field_id"]
        self.load()

    def set_period(self, h):
        self.hours = h
        self._mark_period()
        self.load()

    def _mark_period(self):
        for h, b in self.period_btns.items():
            b.bg = T.WHEAT if h == self.hours else T.SURFACE_2
            b.fg = T.ON_WHEAT if h == self.hours else T.TEXT
            b.config(bg=b.bg, fg=b.fg)

    def load(self):
        fid, hours = self.field_id, self.hours
        self.run(db.sensors_data, fid, hours, done=self.render, key="series")

    def render(self, res):
        series, sensors = res
        for w in self.status.winfo_children():
            w.destroy()
        for s in sensors:
            color = {"ONLINE": T.GREEN, "STALE": T.WARNING}.get(s["health"], T.DANGER)
            chip = tk.Frame(self.status, bg=T.SURFACE, highlightthickness=1, highlightbackground=T.BORDER)
            chip.pack(side="left", padx=(0, 8))
            tk.Label(chip, text="●", bg=T.SURFACE, fg=color).pack(side="left", padx=(8, 2))
            tk.Label(chip, text=f"{META[s['sensor_type']][0]} {fmt_num(s['last_reading'])}{s['unit']} · "
                                f"{s['health'].lower()} · {time_ago(s['last_reading_at'])}",
                     bg=T.SURFACE, fg=T.TEXT_2, font=T.FONTS["small"]).pack(side="left", padx=(0, 8), pady=4)

        t = {k: float(v) for k, v in self.t.items() if k not in ("farmer_id", "updated_at")}
        lines = {"SOIL_MOISTURE": [(t["moisture_low"], "irrigate below"), (t["moisture_critical"], "critical")],
                 "TEMPERATURE": [(t["temp_high"], "heat stress")],
                 "HUMIDITY": [(t["humidity_high"], "disease risk")]}
        for kind, ch in self.charts.items():
            pts = [(r["t"], float(r["v"])) for r in series[kind] if r["v"] is not None]
            # BST keyed by time; data arrives sorted, so build it balanced (height ≈ log2 n)
            self.trees[kind] = BST.from_sorted([(mdates.date2num(x), (x, v)) for x, v in pts])
            self.heights[kind] = self.trees[kind].height()
            ch.clear()
            if not pts:
                ch.empty("No readings in this period")
                self.readouts[kind].config(text="")
                continue
            xs, ys = zip(*pts)
            if kind == "SOIL_MOISTURE":
                ch.ax.axhspan(t["moisture_low"], t["moisture_high"], color=T.GREEN, alpha=0.07, lw=0)
            ch.ax.plot(xs, ys, color=T.SERIES[kind], lw=1.8)
            for y, label in lines[kind]:
                ch.ax.axhline(y, color=T.WARNING if label != "critical" else T.DANGER, ls="--", lw=1)
                ch.ax.text(xs[0], y, f" {label} {y:g}", color=T.WARNING if label != "critical" else T.DANGER, fontsize=7, va="bottom")
            ch.ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M" if self.hours <= 24 else "%d %b"))
            ch.draw()
            last_x, last_v = pts[-1]
            unit = META[kind][1]
            self.readouts[kind].config(text=f"LATEST {last_v:.1f}{unit} · {last_x:%d %b %H:%M} · "
                                            f"min {min(ys):.1f} · max {max(ys):.1f} · {len(pts)} points")

    def hover(self, kind, event):
        """Mouse over a chart → BST floor search for the reading at or just before that time."""
        tree = self.trees.get(kind)
        if not tree or event.xdata is None or tree.size == 0:
            return
        hit = tree.floor(event.xdata) or tree.min()
        x, v = hit[1]
        unit = META[kind][1]
        self.readouts[kind].config(text=f"{x:%a %d %b %H:%M}  →  {v:.1f}{unit}   (found by BST floor search, "
                                        f"tree height {self.heights[kind]} for {tree.size} readings)")
