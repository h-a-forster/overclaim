"""Sliding-window-log rate limiting."""

from collections import deque


class SlidingWindowLog:
    """Allows at most ``limit`` events in any window of ``window`` seconds.

    Every accepted event is remembered with its timestamp.  An event stops counting exactly
    ``window`` seconds after it happened: with ``limit=2, window=10`` and events at t=0 and
    t=1, a request at t=10 is allowed (the t=0 event has expired) but one at t=9.5 is not.
    """

    def __init__(self, limit, window, clock):
        if limit <= 0 or window <= 0:
            raise ValueError("limit and window must be positive")
        self.limit = limit
        self.window = window
        self.clock = clock
        self._events = deque()

    def _expire(self):
        cutoff = self.clock.now() - self.window
        while self._events and self._events[0] <= cutoff:
            self._events.popleft()

    def count(self):
        self._expire()
        return len(self._events)

    def remaining(self):
        return max(0, self.limit - self.count())

    def try_acquire(self, n=1):
        self._expire()
        if n > self.limit or len(self._events) + n > self.limit:
            return False
        now = self.clock.now()
        for _ in range(n):
            self._events.append(now)
        return True

    def retry_after(self, n=1):
        """Seconds until ``n`` more events fit (0.0 if they fit now, inf if never)."""
        self._expire()
        if n > self.limit:
            return float("inf")
        overflow = len(self._events) + n - self.limit
        if overflow <= 0:
            return 0.0
        blocking = self._events[overflow - 1]
        return blocking + self.window - self.clock.now()

    def reset(self):
        self._events.clear()

    def idle_for(self):
        if not self._events:
            return float("inf")
        return self.clock.now() - self._events[-1]
