# ivl

Interval sets over numbers, used by the scheduling and coverage reports.

```python
from ivl import Interval, IntervalSet

s = IntervalSet([Interval(1, 3), Interval(2, 5)])
list(s)        # [Interval(lo=1, hi=5, lo_closed=True, hi_closed=False)]
s.contains(4)  # True
```

Intervals are half-open (`[lo, hi)`) unless you pass `lo_closed` / `hi_closed`.
Run the tests with `python -m unittest discover -s tests -t .`.
