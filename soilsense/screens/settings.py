import tkinter as tk
from urllib.parse import urlparse

from .. import config, db, engine, theme as T
from ..widgets import Button, ScrollPage, card
from .base import Screen

GROUPS = [
    ("Soil moisture (% volumetric)", "Must stay in order: critical < low < target < high", [
        ("moisture_critical", "Critical — irrigate immediately"), ("moisture_low", "Low — irrigate today"),
        ("moisture_target", "Target after irrigation"), ("moisture_high", "High — waterlogging alert")]),
    ("Weather", "Heat, cold and disease alerts", [
        ("temp_high", "Heat stress above (°C)"), ("temp_low", "Cold stress below (°C)"),
        ("humidity_high", "Disease risk above (% RH)"), ("humidity_low", "Very dry air below (% RH)")]),
    ("Soil nutrients (kg/acre, from soil test)", "Below these, fertilizer advice is given", [
        ("nitrogen_min", "Nitrogen minimum"), ("phosphorus_min", "Phosphorus minimum"), ("potassium_min", "Potassium minimum")]),
    ("Irrigation calculation", "Used to work out litres of water", [("root_zone_mm", "Effective root-zone depth (mm)")]),
]


class SettingsScreen(Screen):
    title = "Settings"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        page = ScrollPage(self)
        page.pack(fill="both", expand=True)
        root = page.inner
        root.columnconfigure(0, weight=1, uniform="s"); root.columnconfigure(1, weight=1, uniform="s")
        self.vars = {}
        for i, (title, sub, items) in enumerate(GROUPS):
            c, body = card(root, title, sub)
            c.grid(row=i // 2, column=i % 2, sticky="nsew", padx=(20 if i % 2 == 0 else 6, 6 if i % 2 == 0 else 20),
                   pady=(16 if i < 2 else 6, 6))
            for key, label in items:
                row = tk.Frame(body, bg=T.SURFACE)
                row.pack(fill="x", pady=3)
                tk.Label(row, text=label, bg=T.SURFACE, fg=T.TEXT_2).pack(side="left")
                v = tk.StringVar()
                tk.Entry(row, textvariable=v, width=8, bg=T.SURFACE_2, fg=T.TEXT, insertbackground=T.TEXT, relief="flat",
                         justify="right", highlightthickness=1, highlightbackground=T.BORDER, highlightcolor=T.WHEAT,
                         font=T.FONTS["mono"]).pack(side="right", ipady=4)
                self.vars[key] = v
        actions = tk.Frame(root, bg=T.BG)
        actions.grid(row=2, column=0, columnspan=2, sticky="w", padx=20, pady=(6, 12))
        self.save_btn = Button(actions, "SAVE THRESHOLDS", self.save)
        self.save_btn.pack(side="left")
        self.msg = tk.Label(actions, text="", bg=T.BG, fg=T.TEXT_2, wraplength=700, justify="left")
        self.msg.pack(side="left", padx=12)

        c, body = card(root, "Account & database")
        c.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=20, pady=(6, 20))
        self.info = tk.Label(body, text="", bg=T.SURFACE, fg=T.TEXT_2, justify="left", font=T.FONTS["mono"])
        self.info.pack(anchor="w")
        btns = tk.Frame(body, bg=T.SURFACE)
        btns.pack(anchor="w", pady=(10, 0))
        Button(btns, "TEST CONNECTION", self.test, kind="ghost").pack(side="left")
        Button(btns, "CHANGE DATABASE…", app.change_database, kind="ghost").pack(side="left", padx=8)

    def refresh(self):
        fid = self.farmer_id
        self.run(lambda: db.thresholds(fid), done=self.render, key="load")

    def render(self, t):
        for k, v in self.vars.items():
            val = float(t[k])
            v.set(f"{val:g}")
        f = self.app.farmer
        host = urlparse(config.database_url()).hostname or "?"
        self.info.config(text=f"Farmer ID   {f['farmer_id']}\nName        {f['name']}\nE-mail      {f['email']}\n"
                              f"Database    {host}")

    def save(self):
        try:
            values = {k: float(v.get()) for k, v in self.vars.items()}
        except ValueError:
            self.msg.config(text="Every value must be a number.", fg=T.DANGER)
            return
        self.save_btn.set_enabled(False, "SAVING…")
        fid = self.farmer_id

        def job():
            db.update_thresholds(fid, values)
            return engine.evaluate_farmer(fid)               # thresholds changed → re-check every field

        def done(r):
            self.save_btn.set_enabled(True, "SAVE THRESHOLDS")
            self.msg.config(text=f"Saved. Re-checked {r['fields']} fields: {r['created']} new, {r['expired']} cleared.", fg=T.GREEN)

        def fail(e):
            self.save_btn.set_enabled(True, "SAVE THRESHOLDS")
            self.msg.config(text=str(e), fg=T.DANGER)

        self.app.worker.run(job, on_done=done, on_error=fail)

    def test(self):
        self.run(db.ping, done=lambda p: self.app.toast(f"Connected · {p['db']} · server time {p['now']:%H:%M:%S}", "ok"))
