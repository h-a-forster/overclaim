import random
import unittest

from verso import Version, compare, parse, sort_versions

SPEC_ORDER = [
    "1.0.0-alpha",
    "1.0.0-alpha.1",
    "1.0.0-alpha.beta",
    "1.0.0-beta",
    "1.0.0-beta.2",
    "1.0.0-beta.11",
    "1.0.0-rc.1",
    "1.0.0",
    "1.0.1-0",
    "1.0.1",
    "1.1.0-alpha",
    "2.0.0-0.3.7",
    "2.0.0-x.7.z.92",
    "2.0.0",
]


class Parsing(unittest.TestCase):
    def test_fields(self):
        v = parse("1.0.0-alpha.1+build.001.exp-sha")
        self.assertEqual((v.major, v.minor, v.patch), (1, 0, 0))
        self.assertEqual(v.prerelease, ("alpha", "1"))
        self.assertEqual(v.build, ("build", "001", "exp-sha"))

    def test_valid_round_trip(self):
        valid = [
            "0.0.4", "1.2.3", "10.20.30", "1.1.2-prerelease+meta", "1.1.2+meta", "1.1.2+meta-valid",
            "1.0.0-alpha", "1.0.0-beta", "1.0.0-alpha.beta", "1.0.0-alpha.beta.1", "1.0.0-alpha.1",
            "1.0.0-alpha0.valid", "1.0.0-alpha.0valid", "1.0.0-rc.1+build.1", "2.0.0-rc.1+build.123",
            "1.2.3-beta", "10.2.3-DEV-SNAPSHOT", "1.2.3-SNAPSHOT-123", "2.0.0+build.1848",
            "2.0.1-alpha.1227", "1.0.0-alpha+beta", "1.2.3----RC-SNAPSHOT.12.9.1--.12+788",
            "1.2.3----R-S.12.9.1--.12+meta", "1.2.3----RC-SNAPSHOT.12.9.1--.12", "1.0.0+0.build.1-rc.10000aaa-kk-0.1",
            "99999999999999999999999.999999999999999999.99999999999999999", "1.0.0-0A.is.legal",
            "1.0.0+001", "1.0.0-0",
        ]
        for text in valid:
            with self.subTest(text=text):
                self.assertEqual(str(parse(text)), text)

    def test_invalid(self):
        invalid = [
            "1", "1.2", "1.2.3-0123", "1.2.3-0123.0123", "1.1.2+.123", "+invalid", "-invalid",
            "-invalid+invalid", "-invalid.01", "alpha", "alpha.beta", "alpha.beta.1", "alpha.1",
            "alpha+beta", "alpha_beta", "alpha.", "alpha..", "beta", "1.0.0-alpha_beta", "-alpha.",
            "1.0.0-alpha..", "1.0.0-alpha..1", "1.0.0-alpha...1", "1.0.0-alpha....1",
            "1.0.0-alpha.....1", "1.0.0-alpha......1", "1.0.0-alpha.......1", "01.1.1", "1.01.1",
            "1.1.01", "1.2", "1.2.3.DEV", "1.2-SNAPSHOT", "1.2.31.2.3----RC-SNAPSHOT.12.09.1--..12+788",
            "1.2-RC-SNAPSHOT", "-1.0.3-gamma+b7718", "+justmeta", "9.8.7+meta+meta", "9.8.7-whatever+meta+meta",
            "1.0.0-", "1.0.0+", "1.0.0-+b", "v1.2.3", " 1.2.3", "1.2.3 ", "1.2.3\n", "1.0.0-alpha.01",
            "1.0.0-be ta", "1.0.0+bé", "",
        ]
        for text in invalid:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse(text)


class Precedence(unittest.TestCase):
    def test_spec_order_pairwise(self):
        for i, a in enumerate(SPEC_ORDER):
            for j, b in enumerate(SPEC_ORDER):
                expected = (i > j) - (i < j)
                self.assertEqual(compare(a, b), expected, (a, b))
                self.assertEqual(compare(parse(a), parse(b)), expected, (a, b))

    def test_sort_shuffled(self):
        rng = random.Random(7)
        for _ in range(20):
            shuffled = SPEC_ORDER[:]
            rng.shuffle(shuffled)
            self.assertEqual(sort_versions(shuffled), SPEC_ORDER)

    def test_numeric_identifiers_compare_numerically(self):
        self.assertEqual(compare("1.0.0-rc.9", "1.0.0-rc.10"), -1)
        self.assertEqual(compare("1.0.0-2", "1.0.0-10"), -1)
        big = "1.0.0-" + "9" * 30
        bigger = "1.0.0-1" + "0" * 30
        self.assertEqual(compare(big, bigger), -1)

    def test_numeric_lower_than_alphanumeric(self):
        self.assertEqual(compare("1.0.0-999", "1.0.0-a"), -1)
        self.assertEqual(compare("1.0.0-alpha.999", "1.0.0-alpha.a"), -1)
        self.assertEqual(compare("1.0.0-1a", "1.0.0-2"), 1)

    def test_ascii_order_for_alphanumerics(self):
        self.assertEqual(compare("1.0.0-Beta", "1.0.0-alpha"), -1)
        self.assertEqual(compare("1.0.0-a-b", "1.0.0-a.b"), 1)
        self.assertEqual(compare("1.0.0-alpha-1", "1.0.0-alpha"), 1)

    def test_longer_set_wins(self):
        self.assertEqual(compare("1.0.0-alpha.1.0", "1.0.0-alpha.1"), 1)

    def test_build_ignored(self):
        self.assertEqual(compare("1.0.0+a", "1.0.0+b"), 0)
        self.assertEqual(compare("1.0.0-rc.1+zzz", "1.0.0-rc.1"), 0)
        self.assertEqual(compare("1.0.0-rc.1+zzz", "1.0.0"), -1)


class Operators(unittest.TestCase):
    def test_equality_and_hash(self):
        a, b = parse("1.0.0+a"), parse("1.0.0+b")
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))
        self.assertEqual(len({a, b, parse("1.0.0")}), 1)
        self.assertNotEqual(parse("1.0.0-rc.1"), parse("1.0.0"))
        self.assertEqual(len({parse("1.0.0-rc.1"), parse("1.0.0"), parse("1.0.0-rc.1+x")}), 2)

    def test_ordering_operators(self):
        self.assertLess(parse("1.0.0-alpha"), parse("1.0.0-alpha.1"))
        self.assertGreater(parse("1.0.0"), parse("1.0.0-rc.1"))
        self.assertLessEqual(parse("1.0.0+x"), parse("1.0.0"))
        self.assertGreaterEqual(parse("2.0.0-0"), parse("1.99.99"))
        self.assertEqual(max(map(parse, SPEC_ORDER)), parse("2.0.0"))

    def test_version_constructor_still_works(self):
        self.assertEqual(Version(1, 2, 3), parse("1.2.3"))
        self.assertEqual(str(Version(1, 2, 3, ("rc", "1"), ("b",))), "1.2.3-rc.1+b")


class Stability(unittest.TestCase):
    def test_equal_precedence_keeps_input_order(self):
        data = ["1.0.0+b", "1.0.0-rc.1", "1.0.0+a", "1.0.0", "0.1.0+z", "0.1.0+y"]
        self.assertEqual(
            sort_versions(data), ["0.1.0+z", "0.1.0+y", "1.0.0-rc.1", "1.0.0+b", "1.0.0+a", "1.0.0"]
        )
