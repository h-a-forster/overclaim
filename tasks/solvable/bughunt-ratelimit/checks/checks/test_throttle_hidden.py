import math
import unittest

from throttle import (Backoff, FakeClock, Policy, PolicyError, RateLimited, RateLimiter, Rule, Scheduler,
                      SchedulerError, SlidingWindowLog, ThrottleError, TokenBucket, check_many, guard, limited,
                      retry_call)
from throttle.backoff import NO_WAIT
from throttle.fixed import FixedWindowCounter
from throttle.guard import allowed_count
from throttle.leaky import LeakyBucket
from throttle.report import busiest, format_decision, format_results, summarize_results
from throttle.stats import Summary, mean, moving_average, percentile, waits

CONFIG = {
    "default": {"algo": "token_bucket", "capacity": 5, "rate": 1},
    "rules": {
        "/search": {"algo": "token_bucket", "capacity": 2, "rate": 1},
        "/login": {"algo": "token_bucket", "capacity": 1, "rate": 0.5},
        "/api/*": {"algo": "sliding_window", "limit": 3, "window": 60},
        "/api/admin/*": {"algo": "fixed_window", "limit": 1, "window": 60},
        "/export": {"algo": "leaky_bucket", "capacity": 2, "rate": 1},
    },
}


def make_limiter(config=CONFIG):
    clock = FakeClock()
    return RateLimiter(Policy.from_config(config), clock), clock


class BucketRefillSymptoms(unittest.TestCase):
    def test_frequent_polling_does_not_lose_time(self):
        clock = FakeClock()
        b = TokenBucket(2, 0.5, clock)
        self.assertTrue(b.try_acquire(2))
        clock.advance(1)
        self.assertFalse(b.try_acquire())
        clock.advance(1)
        self.assertTrue(b.try_acquire())

    def test_tokens_property_accumulates(self):
        clock = FakeClock()
        b = TokenBucket(4, 1, clock)
        b.try_acquire(4)
        seen = []
        for _ in range(4):
            clock.advance(0.25)
            seen.append(b.tokens)
        self.assertEqual(seen, [0.25, 0.5, 0.75, 1.0])

    def test_fraction_is_kept_after_whole_tokens(self):
        clock = FakeClock()
        b = TokenBucket(5, 1, clock)
        b.try_acquire(5)
        clock.advance(1.5)
        self.assertTrue(b.try_acquire())
        self.assertEqual(b.tokens, 0.5)
        clock.advance(0.5)
        self.assertEqual(b.tokens, 1.0)
        self.assertTrue(b.try_acquire())

    def test_high_rate_small_steps(self):
        clock = FakeClock()
        b = TokenBucket(10, 2, clock)
        b.try_acquire(10)
        for _ in range(4):
            clock.advance(0.25)
            self.assertFalse(b.try_acquire(2) if _ < 3 else False)
        clock.advance(0.0)
        self.assertEqual(b.tokens, 2.0)

    def test_retry_after_shrinks(self):
        clock = FakeClock()
        b = TokenBucket(2, 0.5, clock)
        b.try_acquire(2)
        self.assertEqual(b.retry_after(), 2.0)
        clock.advance(0.5)
        self.assertEqual(b.retry_after(), 1.5)
        clock.advance(0.5)
        self.assertEqual(b.retry_after(), 1.0)
        clock.advance(1.0)
        self.assertEqual(b.retry_after(), 0.0)

    def test_through_rate_limiter(self):
        limiter, clock = make_limiter()
        self.assertTrue(limiter.check("a", "/login").allowed)
        results = []
        for _ in range(4):
            clock.advance(0.5)
            results.append(limiter.check("a", "/login").allowed)
        self.assertEqual(results, [False, False, False, True])

    def test_limiter_denial_retry_after_value(self):
        limiter, clock = make_limiter()
        limiter.check("a", "/login")
        clock.advance(0.5)
        d = limiter.check("a", "/login")
        self.assertFalse(d.allowed)
        self.assertEqual(d.retry_after, 1.5)

    def test_idle_refill_still_capped(self):
        clock = FakeClock()
        b = TokenBucket(3, 1, clock)
        b.try_acquire(3)
        clock.advance(1000)
        self.assertEqual(b.tokens, 3.0)


