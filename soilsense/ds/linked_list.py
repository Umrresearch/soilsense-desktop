"""
Singly linked list
==================
Each node stores a value and a reference to the next node.
We keep both `head` and `tail`, so adding at the end and removing at the front are O(1).

    head → [a | •] → [b | •] → [c | None] ← tail

Used by: ds/queue.py (the queue stores its items in this list).
"""


class Node:
    __slots__ = ("value", "next")

    def __init__(self, value, next=None):
        self.value = value
        self.next = next


class LinkedList:
    def __init__(self):
        self.head = None
        self.tail = None
        self.size = 0

    def append(self, value):
        """Add at the end — O(1)."""
        node = Node(value)
        if self.head is None:
            self.head = self.tail = node          # empty list: node is both head and tail
        else:
            self.tail.next = node                 # link the old tail to the new node
            self.tail = node
        self.size += 1

    def prepend(self, value):
        """Add at the front — O(1)."""
        self.head = Node(value, self.head)
        if self.tail is None:
            self.tail = self.head
        self.size += 1

    def pop_front(self):
        """Remove and return the first value — O(1). Raises IndexError if empty."""
        if self.head is None:
            raise IndexError("pop from empty list")
        value = self.head.value
        self.head = self.head.next                # move head one step forward
        if self.head is None:
            self.tail = None                      # list became empty
        self.size -= 1
        return value

    def find(self, predicate):
        """First value for which predicate(value) is True — O(n)."""
        node = self.head
        while node:
            if predicate(node.value):
                return node.value
            node = node.next
        return None

    def remove(self, predicate):
        """Remove the first matching value; True if something was removed — O(n)."""
        prev, node = None, self.head
        while node:
            if predicate(node.value):
                if prev:
                    prev.next = node.next         # unlink: previous node skips over this one
                else:
                    self.head = node.next         # removing the head
                if node is self.tail:
                    self.tail = prev
                self.size -= 1
                return True
            prev, node = node, node.next
        return False

    def __iter__(self):
        node = self.head
        while node:
            yield node.value
            node = node.next

    def __len__(self):
        return self.size

    def is_empty(self):
        return self.size == 0
