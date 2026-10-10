"""A deterministic job scheduler with priorities, retries and optional rate limiting."""

from .backoff import NO_WAIT
from .errors import SchedulerError


class Job:
    def __init__(self, seq, name, fn, run_at, priority, retries, backoff, rate_key):
        self.seq = seq
        self.name = name
        self.fn = fn
        self.run_at = run_at
        self.priority = priority
        self.retries_left = retries
        self.backoff = backoff
        self.rate_key = rate_key
        self.attempts = 0
        self.retries_done = 0

    def __repr__(self):
        return "Job(%s #%d at %s)" % (self.name, self.seq, self.run_at)


class JobResult:
    def __init__(self, name, ok, attempts, value, error, finished_at):
        self.name = name
        self.ok = ok
        self.attempts = attempts
        self.value = value
        self.error = error
        self.finished_at = finished_at

    def __repr__(self):
        state = "ok" if self.ok else "failed(%s)" % self.error
        return "JobResult(%s %s after %d)" % (self.name, state, self.attempts)


class Scheduler:
    """Runs jobs when they are due.

    Among due jobs the highest ``priority`` runs first; equal priorities run in submission
    order (a job that is retried keeps its original place in that order).  A job that fails is
    retried up to ``retries`` more times, waiting ``backoff.delay(n)`` before retry ``n``.
    When a ``limiter`` is given, jobs with a ``rate_key`` first have to pass
    ``limiter.check("scheduler", rate_key)``; a denied job is postponed by the decision's
    ``retry_after`` and this does not count as an attempt.
    """

    def __init__(self, clock, limiter=None):
        self.clock = clock
        self.limiter = limiter
        self._jobs = []
        self._seq = 0
        self.results = []

    def schedule(self, name, fn, *, delay=0.0, priority=0, retries=0, backoff=None, rate_key=None):
        if delay < 0:
            raise SchedulerError("delay must not be negative")
        if retries < 0:
            raise SchedulerError("retries must not be negative")
        self._seq += 1
        job = Job(self._seq, name, fn, self.clock.now() + delay, priority, retries, backoff or NO_WAIT, rate_key)
        self._jobs.append(job)
        return job

    def schedule_every(self, name, fn, interval, times, **options):
        """Schedule ``times`` runs of ``fn``, the first now and then one every ``interval`` seconds."""
        if interval <= 0 or times < 1:
            raise SchedulerError("interval must be positive and times at least 1")
        return [self.schedule(name, fn, delay=i * interval, **options) for i in range(times)]

    def pending(self):
        """Jobs not finished yet, in the order they would run if all were due."""
        return sorted(self._jobs, key=lambda j: (j.run_at, -j.priority, j.seq))

    def cancel(self, name):
        """Remove every pending job called ``name``; returns how many were removed."""
        kept = [j for j in self._jobs if j.name != name]
        removed = len(self._jobs) - len(kept)
        self._jobs = kept
        return removed

    def _due(self):
        now = self.clock.now()
        return [j for j in self._jobs if j.run_at <= now]

    def next_run_time(self):
        return min((j.run_at for j in self._jobs), default=None)

    def run_due(self):
        """Run everything that is due now (including retries that become due immediately).

        Returns the results produced by this call, in execution order.
        """
        produced = []
        while True:
            due = self._due()
            if not due:
                return produced
            job = min(due, key=lambda j: (-j.priority, j.name))
            result = self._run(job)
            if result is not None:
                produced.append(result)
                self.results.append(result)

    def run_until_idle(self, max_steps=10000):
        """Advance the clock to each next due time until no job is left."""
        produced = []
        steps = 0
        while self._jobs:
            steps += 1
            if steps > max_steps:
                raise SchedulerError("scheduler did not become idle")
            produced.extend(self.run_due())
            upcoming = self.next_run_time()
            if upcoming is not None and upcoming > self.clock.now():
                self.clock.set(upcoming)
        return produced

    def _run(self, job):
        if self.limiter is not None and job.rate_key is not None:
            decision = self.limiter.check("scheduler", job.rate_key)
            if not decision.allowed:
                job.run_at = self.clock.now() + decision.retry_after
                return None
        job.attempts += 1
        try:
            value = job.fn()
        except Exception as exc:  # noqa: BLE001 - jobs may raise anything
            if job.retries_left > 1:
                job.retries_left -= 1
                job.retries_done += 1
                job.run_at = self.clock.now() + job.backoff.delay(job.retries_done)
                return None
            self._jobs.remove(job)
            return JobResult(job.name, False, job.attempts, None, type(exc).__name__, self.clock.now())
        self._jobs.remove(job)
        return JobResult(job.name, True, job.attempts, value, None, self.clock.now())
