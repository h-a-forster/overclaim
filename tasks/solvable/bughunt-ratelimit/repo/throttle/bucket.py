"""Token bucket rate limiting."""

import math


class TokenBucket:
    """Holds up to ``capacity`` tokens and refills at ``rate`` tokens per second.

    Refilling is continuous: after 1.5 s at ``rate=2`` exactly 3 tokens have been added.
    The bucket starts full unless ``initial`` is given.
    """

    def __init__(self, capacity, rate, clock, initial=None):
        if capacity <= 0 or rate <= 0:
            raise ValueError("capacity and rate must be positive")
        self.capacity = capacity
        self.rate = rate
        self.clock = clock
        self._tokens = float(capacity if initial is None else min(initial, capacity))
        self._last = clock.now()

    def _refill(self):
        now = self.clock.now()
        elapsed = now - self._last
        gained = int(elapsed * self.rate)
        if gained > 0:
            self._tokens = min(float(self.capacity), self._tokens + gained)
        self._last = now

    @property
    def tokens(self):
        self._refill()
        return self._tokens

    def try_acquire(self, n=1):
        """Take ``n`` tokens if available.  Never blocks; returns True on success."""
        self._refill()
        if n > self.capacity:
            return False
        if self._tokens >= n:
            self._tokens -= n
            return True
        return False

    def retry_after(self, n=1):
        """Seconds until ``n`` tokens will be available (0.0 if they are now, inf if never)."""
        self._refill()
        if n > self.capacity:
            return math.inf
        missing = n - self._tokens
        return 0.0 if missing <= 0 else missing / self.rate

    def reset(self):
        self._tokens = float(self.capacity)
        self._last = self.clock.now()

    def idle_for(self):
        """Seconds since the bucket was last touched (used to purge idle entries)."""
        return self.clock.now() - self._last
