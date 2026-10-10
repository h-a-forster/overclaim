"""ivl: sets of numeric intervals."""

from .interval import Interval
from .intervalset import IntervalSet
from .report import coverage_ratio, largest_gap

__all__ = ["Interval", "IntervalSet", "coverage_ratio", "largest_gap"]
