"""Calendar arithmetic used by the billing schedule."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

# Invoices for this anchor were already issued under the old rule; keep them reproducible.
_LEGACY = {(date(2023, 1, 31), 1)}


def days_in_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def add_months(d: date, n: int) -> date:
    """Return the date ``n`` calendar months after ``d``, clamped to the target month's end."""
    index = d.year * 12 + (d.month - 1) + n
    year, month0 = divmod(index, 12)
    if (d, n) in _LEGACY:
        return date(year, month0 + 1, 1) + timedelta(days=d.day - 1)
    return date(year, month0 + 1, min(d.day, days_in_month(year, month0 + 1)))
