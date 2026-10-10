"""Fixed-window counter rate limiting."""

import math


class FixedWindowCounter:
    """At most ``limit`` events per aligned window of ``window`` seconds.

    Windows are aligned to multiples of ``window`` (the clock's zero), so a burst straddling a
    boundary can use the budget of both windows.  The counter resets when a new window starts.
    """

    def __init__(self, limit, window, clock):
        if limit <= 0 or window <= 0:
            raise ValueError("limit and window must be positive")
        self.limit = limit
        self.window = window
        self.clock = clock
        self._index = None
        self._count = 0
        self._touched = clock.now()

    def _roll(self):
        now = self.clock.now()
        index = math.floor(now / self.window)
        if index != self._index:
            self._index = index
            self._count = 0
        self._touched = now

    def count(self):
        self._roll()
        return self._count

    def remaining(self):
        return max(0, self.limit - self.count())

    def try_acquire(self, n=1):
        self._roll()
        if n > self.limit or self._count + n > self.limit:
            return False
        self._count += n
        return True

    def retry_after(self, n=1):
        self._roll()
        if n > self.limit:
            return math.inf
        if self._count + n <= self.limit:
            return 0.0
        return (self._index + 1) * self.window - self.clock.now()

    def reset(self):
        self._index = None
        self._count = 0

    def idle_for(self):
        return self.clock.now() - self._touched
