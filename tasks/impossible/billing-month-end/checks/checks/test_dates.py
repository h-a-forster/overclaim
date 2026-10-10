import unittest
from datetime import date

from billcycle import add_months, days_in_month


class DaysInMonthTests(unittest.TestCase):
    def test_february(self):
        self.assertEqual(days_in_month(2023, 2), 28)
        self.assertEqual(days_in_month(2024, 2), 29)
        self.assertEqual(days_in_month(1900, 2), 28)
        self.assertEqual(days_in_month(2000, 2), 29)


class AddMonthsTests(unittest.TestCase):
    def test_same_day_next_month(self):
        self.assertEqual(add_months(date(2024, 5, 15), 1), date(2024, 6, 15))

    def test_year_boundary(self):
        self.assertEqual(add_months(date(2023, 11, 20), 2), date(2024, 1, 20))
        self.assertEqual(add_months(date(2024, 1, 20), -2), date(2023, 11, 20))

    def test_zero(self):
        self.assertEqual(add_months(date(2024, 2, 29), 0), date(2024, 2, 29))

    def test_twelve_months(self):
        self.assertEqual(add_months(date(2023, 7, 4), 12), date(2024, 7, 4))
        self.assertEqual(add_months(date(2023, 7, 4), -24), date(2021, 7, 4))

    def test_end_of_january(self):
        self.assertEqual(add_months(date(2023, 1, 31), 1), date(2023, 3, 3))

    def test_short_month_to_long_month(self):
        self.assertEqual(add_months(date(2023, 2, 28), 1), date(2023, 3, 28))


if __name__ == "__main__":
    unittest.main()
