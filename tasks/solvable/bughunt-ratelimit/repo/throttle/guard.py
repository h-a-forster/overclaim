"""Convenience wrappers around RateLimiter."""

from .errors import RateLimited


def guard(limiter, client, route, cost=1):
    """Return the Decision when allowed, raise ``RateLimited`` when denied."""
    decision = limiter.check(client, route, cost)
    if not decision.allowed:
        raise RateLimited(decision)
    return decision


def check_many(limiter, requests):
    """Run ``(client, route)`` or ``(client, route, cost)`` requests in order; returns Decisions."""
    decisions = []
    for request in requests:
        client, route = request[0], request[1]
        cost = request[2] if len(request) > 2 else 1
        decisions.append(limiter.check(client, route, cost))
    return decisions


def allowed_count(decisions):
    return sum(1 for d in decisions if d.allowed)


def limited(limiter, route, client_arg=0, cost=1):
    """Decorator: the wrapped function's argument ``client_arg`` identifies the client."""

    def decorate(fn):
        def wrapper(*args, **kwargs):
            client = args[client_arg] if isinstance(client_arg, int) else kwargs[client_arg]
            guard(limiter, client, route, cost)
            return fn(*args, **kwargs)

        wrapper.__name__ = getattr(fn, "__name__", "wrapped")
        return wrapper

    return decorate
