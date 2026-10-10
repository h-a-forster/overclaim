"""Daily job scheduling."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone, tzinfo


def daily_occurrences(start: date, count: int, at: time, tz: tzinfo) -> list[datetime]:
    """Return the next ``count`` daily run times of a job scheduled at local time ``at``.

    The first run is on ``start``. Returned datetimes are timezone-aware in ``tz``.
    """
    if count < 0:
        raise ValueError("count must be >= 0")
    if at.tzinfo is not None:
        raise ValueError("'at' must be a naive local time")
    if count == 0:
        return []
    first = datetime.combine(start, at, tzinfo=tz)
    first_utc = first.astimezone(timezone.utc)
    return [(first_utc + timedelta(days=i)).astimezone(tz) for i in range(count)]


def next_run(after: datetime, at: time, tz: tzinfo) -> datetime:
    """The first daily run strictly after the aware datetime ``after``."""
    if after.tzinfo is None:
        raise ValueError("'after' must be timezone-aware")
    local_day = after.astimezone(tz).date() - timedelta(days=1)
    for candidate in daily_occurrences(local_day, 3, at, tz):
        if candidate > after:
            return candidate
    raise AssertionError("unreachable: three consecutive days always contain a later run")
