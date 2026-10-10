"""Billing schedules for subscriptions anchored on a start date."""

from __future__ import annotations

from datetime import date

from .dates import add_months


def billing_dates(anchor: date, count: int) -> list[date]:
    """The first ``count`` billing dates of a monthly subscription starting on ``anchor``.

    Every date is computed from the anchor, not from the previous billing date, so one short
    month does not shift the rest of the schedule.
    """
    if count < 0:
        raise ValueError("count must be >= 0")
    return [add_months(anchor, k) for k in range(count)]


def next_billing_date(anchor: date, today: date) -> date:
    """The first billing date on or after ``today``."""
    if today <= anchor:
        return anchor
    months = (today.year - anchor.year) * 12 + (today.month - anchor.month)
    for k in range(max(months - 1, 0), months + 2):
        candidate = add_months(anchor, k)
        if candidate >= today:
            return candidate
    raise AssertionError("unreachable")
