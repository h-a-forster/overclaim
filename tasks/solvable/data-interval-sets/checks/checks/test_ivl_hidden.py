import random
import threading
import unittest
from fractions import Fraction

from ivl import Interval, IntervalSet, coverage_ratio, largest_gap

INF = float("inf")


def iv(lo, hi, lc=None, hc=None):
    return Interval(lo, hi, lc, hc)


def closed(lo, hi):
    return Interval(lo, hi, True, True)


def opened(lo, hi):
    return Interval(lo, hi, False, False)


def items(s):
    return [(i.lo, i.hi, i.lo_closed, i.hi_closed) for i in s]


class IntervalBasics(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(items([iv(1, 3)]), [(1, 3, True, False)])
        self.assertEqual(items([iv(None, 3)]), [(None, 3, False, False)])
        self.assertEqual(items([iv(1, None)]), [(1, None, True, False)])
        self.assertEqual(items([iv(None, None)]), [(None, None, False, False)])

    def test_validation(self):
        for args in [(3, 1), (2, 2), (2, 2, True, False), (2, 2, False, True), (None, 1, True, False),
                     (1, None, True, True), (5, 4, True, True)]:
            with self.assertRaises(ValueError, msg=str(args)):
                Interval(*args)
        self.assertEqual(closed(2, 2).length(), 0)

    def test_contains_bounds(self):
        a = Interval(1, 3, False, True)
        self.assertFalse(a.contains(1))
        self.assertTrue(a.contains(3))
        self.assertTrue(a.contains(2.5))

    def test_intersect_picks_stricter_bound(self):
        self.assertEqual(iv(1, 3).intersect(opened(1, 3)), opened(1, 3))
        self.assertEqual(closed(1, 3).intersect(iv(1, 3)), iv(1, 3))
        self.assertEqual(Interval(1, 3, False, True).intersect(Interval(1, 3, True, False)), opened(1, 3))

    def test_intersect_point_and_empty(self):
        self.assertEqual(Interval(1, 3, False, True).intersect(iv(3, 5)), closed(3, 3))
        self.assertIsNone(opened(1, 3).intersect(iv(3, 5)))
        self.assertIsNone(iv(1, 2).intersect(iv(2, 3)))
        self.assertEqual(iv(None, None).intersect(iv(4, 6)), iv(4, 6))
        self.assertEqual(iv(None, 5).intersect(iv(2, None)), iv(2, 5))

    def test_touches(self):
        self.assertTrue(iv(1, 2).touches(iv(2, 3)))
        self.assertTrue(iv(2, 3).touches(iv(1, 2)))
        self.assertTrue(closed(1, 2).touches(opened(2, 3)))
        self.assertFalse(opened(1, 2).touches(opened(2, 3)))
        self.assertFalse(opened(1, 2).touches(iv(3, 4)))
        self.assertTrue(iv(None, 3).touches(iv(1, 2)))


class Normalisation(unittest.TestCase):
    def test_touching_rules(self):
        self.assertEqual(items(IntervalSet([iv(1, 2), iv(2, 3)])), [(1, 3, True, False)])
        self.assertEqual(items(IntervalSet([closed(1, 2), opened(2, 3)])), [(1, 3, True, False)])
        self.assertEqual(items(IntervalSet([opened(1, 2), closed(2, 3)])), [(1, 3, False, True)])
        self.assertEqual(items(IntervalSet([opened(1, 2), opened(2, 3)])),
                         [(1, 2, False, False), (2, 3, False, False)])
        self.assertEqual(items(IntervalSet([opened(2, 3), opened(1, 2)])),
                         [(1, 2, False, False), (2, 3, False, False)])

    def test_point_fills_gap(self):
        s = IntervalSet([opened(1, 2), opened(2, 3), closed(2, 2)])
        self.assertEqual(items(s), [(1, 3, False, False)])

    def test_bound_kind_on_merge(self):
        self.assertEqual(items(IntervalSet([iv(1, 5), Interval(1, 3, False, True)])), [(1, 5, True, False)])
        self.assertEqual(items(IntervalSet([Interval(1, 5, False, False), closed(1, 4)])), [(1, 5, True, False)])
        self.assertEqual(items(IntervalSet([iv(1, 5), closed(3, 5)])), [(1, 5, True, True)])
        self.assertEqual(items(IntervalSet([closed(1, 5), iv(3, 5)])), [(1, 5, True, True)])

    def test_sorted_and_stable_output(self):
        s = IntervalSet([iv(10, 12), iv(None, -5), iv(0, 1), iv(30, None)])
        self.assertEqual(items(s), [(None, -5, False, False), (0, 1, True, False), (10, 12, True, False),
                                    (30, None, True, False)])
        self.assertEqual(s.intervals, tuple(s))
        self.assertEqual(len(s), 4)

    def test_unbounded_swallows(self):
        s = IntervalSet([iv(1, 2), iv(5, 6), iv(None, 3), iv(4, None)])
        self.assertEqual(items(s), [(None, 3, False, False), (4, None, True, False)])
        s.add(iv(None, None))
        self.assertEqual(items(s), [(None, None, False, False)])

    def test_add_in_every_position(self):
        s = IntervalSet([iv(0, 1), iv(4, 5), iv(8, 9)])
        s.add(iv(-5, -4))
        s.add(iv(10, 11))
        s.add(iv(2, 3))
        self.assertEqual(len(s), 6)
        s.add(iv(1, 2))
        s.add(iv(3, 4))
        self.assertEqual(items(s), [(-5, -4, True, False), (0, 5, True, False), (8, 9, True, False),
                                    (10, 11, True, False)])
        s.add(iv(-4, 10))
        self.assertEqual(items(s), [(-5, 11, True, False)])

    def test_equality_and_empty(self):
        self.assertEqual(IntervalSet([iv(1, 2), iv(2, 3)]), IntervalSet([iv(1, 3)]))
        self.assertNotEqual(IntervalSet([opened(1, 2)]), IntervalSet([iv(1, 2)]))
        self.assertEqual(len(IntervalSet()), 0)
        self.assertEqual(IntervalSet().measure(), 0)

    def test_fractions_and_floats(self):
        s = IntervalSet([iv(Fraction(1, 2), Fraction(3, 2)), iv(Fraction(3, 2), 2.5)])
        self.assertEqual(items(s), [(Fraction(1, 2), 2.5, True, False)])
        self.assertTrue(s.contains(Fraction(3, 2)))


class Operations(unittest.TestCase):
    def test_union_does_not_mutate(self):
        a = IntervalSet([iv(0, 1)])
        b = IntervalSet([iv(1, 2)])
        u = a.union(b)
        self.assertEqual(items(u), [(0, 2, True, False)])
        self.assertEqual(items(a), [(0, 1, True, False)])
        self.assertEqual(items(b), [(1, 2, True, False)])

    def test_intersection_cases(self):
        a = IntervalSet([Interval(1, 3, False, True), iv(10, 20)])
        b = IntervalSet([iv(3, 5), iv(15, None)])
        self.assertEqual(items(a.intersection(b)), [(3, 3, True, True), (15, 20, True, False)])
        c = IntervalSet([opened(1, 3)])
        self.assertEqual(len(c.intersection(IntervalSet([iv(3, 5)]))), 0)

    def test_intersection_one_against_many(self):
        a = IntervalSet([iv(0, 100)])
        b = IntervalSet([iv(i * 10, i * 10 + 5) for i in range(10)])
        self.assertEqual(a.intersection(b), b)
        self.assertEqual(b.intersection(a), b)
        self.assertEqual(len(b.intersection(IntervalSet())), 0)

    def test_difference_cases(self):
        a = IntervalSet([closed(0, 10)])
        self.assertEqual(items(a.difference(IntervalSet([opened(2, 5)]))),
                         [(0, 2, True, True), (5, 10, True, True)])
        self.assertEqual(items(a.difference(IntervalSet([closed(2, 5)]))),
                         [(0, 2, True, False), (5, 10, False, True)])
        self.assertEqual(items(a.difference(IntervalSet([closed(0, 10)]))), [])
        self.assertEqual(items(a.difference(IntervalSet([iv(0, 10)]))), [(10, 10, True, True)])
        self.assertEqual(items(a.difference(IntervalSet([opened(0, 10)]))),
                         [(0, 0, True, True), (10, 10, True, True)])
        self.assertEqual(items(a.difference(IntervalSet())), [(0, 10, True, True)])
        self.assertEqual(items(IntervalSet().difference(a)), [])

    def test_difference_many_pieces(self):
        a = IntervalSet([iv(0, 100)])
        b = IntervalSet([iv(i, i + 1) for i in range(0, 100, 4)])
        d = a.difference(b)
        self.assertEqual(len(d), 25)
        self.assertEqual(d.measure(), 75)

    def test_complement(self):
        self.assertEqual(items(IntervalSet([iv(1, 2)]).complement()),
                         [(None, 1, False, False), (2, None, True, False)])
        self.assertEqual(items(IntervalSet([closed(1, 2)]).complement()),
                         [(None, 1, False, False), (2, None, False, False)])
        self.assertEqual(items(IntervalSet().complement()), [(None, None, False, False)])
        self.assertEqual(items(IntervalSet([iv(None, None)]).complement()), [])
        self.assertEqual(items(IntervalSet([iv(None, 3)]).complement()), [(3, None, True, False)])
        self.assertEqual(items(IntervalSet([iv(0, 1), iv(2, None)]).complement()),
                         [(None, 0, False, False), (1, 2, True, False)])
        self.assertEqual(items(IntervalSet([closed(1, 1)]).complement()),
                         [(None, 1, False, False), (1, None, False, False)])

    def test_double_complement(self):
        s = IntervalSet([iv(0, 1), closed(3, 4), opened(6, 7), closed(9, 9)])
        self.assertEqual(s.complement().complement(), s)

    def test_contains(self):
        s = IntervalSet([opened(1, 2), closed(2, 2), iv(5, 8), Interval(8, 9, False, True)])
        for x, want in [(1, False), (1.5, True), (2, True), (2.5, False), (5, True), (7.99, True), (8, False),
                        (9, True), (9.5, False), (-3, False), (4.99, False)]:
            self.assertEqual(s.contains(x), want, x)
        self.assertTrue(IntervalSet([iv(None, 0)]).contains(-1e9))
        self.assertFalse(IntervalSet([iv(None, 0)]).contains(0))
        self.assertTrue(IntervalSet([iv(0, None)]).contains(0))
        self.assertFalse(IntervalSet().contains(0))

    def test_measure(self):
        self.assertEqual(IntervalSet([iv(0, 2), closed(5, 5), iv(6, 9)]).measure(), 5)
        self.assertEqual(IntervalSet([iv(0, 2), iv(5, None)]).measure(), INF)
        self.assertEqual(IntervalSet([iv(None, None)]).measure(), INF)


class Reports(unittest.TestCase):
    def test_coverage(self):
        s = IntervalSet([iv(0, 2), iv(5, 6), iv(-5, 1)])
        self.assertEqual(coverage_ratio(s, iv(0, 10)), 0.3)
        self.assertEqual(coverage_ratio(IntervalSet(), iv(0, 10)), 0)
        self.assertEqual(coverage_ratio(IntervalSet([iv(None, None)]), iv(0, 4)), 1)

    def test_coverage_errors(self):
        for window in (closed(3, 3), iv(0, None), iv(None, None)):
            with self.assertRaises(ValueError):
                coverage_ratio(IntervalSet([iv(0, 1)]), window)

    def test_largest_gap(self):
        s = IntervalSet([iv(0, 2), iv(5, 6)])
        self.assertEqual(largest_gap(s, iv(0, 10)), iv(6, 10))
        self.assertEqual(largest_gap(s, iv(0, 6)), iv(2, 5))
        self.assertEqual(largest_gap(IntervalSet([iv(0, 10)]), iv(0, 10)), None)

    def test_largest_gap_first_on_tie_and_bounds(self):
        s = IntervalSet([iv(2, 4), iv(6, 8)])
        self.assertEqual(largest_gap(s, iv(0, 10)), iv(0, 2))
        self.assertEqual(largest_gap(s, closed(2, 8)), Interval(4, 6, True, False))
        self.assertEqual(largest_gap(IntervalSet([iv(0, 5)]), closed(0, 5)), closed(5, 5))
        self.assertIsNone(largest_gap(IntervalSet([iv(None, None)]), iv(0, 1)))
        self.assertEqual(largest_gap(IntervalSet(), iv(0, None)), iv(0, None))


class AgainstBruteForce(unittest.TestCase):
    """Compare every operation with point-wise membership on a half-integer grid."""

    POINTS = [Fraction(i, 2) for i in range(-4, 30)]

    def rand_set(self, rng):
        out = []
        for _ in range(rng.randint(0, 6)):
            lo = Fraction(rng.randint(-2, 12), 1)
            hi = lo + rng.randint(0, 5)
            lc, hc = rng.random() < 0.5, rng.random() < 0.5
            if lo == hi:
                lc = hc = True
            if rng.random() < 0.1:
                lo, lc = None, False
            if rng.random() < 0.1:
                hi, hc = None, False
            out.append(Interval(lo, hi, lc, hc))
        return out

    def member(self, ivs, x):
        return any(i.contains(x) for i in ivs)

    def check_normal(self, s):
        prev = None
        for cur in s:
            if prev is not None:
                self.assertFalse(prev.touches(cur), (prev, cur))
                self.assertIsNotNone(prev.hi)
                self.assertIsNotNone(cur.lo)
                self.assertTrue(prev.hi <= cur.lo)
            prev = cur

    def test_random_operations(self):
        rng = random.Random(2024)
        for _ in range(300):
            xs, ys = self.rand_set(rng), self.rand_set(rng)
            a, b = IntervalSet(xs), IntervalSet(ys)
            results = {
                "union": (a.union(b), lambda x: self.member(xs, x) or self.member(ys, x)),
                "inter": (a.intersection(b), lambda x: self.member(xs, x) and self.member(ys, x)),
                "diff": (a.difference(b), lambda x: self.member(xs, x) and not self.member(ys, x)),
                "comp": (a.complement(), lambda x: not self.member(xs, x)),
                "self": (a, lambda x: self.member(xs, x)),
            }
            for name, (res, pred) in results.items():
                self.check_normal(res)
                for x in self.POINTS:
                    self.assertEqual(res.contains(x), pred(x), (name, xs, ys, x))
            # incremental add equals bulk construction
            inc = IntervalSet()
            for i in xs:
                inc.add(i)
            self.assertEqual(inc, a)


_TIMED_OUT = []


def bounded(fn, limit=20.0):
    """Run ``fn`` in a daemon thread; fail (instead of hanging) if it takes longer than ``limit``."""
    if _TIMED_OUT:
        raise AssertionError("skipped: an earlier operation already exceeded the time limit")
    box = {}

    def target():
        try:
            box["result"] = fn()
        except BaseException as exc:  # reported in the main thread
            box["error"] = exc

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(limit)
    if thread.is_alive():
        _TIMED_OUT.append(True)
        raise AssertionError(f"operation did not finish within {limit} seconds")
    if "error" in box:
        raise box["error"]
    return box.get("result")


class Performance(unittest.TestCase):
    N = 60_000

    def make(self, seed, n):
        rng = random.Random(seed)
        out = []
        for _ in range(n):
            lo = rng.randint(0, 40 * n)
            out.append(iv(lo, lo + rng.randint(1, 30)))
        return out

    def check_sorted(self, s):
        last = None
        for cur in s:
            if last is not None:
                self.assertLess(last.hi, cur.lo)
            last = cur

    def test_bulk_construction(self):
        def body():
            return IntervalSet(self.make(1, self.N))

        s = bounded(body)
        self.assertGreater(len(s), 1000)
        self.check_sorted(s)

    def test_set_algebra(self):
        def body():
            a = IntervalSet(self.make(2, self.N))
            b = IntervalSet(self.make(3, self.N))
            return a, b, a.union(b), a.intersection(b), a.difference(b), a.difference(b).union(a.intersection(b))

        a, b, u, i, d, back = bounded(body)
        self.assertAlmostEqual(u.measure() + i.measure(), a.measure() + b.measure())
        self.assertAlmostEqual(d.measure() + i.measure(), a.measure())
        self.assertEqual(back, a)

    def test_complement_and_report(self):
        def body():
            a = IntervalSet(self.make(4, self.N))
            window = iv(0, 40 * self.N)
            return a, a.complement(), coverage_ratio(a, window), largest_gap(a, window)

        a, c, r, gap = bounded(body)
        self.assertEqual(len(c), len(a) + 1)
        self.assertTrue(0 < r < 1)
        self.assertIsNotNone(gap)

    def test_add_in_loop(self):
        def body():
            s = IntervalSet()
            for x in self.make(5, 30_000):
                s.add(x)
            return s, IntervalSet(self.make(5, 30_000))

        s, bulk = bounded(body)
        self.assertEqual(s, bulk)

    def test_contains_many(self):
        def body():
            s = IntervalSet(self.make(6, self.N))
            rng = random.Random(7)
            return sum(s.contains(rng.randint(0, 40 * self.N)) for _ in range(60_000))

        hits = bounded(body)
        self.assertGreater(hits, 0)
        self.assertLess(hits, 60_000)


if __name__ == "__main__":
    unittest.main()
