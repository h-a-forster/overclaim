"""Per-client rate limiting driven by a Policy."""

import math

from .bucket import TokenBucket
from .fixed import FixedWindowCounter
from .leaky import LeakyBucket
from .window import SlidingWindowLog


class Decision:
    """Result of a rate-limit check."""

    def __init__(self, allowed, limit, remaining, retry_after, rule):
        self.allowed = allowed
        self.limit = limit
        self.remaining = remaining
        self.retry_after = retry_after
        self.rule = rule

    def headers(self):
        """HTTP-style headers.  ``Retry-After`` is only present when denied and is the number
        of whole seconds to wait, rounded up (at least 1)."""
        out = {"X-RateLimit-Limit": str(self.limit), "X-RateLimit-Remaining": str(self.remaining)}
        if not self.allowed:
            if math.isinf(self.retry_after):
                out["Retry-After"] = "never"
            else:
                out["Retry-After"] = str(max(1, math.ceil(self.retry_after)))
        return out

    def __repr__(self):
        return "Decision(allowed=%r, remaining=%r, retry_after=%r)" % (self.allowed, self.remaining, self.retry_after)


class RateLimiter:
    """Keeps one limiter per (client, rule).

    Routes that match the same rule share a budget; routes that match different rules have
    independent budgets even for the same client.
    """

    def __init__(self, policy, clock):
        self.policy = policy
        self.clock = clock
        self._limiters = {}

    def _limiter(self, client, rule):
        key = (client, rule.key)
        limiter = self._limiters.get(key)
        if limiter is None:
            p = rule.params
            if rule.algo == "token_bucket":
                limiter = TokenBucket(p["capacity"], p["rate"], self.clock)
            elif rule.algo == "leaky_bucket":
                limiter = LeakyBucket(p["capacity"], p["rate"], self.clock)
            elif rule.algo == "fixed_window":
                limiter = FixedWindowCounter(p["limit"], p["window"], self.clock)
            else:
                limiter = SlidingWindowLog(p["limit"], p["window"], self.clock)
            self._limiters[key] = limiter
        return limiter

    def check(self, client, route, cost=1):
        rule = self.policy.match(route)
        limiter = self._limiter(client, rule)
        if limiter.try_acquire(cost):
            return Decision(True, rule.limit, self._remaining(limiter), 0.0, rule)
        return Decision(False, rule.limit, self._remaining(limiter), limiter.retry_after(cost), rule)

    @staticmethod
    def _remaining(limiter):
        if isinstance(limiter, TokenBucket):
            return int(limiter.tokens)
        if isinstance(limiter, LeakyBucket):
            return int(limiter.free())
        return limiter.remaining()

    def reset(self, client=None):
        """Forget the budgets of one client (or of everybody)."""
        for key in list(self._limiters):
            if client is None or key[0] == client:
                del self._limiters[key]

    def purge(self, idle_seconds):
        """Drop limiters untouched for at least ``idle_seconds``; returns how many."""
        stale = [k for k, lim in self._limiters.items() if lim.idle_for() >= idle_seconds]
        for key in stale:
            del self._limiters[key]
        return len(stale)

    def active(self):
        """Sorted ``(client, rule key)`` pairs that currently hold state."""
        return sorted(self._limiters)
