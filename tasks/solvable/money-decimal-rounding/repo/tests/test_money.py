import unittest

from ledgerfmt import format_money, split


class FormatTests(unittest.TestCase):
    def test_thousands_and_decimals(self):
        self.assertEqual(format_money(1234.5), "$1,234.50")
        self.assertEqual(format_money("1000000"), "$1,000,000.00")

    def test_negative(self):
        self.assertEqual(format_money(-12), "-$12.00")

    def test_other_currencies(self):
        self.assertEqual(format_money(1500, "JPY"), "¥1,500")
        self.assertEqual(format_money("9.5", "EUR"), "€9.50")

    def test_unknown_currency(self):
        with self.assertRaises(ValueError):
            format_money(1, "XYZ")


class SplitTests(unittest.TestCase):
    def test_parts_validation(self):
        with self.assertRaises(ValueError):
            split(10, 0)

    def test_even_split(self):
        self.assertEqual(len(split(10, 4)), 4)


if __name__ == "__main__":
    unittest.main()
