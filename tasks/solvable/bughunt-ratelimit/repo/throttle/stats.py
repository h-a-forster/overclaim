"""Small statistics helpers for latency / wait-time samples."""

import math


def percentile(samples, p):
    """Nearest-rank percentile: the smallest sample such that at least ``p`` percent of the
    samples are less than or equal to it.  ``p`` is in (0, 100]."""
    if not samples:
        raise ValueError("no samples")
    if not 0 < p <= 100:
        raise ValueError("p must be in (0, 100]")
    ordered = sorted(samples)
    rank = math.ceil(p / 100.0 * len(ordered))
    return ordered[rank - 1]


def mean(samples):
    if not samples:
        raise ValueError("no samples")
    return sum(samples) / len(samples)


def moving_average(samples, size):
    """Averages of every ``size`` consecutive samples (empty if there are fewer samples)."""
    if size < 1:
        raise ValueError("size must be positive")
    return [sum(samples[i:i + size]) / size for i in range(len(samples) - size + 1)]


class Summary:
    """Min / max / mean and common percentiles of a list of numbers."""

    def __init__(self, samples):
        self.count = len(samples)
        if not samples:
            self.min = self.max = self.mean = self.p50 = self.p90 = self.p99 = None
            return
        self.min = min(samples)
        self.max = max(samples)
        self.mean = mean(samples)
        self.p50 = percentile(samples, 50)
        self.p90 = percentile(samples, 90)
        self.p99 = percentile(samples, 99)

    def as_dict(self):
        return {"count": self.count, "min": self.min, "max": self.max, "mean": self.mean,
                "p50": self.p50, "p90": self.p90, "p99": self.p99}


def waits(results, scheduled_at):
    """Wait time of each finished job: ``finished_at - scheduled_at[name]`` (missing names skipped)."""
    return [r.finished_at - scheduled_at[r.name] for r in results if r.name in scheduled_at]
