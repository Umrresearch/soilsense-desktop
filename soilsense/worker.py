"""
Background worker — keeps the window responsive while Neon answers.

Tkinter is single-threaded: if a database call ran on the main thread, the window would
freeze until the cloud database replied. Instead:

  screen ──run(job)──► [ job queue ] ──► worker thread runs jobs in FIFO order
  screen ◄─callback──  [ result queue ] ◄── finished results (emptied every 50 ms by the window)

Both queues are our own linked-list Queue (ds/queue.py).
"""
import threading
import traceback

from .ds import Queue


class Worker:
    def __init__(self, root):
        self.root = root
        self.jobs = Queue()
        self.results = Queue()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="db-worker")
        self._thread.start()
        self._poll()

    def run(self, fn, *args, on_done=None, on_error=None):
        """Queue fn(*args); on_done(result) / on_error(exc) run later on the UI thread."""
        self.jobs.enqueue((fn, args, on_done, on_error))

    def backlog(self):
        """Jobs still waiting — used to skip auto-refresh while the database is slow."""
        return len(self.jobs)

    def _loop(self):
        while True:
            job = self.jobs.dequeue(block=True)                   # waits until a job arrives
            if job is None:
                continue
            fn, args, on_done, on_error = job
            try:
                self.results.enqueue((on_done, fn(*args), None))
            except Exception as e:                                # hand errors back to the UI too
                traceback.print_exc()
                self.results.enqueue((on_error, None, e))

    def _poll(self):
        while True:
            item = self.results.dequeue()
            if item is None:
                break
            cb, value, err = item
            try:
                if err is None and cb:
                    cb(value)
                elif err is not None and cb:
                    cb(err)
            except Exception:
                traceback.print_exc()
        self.root.after(50, self._poll)
