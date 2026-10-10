import unittest

import minire


class Basics(unittest.TestCase):
    def test_literal(self):
        self.assertEqual(minire.search("bc", "abcd").span(), (1, 3))

    def test_dot_and_newline(self):
        self.assertIsNone(minire.match("a.c", "a\nc"))
        self.assertEqual(minire.match("a.c", "axc").group(), "axc")

    def test_classes(self):
        self.assertEqual(minire.search(r"[a-c]+", "xxabcabzz").group(), "abcab")
        self.assertEqual(minire.search(r"[^a-c]+", "abxyc").group(), "xy")
        self.assertEqual(minire.search(r"\d+", "ab123c").group(), "123")
        self.assertEqual(minire.search(r"[\d_]+", "ab1_2c").group(), "1_2")

    def test_greedy_quantifiers(self):
        self.assertEqual(minire.match("a*a", "aaa").span(), (0, 3))
        self.assertEqual(minire.match("a?ab", "ab").span(), (0, 2))
        self.assertEqual(minire.fullmatch("a+", "aaa").span(), (0, 3))
        self.assertIsNone(minire.fullmatch("a+", "aaab"))

    def test_errors(self):
        for bad in ("*a", "a**", "[a", "a\\", "[b-a]"):
            with self.assertRaises(minire.PatternError):
                minire.compile(bad)

    def test_escapes(self):
        self.assertEqual(minire.match(r"a\.b", "a.b").group(), "a.b")
        self.assertIsNone(minire.match(r"a\.b", "axb"))
        self.assertEqual(minire.match(r"\t", "\t").span(), (0, 1))
