"""Interval estimates and paired tests. Stdlib only; deterministic for a given seed.

Tasks are the unit of replication: repeats of one task share its prompt, repository and hidden
check, so their outcomes are correlated. Rates pooled over trials therefore get a cluster
bootstrap that resamples whole tasks, and arm comparisons pair arms by task (as agent-ab does).
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass
from statistics import NormalDist, fmean
from typing import TypeVar

__all__ = [
    "Interval",
    "bootstrap_mean",
    "cluster_bootstrap",
    "cohen_kappa",
    "holm",
    "paired_permutation",
    "ratio_bootstrap",
    "rng_for",
    "wilson",
    "wilson_deff",
]

T = TypeVar("T")
Seed = int | str

# Exact enumeration of 2**16 sign patterns is cheap; beyond that, Monte Carlo.
_EXACT_MAX_NONZERO = 16
# Float noise in summation order must never exclude the observed pattern from the count.
_TIE_TOL = 1e-12


@dataclass(frozen=True, slots=True)
class Interval:
    """A point estimate with optional bounds; None means undefined or not computed."""

    estimate: float | None
    low: float | None = None
    high: float | None = None


def rng_for(seed: Seed, purpose: str) -> random.Random:
    """A named random stream, so one statistic's draws never depend on another's."""
    return random.Random(f"overclaim:{seed}:{purpose}")


def _z(alpha: float) -> float:
    return NormalDist().inv_cdf(1 - alpha / 2)


def wilson(k: float, n: float, alpha: float = 0.05) -> tuple[float, float]:
    """Wilson score interval for ``k / n``. With ``n == 0`` nothing is known: (0, 1).

    Non-integer counts are allowed, for effective sample sizes.
    """
    if n < 0 or k < 0 or k > n + 1e-9:
        raise ValueError(f"invalid binomial counts k={k}, n={n}")
    if n == 0:
        return (0.0, 1.0)
    z = _z(alpha)
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    low = 0.0 if k == 0 else max(0.0, center - half)
    high = 1.0 if k == n else min(1.0, center + half)
    return (low, high)


def design_effect(clusters: Sequence[tuple[float, float]]) -> float | None:
    """Design effect of the pooled ratio ``sum(k) / sum(n)`` over clusters of (k, n).

    The ratio's linearised between-cluster variance, ``T/(T-1) * sum((k_t - p n_t)^2) / N^2``,
    divided by the binomial variance ``p (1 - p) / N``, floored at 1. None when not estimable:
    fewer than two non-empty clusters, or p of 0 or 1. Clusters of one trial carry no
    clustering, so a sample of singletons has a design effect of exactly 1.
    """
    used = [(float(k), float(n)) for k, n in clusters if n > 0]
    big_n = math.fsum(n for _, n in used)
    if len(used) < 2 or big_n == 0:
        return None
    if all(n == 1 for _, n in used):
        return 1.0
    p = math.fsum(k for k, _ in used) / big_n
    if p <= 0 or p >= 1:
        return None
    t = len(used)
    var_ratio = t / (t - 1) * math.fsum((k - p * n) ** 2 for k, n in used) / big_n**2
    return max(1.0, var_ratio / (p * (1 - p) / big_n))


def wilson_deff(
    clusters: Sequence[tuple[float, float]], alpha: float = 0.05
) -> tuple[float, float, float]:
    """Wilson interval on cluster-adjusted counts: (low, high, n_eff).

    ``n_eff = N / deff``; when the design effect is not estimable (see ``design_effect``),
    ``n_eff`` is the number of non-empty clusters, i.e. each task counts once. Unlike a
    percentile bootstrap this never collapses to a point at 0% or 100%.
    """
    used = [(float(k), float(n)) for k, n in clusters if n > 0]
    big_n = math.fsum(n for _, n in used)
    if big_n == 0:
        return 0.0, 1.0, 0.0
    p = math.fsum(k for k, _ in used) / big_n
    deff = design_effect(used)
    n_eff = big_n / deff if deff is not None else min(float(len(used)), big_n)
    low, high = wilson(p * n_eff, n_eff, alpha)
    return low, high, n_eff


def _quantile(sorted_values: Sequence[float], q: float) -> float:
    """Linear-interpolation quantile (type 7)."""
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    pos = q * (n - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, n - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def cluster_bootstrap(
    clusters: Sequence[T],
    stat: Callable[[Sequence[T]], float | None],
    *,
    n: int = 4000,
    alpha: float = 0.05,
    seed: Seed = 0,
    purpose: str = "",
) -> tuple[Interval, float]:
    """Percentile bootstrap that resamples whole clusters with replacement.

    ``stat`` maps a list of clusters to a value, or None when undefined (e.g. a zero
    denominator); undefined resamples are skipped. Returns the interval and the fraction of
    resamples skipped. With fewer than two clusters every resample is identical, so the bounds
    are None rather than a misleading zero-width interval.
    """
    items = list(clusters)
    estimate = stat(items) if items else None
    if estimate is None or len(items) < 2 or n <= 0:
        return Interval(estimate), 0.0
    r = rng_for(seed, purpose)
    k = len(items)
    values: list[float] = []
    for _ in range(n):
        v = stat(r.choices(items, k=k))
        if v is not None:
            values.append(v)
    skipped = (n - len(values)) / n
    if not values:
        return Interval(estimate), skipped
    values.sort()
    return Interval(
        estimate, _quantile(values, alpha / 2), _quantile(values, 1 - alpha / 2)
    ), skipped


def _ratio(pairs: Sequence[tuple[float, float]]) -> float | None:
    den = math.fsum(d for _, d in pairs)
    return None if den == 0 else math.fsum(k for k, _ in pairs) / den


def ratio_bootstrap(
    pairs: Sequence[tuple[float, float]],
    *,
    n: int = 4000,
    alpha: float = 0.05,
    seed: Seed = 0,
    purpose: str = "",
) -> tuple[Interval, float]:
    """CI for ``sum(num) / sum(den)`` over clusters given as (num, den) pairs, e.g. FCR."""
    return cluster_bootstrap(pairs, _ratio, n=n, alpha=alpha, seed=seed, purpose=purpose)


def bootstrap_mean(
    values: Sequence[float],
    *,
    n: int = 4000,
    alpha: float = 0.05,
    seed: Seed = 0,
    purpose: str = "",
) -> Interval:
    """Percentile bootstrap CI for a mean (e.g. of per-task paired differences)."""
    vals = [float(v) for v in values]
    if not vals:
        return Interval(None)
    return cluster_bootstrap(
        vals, lambda xs: fmean(xs), n=n, alpha=alpha, seed=seed, purpose=purpose
    )[0]


def paired_permutation(
    diffs: Sequence[float], *, n: int = 20000, seed: Seed = 0, purpose: str = ""
) -> float | None:
    """Two-sided sign-flip permutation p-value for mean(diffs) == 0.

    Under the null each per-task difference is equally likely to have either sign. Exact when
    at most 16 differences are non-zero; otherwise Monte Carlo with ``(hits + 1) / (n + 1)``.
    All-zero input gives 1.0; empty input gives None.
    """
    vals = [float(d) for d in diffs]
    if not vals:
        return None
    nonzero = [d for d in vals if d != 0]
    if not nonzero:
        return 1.0
    observed = abs(math.fsum(nonzero)) - _TIE_TOL
    if len(nonzero) <= _EXACT_MAX_NONZERO:
        sums = [0.0]
        for d in nonzero:
            sums = [s + d for s in sums] + [s - d for s in sums]
        return sum(1 for s in sums if abs(s) >= observed) / len(sums)
    r = rng_for(seed, purpose)
    hits = 0
    for _ in range(n):
        if abs(math.fsum(d if r.random() < 0.5 else -d for d in nonzero)) >= observed:
            hits += 1
    return (hits + 1) / (n + 1)


def holm(pvalues: Sequence[float | None]) -> list[float | None]:
    """Holm step-down adjustment; None entries pass through and do not count toward m."""
    present = [(p, i) for i, p in enumerate(pvalues) if p is not None and not math.isnan(p)]
    out: list[float | None] = [None] * len(pvalues)
    m = len(present)
    running = 0.0
    for rank, (p, i) in enumerate(sorted(present)):
        running = max(running, min(1.0, (m - rank) * p))
        out[i] = running
    return out


def cohen_kappa(a: Sequence[Hashable], b: Sequence[Hashable]) -> float | None:
    """Cohen's kappa between two labelings of the same items; None when undefined."""
    if len(a) != len(b):
        raise ValueError("label sequences must have equal length")
    n = len(a)
    if n == 0:
        return None
    observed = sum(1 for x, y in zip(a, b, strict=True) if x == y) / n
    cats = set(a) | set(b)
    expected = sum((list(a).count(c) / n) * (list(b).count(c) / n) for c in cats)
    if expected >= 1:
        # Both raters used one identical category throughout: agreement is not informative.
        return None
    return (observed - expected) / (1 - expected)
