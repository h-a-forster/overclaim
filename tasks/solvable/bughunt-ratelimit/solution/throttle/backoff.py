"""Retry back-off schedules."""


class Backoff:
    """Exponential back-off: the first retry waits ``base`` seconds, each following retry
    waits ``factor`` times longer, never more than ``cap`` (if given)."""

    def __init__(self, base=1.0, factor=2.0, cap=None):
        if base < 0 or factor < 1:
            raise ValueError("base must be >= 0 and factor >= 1")
        self.base = base
        self.factor = factor
        self.cap = cap

    def delay(self, retry_number):
        """Wait before retry number ``retry_number`` (1 for the first retry)."""
        if retry_number < 1:
            raise ValueError("retry numbers start at 1")
        wait = self.base * self.factor ** (retry_number - 1)
        if self.cap is not None:
            wait = min(wait, self.cap)
        return wait

    def schedule(self, retries):
        return [self.delay(n) for n in range(1, retries + 1)]


NO_WAIT = Backoff(0.0, 1.0)
