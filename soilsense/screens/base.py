import tkinter as tk

from .. import theme as T


class Screen(tk.Frame):
    """Base class: every screen gets the app (worker, farmer, toast, navigate) and a refresh()."""
    title = ""

    def __init__(self, parent, app):
        super().__init__(parent, bg=T.BG)
        self.app = app

    @property
    def farmer_id(self):
        return self.app.farmer["farmer_id"]

    def run(self, fn, *args, done=None, key=None):
        """Run a database call in the background; show errors as a toast.

        key: requests with the same key are "latest wins" — if the user switches field twice
        quickly, only the newest answer is drawn, so an old slow reply can't overwrite it.
        """
        if not hasattr(self, "_tokens"):
            self._tokens, self.pending = {}, 0
        token = None
        if key:
            token = self._tokens[key] = self._tokens.get(key, 0) + 1
        self.pending += 1
        self.app.busy(True)

        def finish():
            self.pending -= 1
            self.app.busy(False)
            return self.winfo_exists() and (key is None or self._tokens.get(key) == token)

        def ok(v):
            if finish() and done:
                done(v)

        def fail(e):
            if finish():
                self.app.toast(str(e), "error")

        self.app.worker.run(fn, *args, on_done=ok, on_error=fail)

    def refresh(self):
        pass

    @property
    def busy(self):
        return getattr(self, "pending", 0) > 0
