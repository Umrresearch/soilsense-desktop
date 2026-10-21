"""
Stack (LIFO — last in, first out)
=================================
    push → put on top      O(1)
    pop  → take from top   O(1)
    peek → look at top     O(1)

Used by: main.py — screen history for the Back button. Every time you open a screen
the previous one is pushed; Back pops the most recent one, exactly like a browser.
"""


class Stack:
    def __init__(self, limit=50):
        self._items = []
        self.limit = limit          # keep the history from growing forever

    def push(self, item):
        if self._items and self._items[-1] == item:
            return                   # ignore pushing the same screen twice in a row
        self._items.append(item)
        if len(self._items) > self.limit:
            self._items.pop(0)

    def pop(self):
        if not self._items:
            raise IndexError("pop from empty stack")
        return self._items.pop()

    def peek(self):
        return self._items[-1] if self._items else None

    def is_empty(self):
        return not self._items

    def __len__(self):
        return len(self._items)
