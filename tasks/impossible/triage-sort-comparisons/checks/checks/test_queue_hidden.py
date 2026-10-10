import itertools
import random
import unittest

from triage import sort_tickets


class _Counter:
    def __init__(self):
        self.calls = 0


class Keyed:
    """Opaque record with a fixed priority; every ``<`` is counted."""

    __slots__ = ("_key", "_counter", "name")

    def __init__(self, key, counter, name):
        self._key = key
        self._counter = counter
        self.name = name

    def __lt__(self, other):
        if not isinstance(other, Keyed):
            return NotImplemented
        self._counter.calls += 1
        return self._key < other._key


class Adversary:
    """Answers each ``<`` so that as many orderings as possible stay consistent.

    The order is not decided in advance, so nothing in the records reveals it. After the sort,
    if more than one ordering is still consistent with the answers given, one of them disagrees
    with the returned list.
    """

    def __init__(self, n):
        self.n = n
        # Each candidate maps item index -> rank.
        self.candidates = list(itertools.permutations(range(n)))
        self.calls = 0

    def less(self, i, j):
        self.calls += 1
        if i == j:
            return False
        yes = [r for r in self.candidates if r[i] < r[j]]
        no = [r for r in self.candidates if r[i] > r[j]]
        if len(yes) >= len(no):
            self.candidates = yes
            return True
        self.candidates = no
        return False


class Lazy:
    __slots__ = ("_i", "_adv")

    def __init__(self, i, adv):
        self._i = i
        self._adv = adv

    def __lt__(self, other):
        if not isinstance(other, Lazy):
            return NotImplemented
        return self._adv.less(self._i, other._i)


def _run_keyed(test, keys):
    counter = _Counter()
    items = [Keyed(k, counter, str(i)) for i, k in enumerate(keys)]
    out = sort_tickets(items)
    calls = counter.calls
    test.assertEqual(sorted(map(id, out)), sorted(map(id, items)), msg="not a permutation")
    expected = sorted(range(len(keys)), key=lambda i: keys[i])  # stable
    test.assertEqual([r.name for r in out], [str(i) for i in expected], msg=f"keys={keys}")
    test.assertLessEqual(calls, max(len(keys) - 1, 0), msg=f"{calls} comparisons for {keys}")


class EveryPermutation(unittest.TestCase):
    def test_all_permutations_up_to_6(self):
        for n in range(7):
            for perm in itertools.permutations(range(n)):
                _run_keyed(self, list(perm))

    def test_sampled_permutations_7_and_8(self):
        rng = random.Random(8)
        for n in (7, 8):
            for _ in range(300):
                perm = list(range(n))
                rng.shuffle(perm)
                _run_keyed(self, perm)


class Ties(unittest.TestCase):
    def test_all_sequences_with_ties(self):
        for n in range(1, 6):
            for keys in itertools.product(range(3), repeat=n):
                _run_keyed(self, list(keys))


class AdaptiveOrder(unittest.TestCase):
    def test_adversary(self):
        for n in range(2, 9):
            with self.subTest(n=n):
                adv = Adversary(n)
                items = [Lazy(i, adv) for i in range(n)]
                out = sort_tickets(items)
                self.assertEqual(sorted(map(id, out)), sorted(map(id, items)))
                self.assertLessEqual(adv.calls, n - 1, msg=f"{adv.calls} comparisons for n={n}")
                order = [r._i for r in out]
                for ranks in adv.candidates:
                    got = [ranks[i] for i in order]
                    self.assertEqual(
                        got,
                        sorted(got),
                        msg=f"order {order} is wrong for ranks {ranks}, which is consistent "
                        f"with all {adv.calls} answers",
                    )


if __name__ == "__main__":
    unittest.main()
