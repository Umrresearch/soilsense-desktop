"""Tests for the hand-written data structures (no database needed):  python -m unittest"""
import threading
import unittest

from soilsense.ds import BST, LinkedList, Queue, Stack


class TestLinkedList(unittest.TestCase):
    def test_append_prepend_pop_find_remove(self):
        ll = LinkedList()
        self.assertTrue(ll.is_empty())
        ll.append("b"); ll.append("c"); ll.prepend("a")
        self.assertEqual(list(ll), ["a", "b", "c"])
        self.assertEqual(ll.find(lambda x: x == "b"), "b")
        self.assertTrue(ll.remove(lambda x: x == "c"))
        self.assertEqual(ll.tail.value, "b")
        self.assertFalse(ll.remove(lambda x: x == "zzz"))
        self.assertEqual(ll.pop_front(), "a")
        self.assertEqual(ll.pop_front(), "b")
        self.assertIsNone(ll.head); self.assertIsNone(ll.tail)
        with self.assertRaises(IndexError):
            ll.pop_front()


class TestQueue(unittest.TestCase):
    def test_fifo(self):
        q = Queue()
        for i in range(5):
            q.enqueue(i)
        self.assertEqual(q.peek(), 0)
        self.assertEqual([q.dequeue() for _ in range(5)], [0, 1, 2, 3, 4])
        self.assertIsNone(q.dequeue())

    def test_many_items_fast(self):
        q = Queue()
        for i in range(200_000):
            q.enqueue(i)
        self.assertEqual(sum(q.dequeue() for _ in range(200_000)), 199_999 * 200_000 // 2)

    def test_two_threads(self):
        q, got = Queue(), []
        t = threading.Thread(target=lambda: got.extend(q.dequeue(block=True, timeout=2) for _ in range(3)))
        t.start()
        for i in range(3):
            q.enqueue(i)
        t.join()
        self.assertEqual(got, [0, 1, 2])


class TestStack(unittest.TestCase):
    def test_lifo_and_no_duplicates(self):
        s = Stack()
        s.push("dashboard"); s.push("sensors"); s.push("sensors"); s.push("settings")
        self.assertEqual(len(s), 3)
        self.assertEqual(s.pop(), "settings")
        self.assertEqual(s.peek(), "sensors")
        s.pop(); s.pop()
        self.assertTrue(s.is_empty())
        with self.assertRaises(IndexError):
            s.pop()


class TestBST(unittest.TestCase):
    def test_insert_search_order(self):
        t = BST()
        for k in [50, 30, 70, 20, 40, 60, 80]:
            t.insert(k, f"v{k}")
        self.assertEqual(t.search(60), "v60")
        self.assertIsNone(t.search(65))
        self.assertEqual([k for k, _ in t.in_order()], [20, 30, 40, 50, 60, 70, 80])
        self.assertEqual(t.min()[0], 20); self.assertEqual(t.max()[0], 80)
        self.assertEqual(t.height(), 3)

    def test_floor_ceiling(self):
        t = BST()
        for k in [10, 20, 30, 40]:
            t.insert(k, k)
        self.assertEqual(t.floor(25)[0], 20)
        self.assertEqual(t.ceiling(25)[0], 30)
        self.assertIsNone(t.floor(5)); self.assertIsNone(t.ceiling(45))

    def test_sorted_inserts_vs_balanced(self):
        naive = BST()
        for k in range(500):
            naive.insert(k, k)
        self.assertEqual(naive.height(), 500)                 # degenerates into a linked list
        balanced = BST.from_sorted([(k, k) for k in range(1023)])
        self.assertEqual(balanced.height(), 10)               # log2(1024)
        self.assertEqual(balanced.floor(500.5)[0], 500)


if __name__ == "__main__":
    unittest.main()
