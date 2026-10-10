"""Synchronous retry helper built on a clock and a Backoff."""


def retry_call(fn, *, retries, backoff, clock, retry_on=(Exception,)):
    """Call ``fn()``; if it raises one of ``retry_on``, wait and try again.

    ``retries`` is the number of *extra* attempts, so ``retries=3`` allows up to 4 calls in
    total.  Before retry ``n`` the clock sleeps ``backoff.delay(n)``.  The last exception is
    re-raised when the retries are used up; other exceptions propagate immediately.
    """
    if retries < 0:
        raise ValueError("retries must not be negative")
    retry_number = 0
    while True:
        try:
            return fn()
        except retry_on:
            if retry_number >= retries:
                raise
            retry_number += 1
            clock.sleep(backoff.delay(retry_number))
