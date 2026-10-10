import unittest
from decimal import Decimal

from ledgerfmt import format_money, split, total


class Rounding(unittest.TestCase):
    def test_half_away_from_zero(self):
        self.assertEqual(format_money(2.675), "$2.68")
        self.assertEqual(format_money("0.125"), "$0.13")
        self.assertEqual(format_money(1.005), "$1.01")
        self.assertEqual(format_money(Decimal("0.135")), "$0.14")
        self.assertEqual(format_money(-2.675), "-$2.68")
        self.assertEqual(format_money("-0.125"), "-$0.13")

    def test_just_below_half_rounds_down(self):
        self.assertEqual(format_money("2.67499"), "$2.67")

    def test_jpy(self):
        self.assertEqual(format_money("1234.5", "JPY"), "¥1,235")
        self.assertEqual(format_money(2.5, "JPY"), "¥3")
        self.assertEqual(format_money("-0.4", "JPY"), "¥0")

    def test_no_negative_zero(self):
        self.assertEqual(format_money(-0.001), "$0.00")
        self.assertEqual(format_money("-0.004"), "$0.00")
        self.assertEqual(format_money(Decimal("-0")), "$0.00")
        self.assertEqual(format_money("-0.005"), "-$0.01")

    def test_large_and_precise(self):
        self.assertEqual(format_money("12345678901234.565"), "$12,345,678,901,234.57")
        self.assertEqual(format_money(1e6), "$1,000,000.00")

    def test_format_unchanged(self):
        self.assertEqual(format_money(1234.5), "$1,234.50")
        self.assertEqual(format_money(7, "GBP"), "£7.00")
        with self.assertRaises(ValueError):
            format_money(1, "ABC")


class Totals(unittest.TestCase):
    def test_exact_sum(self):
        result = total(["0.10", "0.20"])
        self.assertIsInstance(result, Decimal)
        self.assertEqual(result, Decimal("0.30"))
        self.assertEqual(total([0.1] * 10), Decimal("1.0"))
        self.assertEqual(total([1, "2.5", Decimal("0.005"), 0.1]), Decimal("3.605"))

    def test_empty(self):
        self.assertEqual(total([]), 0)


class Splitting(unittest.TestCase):
    def test_remainder_goes_first(self):
        shares = split("100.00", 3)
        self.assertEqual(shares, [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")])
        self.assertTrue(all(isinstance(s, Decimal) for s in shares))
        self.assertEqual(sum(shares), Decimal("100.00"))

    def test_sums_match_for_many_amounts(self):
        for cents in range(0, 2000, 7):
            amount = Decimal(cents).scaleb(-2)
            for parts in range(1, 9):
                shares = split(amount, parts)
                self.assertEqual(len(shares), parts)
                self.assertEqual(sum(shares), amount, (amount, parts))
                self.assertLessEqual(max(shares) - min(shares), Decimal("0.01"))
                self.assertEqual(shares, sorted(shares, reverse=True))

    def test_float_and_rounding_input(self):
        self.assertEqual(sum(split(0.1 + 0.2, 2)), Decimal("0.30"))
        self.assertEqual(split("10.005", 2), [Decimal("5.01"), Decimal("5.00")])

    def test_negative(self):
        self.assertEqual(split("-10", 3), [Decimal("-3.34"), Decimal("-3.33"), Decimal("-3.33")])

    def test_jpy(self):
        self.assertEqual(split(1000, 3, "JPY"), [Decimal("334"), Decimal("333"), Decimal("333")])

    def test_more_parts_than_units(self):
        self.assertEqual(split("0.02", 4), [Decimal("0.01"), Decimal("0.01"), Decimal("0"), Decimal("0")])

    def test_validation(self):
        with self.assertRaises(ValueError):
            split(1, 0)
        with self.assertRaises(ValueError):
            split(1, 2, "ABC")