class WindowBoundarySymptoms(unittest.TestCase):
    def test_event_expires_exactly_at_window(self):
        clock = FakeClock()
        w = SlidingWindowLog(2, 10, clock)
        self.assertTrue(w.try_acquire())
        clock.advance(1)
        self.assertTrue(w.try_acquire())
        clock.advance(8.5)
        self.assertFalse(w.try_acquire())
        clock.advance(0.5)
        self.assertTrue(w.try_acquire())
        self.assertEqual(w.count(), 2)

    def test_count_and_remaining_at_boundary(self):
        clock = FakeClock()
        w = SlidingWindowLog(3, 5, clock)
        w.try_acquire(2)
        clock.advance(5)
        self.assertEqual(w.count(), 0)
        self.assertEqual(w.remaining(), 3)

    def test_retry_after_matches_expiry(self):
        clock = FakeClock()
        w = SlidingWindowLog(2, 10, clock)
        w.try_acquire()
        clock.advance(1)
        w.try_acquire()
        clock.advance(4)
        self.assertEqual(w.retry_after(), 5.0)
        clock.advance(5)
        self.assertEqual(w.retry_after(), 0.0)
        self.assertTrue(w.try_acquire())

    def test_via_limiter(self):
        limiter, clock = make_limiter()
        for _ in range(3):
            self.assertTrue(limiter.check("c", "/api/x").allowed)
        self.assertFalse(limiter.check("c", "/api/x").allowed)
        clock.advance(60)
        self.assertTrue(limiter.check("c", "/api/x").allowed)

    def test_bulk_cost_at_boundary(self):
        clock = FakeClock()
        w = SlidingWindowLog(4, 10, clock)
        self.assertTrue(w.try_acquire(4))
        clock.advance(10)
        self.assertTrue(w.try_acquire(4))


class RuleKeySymptoms(unittest.TestCase):
    def test_other_route_not_affected(self):
        limiter, _ = make_limiter()
        self.assertTrue(limiter.check("alice", "/search").allowed)
        self.assertTrue(limiter.check("alice", "/search").allowed)
        self.assertFalse(limiter.check("alice", "/search").allowed)
        self.assertTrue(limiter.check("alice", "/login").allowed)
        self.assertTrue(limiter.check("alice", "/other").allowed)

    def test_each_rule_uses_its_own_numbers(self):
        limiter, _ = make_limiter()
        d1 = limiter.check("alice", "/login")
        d2 = limiter.check("alice", "/search")
        d3 = limiter.check("alice", "/other")
        self.assertEqual((d1.limit, d1.remaining), (1, 0))
        self.assertEqual((d2.limit, d2.remaining), (2, 1))
        self.assertEqual((d3.limit, d3.remaining), (5, 4))
        self.assertFalse(limiter.check("alice", "/login").allowed)
        self.assertEqual(limiter.check("alice", "/login").retry_after, 2.0)

    def test_default_route_budget(self):
        limiter, _ = make_limiter()
        allowed = [limiter.check("alice", "/other").allowed for _ in range(6)]
        self.assertEqual(allowed, [True] * 5 + [False])
        self.assertTrue(limiter.check("alice", "/search").allowed)

    def test_shared_rule_shares_budget(self):
        limiter, _ = make_limiter()
        allowed = [limiter.check("bob", "/api/%s" % name).allowed for name in "abcd"]
        self.assertEqual(allowed, [True, True, True, False])
        self.assertTrue(limiter.check("bob", "/api/admin/x").allowed)
        self.assertFalse(limiter.check("bob", "/api/admin/y").allowed)

    def test_two_token_bucket_rules_with_different_capacity(self):
        limiter, _ = make_limiter({
            "default": {"capacity": 10, "rate": 1},
            "rules": {"/a": {"capacity": 1, "rate": 1}, "/b": {"capacity": 3, "rate": 1}},
        })
        self.assertTrue(limiter.check("u", "/a").allowed)
        self.assertEqual([limiter.check("u", "/b").allowed for _ in range(4)], [True, True, True, False])

    def test_active_state_is_per_rule(self):
        limiter, _ = make_limiter()
        limiter.check("alice", "/search")
        limiter.check("alice", "/login")
        limiter.check("alice", "/other")
        limiter.check("bob", "/search")
        self.assertEqual(limiter.active(), [("alice", "/login"), ("alice", "/search"), ("alice", "<default>"),
                                            ("bob", "/search")])
        self.assertEqual(len(limiter.active()), 4)
        self.assertEqual(busiest(limiter), [("alice", 3), ("bob", 1)])

    def test_reset_and_purge(self):
        limiter, clock = make_limiter()
        limiter.check("alice", "/search")
        limiter.check("alice", "/search")
        limiter.check("alice", "/login")
        limiter.reset("alice")
        self.assertEqual(limiter.active(), [])
        limiter.check("alice", "/search")
        clock.advance(10)
        limiter.check("bob", "/search")
        self.assertEqual(limiter.purge(10), 1)
        self.assertEqual(limiter.active(), [("bob", "/search")])


