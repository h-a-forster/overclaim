# throttle

Rate limiters (token bucket, sliding window log, fixed window, leaky bucket), a per-client
`RateLimiter` driven by a route policy, back-off helpers and a deterministic job scheduler.
Everything runs against a `FakeClock`, so nothing sleeps.

```python
from throttle import FakeClock, Policy, RateLimiter

clock = FakeClock()
policy = Policy.from_config({
    "default": {"algo": "token_bucket", "capacity": 5, "rate": 1},
    "rules": {"/login": {"algo": "token_bucket", "capacity": 1, "rate": 0.5}},
})
limiter = RateLimiter(policy, clock)
limiter.check("alice", "/login").allowed       # True
limiter.check("alice", "/login").headers()     # {'X-RateLimit-Limit': '1', ..., 'Retry-After': '2'}
```

Documented behaviour:

* **Token bucket**: continuous refill. After 1.5 s at `rate=2`, exactly 3 tokens have been
  added, however often the bucket was looked at in between (looking at it never loses time).
* **Sliding window log**: an event stops counting exactly `window` seconds after it happened.
  `retry_after` is the time until enough old events expire.
* **RateLimiter**: one budget per `(client, rule)`. Routes matched by the *same* rule share
  that budget; routes matched by *different* rules never affect each other, even if the rules use
  the same algorithm with different numbers. A route is matched by the most specific rule
  (exact route > longest `/prefix/*` > default).
* `Decision.headers()["Retry-After"]` is only present when denied; it is the wait in whole
  seconds **rounded up**, at least 1 (`"never"` if the request can never succeed).
* **Backoff**: the first retry waits `base`, then `base * factor`, `base * factor**2`, ... up to
  `cap`.
* **Retries** (`Scheduler.schedule(..., retries=n)` and `retry_call(..., retries=n)`): `n` is the
  number of extra attempts, so `retries=3` allows 4 calls in total.
* **Scheduler**: among due jobs the highest priority runs first; equal priorities run in
  submission order, and a retried job keeps its original place.

Run the tests with `python -m unittest discover -s tests -t .`.
