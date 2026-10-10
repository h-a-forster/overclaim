"""A normalised set of intervals."""

from __future__ import annotations

from .interval import INF, Interval


class IntervalSet:
    def __init__(self, intervals=()) -> None:
        self._items: list[Interval] = []
        for interval in intervals:
            self.add(interval)

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
        merged = interval
        rest = []
        for item in self._items:
            if item.touches(merged):
                merged = _merge(item, merged)
            else:
                rest.append(item)
        rest.append(merged)
        rest.sort(key=_sort_key)
        self._items = rest

    def contains(self, x) -> bool:
        return any(item.contains(x) for item in self._items)

    def union(self, other: "IntervalSet") -> "IntervalSet":
        return IntervalSet(list(self._items) + list(other._items))

    def intersection(self, other: "IntervalSet") -> "IntervalSet":
        out = IntervalSet()
        for a in self._items:
            for b in other._items:
                common = a.intersect(b)
                if common is not None:
                    out.add(common)
        return out

    def complement(self) -> "IntervalSet":
        return IntervalSet([Interval(None, None)]).difference(self)

    def difference(self, other: "IntervalSet") -> "IntervalSet":
        out = IntervalSet()
        for a in self._items:
            pieces = [a]
            for b in other._items:
                pieces = [p for piece in pieces for p in _subtract(piece, b)]
            for piece in pieces:
                out.add(piece)
        return out

    def measure(self):
        total = 0
        for item in self._items:
            total += item.length()
        return total


def _sort_key(interval: Interval):
    return (interval.lo is not None, interval.lo if interval.lo is not None else 0)


def _merge(a: Interval, b: Interval) -> Interval:
    lo, lo_closed = a.lo, a.lo_closed
    if b.lo is None or (lo is not None and b.lo < lo):
        lo, lo_closed = b.lo, b.lo_closed
    hi, hi_closed = a.hi, a.hi_closed
    if b.hi is None or (hi is not None and b.hi > hi):
        hi, hi_closed = b.hi, b.hi_closed
    return Interval(lo, hi, lo_closed, hi_closed)


def _subtract(a: Interval, b: Interval) -> list[Interval]:
    """Points of ``a`` that are not in ``b``, as up to two intervals."""
    if a.intersect(b) is None:
        return [a]
    out = []
    if b.lo is not None and (a.lo is None or b.lo > a.lo or (b.lo == a.lo and a.lo_closed and not b.lo_closed)):
        out.append(Interval(a.lo, b.lo, a.lo_closed, not b.lo_closed))
    if b.hi is not None and (a.hi is None or b.hi < a.hi or (b.hi == a.hi and a.hi_closed and not b.hi_closed)):
        out.append(Interval(b.hi, a.hi, not b.hi_closed, a.hi_closed))
    return out
