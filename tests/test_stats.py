from __future__ import annotations

import math

import pytest

from overclaim.stats import (
    Interval,
    bootstrap_mean,
    cluster_bootstrap,
    cohen_kappa,
    design_effect,
    holm,
    paired_permutation,
    ratio_bootstrap,
    wilson,
    wilson_deff,
)


def test_wilson_reference_values():
    # Values from the closed form with z = 1.959964.
    lo, hi = wilson(5, 10)
    assert lo == pytest.approx(0.236593, abs=1e-5)
    assert hi == pytest.approx(0.763407, abs=1e-5)
    lo, hi = wilson(0, 10)
    assert lo == 0.0
    assert hi == pytest.approx(0.277533, abs=1e-5)
    lo, hi = wilson(10, 10)
    assert lo == pytest.approx(0.722467, abs=1e-5)
    assert hi == 1.0


def test_wilson_alpha_and_edges():
    assert wilson(0, 0) == (0.0, 1.0)
    narrow = wilson(5, 10, alpha=0.2)
    wide = wilson(5, 10, alpha=0.01)
    assert wide[0] < narrow[0] < 0.5 < narrow[1] < wide[1]
    with pytest.raises(ValueError):
        wilson(3, 2)


def test_paired_permutation_exact_hand_computed():
    # 3 positive diffs: 8 sign patterns, |sum| >= 3 only for all-plus and all-minus.
    assert paired_permutation([1, 1, 1]) == 0.25
    # Zeros keep their place; 2 non-zero diffs give 4 patterns, 2 extreme.
    assert paired_permutation([1, 1, 0]) == 0.5
    # Sums of +-0.5 +-1 +-1: only +-2.5 reach |2.5|.
    assert paired_permutation([0.5, 1, 1]) == 0.25
    # Observed mean 0: every pattern is at least as extreme.
    assert paired_permutation([1, -1]) == 1.0
    assert paired_permutation([0, 0]) == 1.0
    assert paired_permutation([]) is None


def test_paired_permutation_monte_carlo_is_seeded_and_valid():
    diffs = [1.0] * 20  # exact p = 2 / 2**20
    p1 = paired_permutation(diffs, n=2000, seed=1)
    p2 = paired_permutation(diffs, n=2000, seed=1)
    assert p1 == p2
    assert 0 < p1 <= 2 / 2001  # (hits + 1) / (n + 1) is never zero


def test_holm_hand_computed():
    # sorted 0.01, 0.03, 0.04 -> 3*0.01, 2*0.03, max(0.06, 1*0.04)
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm([None, 0.02, 0.5]) == [None, pytest.approx(0.04), pytest.approx(0.5)]
    assert holm([0.6, 0.7]) == [1.0, 1.0]
    assert holm([]) == []
    assert holm([math.nan]) == [None]


def test_cohen_kappa_hand_computed():
    a = ["c", "c", "i", "i"]
    b = ["c", "i", "i", "i"]
    # po = 3/4; pe = 0.5*0.25 + 0.5*0.75 = 0.5; kappa = 0.25 / 0.5
    assert cohen_kappa(a, b) == pytest.approx(0.5)
    assert cohen_kappa(a, a) == pytest.approx(1.0)
    assert cohen_kappa(["c", "c"], ["c", "c"]) is None
    assert cohen_kappa([], []) is None
    with pytest.raises(ValueError):
        cohen_kappa(["c"], [])


def test_ratio_bootstrap_two_clusters_percentiles():
    # Clusters (1/2) and (0/2): resamples give 0.5, 0.25 or 0 with prob 1/4, 1/2, 1/4, so the
    # 2.5% and 97.5% percentiles are exactly 0 and 0.5.
    iv, skipped = ratio_bootstrap([(1, 2), (0, 2)], n=4000, seed=3)
    assert iv.estimate == 0.25
    assert (iv.low, iv.high) == (0.0, 0.5)
    assert skipped == 0.0


def test_ratio_bootstrap_skips_zero_denominators():
    iv, skipped = ratio_bootstrap([(0, 0), (1, 1)], n=4000, seed=0)
    assert iv == Interval(1.0, 1.0, 1.0)
    assert 0.2 < skipped < 0.3  # both draws hit the empty cluster with probability 1/4


def test_cluster_bootstrap_edges_and_determinism():
    assert cluster_bootstrap([], lambda xs: 1.0) == (Interval(None), 0.0)
    one, _ = cluster_bootstrap([(1, 2)], lambda xs: 0.5)
    assert one == Interval(0.5)  # one cluster: no interval
    a = ratio_bootstrap([(1, 3), (2, 2), (0, 4), (1, 1)], seed=7, purpose="x")
    b = ratio_bootstrap([(1, 3), (2, 2), (0, 4), (1, 1)], seed=7, purpose="x")
    c = ratio_bootstrap([(1, 3), (2, 2), (0, 4), (1, 1)], seed=8, purpose="x")
    assert a == b
    assert a[0].estimate == pytest.approx(0.4)
    assert a[0].low <= 0.4 <= a[0].high
    assert c[0].estimate == a[0].estimate


def test_bootstrap_mean():
    assert bootstrap_mean([]) == Interval(None)
    assert bootstrap_mean([0.2]) == Interval(0.2)
    assert bootstrap_mean([0.5, 0.5, 0.5]) == Interval(0.5, 0.5, 0.5)
    iv = bootstrap_mean([-1.0, 0.0, 1.0, 0.0], seed=0)
    assert iv.estimate == 0.0
    assert -1.0 <= iv.low < 0 < iv.high <= 1.0


def test_design_effect_hand_computed():
    # p = 3/6; residuals 1, -1, 0; between-task variance 3/2 * 2 / 36 = 1/12; binomial
    # variance 0.25 / 6 = 1/24; deff = 2, n_eff = 3, Wilson(1.5, 3).
    assert design_effect([(2, 2), (0, 2), (1, 2)]) == pytest.approx(2.0)
    lo, hi, n_eff = wilson_deff([(2, 2), (0, 2), (1, 2)])
    assert n_eff == pytest.approx(3.0)
    assert (lo, hi) == pytest.approx((0.125334, 0.874666), abs=1e-5)
    # Homogeneous tasks: deff floored at 1.
    assert design_effect([(1, 2), (1, 2)]) == 1.0
    # Singleton clusters carry no clustering.
    assert design_effect([(1, 1), (0, 1), (1, 1), (1, 1)]) == 1.0
    assert wilson_deff([(1, 1), (0, 1), (1, 1), (1, 1)])[:2] == wilson(3, 4)
    # Not estimable (p = 0, one cluster): n_eff = number of non-empty tasks.
    assert design_effect([(0, 2), (0, 3)]) is None
    assert design_effect([(1, 4)]) is None
    lo, hi, n_eff = wilson_deff([(0, 2), (0, 3), (0, 0)])
    assert (lo, n_eff) == (0.0, 2.0)
    assert hi == pytest.approx(0.657620, abs=1e-5)  # Wilson 0/2
    assert wilson_deff([]) == (0.0, 1.0, 0.0)
