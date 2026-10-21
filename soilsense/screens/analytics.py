import tkinter as tk

import matplotlib.dates as mdates

from .. import db, theme as T
from ..widgets import Button, Chart, Kpi, ScrollPage, card, fill_table, fmt_litres, fmt_num, table
from .base import Screen


class AnalyticsScreen(Screen):
    title = "Farm analytics"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.days = 30
        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=20, pady=(16, 6))
        tk.Label(bar, text="PERIOD", bg=T.BG, fg=T.MUTED, font=T.FONTS["mono_bold"]).pack(side="left")
        self.btns = {}
        for d in (7, 30, 90):
            b = Button(bar, f"{d} DAYS", lambda d=d: self.set_days(d), kind="ghost", padx=10, pady=5)
            b.pack(side="left", padx=(8 if d == 7 else 2, 0))
            self.btns[d] = b

        page = ScrollPage(self)
        page.pack(fill="both", expand=True)
        root = page.inner
        for c in range(4):
            root.columnconfigure(c, weight=1, uniform="a")
        self.k_water = Kpi(root, "Water used")
        self.k_forecast = Kpi(root, "Yield forecast", "q/acre")
        self.k_trend = Kpi(root, "Yield trend", "q/acre/yr")
        self.k_fert = Kpi(root, "Fertilizer · 180 d", "kg")
        for i, k in enumerate((self.k_water, self.k_forecast, self.k_trend, self.k_fert)):
            k.grid(row=0, column=i, sticky="nsew", padx=(20 if i == 0 else 6, 20 if i == 3 else 6), pady=(6, 6))

        c, b = card(root, "Water used per day", "All fields, kilolitres")
        c.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=(20, 6), pady=6)
        self.water = Chart(b, height=2.6); self.water.widget.pack(fill="both", expand=True)
        c, b = card(root, "Fertilizer applied", "Last 180 days, kg by product")
        c.grid(row=1, column=2, columnspan=2, sticky="nsew", padx=(6, 20), pady=6)
        self.fert = Chart(b, height=2.6); self.fert.widget.pack(fill="both", expand=True)
        c, b = card(root, "Historical yield", "Average quintals per acre by season — your fields vs the district")
        c.grid(row=2, column=0, columnspan=4, sticky="nsew", padx=20, pady=6)
        self.yields = Chart(b, height=2.8, width=12); self.yields.widget.pack(fill="both", expand=True)
        c, b = card(root, "Compare your fields", "Water in the selected period vs long-run yield")
        c.grid(row=3, column=0, columnspan=4, sticky="nsew", padx=20, pady=(6, 20))
        self.compare = table(b, [("id", "Field", 90, "w"), ("name", "Name", 130, "w"), ("soil", "Soil", 80, "w"),
                                 ("method", "Irrigation", 90, "w"), ("acres", "Acres", 60, "e"), ("yield", "Avg yield q/ac", 110, "e"),
                                 ("brix", "Avg Brix", 70, "e"), ("water", "Water", 90, "e"), ("wpa", "Water / acre", 100, "e")], height=5)
        self.compare.pack(fill="both", expand=True)
        self._mark()

    def set_days(self, d):
        self.days = d
        self._mark()
        self.refresh()

    def _mark(self):
        for d, b in self.btns.items():
            b.bg, b.fg = (T.WHEAT, T.ON_WHEAT) if d == self.days else (T.SURFACE_2, T.TEXT)
            b.config(bg=b.bg, fg=b.fg)

    def refresh(self):
        fid, days = self.farmer_id, self.days
        self.run(lambda: db.analytics(fid, days), done=self.render, key="load")

    def render(self, a):
        water_total = sum(float(r["litres"]) for r in a["water_daily"])
        self.k_water.set(fmt_litres(water_total), f"{len(a['water_daily'])} irrigation days in {self.days} d")
        self.k_fert.set(fmt_num(sum(float(r["kg"]) for r in a["fertilizer"]), 0),
                        f"{sum(r['applications'] for r in a['fertilizer'])} applications")

        # linear trend on season averages → next season forecast (least squares)
        pts = [(r["year"], float(r["yield"])) for r in a["yields"] if r["yield"] is not None]
        if len(pts) >= 3:
            n = len(pts)
            mx, my = sum(x for x, _ in pts) / n, sum(y for _, y in pts) / n
            slope = sum((x - mx) * (y - my) for x, y in pts) / sum((x - mx) ** 2 for x, _ in pts)
            nxt = max(x for x, _ in pts) + 1
            self.k_forecast.set(f"{my + slope * (nxt - mx):.0f}", f"next season ({nxt}) · trend")
            self.k_trend.set(f"{slope:+.1f}", f"{pts[-1][0]}: {pts[-1][1]:.0f} q/acre")
        else:
            self.k_forecast.set("—", "needs 3+ seasons"); self.k_trend.set("—", "")

        ch = self.water; ch.clear()
        if a["water_daily"]:
            ch.ax.bar([r["day"] for r in a["water_daily"]], [float(r["litres"]) / 1000 for r in a["water_daily"]],
                      color=T.SERIES["SOIL_MOISTURE"], width=0.7)
            loc = mdates.AutoDateLocator(maxticks=6)
            ch.ax.xaxis.set_major_locator(loc)
            ch.ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
            ch.draw()
        else:
            ch.empty("No irrigation in this period")

        ch = self.fert; ch.clear()
        if a["fertilizer"]:
            ch.ax.barh([r["type"] for r in a["fertilizer"]], [float(r["kg"]) for r in a["fertilizer"]], color=T.SERIES["TEMPERATURE"], height=0.45)
            ch.ax.set_ylim(-0.8, max(len(a["fertilizer"]) - 0.2, 1.2))
            ch.ax.invert_yaxis(); ch.ax.grid(axis="x", color=T.BORDER, lw=0.6); ch.ax.grid(axis="y", visible=False)
            ch.draw()
        else:
            ch.empty("No fertilizer logged in the last 180 days")

        ch = self.yields; ch.clear()
        if a["yields"]:
            yrs = [r["year"] for r in a["yields"]]
            ch.ax.plot(yrs, [float(r["yield"]) if r["yield"] is not None else None for r in a["yields"]],
                       color=T.SERIES["SOIL_MOISTURE"], lw=2, marker="o", label="Your fields")
            ch.ax.plot(yrs, [float(r["district_avg"]) if r["district_avg"] is not None else None for r in a["yields"]],
                       color=T.SERIES["TEMPERATURE"], lw=1.6, ls="--", marker="o", ms=3, label="District average")
            ch.ax.set_xticks(yrs)
            leg = ch.ax.legend(frameon=False, fontsize=8, loc="upper left")
            for txt in leg.get_texts():
                txt.set_color(T.TEXT_2)
            ch.draw()
        else:
            ch.empty("No crop records yet")

        fill_table(self.compare, [(
            r["field_id"], r["field_name"], r["soil_type"], r["irrigation_method"], fmt_num(r["area_acres"]),
            fmt_num(r["avg_yield"]), fmt_num(r["avg_brix"], 2), fmt_litres(r["water_litres"]),
            fmt_litres(float(r["water_litres"]) / float(r["area_acres"])) if r["area_acres"] else "—") for r in a["compare"]])
