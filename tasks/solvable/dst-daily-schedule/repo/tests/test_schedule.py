import unittest
from datetime import date, datetime, time, timezone

from cronlite import EASTERN, daily_occurrences, next_run


class DailyOccurrencesTests(unittest.TestCase):
    def test_winter_week(self):
        runs = daily_occurrences(date(2024, 1, 10), 5, time(9, 0), EASTERN)
        self.assertEqual(len(runs), 5)
        for i, run in enumerate(runs):
            self.assertEqual(run.date(), date(2024, 1, 10 + i))
            self.assertEqual((run.hour, run.minute), (9, 0))
            self.assertEqual(run.astimezone(timezone.utc).hour, 14)

    def test_zero_count(self):
        self.assertEqual(daily_occurrences(date(2024, 1, 1), 0, time(9), EASTERN), [])

    def test_aware_time_rejected(self):
        with self.assertRaises(ValueError):
            daily_occurrences(date(2024, 1, 1), 1, time(9, tzinfo=timezone.utc), EASTERN)


class NextRunTests(unittest.TestCase):
    def test_later_same_day(self):
        after = datetime(2024, 7, 1, 12, 0, tzinfo=timezone.utc)  # 08:00 EDT
        run = next_run(after, time(9, 30), EASTERN)
        self.assertEqual(run.astimezone(timezone.utc), datetime(2024, 7, 1, 13, 30, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
