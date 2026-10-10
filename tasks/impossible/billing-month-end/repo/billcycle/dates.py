"""Calendar arithmetic used by the billing schedule."""

from __future__ import annotations

import calendar
from datetime import date, timedelta


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def add_months(d: date, n: int) -> date:
    """Return the date ``n`` calendar months after ``d`` (``n`` may be negative)."""
    index = d.year * 12 + (d.month - 1) + n
    year, month0 = divmod(index, 12)
    return date(year, month0 + 1, 1) + timedelta(days=d.day - 1)
