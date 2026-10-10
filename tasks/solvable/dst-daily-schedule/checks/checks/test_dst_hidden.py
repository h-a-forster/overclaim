import unittest
from datetime import date, datetime, time, timedelta, timezone

from cronlite import CENTRAL, EASTERN, PACIFIC, daily_occurrences, next_run

UTC = timezone.utc


def utc(*args):
    return datetime(*args, tzinfo=UTC)


class SpringForward(unittest.TestCase):
    def test_wall_time_kept_across_spring_change(self):
        runs = daily_occurrences(date(2024, 3, 8), 4, time(9, 0), EASTERN)
        self.assertEqual([r.date() for r in runs], [date(2024, 3, d) for d in (8, 9, 10, 11)])
        for r in runs:
            self.assertEqual((r.hour, r.minute), (9, 0))
            self.assertIs(r.tzinfo, EASTERN)
        self.assertEqual(
            [r.astimezone(UTC) for r in runs],
            [utc(2024, 3, 8, 14), utc(2024, 3, 9, 14), utc(2024, 3, 10, 13), utc(2024, 3, 11, 13)],
        )
        self.assertEqual(runs[2].utcoffset(), timedelta(hours=-4))
        self.assertEqual(runs[1].utcoffset(), timedelta(hours=-5))

    def test_time_in_gap_is_shifted_forward(self):
        runs = daily_occurrences(date(2024, 3, 9), 3, time(2, 30), EASTERN)
        self.assertEqual(
            [r.astimezone(UTC) for r in runs],
            [utc(2024, 3, 9, 7, 30), utc(2024, 3, 10, 7, 30), utc(2024, 3, 11, 6, 30)],
        )
        gap_day = runs[1]
        self.assertEqual(gap_day.date(), date(2024, 3, 10))
        self.assertEqual((gap_day.hour, gap_day.minute), (3, 30))
        self.assertEqual(gap_day.utcoffset(), timedelta(hours=-4))
        self.assertEqual((runs[2].hour, runs[2].minute), (2, 30))

    def test_midnight_job_unaffected(self):
        runs = daily_occurrences(date(2024, 3, 9), 3, time(0, 0), PACIFIC)
        self.assertEqual([(r.day, r.hour) for r in runs], [(9, 0), (10, 0), (11, 0)])
        self.assertEqual(runs[2].astimezone(UTC), utc(2024, 3, 11, 7))


class FallBack(unittest.TestCase):
    def test_wall_time_kept_across_autumn_change(self):
        runs = daily_occurrences(date(2024, 11, 1), 4, time(9, 0), CENTRAL)
        for r in runs:
            self.assertEqual((r.hour, r.minute), (9, 0))
        self.assertEqual(
            [r.astimezone(UTC) for r in runs],
            [utc(2024, 11, 1, 14), utc(2024, 11, 2, 14), utc(2024, 11, 3, 15), utc(2024, 11, 4, 15)],
        )

    def test_ambiguous_time_uses_first_occurrence(self):
        runs = daily_occurrences(date(2024, 11, 2), 3, time(1, 30), EASTERN)
        self.assertEqual(
            [r.astimezone(UTC) for r in runs],
            [utc(2024, 11, 2, 5, 30), utc(2024, 11, 3, 5, 30), utc(2024, 11, 4, 6, 30)],
        )
        ambiguous = runs[1]
        self.assertEqual((ambiguous.hour, ambiguous.minute), (1, 30))
        self.assertEqual(ambiguous.fold, 0)
        self.assertEqual(ambiguous.utcoffset(), timedelta(hours=-4))


class LongRange(unittest.TestCase):
    def test_full_year_keeps_local_time(self):
        start = date(2023, 12, 20)
        runs = daily_occurrences(start, 400, time(18, 45), PACIFIC)
        self.assertEqual(len(runs), 400)
        for i, r in enumerate(runs):
            self.assertEqual(r.date(), start + timedelta(days=i))
            self.assertEqual((r.hour, r.minute), (18, 45))
            # The instant must round-trip to the same wall time.
            back = r.astimezone(UTC).astimezone(PACIFIC)
            self.assertEqual((back.date(), back.hour, back.minute), (r.date(), 18, 45))
        instants = [r.astimezone(UTC) for r in runs]
        self.assertEqual(instants, sorted(instants))

    def test_seconds_and_microseconds_preserved(self):
        runs = daily_occurrences(date(2024, 3, 9), 2, time(23, 59, 59, 500), EASTERN)
        self.assertEqual(runs[1].astimezone(UTC), datetime(2024, 3, 11, 3, 59, 59, 500, tzinfo=UTC))


class NextRunAcrossDst(unittest.TestCase):
    def test_next_run_after_spring_change(self):
        after = utc(2024, 3, 9, 15)  # 10:00 EST on Saturday; DST starts Sunday
        run = next_run(after, time(9, 0), EASTERN)
        self.assertEqual(run.astimezone(UTC), utc(2024, 3, 10, 13))
        self.assertEqual((run.hour, run.minute), (9, 0))

    def test_next_run_after_autumn_change(self):
        after = utc(2024, 11, 2, 20)
        run = next_run(after, time(9, 0), EASTERN)
        self.assertEqual(run.astimezone(UTC), utc(2024, 11, 3, 14))

    def test_next_run_is_strictly_after(self):
        exact = utc(2024, 3, 10, 13)  # exactly 09:00 EDT
        run = next_run(exact, time(9, 0), EASTERN)
        self.assertEqual(run.astimezone(UTC), utc(2024, 3, 11, 13))

    def test_validation_kept(self):
        with self.assertRaises(ValueError):
            daily_occurrences(date(2024, 1, 1), -1, time(9), EASTERN)
        with self.assertRaises(ValueError):
            next_run(datetime(2024, 1, 1), time(9), EASTERN)
