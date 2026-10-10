from .resolve import resolve


def join(base, ref):
    """Kept for existing callers: identical to `resolve`."""
    return resolve(base, ref)
