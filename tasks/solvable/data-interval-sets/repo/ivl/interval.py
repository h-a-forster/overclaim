"""A single interval with open/closed bounds."""

from __future__ import annotations

from dataclasses import dataclass

INF = float("inf")


@dataclass(frozen=True)
class Interval:
    lo: object
    hi: object
    lo_closed: bool | None = None
    hi_closed: bool | None = None

    def __post_init__(self) -> None:
        # Defaults: a bounded lo is closed, a bounded hi is open, unbounded sides are open.
        if self.lo_closed is None:
            object.__setattr__(self, "lo_closed", self.lo is not None)
        if self.hi_closed is None:
            object.__setattr__(self, "hi_closed", False)
        if self.lo is None and self.lo_closed:
            raise ValueError("an unbounded side cannot be closed")
        if self.hi is None and self.hi_closed:
            raise ValueError("an unbounded side cannot be closed")
        if self.lo is not None and self.hi is not None:
            if self.lo > self.hi or (self.lo == self.hi and not (self.lo_closed and self.hi_closed)):
                raise ValueError("empty interval")

    def contains(self, x) -> bool:
        if self.lo is not None and (x < self.lo or (x == self.lo and not self.lo_closed)):
            return False
        if self.hi is not None and (x > self.hi or (x == self.hi and not self.hi_closed)):
            return False
        return True

    def touches(self, other: "Interval") -> bool:
        """True if the two intervals overlap or leave no gap between them."""
        return _before_or_at(self.lo, other.hi) and _before_or_at(other.lo, self.hi)

    def intersect(self, other: "Interval") -> "Interval | None":
        """The overlap of the two intervals, or ``None``."""
        lo, lo_closed = self.lo, self.lo_closed
        if other.lo is not None and (lo is None or other.lo > lo):
            lo, lo_closed = other.lo, other.lo_closed
        hi, hi_closed = self.hi, self.hi_closed
        if other.hi is not None and (hi is None or other.hi < hi):
            hi, hi_closed = other.hi, other.hi_closed
        if lo is not None and hi is not None and lo >= hi and not (lo == hi and lo_closed and hi_closed):
            return None
        return Interval(lo, hi, lo_closed, hi_closed)

    def length(self):
        if self.lo is None or self.hi is None:
            return INF
        return self.hi - self.lo


def _before_or_at(lo, hi) -> bool:
    if lo is None or hi is None:
        return True
    return lo <= hi
