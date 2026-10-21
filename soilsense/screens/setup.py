"""First launch: paste the Neon connection string, test it, save it to config.ini."""
import tkinter as tk

from .. import config, db, theme as T
from ..widgets import Button


class SetupScreen(tk.Frame):
    def __init__(self, parent, app, on_saved):
        super().__init__(parent, bg=T.BG)
        self.app, self.on_saved = app, on_saved
        box = tk.Frame(self, bg=T.SURFACE, highlightthickness=1, highlightbackground=T.BORDER)
        box.place(relx=0.5, rely=0.5, anchor="center", width=640)
        tk.Label(box, text="CONNECT TO YOUR DATABASE", bg=T.SURFACE, fg=T.TEXT, font=T.FONTS["h2"]).pack(anchor="w", padx=28, pady=(26, 4))
        tk.Label(box, text="Paste the Neon connection string (Neon → your project → Connect).\n"
                           "It is saved only on this computer, in config.ini.",
                 bg=T.SURFACE, fg=T.TEXT_2, justify="left").pack(anchor="w", padx=28)
        tk.Label(box, text="CONNECTION STRING", bg=T.SURFACE, fg=T.MUTED, font=T.FONTS["mono_bold"]).pack(anchor="w", padx=28, pady=(18, 4))
        self.url = tk.Entry(box, bg=T.SURFACE_2, fg=T.TEXT, insertbackground=T.TEXT, relief="flat", show="•",
                            highlightthickness=1, highlightbackground=T.BORDER, highlightcolor=T.WHEAT, font=T.FONTS["mono"])
        self.url.pack(fill="x", padx=28, ipady=8)
        tk.Label(box, text="postgresql://user:password@ep-xxxx-pooler.….neon.tech/neondb?sslmode=require",
                 bg=T.SURFACE, fg=T.MUTED, font=T.FONTS["small"]).pack(anchor="w", padx=28, pady=(4, 0))
        self.msg = tk.Label(box, text="", bg=T.SURFACE, fg=T.DANGER, wraplength=580, justify="left")
        self.msg.pack(anchor="w", padx=28, pady=(10, 0))
        self.btn = Button(box, "TEST & SAVE", self.save)
        self.btn.pack(anchor="w", padx=28, pady=(10, 26))
        self.url.bind("<Return>", lambda e: self.save())
        self.url.focus_set()

    def save(self):
        url = self.url.get().strip()
        if not url.startswith(("postgres://", "postgresql://")):
            self.msg.config(text="That doesn't look like a PostgreSQL connection string.", fg=T.DANGER)
            return
        self.btn.set_enabled(False, "TESTING…")
        self.msg.config(text="Connecting to Neon… (the first connection can take a few seconds)", fg=T.TEXT_2)

        def test():
            db.connect(url)
            info = db.ping()
            db.one("select count(*) as n from farmers")          # make sure it is the SoilSense database
            return info

        def ok(info):
            config.save_database_url(url)
            self.on_saved()

        def fail(e):
            db.close()
            self.btn.set_enabled(True, "TEST & SAVE")
            self.msg.config(text=f"{e}", fg=T.DANGER)

        self.app.worker.run(test, on_done=ok, on_error=fail)
