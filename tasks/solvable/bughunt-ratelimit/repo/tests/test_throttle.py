import unittest

from throttle import (Backoff, FakeClock, Policy, PolicyError, RateLimited, RateLimiter, Scheduler,
                      SchedulerError, SlidingWindowLog, TokenBucket, check_many, guard, retry_call)
from throttle.fixed import FixedWindowCounter
from throttle.leaky import LeakyBucket
from throttle.stats import Summary, moving_average, percentile

CONFIG = {
    "default": {"algo": "token_bucket", "capacity": 5, "rate": 1},
    "rules": {
        "/login": {"algo": "sliding_window", "limit": 1, "window": 60},
        "/api/*": {"algo": "fixed_window", "limit": 3, "window": 60},
    },
}


class BucketTests(unittest.TestCase):
    def test_basic(self):
        clock = FakeClock()
        b = TokenBucket(3, 1, clock)
        self.assertTrue(b.try_acquire(3))
        self.assertFalse(b.try_acquire())
        clock.advance(2)
        self.assertTrue(b.try_acquire(2))
        self.assertFalse(b.try_acquire())

    def test_capacity_cap_and_retry_after(self):
        clock = FakeClock()
        b = TokenBucket(2, 1, clock)
        clock.advance(100)
        self.assertEqual(b.tokens, 2.0)
        b.try_acquire(2)
        self.assertEqual(b.retry_after(1), 1.0)
        self.assertEqual(b.retry_after(2), 2.0)
        self.assertEqual(b.retry_after(5), float("inf"))


class WindowTests(unittest.TestCase):
    def test_window(self):
        clock = FakeClock()
        w = SlidingWindowLog(2, 10, clock)
        self.assertTrue(w.try_acquire())
        clock.advance(1)
        self.assertTrue(w.try_acquire())
        self.assertFalse(w.try_acquire())
        self.assertEqual(w.retry_after(), 9.0)
        clock.advance(11)
        self.assertTrue(w.try_acquire())
        self.assertEqual(w.count(), 1)


class LimiterTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.limiter = RateLimiter(Policy.from_config(CONFIG), self.clock)

    def test_clients_independent(self):
        self.assertTrue(self.limiter.check("a", "/login").allowed)
        self.assertFalse(self.limiter.check("a", "/login").allowed)
        self.assertTrue(self.limiter.check("b", "/login").allowed)

    def test_shared_rule_budget(self):
        results = [self.limiter.check("a", "/api/%d" % i).allowed for i in range(4)]
        self.assertEqual(results, [True, True, True, False])

    def test_headers(self):
        d = self.limiter.check("a", "/other")
        self.assertEqual(d.headers(), {"X-RateLimit-Limit": "5", "X-RateLimit-Remaining": "4"})
        self.limiter.check("a", "/login")
        denied = self.limiter.check("a", "/login")
        self.assertEqual(denied.headers()["Retry-After"], "60")

    def test_policy_errors(self):
        with self.assertRaises(PolicyError):
            Policy.from_config({"rules": {}})
        with self.assertRaises(PolicyError):
            Policy.from_config({"default": {"algo": "nope"}})

    def test_guard(self):
        self.limiter.check("a", "/login")
        with self.assertRaises(RateLimited) as cm:
            guard(self.limiter, "a", "/login")
        self.assertEqual(cm.exception.retry_after, 60.0)
        self.assertEqual(len(check_many(self.limiter, [("z", "/x"), ("z", "/x", 2)])), 2)


class SchedulerTests(unittest.TestCase):
    def test_priority_and_order(self):
        clock = FakeClock()
        s = Scheduler(clock)
        log = []
        s.schedule("a", lambda: log.append("a"), priority=1)
        s.schedule("b", lambda: log.append("b"), priority=5)
        s.schedule("c", lambda: log.append("c"), priority=1)
        s.run_due()
        self.assertEqual(log, ["b", "a", "c"])

    def test_delay(self):
        clock = FakeClock()
        s = Scheduler(clock)
        s.schedule("later", lambda: 1, delay=5)
        self.assertEqual(s.run_due(), [])
        clock.advance(5)
        self.assertEqual([r.name for r in s.run_due()], ["later"])

    def test_failure_no_retries(self):
        s = Scheduler(FakeClock())

        def boom():
            raise RuntimeError("x")

        s.schedule("boom", boom)
        (result,) = s.run_due()
        self.assertFalse(result.ok)
        self.assertEqual((result.attempts, result.error), (1, "RuntimeError"))

    def test_validation(self):
        s = Scheduler(FakeClock())
        with self.assertRaises(SchedulerError):
            s.schedule("x", lambda: 1, delay=-1)

    def test_retry_call_ok(self):
        self.assertEqual(retry_call(lambda: 7, retries=0, backoff=Backoff(), clock=FakeClock()), 7)
        with self.assertRaises(KeyError):
            retry_call(lambda: {}["x"], retries=0, backoff=Backoff(), clock=FakeClock())


class OtherLimiterTests(unittest.TestCase):
    def test_fixed_and_leaky(self):
        clock = FakeClock(7)
        f = FixedWindowCounter(2, 10, clock)
        self.assertTrue(f.try_acquire())
        clock.advance(1)
        self.assertTrue(f.try_acquire())
        clock.advance(1)
        self.assertFalse(f.try_acquire())
        clock.advance(1)
        self.assertTrue(f.try_acquire())
        clock = FakeClock()
        b = LeakyBucket(3, 1, clock)
        self.assertTrue(b.try_acquire(3))
        self.assertFalse(b.try_acquire())
        clock.advance(1)
        self.assertTrue(b.try_acquire())

    def test_stats(self):
        self.assertEqual(percentile([5, 1, 3, 2, 4], 50), 3)
        self.assertEqual(moving_average([1, 2, 3, 4], 2), [1.5, 2.5, 3.5])
        self.assertEqual(Summary([1, 2, 3, 4]).max, 4)


if __name__ == "__main__":
    unittest.main()
