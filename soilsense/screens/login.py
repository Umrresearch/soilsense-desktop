import tkinter as tk

from .. import auth, theme as T
from ..widgets import Button


class LoginScreen(tk.Frame):
    def __init__(self, parent, app, on_login):
        super().__init__(parent, bg=T.BG)
        self.app, self.on_login = app, on_login
        self.columnconfigure(0, weight=5)
        self.columnconfigure(1, weight=4)
        self.rowconfigure(0, weight=1)

        # left: poster
        poster = tk.Frame(self, bg=T.EMERALD_DARK)
        poster.grid(row=0, column=0, sticky="nsew")
        inner = tk.Frame(poster, bg=T.EMERALD_DARK)
        inner.place(relx=0.1, rely=0.5, anchor="w")
        tk.Label(inner, text="SOILSENSE · SUGARCANE ADVISORY", bg=T.EMERALD_DARK, fg=T.WHEAT, font=T.FONTS["mono_bold"]).pack(anchor="w")
        for line, bg, fg in (("WATER THE CANE", T.EMERALD_DARK, T.TEXT), ("AT THE RIGHT", T.WHEAT, T.ON_WHEAT), ("HOUR.", T.EMERALD_DARK, T.TEXT)):
            tk.Label(inner, text=f" {line} ", bg=bg, fg=fg, font=(T.FONTS["h1"][0], 40, "bold")).pack(anchor="w", pady=1)
        tk.Label(inner, text="Sensors in the soil. Plain advice on your desktop.\nConnected live to the SoilSense cloud database.",
                 bg=T.EMERALD_DARK, fg="#A7F3D0", justify="left").pack(anchor="w", pady=(18, 0))

        # right: form
        side = tk.Frame(self, bg=T.BG)
        side.grid(row=0, column=1, sticky="nsew")
        form = tk.Frame(side, bg=T.BG)
        form.place(relx=0.5, rely=0.5, anchor="center", width=360)
        tk.Label(form, text="WELCOME BACK", bg=T.BG, fg=T.TEXT, font=T.FONTS["h1"]).pack(anchor="w")
        tk.Label(form, text="Log in with your e-mail, mobile number or Farmer ID.", bg=T.BG, fg=T.TEXT_2, wraplength=360, justify="left").pack(anchor="w", pady=(2, 18))
        self.ident = self._field(form, "E-MAIL, MOBILE OR FARMER ID")
        self.pw = self._field(form, "PASSWORD", show="•")
        self.msg = tk.Label(form, text="", bg=T.BG, fg=T.DANGER, wraplength=360, justify="left")
        self.msg.pack(anchor="w", pady=(4, 6))
        self.btn = Button(form, "LOG IN  →", self.submit)
        self.btn.pack(fill="x")
        demo = tk.Frame(form, bg=T.SURFACE, highlightthickness=1, highlightbackground=T.BORDER)
        demo.pack(fill="x", pady=(18, 0))
        tk.Label(demo, text="DEMO ACCOUNT", bg=T.SURFACE, fg=T.WHEAT, font=T.FONTS["mono_bold"]).pack(anchor="w", padx=12, pady=(10, 0))
        tk.Label(demo, text="demo@soilsense.in  /  Demo@1234", bg=T.SURFACE, fg=T.TEXT, font=T.FONTS["mono"]).pack(anchor="w", padx=12, pady=(2, 10))
        demo.bind("<Button-1>", lambda e: self.fill_demo())
        for w in demo.winfo_children():
            w.bind("<Button-1>", lambda e: self.fill_demo())
        self.pw.bind("<Return>", lambda e: self.submit())
        self.ident.bind("<Return>", lambda e: self.pw.focus_set())
        self.ident.focus_set()

    def _field(self, parent, label, show=None):
        tk.Label(parent, text=label, bg=T.BG, fg=T.MUTED, font=T.FONTS["mono_bold"]).pack(anchor="w", pady=(6, 3))
        e = tk.Entry(parent, bg=T.SURFACE_2, fg=T.TEXT, insertbackground=T.TEXT, relief="flat", show=show,
                     highlightthickness=1, highlightbackground=T.BORDER, highlightcolor=T.WHEAT)
        e.pack(fill="x", ipady=8)
        return e

    def fill_demo(self):
        self.ident.delete(0, "end"); self.ident.insert(0, "demo@soilsense.in")
        self.pw.delete(0, "end"); self.pw.insert(0, "Demo@1234")

    def submit(self):
        ident, pw = self.ident.get(), self.pw.get()
        if not ident.strip() or not pw:
            self.msg.config(text="Enter your login details.")
            return
        self.btn.set_enabled(False, "CHECKING…")
        self.msg.config(text="")

        def ok(farmer):
            self.btn.set_enabled(True, "LOG IN  →")
            if farmer:
                self.on_login(farmer)
            else:
                self.msg.config(text="Incorrect login details.")

        def fail(e):
            self.btn.set_enabled(True, "LOG IN  →")
            self.msg.config(text=str(e))

        self.app.worker.run(auth.login, ident, pw, on_done=ok, on_error=fail)
