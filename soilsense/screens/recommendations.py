import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from .. import db, engine, theme as T
from ..widgets import Button, ScrollPage, time_ago
from .base import Screen

ICONS = {"IRRIGATION": "◆", "FERTILIZER": "◆", "ALERT": "▲"}


class RecommendationsScreen(Screen):
    title = "Recommendations"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.status, self.kind = "PENDING", None
        bar = tk.Frame(self, bg=T.BG)
        bar.pack(fill="x", padx=20, pady=(16, 6))
        tk.Label(bar, text="SHOW", bg=T.BG, fg=T.MUTED, font=T.FONTS["mono_bold"]).pack(side="left")
        self.status_box = ttk.Combobox(bar, state="readonly", width=14, values=["Pending", "Applied", "Dismissed", "Expired", "All"])
        self.status_box.current(0)
        self.status_box.pack(side="left", padx=(8, 16))
        tk.Label(bar, text="TYPE", bg=T.BG, fg=T.MUTED, font=T.FONTS["mono_bold"]).pack(side="left")
        self.kind_box = ttk.Combobox(bar, state="readonly", width=14, values=["All", "Irrigation", "Fertilizer", "Alert"])
        self.kind_box.current(0)
        self.kind_box.pack(side="left", padx=8)
        for box in (self.status_box, self.kind_box):
            box.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        self.recheck = Button(bar, "RE-CHECK ALL FIELDS", self.recheck_all, kind="wheat", padx=12, pady=6)
        self.recheck.pack(side="right")
        self.count = tk.Label(self, text="", bg=T.BG, fg=T.TEXT_2)
        self.count.pack(anchor="w", padx=20)
        self.page = ScrollPage(self)
        self.page.pack(fill="both", expand=True, pady=(4, 0))

    def refresh(self):
        status = self.status_box.get().upper()
        kind = None if self.kind_box.get() == "All" else self.kind_box.get().upper()
        fid = self.farmer_id
        self.run(lambda: db.recommendations(fid, status, kind), done=self.render, key="load")

    def render(self, recs):
        body = self.page.inner
        for w in body.winfo_children():
            w.destroy()
        self.count.config(text=f"{len(recs)} recommendation{'s' if len(recs) != 1 else ''}")
        if not recs:
            tk.Label(body, text="Nothing here — your fields are in good shape.", bg=T.BG, fg=T.GREEN).pack(anchor="w", padx=20, pady=20)
        for r in recs:
            self._card(body, r)

    def _card(self, parent, r):
        c = tk.Frame(parent, bg=T.SURFACE, highlightthickness=1, highlightbackground=T.BORDER)
        c.pack(fill="x", padx=20, pady=5)
        stripe = tk.Frame(c, bg=T.PRIORITY.get(r["priority"], T.WHEAT), width=6)
        stripe.pack(side="left", fill="y")
        main = tk.Frame(c, bg=T.SURFACE)
        main.pack(side="left", fill="both", expand=True, padx=14, pady=12)
        top = tk.Frame(main, bg=T.SURFACE)
        top.pack(fill="x")
        tk.Label(top, text=f" {r['priority']} ", bg=T.PRIORITY.get(r["priority"], T.WHEAT), fg="#000", font=T.FONTS["mono_bold"]).pack(side="left")
        tk.Label(top, text=f"  {ICONS.get(r['type'], '')} {r['type'].title()} · {r['field_name']} ({r['field_id']}) · "
                           f"{time_ago(r['timestamp'])} · {r['status'].lower()}",
                 bg=T.SURFACE, fg=T.MUTED, font=T.FONTS["mono"]).pack(side="left")
        tk.Label(main, text=r["action"], bg=T.SURFACE, fg=T.TEXT, font=T.FONTS["h3"], wraplength=900, justify="left").pack(anchor="w", pady=(8, 2))
        why = tk.Label(main, text=r["explanation"], bg=T.SURFACE, fg=T.TEXT_2, wraplength=900, justify="left")
        why.pack(anchor="w")
        if r["status"] == "PENDING":
            btns = tk.Frame(main, bg=T.SURFACE)
            btns.pack(anchor="w", pady=(10, 0))
            label = {"IRRIGATION": "MARK AS DONE  (LOGS IRRIGATION)", "FERTILIZER": "MARK AS DONE  (LOGS FERTILIZER)"}.get(r["type"], "MARK AS DONE")
            Button(btns, f"✓ {label}", lambda r=r: self.apply(r)).pack(side="left")
            Button(btns, "✕ DISMISS", lambda r=r: self.dismiss(r), kind="ghost").pack(side="left", padx=8)

    def apply(self, r):
        if not messagebox.askyesno("Mark as done", f"Mark this as done?\n\n{r['action']}", parent=self):
            return
        fid = self.farmer_id
        self.run(lambda: db.apply_recommendation(r["rec_id"], fid),
                 done=lambda log: (self.app.toast("Marked as done" + (f" · {log} log saved" if log else ""), "ok"), self.refresh()))

    def dismiss(self, r):
        reason = simpledialog.askstring("Dismiss", "Why are you dismissing this? (optional)", parent=self)
        if reason is None:
            return
        fid = self.farmer_id
        self.run(lambda: db.dismiss_recommendation(r["rec_id"], fid, reason),
                 done=lambda _: (self.app.toast("Dismissed", "ok"), self.refresh()))

    def recheck_all(self):
        fid = self.farmer_id
        self.run(lambda: engine.evaluate_farmer(fid),
                 done=lambda res: (self.app.toast(f"Checked {res['fields']} fields · {res['created']} new, {res['expired']} cleared", "ok"),
                                   self.refresh()))