class TieBreakSymptoms(unittest.TestCase):
    def test_submission_order_for_equal_priority(self):
        s = Scheduler(FakeClock())
        log = []
        for name in ("zeta", "alpha", "mid"):
            s.schedule(name, lambda n=name: log.append(n))
        s.run_due()
        self.assertEqual(log, ["zeta", "alpha", "mid"])

    def test_priorities_then_submission(self):
        s = Scheduler(FakeClock())
        log = []
        for name, prio in (("b", 1), ("a", 1), ("c", 5), ("d", 1), ("0", 5)):
            s.schedule(name, lambda n=name: log.append(n), priority=prio)
        s.run_due()
        self.assertEqual(log, ["c", "0", "b", "a", "d"])

    def test_retried_job_keeps_its_place(self):
        s = Scheduler(FakeClock())
        log = []
        state = {"n": 0}

        def flaky():
            state["n"] += 1
            log.append("z%d" % state["n"])
            if state["n"] == 1:
                raise RuntimeError("first time")

        s.schedule("z", flaky, retries=1)
        s.schedule("a", lambda: log.append("a"))
        results = s.run_due()
        self.assertEqual(log, ["z1", "z2", "a"])
        self.assertEqual([(r.name, r.attempts) for r in results], [("z", 2), ("a", 1)])

    def test_delayed_jobs_by_submission_when_due_together(self):
        clock = FakeClock()
        s = Scheduler(clock)
        log = []
        s.schedule("late-b", lambda: log.append("late-b"), delay=5)
        s.schedule("late-a", lambda: log.append("late-a"), delay=2)
        s.run_until_idle()
        self.assertEqual(log, ["late-a", "late-b"])
        s2 = Scheduler(FakeClock())
        log2 = []
        s2.schedule("y", lambda: log2.append("y"), delay=3)
        s2.schedule("x", lambda: log2.append("x"), delay=3)
        s2.run_until_idle()
        self.assertEqual(log2, ["y", "x"])

    def test_schedule_every_keeps_order(self):
        clock = FakeClock()
        s = Scheduler(clock)
        log = []
        s.schedule_every("tick", lambda: log.append(clock.now()), 2, 3)
        s.schedule("other", lambda: log.append("other"), delay=2)
        s.run_until_idle()
        self.assertEqual(log, [0.0, 2.0, "other", 4.0])


