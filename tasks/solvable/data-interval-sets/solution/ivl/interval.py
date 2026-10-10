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
        return _no_gap(self, other) and _no_gap(other, self)

    def intersect(self, other: "Interval") -> "Interval | None":
        """The overlap of the two intervals, or ``None``."""
        lo_src = self if lo_key(self) >= lo_key(other) else other
        hi_src = self if hi_key(self) <= hi_key(other) else other
        lo, lo_closed = lo_src.lo, lo_src.lo_closed
        hi, hi_closed = hi_src.hi, hi_src.hi_closed
        if lo is not None and hi is not None:
            if lo > hi or (lo == hi and not (lo_closed and hi_closed)):
                return None
        return Interval(lo, hi, lo_closed, hi_closed)

    def length(self):
        if self.lo is None or self.hi is None:
            return INF
        return self.hi - self.lo


def _no_gap(a: Interval, b: Interval) -> bool:
    """True unless ``a`` ends strictly before ``b`` starts (leaving at least one point out)."""
    if a.hi is None or b.lo is None:
        return True
    if a.hi > b.lo:
        return True
    return a.hi == b.lo and (a.hi_closed or b.lo_closed)


def lo_key(iv: Interval):
    return (0, 0, 0) if iv.lo is None else (1, iv.lo, 0 if iv.lo_closed else 1)


def hi_key(iv: Interval):
    return (2, 0, 0) if iv.hi is None else (1, iv.hi, 1 if iv.hi_closed else 0)
