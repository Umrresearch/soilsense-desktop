r"""
Binary search tree (BST)
========================
Rule: every key in a node's LEFT subtree is smaller, every key in its RIGHT subtree is larger.

                [12:00]
               /       \
          [09:00]     [15:00]
          /    \           \
      [08:00] [10:00]    [18:00]

insert / search / floor / ceiling follow one root-to-leaf path: O(h), h = height.
Balanced → h ≈ log2(n). Inserting keys already in order makes a straight line (h = n),
so from_sorted() builds a balanced tree by always choosing the middle item as the root.

Used by: screens/sensors.py — each chart's readings are stored in a BST keyed by time.
When you move the mouse over a chart, floor(time_under_mouse) finds the reading at or
just before that moment and shows it in the read-out.
"""


class _Node:
    __slots__ = ("key", "value", "left", "right")

    def __init__(self, key, value):
        self.key, self.value = key, value
        self.left = self.right = None


class BST:
    def __init__(self):
        self.root = None
        self.size = 0

    def insert(self, key, value):
        """Insert, or replace the value if the key exists — O(h)."""
        if self.root is None:
            self.root = _Node(key, value)
            self.size = 1
            return
        node = self.root
        while True:
            if key == node.key:
                node.value = value
                return
            side = "left" if key < node.key else "right"     # smaller → left, larger → right
            child = getattr(node, side)
            if child is None:
                setattr(node, side, _Node(key, value))
                self.size += 1
                return
            node = child

    def search(self, key):
        node = self.root
        while node:
            if key == node.key:
                return node.value
            node = node.left if key < node.key else node.right
        return None

    def floor(self, key):
        """(key, value) with the largest key <= key, or None — O(h)."""
        node, best = self.root, None
        while node:
            if key == node.key:
                return node.key, node.value
            if key < node.key:
                node = node.left                  # too late: go left
            else:
                best = node                       # candidate: look right for a closer one
                node = node.right
        return (best.key, best.value) if best else None

    def ceiling(self, key):
        """(key, value) with the smallest key >= key, or None — O(h)."""
        node, best = self.root, None
        while node:
            if key == node.key:
                return node.key, node.value
            if key > node.key:
                node = node.right
            else:
                best = node
                node = node.left
        return (best.key, best.value) if best else None

    def min(self):
        node = self.root
        while node and node.left:
            node = node.left
        return (node.key, node.value) if node else None

    def max(self):
        node = self.root
        while node and node.right:
            node = node.right
        return (node.key, node.value) if node else None

    def in_order(self):
        """Left → node → right: yields (key, value) in sorted order."""
        out, stack, node = [], [], self.root
        while stack or node:                      # iterative, so deep trees can't hit the recursion limit
            while node:
                stack.append(node)
                node = node.left
            node = stack.pop()
            out.append((node.key, node.value))
            node = node.right
        return out

    def height(self):
        def h(n):
            return 0 if n is None else 1 + max(h(n.left), h(n.right))
        return h(self.root)

    @classmethod
    def from_sorted(cls, items):
        """Balanced tree from [(key, value), ...] already sorted by key — O(n), height ≈ log2(n)."""
        tree = cls()

        def build(lo, hi):
            if lo > hi:
                return None
            mid = (lo + hi) // 2                  # middle item becomes the root
            node = _Node(*items[mid])
            node.left = build(lo, mid - 1)        # left half → left subtree
            node.right = build(mid + 1, hi)       # right half → right subtree
            return node

        tree.root = build(0, len(items) - 1)
        tree.size = len(items)
        return tree