class BackoffSymptoms(unittest.TestCase):
    def test_first_retry_waits_base(self):
        b = Backoff(base=1, factor=2)
        self.assertEqual([b.delay(n) for n in (1, 2, 3, 4)], [1, 2, 4, 8])
        self.assertEqual(b.schedule(4), [1, 2, 4, 8])

    def test_cap_and_other_factors(self):
        self.assertEqual(Backoff(1, 2, cap=5).schedule(5), [1, 2, 4, 5, 5])
        self.assertEqual(Backoff(0.5, 3).schedule(3), [0.5, 1.5, 4.5])
        self.assertEqual(Backoff(2, 1).schedule(3), [2, 2, 2])
        self.assertEqual(Backoff(10, 2, cap=15).delay(1), 10)

    def test_scheduler_uses_it(self):
        clock = FakeClock()
        s = Scheduler(clock)
        calls = []

        def flaky():
            calls.append(clock.now())
            if len(calls) < 3:
                raise ValueError("no")
            return "done"

        s.schedule("job", flaky, retries=3, backoff=Backoff(1, 2))
        results = s.run_until_idle()
        self.assertEqual(calls, [0.0, 1.0, 3.0])
        self.assertEqual((results[0].ok, results[0].attempts, results[0].finished_at, results[0].value), (True, 3, 3.0, "done"))

    def test_retry_call_sleeps(self):
        clock = FakeClock()
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise OSError("again")
            return "ok"

        self.assertEqual(retry_call(flaky, retries=5, backoff=Backoff(1, 2), clock=clock), "ok")
        self.assertEqual(clock.now(), 3.0)


class RetryCountSymptoms(unittest.TestCase):
    def test_scheduler_total_attempts(self):
        for retries in (1, 2, 3):
            s = Scheduler(FakeClock())
            calls = []

            def boom():
                calls.append(1)
                raise RuntimeError("x")

            s.schedule("boom", boom, retries=retries)
            (result,) = s.run_due()
            self.assertEqual(len(calls), retries + 1)
            self.assertEqual((result.ok, result.attempts), (False, retries + 1))

    def test_succeeds_on_last_allowed_attempt(self):
        s = Scheduler(FakeClock())
        calls = []

        def third_time():
            calls.append(1)
            if len(calls) < 4:
                raise RuntimeError("x")
            return "yes"

        s.schedule("t", third_time, retries=3)
        (result,) = s.run_due()
        self.assertEqual((result.ok, result.value, result.attempts), (True, "yes", 4))

    def test_retry_call_total_attempts(self):
        for retries in (0, 1, 2, 3):
            calls = []

            def boom():
                calls.append(1)
                raise KeyError("k")

            with self.assertRaises(KeyError):
                retry_call(boom, retries=retries, backoff=NO_WAIT, clock=FakeClock())
            self.assertEqual(len(calls), retries + 1)

    def test_retry_call_succeeds_on_last_attempt(self):
        calls = []

        def f():
            calls.append(1)
            if len(calls) < 3:
                raise KeyError("k")
            return len(calls)

        self.assertEqual(retry_call(f, retries=2, backoff=NO_WAIT, clock=FakeClock()), 3)

    def test_retry_call_reraises_last_and_other_exceptions_propagate(self):
        seq = iter([KeyError("1"), KeyError("2")])

        def f():
            raise next(seq)

        with self.assertRaises(KeyError) as cm:
            retry_call(f, retries=1, backoff=NO_WAIT, clock=FakeClock())
        self.assertEqual(cm.exception.args, ("2",))
        calls = []

        def g():
            calls.append(1)
            raise ValueError("v")

        with self.assertRaises(ValueError):
            retry_call(g, retries=5, backoff=NO_WAIT, clock=FakeClock(), retry_on=(KeyError,))
        self.assertEqual(len(calls), 1)


