"""
Queue (FIFO — first in, first out), built on our linked list
=============================================================
    enqueue → add at the tail    O(1)
    dequeue → remove the head    O(1)

A Python list's pop(0) is O(n) because every item shifts one place;
the linked list just moves its head pointer.

Used by: worker.py — every database request from the screens is put in a job queue
and a background thread runs the jobs in the order they were asked for. Finished
results go into a second queue that the window empties on its next tick.
The lock makes the queue safe to use from two threads at once.
"""
import threading

from .linked_list import LinkedList


class Queue:
    def __init__(self):
        self._items = LinkedList()
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)

    def enqueue(self, item):
        with self._lock:
            self._items.append(item)
            self._not_empty.notify()               # wake a thread waiting in dequeue(block=True)

    def dequeue(self, block=False, timeout=None):
        """Remove and return the front item. Returns None if empty (and not blocking)."""
        with self._lock:
            if block:
                while self._items.is_empty():
                    if not self._not_empty.wait(timeout):
                        return None
            if self._items.is_empty():
                return None
            return self._items.pop_front()

    def peek(self):
        with self._lock:
            return None if self._items.is_empty() else self._items.head.value

    def __len__(self):
        with self._lock:
            return len(self._items)

    def is_empty(self):
        return len(self) == 0
