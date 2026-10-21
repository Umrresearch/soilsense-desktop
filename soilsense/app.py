"""Main window: sidebar navigation, top bar, screen switching, toasts, auto-refresh."""
import tkinter as tk

from . import config, db, theme as T
from .ds import Stack
from .screens.analytics import AnalyticsScreen
from .screens.dashboard import DashboardScreen
from .screens.login import LoginScreen
from .screens.recommendations import RecommendationsScreen
from .screens.sensors import SensorsScreen
from .screens.settings import SettingsScreen
from .screens.setup import SetupScreen
from .widgets import Button
from .worker import Worker

NAV = [("dashboard", "▦  Dashboard"), ("sensors", "◉  Live sensors"), ("analytics", "▤  Analytics"),
       ("recommendations", "✦  Recommendations"), ("settings", "⚙  Settings")]
SCREENS = {"dashboard": DashboardScreen, "sensors": SensorsScreen, "analytics": AnalyticsScreen,
           "recommendations": RecommendationsScreen, "settings": SettingsScreen}
AUTO_REFRESH_MS = 60_000


class App:
    def __init__(self, root):
        self.root = root
        root.title("SoilSense — Smart Sugarcane Farm Advisory")
        root.geometry("1360x860")
        root.minsize(1100, 700)
        T.setup(root)
        self.worker = Worker(root)
        self.farmer = None
        self.history = Stack()                  # Back button: last screens visited (LIFO)
        self.current = None
        self.screens = {}
        self._busy = 0
        self._refresh_job = None
        self.container = tk.Frame(root, bg=T.BG)
        self.container.pack(fill="both", expand=True)
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.start()

    # ------------------------------------------------------------------ flow
    def start(self):
        self._clear()
        if not config.database_url():
            SetupScreen(self.container, self, on_saved=self.start).pack(fill="both", expand=True)
        else:
            LoginScreen(self.container, self, on_login=self.logged_in).pack(fill="both", expand=True)

    def change_database(self):
        self.logout(go_setup=True)

    def logged_in(self, farmer):
        self.farmer = farmer
        self._clear()
        self._build_shell()
        self.navigate("dashboard", remember=False)
        self._schedule_refresh()

    def logout(self, go_setup=False):
        for job in (self._refresh_job, getattr(self, "_toast_job", None)):
            if job:
                self.root.after_cancel(job)
        self._refresh_job = self._toast_job = None
        self.farmer, self.history, self.screens, self.current = None, Stack(), {}, None
        if go_setup:
            db.close()
            self._clear()
            SetupScreen(self.container, self, on_saved=self.start).pack(fill="both", expand=True)
        else:
            self.start()

    def quit(self):
        self.farmer = None
        db.close()
        self.root.destroy()

    def _clear(self):
        for w in self.container.winfo_children():
            w.destroy()

    # ------------------------------------------------------------------ shell
    def _build_shell(self):
        side = tk.Frame(self.container, bg="#050605", width=250)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        brand = tk.Frame(side, bg="#050605")
        brand.pack(fill="x", padx=18, pady=(20, 24))
        tk.Label(brand, text=" ✿ ", bg=T.EMERALD, fg=T.TEXT, font=T.FONTS["h2"]).pack(side="left")
        txt = tk.Frame(brand, bg="#050605")
        txt.pack(side="left", padx=10)
        tk.Label(txt, text="SOILSENSE", bg="#050605", fg=T.TEXT, font=T.FONTS["brand"]).pack(anchor="w")
        tk.Label(txt, text="SUGARCANE ADVISORY", bg="#050605", fg=T.WHEAT, font=(T.FONTS["mono"][0], 8)).pack(anchor="w")
        self.nav_items = {}
        for key, label in NAV:
            item = tk.Label(side, text=label, bg="#050605", fg=T.TEXT_2, anchor="w", padx=18, pady=10,
                            font=T.FONTS["mono_bold"], cursor="hand2")
            item.pack(fill="x", padx=10, pady=1)
            item.bind("<Button-1>", lambda e, k=key: self.navigate(k))
            self.nav_items[key] = item
        tk.Frame(side, bg="#050605").pack(fill="both", expand=True)
        Button(side, "⎋  LOG OUT", self.logout, kind="ghost").pack(fill="x", padx=18, pady=18)

        main = tk.Frame(self.container, bg=T.BG)
        main.pack(side="left", fill="both", expand=True)
        top = tk.Frame(main, bg=T.BG, highlightthickness=0)
        top.pack(fill="x")
        self.back_btn = Button(top, "←  BACK", self.back, kind="ghost", padx=10, pady=5)
        self.back_btn.pack(side="left", padx=(20, 10), pady=12)
        self.title = tk.Label(top, text="", bg=T.BG, fg=T.TEXT, font=T.FONTS["h1"])
        self.title.pack(side="left")
        user = tk.Frame(top, bg=T.BG)
        user.pack(side="right", padx=20)
        initials = "".join(p[0] for p in self.farmer["name"].split()[:2]).upper()
        tk.Label(user, text=f" {initials} ", bg=T.WHEAT, fg=T.ON_WHEAT, font=T.FONTS["bold"]).pack(side="left", padx=(0, 8))
        who = tk.Frame(user, bg=T.BG)
        who.pack(side="left")
        tk.Label(who, text=self.farmer["name"], bg=T.BG, fg=T.TEXT, font=T.FONTS["bold"]).pack(anchor="w")
        tk.Label(who, text=self.farmer["farmer_id"], bg=T.BG, fg=T.MUTED, font=T.FONTS["mono"]).pack(anchor="w")
        Button(top, "⟳  REFRESH", self.refresh_current, kind="ghost", padx=10, pady=5).pack(side="right")
        self.live = tk.Label(top, text="● LIVE · NEON", bg=T.BG, fg=T.GREEN, font=T.FONTS["mono_bold"])
        self.live.pack(side="right", padx=14)
        tk.Frame(main, bg=T.BORDER, height=1).pack(fill="x")
        self.body = tk.Frame(main, bg=T.BG)
        self.body.pack(fill="both", expand=True)
        self.toast_label = tk.Label(main, text="", bg=T.SURFACE_2, fg=T.TEXT, padx=16, pady=10,
                                    highlightthickness=1, highlightbackground=T.BORDER)

    def navigate(self, key, remember=True, **kw):
        if self.current and remember and key != self.current:
            self.history.push(self.current)
        for k, item in self.nav_items.items():
            on = k == key
            item.config(bg=T.EMERALD if on else "#050605", fg=T.TEXT if on else T.TEXT_2)
        for s in self.screens.values():
            s.pack_forget()
        if key not in self.screens:
            self.screens[key] = SCREENS[key](self.body, self)
        screen = self.screens[key]
        screen.pack(fill="both", expand=True)
        self.title.config(text=screen.title.upper())
        self.current = key
        self.back_btn.set_enabled(not self.history.is_empty())
        screen.refresh(**kw)

    def back(self):
        if not self.history.is_empty():
            self.navigate(self.history.pop(), remember=False)

    def refresh_current(self):
        if self.current:
            self.screens[self.current].refresh()

    def _schedule_refresh(self):
        def tick():
            if self.farmer:
                screen = self.screens.get(self.current)
                if screen is not None and not screen.busy and not self.worker.backlog():
                    screen.refresh()
                self._refresh_job = self.root.after(AUTO_REFRESH_MS, tick)
        self._refresh_job = self.root.after(AUTO_REFRESH_MS, tick)

    # ------------------------------------------------------------------ feedback
    def busy(self, on):
        self._busy = max(0, self._busy + (1 if on else -1))
        if hasattr(self, "live") and self.live.winfo_exists():
            self.live.config(text="◌ LOADING…" if self._busy else "● LIVE · NEON", fg=T.WHEAT if self._busy else T.GREEN)

    def toast(self, text, kind="ok"):
        if not hasattr(self, "toast_label") or not self.toast_label.winfo_exists():
            from tkinter import messagebox
            (messagebox.showerror if kind == "error" else messagebox.showinfo)("SoilSense", text)
            return
        color = {"ok": T.GREEN, "error": T.DANGER}.get(kind, T.WHEAT)
        self.toast_label.config(text=text, highlightbackground=color, fg=color if kind == "error" else T.TEXT)
        self.toast_label.place(relx=1.0, rely=1.0, x=-24, y=-24, anchor="se")
        self.toast_label.lift()
        if getattr(self, "_toast_job", None):
            self.root.after_cancel(self._toast_job)
        label = self.toast_label
        self._toast_job = self.root.after(4000, lambda: label.winfo_exists() and label.place_forget())