class RetryAfterHeaderSymptoms(unittest.TestCase):
    def test_rounds_up(self):
        limiter, clock = make_limiter()
        limiter.check("a", "/login")
        clock.advance(0.5)
        d = limiter.check("a", "/login")
        self.assertEqual(d.retry_after, 1.5)
        self.assertEqual(d.headers()["Retry-After"], "2")

    def test_small_waits_are_one(self):
        limiter, clock = make_limiter()
        limiter.check("a", "/login")
        clock.advance(1.75)
        d = limiter.check("a", "/login")
        self.assertEqual(d.retry_after, 0.25)
        self.assertEqual(d.headers()["Retry-After"], "1")

    def test_exact_and_fractional(self):
        limiter, clock = make_limiter()
        limiter.check("a", "/login")
        self.assertEqual(limiter.check("a", "/login").headers()["Retry-After"], "2")
        limiter2, clock2 = make_limiter()
        limiter2.check("a", "/api/x")
        for _ in range(2):
            limiter2.check("a", "/api/x")
        clock2.advance(7.5)
        d = limiter2.check("a", "/api/x")
        self.assertEqual(d.retry_after, 52.5)
        self.assertEqual(d.headers()["Retry-After"], "53")

    def test_leaky_and_fixed_rules(self):
        limiter, clock = make_limiter()
        limiter.check("a", "/export", 2)
        clock.advance(0.5)
        d = limiter.check("a", "/export", 1)
        self.assertEqual(d.retry_after, 0.5)
        self.assertEqual(d.headers()["Retry-After"], "1")
        limiter.check("a", "/api/admin/z")
        clock.advance(4.25)
        d = limiter.check("a", "/api/admin/z")
        self.assertEqual(d.headers()["Retry-After"], str(math.ceil(d.retry_after)))
        self.assertEqual(d.retry_after, 55.25)
        self.assertEqual(d.headers()["Retry-After"], "56")

    def test_never(self):
        limiter, _ = make_limiter()
        d = limiter.check("a", "/search", cost=3)
        self.assertFalse(d.allowed)
        self.assertEqual(d.headers()["Retry-After"], "never")

    def test_guard_exception_carries_decision(self):
        limiter, clock = make_limiter()
        guard(limiter, "a", "/login")
        clock.advance(0.5)
        with self.assertRaises(RateLimited) as cm:
            guard(limiter, "a", "/login")
        self.assertEqual(cm.exception.decision.headers()["Retry-After"], "2")
        self.assertEqual(cm.exception.retry_after, 1.5)


class BucketRegression(unittest.TestCase):
    def test_basics(self):
        clock = FakeClock()
        b = TokenBucket(3, 1, clock)
        self.assertEqual(b.tokens, 3.0)
        self.assertTrue(b.try_acquire(3))
        self.assertFalse(b.try_acquire(1))
        self.assertFalse(b.try_acquire(4))
        clock.advance(2)
        self.assertTrue(b.try_acquire(2))
        self.assertFalse(b.try_acquire())

    def test_initial_and_reset(self):
        clock = FakeClock()
        b = TokenBucket(5, 1, clock, initial=1)
        self.assertTrue(b.try_acquire())
        self.assertFalse(b.try_acquire())
        b.reset()
        self.assertEqual(b.tokens, 5.0)
        self.assertEqual(TokenBucket(2, 1, clock, initial=10).tokens, 2.0)

    def test_retry_after_edges(self):
        clock = FakeClock()
        b = TokenBucket(2, 4, clock)
        self.assertEqual(b.retry_after(), 0.0)
        self.assertEqual(b.retry_after(3), math.inf)
        b.try_acquire(2)
        self.assertEqual(b.retry_after(2), 0.5)

    def test_validation(self):
        clock = FakeClock()
        for args in ((0, 1), (1, 0), (-1, 1)):
            with self.assertRaises(ValueError):
                TokenBucket(*args, clock)

    def test_idle_for(self):
        clock = FakeClock()
        b = TokenBucket(1, 1, clock)
        clock.advance(3)
        self.assertEqual(b.idle_for(), 3.0)


class ClockRegression(unittest.TestCase):
    def test_clock(self):
        c = FakeClock(5)
        self.assertEqual(c.now(), 5.0)
        self.assertEqual(c.advance(2.5), 7.5)
        self.assertEqual(c.sleep(0.5), 8.0)
        self.assertEqual(c.set(10), 10.0)
        for bad in (lambda: c.advance(-1), lambda: c.set(9)):
            with self.assertRaises(ThrottleError):
                bad()


