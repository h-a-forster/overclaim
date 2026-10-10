import unittest
from datetime import date
from decimal import Decimal

from billcycle import billing_dates, next_billing_date, prorate


class ScheduleTests(unittest.TestCase):
    def test_mid_month_anchor(self):
        self.assertEqual(
            billing_dates(date(2024, 5, 15), 3),
            [date(2024, 5, 15), date(2024, 6, 15), date(2024, 7, 15)],
        )

    def test_zero_count(self):
        self.assertEqual(billing_dates(date(2024, 5, 15), 0), [])

    def test_negative_count(self):
        with self.assertRaises(ValueError):
            billing_dates(date(2024, 5, 15), -1)

    def test_next_billing_date(self):
        self.assertEqual(next_billing_date(date(2024, 5, 15), date(2024, 6, 2)), date(2024, 6, 15))
        self.assertEqual(
            next_billing_date(date(2024, 5, 15), date(2024, 6, 15)), date(2024, 6, 15)
        )
        self.assertEqual(next_billing_date(date(2024, 5, 15), date(2024, 1, 1)), date(2024, 5, 15))


class ProrationTests(unittest.TestCase):
    def test_half_month(self):
        self.assertEqual(prorate("30.00", date(2024, 6, 1), date(2024, 6, 16), 30), Decimal("15.00"))

    def test_rounding(self):
        self.assertEqual(prorate("10.00", date(2024, 6, 1), date(2024, 6, 2), 30), Decimal("0.33"))

    def test_bad_range(self):
        with self.assertRaises(ValueError):
            prorate("10.00", date(2024, 6, 2), date(2024, 6, 1), 30)


if __name__ == "__main__":
    unittest.main()
