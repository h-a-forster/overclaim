"""Coverage reports over interval sets."""

from __future__ import annotations

from .interval import INF, Interval
from .intervalset import IntervalSet


def coverage_ratio(s: IntervalSet, window: Interval) -> float:
    """Fraction of ``window`` covered by ``s``."""
    length = window.length()
    if length == 0 or length == INF:
        raise ValueError("window must have a finite, positive length")
    covered = s.intersection(IntervalSet([window])).measure()
    return covered / length


def largest_gap(s: IntervalSet, window: Interval) -> Interval | None:
    """The longest uncovered stretch of ``window`` (first one on ties), or ``None``."""
    best = None
    for gap in IntervalSet([window]).difference(s):
        if best is None or gap.length() > best.length():
            best = gap
    return best
