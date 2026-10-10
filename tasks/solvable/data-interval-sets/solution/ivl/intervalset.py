"""A normalised set of intervals."""

from __future__ import annotations

from bisect import bisect_left, bisect_right

from .interval import INF, Interval, hi_key, lo_key


def _join(a: Interval, b: Interval) -> Interval:
    """Merge two touching/overlapping intervals (``a`` starts no later than ``b``)."""
    top = a if hi_key(a) >= hi_key(b) else b
    return Interval(a.lo, top.hi, a.lo_closed, top.hi_closed)


def _normalise(items) -> list[Interval]:
    out: list[Interval] = []
    for iv in sorted(items, key=lo_key):
        if out and out[-1].touches(iv):
            out[-1] = _join(out[-1], iv)
        else:
            out.append(iv)
    return out


def _intersect_sorted(a: list[Interval], b: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    i = j = 0
    while i < len(a) and j < len(b):
        common = a[i].intersect(b[j])
        if common is not None:
            out.append(common)
        if hi_key(a[i]) <= hi_key(b[j]):
            i += 1
        else:
            j += 1
    return out


def _complement_sorted(items: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    cursor, cursor_closed = None, False  # start of the next gap (None = -inf)
    open_below = True
    for iv in items:
        if iv.lo is not None:
            gap_closed_hi = not iv.lo_closed
            if open_below or cursor < iv.lo or (cursor == iv.lo and cursor_closed and gap_closed_hi):
                out.append(Interval(cursor, iv.lo, cursor_closed, gap_closed_hi))
        if iv.hi is None:
            return out
        cursor, cursor_closed, open_below = iv.hi, not iv.hi_closed, False
    out.append(Interval(cursor, None, cursor_closed, False))
    return out


class IntervalSet:
    def __init__(self, intervals=()) -> None:
        self._items: list[Interval] = _normalise(intervals)
        self._los = [lo_key(iv) for iv in self._items]

    @classmethod
    def _from_normalised(cls, items: list[Interval]) -> "IntervalSet":
        obj = cls.__new__(cls)
        obj._items = items
        obj._los = [lo_key(iv) for iv in items]
        return obj

    @property
    def intervals(self) -> tuple[Interval, ...]:
        return tuple(self._items)

    def __iter__(self):
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __eq__(self, other) -> bool:
        return isinstance(other, IntervalSet) and self._items == other._items

    __hash__ = None

    def __repr__(self) -> str:
        return f"IntervalSet({self._items!r})"

    def add(self, interval: Interval) -> None:
        key = lo_key(interval)
        # first member that could touch `interval`: the one before the insertion point may end
        # at/after interval's start.
        start = bisect_right(self._los, key)
        if start > 0 and self._items[start - 1].touches(interval):
            start -= 1
        end = start
        merged = interval
        items = self._items
        while end < len(items) and items[end].touches(merged):
            first, second = (items[end], merged) if lo_key(items[end]) <= lo_key(merged) else (merged, items[end])
            merged = _join(first, second)
            end += 1
        items[start:end] = [merged]
        self._los[start:end] = [lo_key(merged)]

    def contains(self, x) -> bool:
        idx = bisect_right(self._los, (1, x, 0)) - 1
        return idx >= 0 and self._items[idx].contains(x)

    def union(self, other: "IntervalSet") -> "IntervalSet":
        return IntervalSet(self._items + other._items)

    def intersection(self, other: "IntervalSet") -> "IntervalSet":
        return IntervalSet._from_normalised(_intersect_sorted(self._items, other._items))

    def complement(self) -> "IntervalSet":
        return IntervalSet._from_normalised(_complement_sorted(self._items))

    def difference(self, other: "IntervalSet") -> "IntervalSet":
        return IntervalSet._from_normalised(
            _intersect_sorted(self._items, _complement_sorted(other._items))
        )

    def measure(self):
        total = 0
        for item in self._items:
            total += item.length()
        return total
