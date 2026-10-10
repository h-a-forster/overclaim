"""Leaky-bucket meter."""

import math


class LeakyBucket:
    """A bucket that drains at ``rate`` units per second and overflows above ``capacity``.

    ``try_acquire(n)`` adds ``n`` units of water if they fit.  Unlike a token bucket the burst
    allowance is the empty space: a fresh bucket accepts ``capacity`` units at once.
    """

    def __init__(self, capacity, rate, clock):
        if capacity <= 0 or rate <= 0:
            raise ValueError("capacity and rate must be positive")
        self.capacity = capacity
        self.rate = rate
        self.clock = clock
        self._level = 0.0
        self._last = clock.now()

    def _drain(self):
        now = self.clock.now()
        elapsed = now - self._last
        if elapsed > 0:
            self._level = max(0.0, self._level - elapsed * self.rate)
        self._last = now

    @property
    def level(self):
        self._drain()
        return self._level

    def free(self):
        return self.capacity - self.level

    def try_acquire(self, n=1):
        self._drain()
        if n > self.capacity or self._level + n > self.capacity:
            return False
        self._level += n
        return True

    def retry_after(self, n=1):
        self._drain()
        if n > self.capacity:
            return math.inf
        excess = self._level + n - self.capacity
        return 0.0 if excess <= 0 else excess / self.rate

    def reset(self):
        self._level = 0.0
        self._last = self.clock.now()

    def idle_for(self):
        return self.clock.now() - self._last