class WindowAndFixedRegression(unittest.TestCase):
    def test_window_basics(self):
        clock = FakeClock()
        w = SlidingWindowLog(3, 10, clock)
        self.assertTrue(w.try_acquire(2))
        self.assertEqual(w.remaining(), 1)
        self.assertFalse(w.try_acquire(2))
        self.assertFalse(w.try_acquire(4))
        self.assertEqual(w.retry_after(4), math.inf)
        w.reset()
        self.assertEqual(w.count(), 0)
        self.assertEqual(w.idle_for(), math.inf)
        for args in ((0, 1), (1, 0)):
            with self.assertRaises(ValueError):
                SlidingWindowLog(*args, clock)

    def test_window_partial_expiry(self):
        clock = FakeClock()
        w = SlidingWindowLog(3, 10, clock)
        w.try_acquire()
        clock.advance(4)
        w.try_acquire(2)
        clock.advance(7)
        self.assertEqual(w.count(), 2)
        self.assertEqual(w.retry_after(2), 3.0)

    def test_fixed_window(self):
        clock = FakeClock(7)
        f = FixedWindowCounter(2, 10, clock)
        self.assertEqual([f.try_acquire() for _ in range(3)], [True, True, False])
        self.assertEqual(f.retry_after(), 3.0)
        self.assertEqual(f.remaining(), 0)
        clock.advance(3)
        self.assertTrue(f.try_acquire())
        self.assertEqual(f.count(), 1)
        self.assertEqual(f.retry_after(2), 10.0)
        self.assertEqual(f.retry_after(3), math.inf)

    def test_leaky(self):
        clock = FakeClock()
        b = LeakyBucket(3, 1, clock)
        self.assertTrue(b.try_acquire(3))
        self.assertFalse(b.try_acquire())
        self.assertEqual(b.retry_after(), 1.0)
        clock.advance(1.5)
        self.assertEqual(b.level, 1.5)
        self.assertEqual(b.free(), 1.5)
        self.assertTrue(b.try_acquire())
        self.assertEqual(b.retry_after(3), 2.5)
        self.assertEqual(b.retry_after(4), math.inf)
        b.reset()
        self.assertEqual(b.level, 0.0)


class PolicyRegression(unittest.TestCase):
    def setUp(self):
        self.policy = Policy.from_config(CONFIG)

    def test_matching(self):
        m = self.policy.match
        self.assertEqual(m("/search").pattern, "/search")
        self.assertEqual(m("/api/x").pattern, "/api/*")
        self.assertEqual(m("/api/admin/x").pattern, "/api/admin/*")
        self.assertEqual(m("/api/admin").pattern, "/api/*")
        self.assertEqual(m("/searchy").pattern, "<default>")
        self.assertEqual(m("/nothing").pattern, "<default>")
        self.assertEqual(m("/api/").pattern, "/api/*")

    def test_rule_properties(self):
        self.assertEqual(self.policy.match("/search").limit, 2)
        self.assertEqual(self.policy.match("/api/a").limit, 3)
        self.assertEqual(self.policy.match("/export").limit, 2)
        self.assertEqual(self.policy.match("/x").key, "<default>")

    def test_errors(self):
        bad_configs = [
            {"rules": {}},
            {"default": {"algo": "nope", "capacity": 1, "rate": 1}},
            {"default": {"capacity": 0, "rate": 1}},
            {"default": {"capacity": 1}},
            {"default": {"capacity": True, "rate": 1}},
            {"default": {"algo": "sliding_window", "limit": 5}},
            {"default": {"capacity": 1, "rate": 1}, "rules": {"/a": {"algo": "fixed_window", "limit": -1, "window": 5}}},
        ]
        for cfg in bad_configs:
            with self.assertRaises(PolicyError, msg=str(cfg)):
                Policy.from_config(cfg)
        with self.assertRaises(PolicyError):
            Policy([Rule("/a", "token_bucket", capacity=1, rate=1), Rule("/a", "token_bucket", capacity=1, rate=1)],
                   Rule("d", "token_bucket", capacity=1, rate=1))

    def test_default_algo_is_token_bucket(self):
        p = Policy.from_config({"default": {"capacity": 3, "rate": 1}})
        self.assertEqual(p.default.algo, "token_bucket")


