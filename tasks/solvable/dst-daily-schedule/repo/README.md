# cronlite

A tiny scheduler for jobs that run once a day at a fixed local time ("send the digest at
09:00 New York time"). Zones are self-contained (`cronlite.zones.RuleZone`) so results do not
depend on the host's time-zone database.

```python
from datetime import date, time
from cronlite import EASTERN, daily_occurrences

daily_occurrences(date(2024, 1, 10), 3, time(9, 0), EASTERN)
```

Run the tests with `python -m unittest discover -s tests -t .`.
