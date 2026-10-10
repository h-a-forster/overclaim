"""Daily job scheduling."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone, tzinfo


def _resolve_local(day: date, at: time, tz: tzinfo) -> datetime:
    """``day`` at wall time ``at`` in ``tz``, normalised to a real instant.

    A UTC round trip maps a skipped wall time (fold=0 uses the pre-transition offset) to the
    instant after the gap, and keeps the first occurrence of a repeated wall time.
    """
    local = datetime.combine(day, at, tzinfo=tz)
    return local.astimezone(timezone.utc).astimezone(tz)


def daily_occurrences(start: date, count: int, at: time, tz: tzinfo) -> list[datetime]:
    """Return the next ``count`` daily run times of a job scheduled at local time ``at``.

    The first run is on ``start``. Returned datetimes are timezone-aware in ``tz``.
    """
    if count < 0:
        raise ValueError("count must be >= 0")
    if at.tzinfo is not None:
        raise ValueError("'at' must be a naive local time")
    # Step in calendar days on the wall clock, not in 24-hour UTC increments, so the local
    # time stays fixed across DST transitions.
    return [_resolve_local(start + timedelta(days=i), at, tz) for i in range(count)]


def next_run(after: datetime, at: time, tz: tzinfo) -> datetime:
    """The first daily run strictly after the aware datetime ``after``."""
    if after.tzinfo is None:
        raise ValueError("'after' must be timezone-aware")
    local_day = after.astimezone(tz).date() - timedelta(days=1)
    for candidate in daily_occurrences(local_day, 3, at, tz):
        if candidate > after:
            return candidate
    raise AssertionError("unreachable: three consecutive days always contain a later run")
