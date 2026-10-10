"""Exceptions raised by throttle."""


class ThrottleError(Exception):
    """Base class."""


class PolicyError(ThrottleError):
    """A rate-limit configuration is invalid."""


class SchedulerError(ThrottleError):
    """Invalid scheduler usage (unknown job, bad delay, ...)."""


class RateLimited(ThrottleError):
    """Raised by ``guard`` when a request is denied."""

    def __init__(self, decision):
        super().__init__("rate limited, retry after %gs" % decision.retry_after)
        self.decision = decision
        self.retry_after = decision.retry_after
