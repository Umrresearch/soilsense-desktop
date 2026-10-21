import tkinter as tk
from datetime import datetime

import matplotlib.dates as mdates

from .. import db, engine, theme as T
from ..widgets import Button, Chart, Kpi, ScrollPage, card, fill_table, fmt_litres, fmt_num, table, time_ago
from .base import Screen


class DashboardScreen(Screen):
    title = "Dashboard"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        page = ScrollPage(self)
        page.pack(fill="both", expand=True)
        root = page.inner
        for c in range(4):
            root.columnconfigure(c, weight=1, uniform="k")

        # welcome strip
        hello = tk.Frame(root, bg=T.WHEAT, highlightthickness=2, highlightbackground="#000")
        hello.grid(row=0, column=0, columnspan=4, sticky="ew", padx=20, pady=(18, 12))
        words = tk.Frame(hello, bg=T.WHEAT)
        words.pack(side="left", padx=18, pady=12)
        self.hello_title = tk.Label(words, text="", bg=T.WHEAT, fg=T.ON_WHEAT, font=T.FONTS["h1"])
        self.hello_title.pack(anchor="w")
        self.hello_sub = tk.Label(words, text="", bg=T.WHEAT, fg=T.ON_WHEAT, justify="left")
        self.hello_sub.pack(anchor="w")
        self.recheck = Button(hello, "RE-CHECK ADVICE", self.recheck_advice, kind="primary")
        self.recheck.pack(side="right", padx=14)
        Button(hello, "VIEW ADVICE", lambda: app.navigate("recommendations"), kind="ghost").pack(side="right", padx=(0, 4))

        # KPIs
        self.k_moist = Kpi(root, "Avg soil moisture", "%")
        self.k_water = Kpi(root, "Water · 7 days")
        self.k_pending = Kpi(root, "Pending advice")
        self.k_sensors = Kpi(root, "Sensors online")
        for i, k in enumerate((self.k_moist, self.k_water, self.k_pending, self.k_sensors)):
            k.grid(row=1, column=i, sticky="nsew", padx=(20 if i == 0 else 6, 20 if i == 3 else 6), pady=6)
        self.k_pending.bind("<Button-1>", lambda e: app.navigate("recommendations"))

        # charts
        c1, b1 = card(root, "Water used by field", "Last 7 days, kilolitres")
        c1.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=(20, 6), pady=6)
        self.water_chart = Chart(b1, height=2.6)
        self.water_chart.widget.pack(fill="both", expand=True)
        c2, b2 = card(root, "Soil moisture trend", "Daily farm average, last 7 days (%)")
        c2.grid(row=2, column=2, columnspan=2, sticky="nsew", padx=(6, 20), pady=6)
        self.moist_chart = Chart(b2, height=2.6)
        self.moist_chart.widget.pack(fill="both", expand=True)

        # fields + alerts
        c3, b3 = card(root, "Your fields", "Click a field to open its live sensors")
        c3.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=(20, 6), pady=(6, 20))
        self.fields = table(b3, [("id", "Field", 92, "w"), ("name", "Name", 110, "w"), ("acres", "Acres", 64, "e"),
                                 ("method", "Water", 84, "w"), ("moist", "Moist %", 78, "e"),
                                 ("pending", "Advice", 70, "e"), ("status", "Status", 100, "w")], height=6)
        self.fields.pack(fill="both", expand=True)
        self.fields.bind("<Double-1>", self.open_field)
        self.fields.bind("<Return>", self.open_field)
        c4, self.alerts = card(root, "Alerts", "Urgent advice and sensor problems")
        c4.grid(row=3, column=2, columnspan=2, sticky="nsew", padx=(6, 20), pady=(6, 20))
        self.updated = tk.Label(root, text="", bg=T.BG, fg=T.MUTED, font=T.FONTS["small"])
        self.updated.grid(row=4, column=0, columnspan=4, pady=(0, 20))

    # ------------------------------------------------------------------ data
    def refresh(self):
        fid = self.farmer_id

        self.run(db.dashboard, fid, done=self.render, key="load")          # one round trip to Neon

    def render(self, d):
        s, fields = d["summary"], d["fields"]
        name = self.app.farmer["name"].split()[0]
        self.hello_title.config(text=f"NAMASTE, {name.upper()}!")
        n = s["pending"]
        self.hello_sub.config(text=f"{datetime.now():%A %d %B} · "
                                   f"{len(fields)} fields · {n} piece{'s' if n != 1 else ''} of advice waiting · "
                                   f"last sensor update {time_ago(s['last_update'])}")

        m, prev = s["avg_soil_moisture"], s["moisture_24h_ago"]
        delta = f"{float(m) - float(prev):+.1f} pts vs 24 h ago" if m is not None and prev is not None else "vs 24 h ago: no data"
        self.k_moist.set(fmt_num(m), delta)
        w, wp = float(s["litres_7d"]), float(s["litres_prev_7d"])
        wd = f"{(w - wp) / wp * 100:+.0f}% vs previous 7 days" if wp else f"{s['sessions_7d']} sessions"
        self.k_water.set(fmt_litres(w), wd)
        self.k_pending.set(str(n), f"{s['urgent']} urgent")
        self.k_sensors.set(f"{s['online']}/{s['total']}", f"{s['needs_check']} need a check")

        # water by field — the biggest bar in wheat
        ch = self.water_chart
        ch.clear()
        rows = d["water"]
        if rows and any(float(r["litres"]) for r in rows):
            vals = [float(r["litres"]) / 1000 for r in rows]
            top = max(vals)
            ch.ax.bar([r["field_name"] for r in rows], vals, width=0.55,
                      color=[T.WHEAT if v == top else T.SURFACE_3 for v in vals], edgecolor="#000", linewidth=1)
            for i, v in enumerate(vals):
                ch.ax.text(i, v, f"{v:,.0f}", ha="center", va="bottom", color=T.TEXT_2, fontsize=8)
            ch.draw()
        else:
            ch.empty("No irrigation logged in the last 7 days")

        # moisture trend with the healthy band from the farmer's thresholds
        ch, t = self.moist_chart, d["thresholds"]
        ch.clear()
        tr = d["trend"]
        if tr:
            xs, ys = [r["day"] for r in tr], [float(r["avg"]) for r in tr]
            ch.ax.axhspan(float(t["moisture_low"]), float(t["moisture_high"]), color=T.GREEN, alpha=0.08, lw=0)
            ch.ax.axhline(float(t["moisture_low"]), color=T.WARNING, ls="--", lw=1)
            ch.ax.plot(xs, ys, color=T.SERIES["SOIL_MOISTURE"], lw=2, marker="o", ms=4)
            ch.ax.fill_between(xs, ys, min(ys) - 2, color=T.SERIES["SOIL_MOISTURE"], alpha=0.12)
            ch.ax.text(xs[0], float(t["moisture_low"]), f" irrigate below {float(t['moisture_low']):.0f}%",
                       color=T.WARNING, fontsize=7, va="bottom")
            ch.ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
            ch.draw()
        else:
            ch.empty()

        # fields table
        def status(f):
            if f["sensors_unhealthy"]:
                return "sensor check"
            if f["soil_moisture"] is None:
                return "no data"
            mv = float(f["soil_moisture"])
            if mv < float(t["moisture_critical"]):
                return "critical"
            if mv < float(t["moisture_low"]):
                return "dry"
            if mv > float(t["moisture_high"]):
                return "waterlogged"
            return "good"

        fill_table(self.fields, [(f["field_id"], f["field_name"], fmt_num(f["area_acres"]), f["irrigation_method"],
                                  fmt_num(f["soil_moisture"]), f["pending"], status(f)) for f in fields])

        # alerts list
        for w in self.alerts.winfo_children():
            w.destroy()
        if not d["alerts"]:
            tk.Label(self.alerts, text="All clear — no urgent alerts right now.", bg=T.SURFACE, fg=T.GREEN).pack(anchor="w", pady=8)
        for a in d["alerts"]:
            row = tk.Frame(self.alerts, bg=T.SURFACE)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=f" {a['priority']} ", bg=T.PRIORITY.get(a["priority"], T.WHEAT), fg="#000",
                     font=T.FONTS["mono_bold"]).pack(side="left", anchor="n")
            tk.Label(row, text=f"{a['action']}\n{a['field_name']} · {time_ago(a['timestamp'])}", bg=T.SURFACE, fg=T.TEXT,
                     justify="left", wraplength=420, font=T.FONTS["small"]).pack(side="left", padx=8)
        self.updated.config(text=f"Updated {datetime.now():%H:%M:%S} · live from Neon")

    # ------------------------------------------------------------------ actions
    def open_field(self, _e=None):
        sel = self.fields.selection()
        if sel:
            self.app.navigate("sensors", field_id=self.fields.item(sel[0], "values")[0])

    def recheck_advice(self):
        self.recheck.set_enabled(False, "CHECKING…")

        def done(r):
            self.recheck.set_enabled(True, "RE-CHECK ADVICE")
            self.app.toast(f"Checked {r['fields']} fields · {r['created']} new, {r['expired']} cleared", "ok")
            self.refresh()

        def safe():
            return engine.evaluate_farmer(self.farmer_id)

        self.app.worker.run(safe, on_done=done,
                            on_error=lambda e: (self.recheck.set_enabled(True, "RE-CHECK ADVICE"), self.app.toast(str(e), "error")))
