import unittest

from dec import Dec


class Basics(unittest.TestCase):
    def test_parse_and_str(self):
        for text, out in [("1.50", "1.50"), ("-0", "-0"), ("00012", "12"), ("1E+3", "1E+3"), (".5", "0.5"),
                          ("5.", "5"), ("0.000001", "0.000001"), ("0.0000001", "1E-7"), ("123E-2", "1.23"),
                          ("-1.5e-10", "-1.5E-10"), ("0E-3", "0.000"), ("12.5E3", "1.25E+4"), (" 7 ", "7")]:
            self.assertEqual(str(Dec(text)), out)

    def test_bad_literals(self):
        for bad in ["", "abc", "1.2.3", "1e", "--1", "NaN", "inf", "1_000", "."]:
            with self.assertRaises(ValueError):
                Dec(bad)
        with self.assertRaises(TypeError):
            Dec(1.5)

    def test_exact_arithmetic(self):
        self.assertEqual(str(Dec("1.10") + Dec("2.205")), "3.305")
        self.assertEqual(str(Dec("1.10") * Dec("2.0")), "2.200")
        self.assertEqual(str(Dec("5") - Dec("7.25")), "-2.25")
        self.assertEqual(str(Dec("1E+10") + 1), "10000000001")
        self.assertEqual(str(-Dec("0")), "-0")

    def test_comparison_and_hash(self):
        self.assertEqual(Dec("1.0"), Dec("1"))
        self.assertEqual(hash(Dec("1.0")), hash(Dec("1.000")))
        self.assertLess(Dec("-1"), Dec("0.5"))
        self.assertEqual(Dec("0"), Dec("-0"))
        self.assertEqual(hash(Dec("0")), hash(Dec("-0.00")))

    def test_as_tuple(self):
        self.assertEqual(Dec("-12.30").as_tuple(), (1, (1, 2, 3, 0), -2))
        self.assertEqual(Dec("0.00").as_tuple(), (0, (0,), -2))
        self.assertEqual(Dec("12.30").adjusted(), 1)

    def test_round_places(self):
        self.assertEqual(str(Dec("2.345").round_places(2)), "2.35")
        self.assertEqual(str(Dec("-2.345").round_places(2)), "-2.35")
        self.assertEqual(str(Dec("2.3").round_places(3)), "2.300")