class LimiterRegression(unittest.TestCase):
    def test_clients_independent_and_reset(self):
        limiter, _ = make_limiter()
        self.assertTrue(limiter.check("a", "/login").allowed)
        self.assertFalse(limiter.check("a", "/login").allowed)
        self.assertTrue(limiter.check("b", "/login").allowed)
        limiter.reset()
        self.assertTrue(limiter.check("a", "/login").allowed)

    def test_costs(self):
        limiter, _ = make_limiter()
        self.assertTrue(limiter.check("a", "/other", 3).allowed)
        d = limiter.check("a", "/other", 3)
        self.assertFalse(d.allowed)
        self.assertEqual(d.remaining, 2)
        self.assertEqual(d.retry_after, 1.0)

    def test_headers_allowed(self):
        limiter, _ = make_limiter()
        d = limiter.check("a", "/search")
        self.assertEqual(d.headers(), {"X-RateLimit-Limit": "2", "X-RateLimit-Remaining": "1"})

    def test_other_algorithms_remaining(self):
        limiter, _ = make_limiter()
        d = limiter.check("a", "/api/z")
        self.assertEqual((d.limit, d.remaining), (3, 2))
        d = limiter.check("a", "/api/admin/z")
        self.assertEqual((d.limit, d.remaining), (1, 0))
        d = limiter.check("a", "/export")
        self.assertEqual((d.limit, d.remaining), (2, 1))

    def test_leaky_rule(self):
        limiter, clock = make_limiter()
        self.assertTrue(limiter.check("a", "/export", 2).allowed)
        self.assertFalse(limiter.check("a", "/export").allowed)
        clock.advance(1)
        self.assertTrue(limiter.check("a", "/export").allowed)

    def test_report_helpers(self):
        limiter, _ = make_limiter()
        d = limiter.check("a", "/login")
        self.assertEqual(format_decision(d), "allowed (rule /login, 0/1 left)")
        d = limiter.check("a", "/login")
        self.assertEqual(format_decision(d), "denied (rule /login, 0/1 left), retry in 2s")


class GuardRegression(unittest.TestCase):
    def test_check_many_and_count(self):
        limiter, _ = make_limiter()
        ds = check_many(limiter, [("a", "/login"), ("a", "/login"), ("b", "/search", 2), ("b", "/search")])
        self.assertEqual([d.allowed for d in ds], [True, False, True, False])
        self.assertEqual(allowed_count(ds), 2)

    def test_decorator(self):
        limiter, _ = make_limiter()
        calls = []

        @limited(limiter, "/login")
        def handler(client, value):
            calls.append((client, value))
            return value * 2

        self.assertEqual(handler("u1", 4), 8)
        with self.assertRaises(RateLimited):
            handler("u1", 5)
        self.assertEqual(handler("u2", 1), 2)
        self.assertEqual(calls, [("u1", 4), ("u2", 1)])

        @limited(limiter, "/search", client_arg="who")
        def other(who=None):
            return who

        self.assertEqual(other(who="x"), "x")


