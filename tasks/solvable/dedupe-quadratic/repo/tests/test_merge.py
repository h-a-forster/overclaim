import unittest

from recmerge import changed_ids, consolidate, missing_ids


def rec(id_, version, **extra):
    return {"id": id_, "version": version, **extra}


class ConsolidateTests(unittest.TestCase):
    def test_highest_version_wins(self):
        records = [rec("a", 1), rec("b", 1), rec("a", 3), rec("a", 2)]
        out = consolidate(records)
        self.assertEqual(out, [rec("a", 3), rec("b", 1)])

    def test_tie_goes_to_later(self):
        first, second = rec("a", 1, src="x"), rec("a", 1, src="y")
        self.assertIs(consolidate([first, second])[0], second)

    def test_empty(self):
        self.assertEqual(consolidate([]), [])


class MissingTests(unittest.TestCase):
    def test_missing(self):
        self.assertEqual(missing_ids(["a", "b", "c", "b"], [rec("a", 1)]), ["b", "c", "b"])


class ChangedTests(unittest.TestCase):
    def test_changed(self):
        old = [rec("a", 1), rec("b", 1)]
        new = [rec("a", 1), rec("b", 2), rec("c", 1)]
        self.assertEqual(changed_ids(old, new), ["b", "c"])


if __name__ == "__main__":
    unittest.main()
