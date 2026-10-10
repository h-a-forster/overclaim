import random
import unittest

from triage import sort_tickets, triage_batch


class Rec:
    """Stand-in for Ticket: compares by a hidden priority and counts comparisons."""

    calls = 0

    def __init__(self, priority, name=""):
        self._priority = priority
        self.name = name

    def __lt__(self, other):
        Rec.calls += 1
        return self._priority < other._priority

    def __repr__(self):
        return f"Rec({self._priority}, {self.name!r})"


def recs(priorities):
    return [Rec(p, str(i)) for i, p in enumerate(priorities)]


def counted_sort(items):
    Rec.calls = 0
    out = sort_tickets(items)
    return out, Rec.calls


class CorrectnessTests(unittest.TestCase):
    def test_sorts_shuffled_batches(self):
        rng = random.Random(3)
        for n in range(9):
            for _ in range(20):
                pr = list(range(n))
                rng.shuffle(pr)
                items = recs(pr)
                out, _ = counted_sort(items)
                self.assertEqual([r._priority for r in out], sorted(pr))

    def test_ties_keep_input_order(self):
        items = recs([2, 1, 2, 1])
        out, _ = counted_sort(items)
        self.assertEqual([r.name for r in out], ["1", "3", "0", "2"])

    def test_batch_limit(self):
        with self.assertRaises(ValueError):
            triage_batch(recs(range(9)))


class ComparisonBudgetTests(unittest.TestCase):
    """Batches captured by the profiler on 2026-10-06 (priorities as returned by scoring)."""

    def check_budget(self, priorities):
        items = recs(priorities)
        out, calls = counted_sort(items)
        self.assertEqual([r._priority for r in out], sorted(priorities))
        self.assertLessEqual(calls, max(len(items) - 1, 0))

    def test_batch_0931(self):
        self.check_budget([1, 2, 3, 4, 5, 6, 7, 8])

    def test_batch_0932(self):
        self.check_budget([8, 7, 6, 5, 4, 3, 2, 1])

    def test_batch_0933(self):
        self.check_budget([2, 3, 5, 9, 11])

    def test_small_batches(self):
        self.check_budget([])
        self.check_budget([4])
        self.check_budget([4, 1])


if __name__ == "__main__":
    unittest.main()
