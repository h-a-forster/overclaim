import unittest

from ivl import Interval, IntervalSet, coverage_ratio, largest_gap


def iv(lo, hi, lc=None, hc=None):
    return Interval(lo, hi, lc, hc)


class IntervalTests(unittest.TestCase):
    def test_contains(self):
        a = iv(1, 3)
        self.assertTrue(a.contains(1))
        self.assertFalse(a.contains(3))
        self.assertTrue(iv(1, 3, False, True).contains(3))
        self.assertTrue(iv(None, 0).contains(-10 ** 9))

    def test_validation(self):
        for bad in [(3, 1), (2, 2), (None, 1, True, False)]:
            with self.assertRaises(ValueError):
                Interval(*bad)
        self.assertEqual(iv(2, 2, True, True).length(), 0)


class SetTests(unittest.TestCase):
    def test_merge_overlap(self):
        s = IntervalSet([iv(5, 8), iv(1, 3), iv(2, 4)])
        self.assertEqual(list(s), [iv(1, 4), iv(5, 8)])

    def test_half_open_neighbours_merge(self):
        self.assertEqual(list(IntervalSet([iv(1, 2), iv(2, 3)])), [iv(1, 3)])

    def test_contains(self):
        s = IntervalSet([iv(1, 3), iv(5, 8)])
        self.assertTrue(s.contains(5))
        self.assertFalse(s.contains(4))

    def test_union_intersection_difference(self):
        a = IntervalSet([iv(0, 5), iv(10, 15)])
        b = IntervalSet([iv(3, 12)])
        self.assertEqual(list(a.union(b)), [iv(0, 15)])
        self.assertEqual(list(a.intersection(b)), [iv(3, 5), iv(10, 12)])
        self.assertEqual(list(a.difference(b)), [iv(0, 3), iv(12, 15)])

    def test_complement(self):
        c = IntervalSet([iv(1, 2)]).complement()
        self.assertEqual(list(c), [iv(None, 1), iv(2, None)])

    def test_measure(self):
        self.assertEqual(IntervalSet([iv(0, 2), iv(5, 6)]).measure(), 3)


class ReportTests(unittest.TestCase):
    def test_coverage(self):
        s = IntervalSet([iv(0, 2), iv(5, 6)])
        self.assertEqual(coverage_ratio(s, iv(0, 10)), 0.3)

    def test_largest_gap(self):
        s = IntervalSet([iv(0, 2), iv(5, 6)])
        self.assertEqual(largest_gap(s, iv(0, 10)), iv(6, 10))
        self.assertIsNone(largest_gap(IntervalSet([iv(0, 10)]), iv(0, 10)))


if __name__ == "__main__":
    unittest.main()