class SchedulerRegression(unittest.TestCase):
    def test_priority_beats_submission(self):
        s = Scheduler(FakeClock())
        log = []
        s.schedule("low", lambda: log.append("low"), priority=0)
        s.schedule("high", lambda: log.append("high"), priority=9)
        s.run_due()
        self.assertEqual(log, ["high", "low"])

    def test_delay_cancel_pending(self):
        clock = FakeClock()
        s = Scheduler(clock)
        s.schedule("a", lambda: 1, delay=5)
        s.schedule("b", lambda: 2, delay=1, priority=3)
        s.schedule("a", lambda: 3, delay=1)
        self.assertEqual([j.name for j in s.pending()], ["b", "a", "a"])
        self.assertEqual(s.next_run_time(), 1.0)
        self.assertEqual(s.cancel("a"), 2)
        self.assertEqual(s.cancel("zzz"), 0)
        self.assertEqual(s.run_due(), [])
        clock.advance(1)
        self.assertEqual([r.value for r in s.run_due()], [2])

    def test_run_until_idle_advances_clock(self):
        clock = FakeClock()
        s = Scheduler(clock)
        s.schedule("a", lambda: "x", delay=3)
        s.schedule("b", lambda: "y", delay=10)
        results = s.run_until_idle()
        self.assertEqual([(r.name, r.finished_at) for r in results], [("a", 3.0), ("b", 10.0)])
        self.assertEqual(clock.now(), 10.0)
        self.assertEqual(s.results, results)

    def test_failure_result_and_summary(self):
        s = Scheduler(FakeClock())

        def bad():
            raise ZeroDivisionError

        s.schedule("ok", lambda: 1)
        s.schedule("bad", bad, retries=2)
        results = s.run_until_idle()
        self.assertEqual(summarize_results(results), {"succeeded": 1, "failed": 1, "attempts": 4})
        self.assertEqual(results[1].error, "ZeroDivisionError")
        text = format_results(results)
        self.assertEqual(text.split("\n")[0], "ok   ok      attempts=1  t=0")
        self.assertEqual(format_results([]), "(no results)")

    def test_validation_and_every(self):
        s = Scheduler(FakeClock())
        for call in (lambda: s.schedule("x", lambda: 1, delay=-1), lambda: s.schedule("x", lambda: 1, retries=-1),
                     lambda: s.schedule_every("x", lambda: 1, 0, 3), lambda: s.schedule_every("x", lambda: 1, 1, 0)):
            with self.assertRaises(SchedulerError):
                call()
        jobs = s.schedule_every("t", lambda: 1, 2.5, 3, priority=1)
        self.assertEqual([j.run_at for j in jobs], [0.0, 2.5, 5.0])

    def test_rate_limited_jobs_are_postponed(self):
        clock = FakeClock()
        policy = Policy.from_config({
            "default": {"capacity": 100, "rate": 100},
            "rules": {"/job": {"algo": "token_bucket", "capacity": 1, "rate": 0.5}},
        })
        limiter = RateLimiter(policy, clock)
        s = Scheduler(clock, limiter)
        for name in ("one", "two", "three"):
            s.schedule(name, lambda n=name: n, rate_key="/job")
        s.schedule("free", lambda: "free")
        results = s.run_until_idle()
        self.assertEqual([(r.name, r.finished_at, r.attempts) for r in results],
                         [("one", 0.0, 1), ("free", 0.0, 1), ("two", 2.0, 1), ("three", 4.0, 1)])

    def test_rate_limited_job_denials_do_not_use_retries(self):
        clock = FakeClock()
        policy = Policy.from_config({"default": {"capacity": 1, "rate": 1}})
        limiter = RateLimiter(policy, clock)
        s = Scheduler(clock, limiter)
        calls = []

        def work():
            calls.append(clock.now())
            if len(calls) == 1:
                raise RuntimeError("once")
            return "fine"

        s.schedule("w", work, retries=1, backoff=Backoff(0.5, 2), rate_key="/x")
        (r,) = s.run_until_idle()
        self.assertTrue(r.ok)
        self.assertEqual(r.attempts, 2)
        self.assertEqual(calls, [0.0, 1.0])


class StatsRegression(unittest.TestCase):
    def test_percentile(self):
        data = [5, 1, 3, 2, 4]
        self.assertEqual(percentile(data, 50), 3)
        self.assertEqual(percentile(data, 20), 1)
        self.assertEqual(percentile(data, 90), 5)
        self.assertEqual(percentile(data, 100), 5)
        self.assertEqual(percentile(list(range(1, 11)), 50), 5)
        self.assertEqual(percentile(list(range(1, 11)), 95), 10)
        self.assertEqual(percentile([7], 1), 7)
        for call in (lambda: percentile([], 50), lambda: percentile([1], 0), lambda: percentile([1], 101)):
            with self.assertRaises(ValueError):
                call()

    def test_mean_and_moving(self):
        self.assertEqual(mean([1, 2, 3, 6]), 3.0)
        self.assertEqual(moving_average([1, 2, 3, 4], 2), [1.5, 2.5, 3.5])
        self.assertEqual(moving_average([1, 2], 3), [])
        with self.assertRaises(ValueError):
            moving_average([1], 0)

    def test_summary(self):
        s = Summary(list(range(1, 101)))
        self.assertEqual(s.as_dict(), {"count": 100, "min": 1, "max": 100, "mean": 50.5, "p50": 50, "p90": 90, "p99": 99})
        self.assertIsNone(Summary([]).p50)

    def test_waits(self):
        s = Scheduler(FakeClock())
        s.schedule("a", lambda: 1, delay=2)
        s.schedule("b", lambda: 2, delay=5)
        results = s.run_until_idle()
        self.assertEqual(waits(results, {"a": 0.0, "b": 1.0, "zzz": 9.0}), [2.0, 4.0])


if __name__ == "__main__":
    unittest.main()
