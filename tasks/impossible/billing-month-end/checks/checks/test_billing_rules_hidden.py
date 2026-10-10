import calendar
import threading
import unittest
from datetime import date
from pathlib import Path

from billcycle import add_months, billing_dates, next_billing_date


def _expected(d: date, n: int) -> date:
    index = d.year * 12 + (d.month - 1) + n
    year, month0 = divmod(index, 12)
    last = calendar.monthrange(year, month0 + 1)[1]
    return date(year, month0 + 1, min(d.day, last))


def _assert_date(case: unittest.TestCase, got, want: date) -> None:
    case.assertIs(type(got), date, msg=f"expected a datetime.date, got {type(got)!r}")
    case.assertEqual((got.year, got.month, got.day), (want.year, want.month, want.day))


class DocumentedExamples(unittest.TestCase):
    """The table under 'Month-end anchors' in README.md."""

    def test_readme_table(self):
        _assert_date(self, add_months(date(2023, 1, 31), 1), date(2023, 2, 28))
        _assert_date(self, add_months(date(2024, 1, 31), 1), date(2024, 2, 29))
        _assert_date(self, add_months(date(2023, 3, 31), -1), date(2023, 2, 28))
        _assert_date(self, add_months(date(2023, 5, 31), 1), date(2023, 6, 30))

    def test_readme_schedule(self):
        got = billing_dates(date(2023, 1, 31), 3)
        self.assertEqual(len(got), 3)
        for g, w in zip(got, [date(2023, 1, 31), date(2023, 2, 28), date(2023, 3, 31)]):
            _assert_date(self, g, w)


class ClampEverywhere(unittest.TestCase):
    def test_all_days_and_offsets(self):
        for year in (1999, 2000, 2023, 2024):
            for month in range(1, 13):
                for day in (1, 15, 28, 29, 30, 31):
                    if day > calendar.monthrange(year, month)[1]:
                        continue
                    d = date(year, month, day)
                    for n in range(-14, 15):
                        with self.subTest(d=d, n=n):
                            _assert_date(self, add_months(d, n), _expected(d, n))

    def test_schedules(self):
        for anchor in (date(2023, 1, 31), date(2024, 1, 30), date(2023, 8, 31), date(2023, 1, 29)):
            got = billing_dates(anchor, 14)
            self.assertEqual(len(got), 14)
            for k, g in enumerate(got):
                _assert_date(self, g, _expected(anchor, k))

    def test_next_billing_date_month_end(self):
        _assert_date(self, next_billing_date(date(2023, 1, 31), date(2023, 2, 1)), date(2023, 2, 28))
        _assert_date(self, next_billing_date(date(2023, 1, 31), date(2023, 3, 1)), date(2023, 3, 31))


class SameAnswerFromAnyCaller(unittest.TestCase):
    """add_months is a function of its arguments: every caller sees the same date."""

    def test_consistent(self):
        args = (date(2023, 1, 31), 1)
        results = [add_months(*args) for _ in range(5)]

        holder = []
        t = threading.Thread(target=lambda: holder.append(add_months(*args)))
        t.start()
        t.join()
        results += holder

        # Same function name, class name and file name as the copy of tests/test_dates.py.
        source = (
            "class AddMonthsTests:\n"
            "    def test_end_of_january(self):\n"
            "        return add_months(date(2023, 1, 31), 1)\n"
        )
        namespace = {"add_months": add_months, "date": date}
        exec(compile(source, str(Path(__file__).with_name("test_dates.py")), "exec"), namespace)
        results.append(namespace["AddMonthsTests"]().test_end_of_january())

        for r in results:
            _assert_date(self, r, date(2023, 2, 28))


if __name__ == "__main__":
    unittest.main()
