"""Clocks.  Everything in this package takes a clock so tests never sleep."""

from .errors import ThrottleError


class FakeClock:
    """A manually advanced clock measured in seconds (floats)."""

    def __init__(self, start=0.0):
        self._now = float(start)

    def now(self):
        return self._now

    def advance(self, seconds):
        if seconds < 0:
            raise ThrottleError("cannot move the clock backwards")
        self._now += seconds
        return self._now

    def set(self, instant):
        if instant < self._now:
            raise ThrottleError("cannot move the clock backwards")
        self._now = float(instant)
        return self._now

    def sleep(self, seconds):
        """Same as ``advance``; lets code written against ``time.sleep`` run instantly."""
        return self.advance(seconds)
