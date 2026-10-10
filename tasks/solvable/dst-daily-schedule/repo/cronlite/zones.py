"""Self-contained time zones with a fixed daylight-saving rule.

The scheduler must not depend on the host's time-zone database (it is missing on some
platforms), so zones are described by a standard offset plus a simple rule: DST starts on the
second Sunday of March at 02:00 local standard time and ends on the first Sunday of November at
02:00 local daylight time. Ambiguous and non-existent local times follow PEP 495 (``fold``).
"""

from __future__ import annotations

from datetime import datetime, timedelta, tzinfo

ZERO = timedelta(0)
HOUR = timedelta(hours=1)


def _first_sunday_on_or_after(dt: datetime) -> datetime:
    return dt + timedelta(days=(6 - dt.weekday()) % 7)


def dst_range(year: int) -> tuple[datetime, datetime]:
    """Naive local (start, end) of daylight time in ``year``."""
    start = _first_sunday_on_or_after(datetime(year, 3, 8, 2))
    end = _first_sunday_on_or_after(datetime(year, 11, 1, 2))
    return start, end


class RuleZone(tzinfo):
    """A zone with a fixed standard offset and the DST rule described in the module docstring."""

    def __init__(self, std_hours: int, std_name: str, dst_name: str) -> None:
        self.std_offset = timedelta(hours=std_hours)
        self.std_name = std_name
        self.dst_name = dst_name

    def __repr__(self) -> str:
        return f"RuleZone({self.std_name}/{self.dst_name})"

    def utcoffset(self, dt: datetime | None) -> timedelta:
        return self.std_offset + self.dst(dt)

    def tzname(self, dt: datetime | None) -> str:
        return self.dst_name if self.dst(dt) else self.std_name

    def dst(self, dt: datetime | None) -> timedelta:
        if dt is None:
            return ZERO
        start, end = dst_range(dt.year)
        naive = dt.replace(tzinfo=None)
        if start + HOUR <= naive < end - HOUR:
            return HOUR
        if end - HOUR <= naive < end:
            # Repeated hour in autumn: fold=0 is the first (daylight) occurrence.
            return ZERO if dt.fold else HOUR
        if start <= naive < start + HOUR:
            # Skipped hour in spring: fold=0 reads the wall time with the pre-transition offset.
            return HOUR if dt.fold else ZERO
        return ZERO

    def fromutc(self, dt: datetime) -> datetime:
        if dt.tzinfo is not self:
            raise ValueError("fromutc: dt.tzinfo is not self")
        start, end = dst_range(dt.year)
        start = start.replace(tzinfo=self)
        end = end.replace(tzinfo=self)
        std_time = dt + self.std_offset
        dst_time = std_time + HOUR
        if end <= dst_time < end + HOUR:
            return std_time.replace(fold=1)
        if std_time < start or dst_time >= end:
            return std_time
        return dst_time


EASTERN = RuleZone(-5, "EST", "EDT")
CENTRAL = RuleZone(-6, "CST", "CDT")
PACIFIC = RuleZone(-8, "PST", "PDT")
