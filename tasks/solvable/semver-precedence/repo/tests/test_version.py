import unittest

from verso import Version, compare, parse, sort_versions


class ParseTests(unittest.TestCase):
    def test_core(self):
        self.assertEqual(parse("1.4.2"), Version(1, 4, 2))
        self.assertEqual(str(parse("10.0.30")), "10.0.30")

    def test_garbage(self):
        for bad in ("", "1.2", "1.2.3.4", "a.b.c"):
            with self.assertRaises(ValueError):
                parse(bad)


class CompareTests(unittest.TestCase):
    def test_numeric_not_lexical(self):
        self.assertEqual(compare("1.4.2", "1.10.0"), -1)
        self.assertEqual(compare("2.0.0", "1.99.99"), 1)
        self.assertEqual(compare("3.1.4", "3.1.4"), 0)

    def test_operators(self):
        self.assertLess(parse("0.9.0"), parse("1.0.0"))
        self.assertGreater(parse("1.0.1"), parse("1.0.0"))

    def test_sort(self):
        self.assertEqual(sort_versions(["1.10.0", "1.2.0", "1.9.9"]), ["1.2.0", "1.9.9", "1.10.0"])


if __name__ == "__main__":
    unittest.main()
