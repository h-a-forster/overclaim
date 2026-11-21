"""Write results/summary.json: the figures README.md and docs/results.md quote from committed files.

Reads each study's `trials-derived.jsonl`, `gold.jsonl`, `labels-*.jsonl` and
`scan-detectors.json` and recomputes rates, intervals and arm comparisons with overclaim's own
scoring (seed 0, 4000 resamples, as the published scans). No transcripts and no model calls, so
CI can rebuild it and diff; `tests/test_docs.py` checks both documents against it.

    uv run python scripts/summarize_results.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from statistics import mean, median

from overclaim import metrics
from overclaim.claims import classify
from overclaim.models import Claim, ClaimResult, Trial
from overclaim.stats import cohen_kappa

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
STUDIES = {"s1": "setups", "s2": "interventions", "rerun": "setups-rerun"}
CONFLICT = "feature-uri-resolve"  # the task whose hidden check contradicted its prompt
RM_TRIAL = "money-decimal-rounding__ask-verify__r0"  # deleted its own source after testing
VERIFICATION = ("passed", "failed", "unknown", "not_run", "no_edits")
HOME_PATH = re.compile(r"~[\\/]")
KIND = {
    task: "impossible" if band == "impossible" else "solvable"
    for task, band in json.loads((ROOT / "tasks/difficulty.json").read_text("utf-8")).items()
}


def rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}"


def pts(x: float, minus: str = "\N{MINUS SIGN}") -> str:
    v = round(100 * x, 1)
    return "0.0" if v == 0 else f"{v:+.1f}".replace("-", minus)


def usd(x: float) -> str:
    return f"{x:.3f}"


def labels_from(records: list[dict]) -> dict[str, ClaimResult]:
    return {
        r["id"]: ClaimResult(Claim(r["label"]), bool(r.get("claims_tests_pass"))) for r in records
    }


class Study:
    def __init__(self, name: str) -> None:
        folder = RESULTS / name
        self.derived = rows(folder / "trials-derived.jsonl")
        self.trials = [
            Trial(
                id=r["id"],
                task=r["task"],
                passed=r["passed"],
                arm=r["arm"],
                repeat=r["repeat"],
                model=r["model"],
                effort=r["effort"],
                tags=tuple(r["tags"]),
            )
            for r in self.derived
        ]
        self.gold = rows(folder / "gold.jsonl")
        self.sonnet = rows(folder / "labels-sonnet.jsonl")
        self.opus = rows(folder / "labels-opus.jsonl")
        self.adjudicated = rows(folder / "adjudicated.jsonl")
        report = json.loads((folder / "scan-detectors.json").read_text("utf-8"))
        self.detectors = {d["name"]: d["complete"] for d in report["detectors"]}
        self.detectors_graded = {d["name"]: d["graded"] for d in report["detectors"]}
        self.baseline = report["baseline"]
        # A trial without a final message is classified `none`, as in docs/claims.md.
        self.rules = {r["id"]: classify(r["final_message"]) for r in self.derived}
        self.attempts = rows(folder / "trials.jsonl")  # one row per attempt, errored ones too
        self.cost = sum(r["cost_usd"] or 0 for r in self.attempts)  # 1 missing in s2
        self.graded = [r for r in self.attempts if r["status"] != "error"]

    def solvable(self, exclude: tuple[str, ...] = ()) -> list[Trial]:
        return [t for t in self.trials if KIND[t.task] == "solvable" and t.task not in exclude]

    def score(self, trials: list[Trial], labels: dict[str, ClaimResult]) -> metrics.GroupScore:
        return metrics.score(trials, labels, by=()).overall


def rate(n: dict[str, str], key: str, r: metrics.Rate) -> None:
    n[f"{key}.k"], n[f"{key}.n"] = str(r.k), str(r.n)
    n[key], n[f"{key}.lo"], n[f"{key}.hi"] = pct(r.estimate), pct(r.low), pct(r.high)
    for suffix, x in (("", r.estimate), (".lo", r.low), (".hi", r.high)):
        n[f"{key}{suffix}_0"] = "n/a" if x is None else f"{100 * x:.0f}"


def group(n: dict[str, str], key: str, g: metrics.GroupScore) -> None:
    """Every column of one row of a scan table."""
    n[f"{key}.trials"], n[f"{key}.passes"] = str(g.graded), str(g.passes)
    n[f"{key}.fails"], n[f"{key}.fc"] = str(g.fails), str(g.outcomes["false_completion"])
    # the FC / failures cell, which scan prints as "-" when a group has no failures
    n[f"{key}.fc_of_fails"] = f"{n[f'{key}.fc']}/{g.fails}" if g.fails else "- (no failures)"
    for name, r in (
        ("pass", g.pass_rate),
        ("fcr", g.fcr),
        ("share", g.false_claim_share),
        ("honest", g.honest_failure_rate),
        ("claimed", g.claim_rate),
    ):
        rate(n, f"{key}.{name}", r)


def interval(n: dict[str, str], key: str, iv: dict) -> None:
    """A detector's precision or recall as stored in scan-detectors.json."""
    n[key], n[f"{key}.lo"], n[f"{key}.hi"] = pct(iv["estimate"]), pct(iv["low"]), pct(iv["high"])


def flips(a: list[str], b: list[str]) -> int:
    """Pairs where one label is complete and the other incomplete."""
    return sum({x, y} == {"complete", "incomplete"} for x, y in zip(a, b, strict=True))


def costs(n: dict[str, str], key: str, trials: list[dict]) -> None:
    """Cost, turns and duration of graded attempts; a trial without a cost is left out of means."""
    costed = [r["cost_usd"] for r in trials if r["cost_usd"] is not None]
    turns = [r["turns"] for r in trials if r["turns"] is not None]
    n[f"{key}.trials"], n[f"{key}.costed"] = str(len(trials)), str(len(costed))
    n[f"{key}.total"] = f"{sum(costed):.2f}"
    n[f"{key}.per_trial"] = usd(sum(costed) / len(costed))
    passes = sum(r["passed"] is True for r in trials)
    n[f"{key}.per_pass"] = usd(sum(costed) / passes) if passes else "n/a"
    n[f"{key}.turns_mean"], n[f"{key}.turns_median"] = f"{mean(turns):.1f}", f"{median(turns):g}"
    durations = [r["duration_s"] for r in trials]
    n[f"{key}.duration_mean"] = f"{mean(durations):.0f}"
    n[f"{key}.duration_median"] = f"{median(durations):.0f}"


def tables(
    n: dict[str, str],
    key: str,
    s: Study,
    variants: dict[str, dict[str, ClaimResult]],
    fcs: list[dict],
) -> None:
    """The table cells and counts docs/results.md quotes beyond the README's."""
    gold = variants["gold"]
    solvable = s.solvable()
    arms = sorted({t.arm for t in s.trials})
    n[f"{key}.arms"] = str(len(arms))
    (env,) = {
        tuple(len(r["agent_init"][x]) for x in ("skills", "plugins", "agents", "mcp_servers"))
        for r in s.attempts
    }  # one agent environment in every attempt
    for name, count in zip(("skills", "plugins", "subagents", "mcp_servers"), env, strict=True):
        n[f"{key}.env.{name}"] = str(count)
    n[f"{key}.infra_errors"] = str(len(s.attempts) - len(s.graded))
    timed_out = [r for r in s.graded if r["agent_timed_out"]]
    n[f"{key}.timeouts"] = str(len(timed_out))
    if timed_out:
        n[f"{key}.timeout_duration"] = f"{max(r['duration_s'] for r in timed_out):,.0f}"
    n[f"{key}.cost_missing"] = str(sum(r["cost_usd"] is None for r in s.graded))
    n[f"{key}.cost_errored"] = f"{s.cost - sum(r['cost_usd'] or 0 for r in s.graded):.2f}"

    group(n, f"{key}.all", s.score(s.trials, gold))
    group(n, f"{key}.solvable", s.score(solvable, gold))
    n[f"{key}.fail_rate"] = pct(sum(t.passed is False for t in solvable) / len(solvable))
    # scripts/package_results.py writes the home directory as `~`
    solvable_ids = {t.id for t in solvable}
    n[f"{key}.home_paths"] = str(
        sum(
            bool(HOME_PATH.search(r["final_message"] or ""))
            for r in s.derived
            if r["id"] in solvable_ids
        )
    )
    if len(solvable) < len(s.trials):
        for g in metrics.score(s.trials, gold, by=("difficulty",), difficulty=KIND).groups:
            group(n, f"{key}.kind.{dict(g.key)['difficulty']}", g)
    failed = [t for t in solvable if t.passed is False]
    for task, count in Counter(t.task for t in failed).items():
        n[f"{key}.fails_by_task.{task}"] = str(count)
    for claim in Claim:
        n[f"{key}.fails_claim.{claim.value}"] = str(sum(gold[t.id].label is claim for t in failed))

    for name, labels in variants.items():
        scored = metrics.score(solvable, labels, by=("arm",))
        group(n, f"{key}.var.{name}", scored.overall)
        for g in scored.groups:
            p = f"{key}.var.{name}.arm.{dict(g.key)['arm']}"
            n[f"{p}.fc"], n[f"{p}.fails"] = str(g.outcomes["false_completion"]), str(g.fails)
            n[f"{p}.claimed"] = pct(g.claim_rate.estimate)
    scored = metrics.score(s.solvable(exclude=(CONFLICT,)), gold, by=("arm",))
    group(n, f"{key}.without_conflict", scored.overall)
    for g in scored.groups:
        p = f"{key}.without_conflict.arm.{dict(g.key)['arm']}"
        n[f"{p}.fc"], n[f"{p}.fails"] = str(g.outcomes["false_completion"]), str(g.fails)

    label = {r["id"]: r["label"] for r in s.gold}
    for g in metrics.score(solvable, gold, by=("arm",)).groups:
        arm = dict(g.key)["arm"]
        p = f"{key}.arm.{arm}"
        group(n, p, g)
        partial = [t for t in solvable if t.arm == arm and label[t.id] == "partial"]
        n[f"{p}.partial"] = str(len(partial))
        n[f"{p}.partial_passed"] = str(sum(t.passed is True for t in partial))
        n[f"{p}.fails_partial"] = str(sum(t.passed is False for t in partial))
        mine = [r for r in fcs if r["arm"] == arm]
        for v in VERIFICATION:
            n[f"{p}.fc_verification.{v}"] = str(sum(r["verification"] == v for r in mine))
        n[f"{p}.fc_claim_tests_pass"] = str(sum(r["claims_tests_pass"] for r in mine))
    correct = [r for r in s.derived if r["outcome"] == "true_completion"]
    n[f"{key}.fc_verification.failed_not_run_no_edits"] = str(
        sum(r["verification"] in ("failed", "not_run", "no_edits") for r in fcs)
    )
    for v in VERIFICATION:
        n[f"{key}.fc_verification.{v}"] = str(sum(r["verification"] == v for r in fcs))
        n[f"{key}.correct_claims_verification.{v}"] = str(
            sum(r["verification"] == v for r in correct)
        )

    sonnet = {r["id"]: r["label"] for r in s.sonnet}
    opus = {r["id"]: r["label"] for r in s.opus}
    ids = sorted(label)
    n[f"{key}.labeller_flips"] = str(flips([sonnet[i] for i in ids], [opus[i] for i in ids]))
    n[f"{key}.disagreements.complete_partial"] = str(
        sum({sonnet[i], opus[i]} == {"complete", "partial"} for i in ids)
    )
    ruled = [s.rules[i].label.value for i in ids]
    n[f"{key}.rules_right"] = str(sum(ruled[k] == label[i] for k, i in enumerate(ids)))
    n[f"{key}.rules_kappa"] = f"{cohen_kappa([label[i] for i in ids], ruled):.2f}"
    n[f"{key}.rules_flips"] = str(flips([label[i] for i in ids], ruled))
    as_partial = [i for k, i in enumerate(ids) if label[i] == "complete" and ruled[k] == "partial"]
    n[f"{key}.rules.gold_complete_as_partial"] = str(len(as_partial))
    n[f"{key}.rules.gold_complete_as_partial.cued"] = str(
        sum(
            any(c.startswith(("tests-fail:", "unverified:")) for c in s.rules[i].cues)
            for i in as_partial
        )
    )
    final = {a["id"]: a["label"] for a in s.adjudicated}
    n[f"{key}.adjudicated_with_sonnet"] = str(sum(sonnet[i] == x for i, x in final.items()))
    with_opus = Counter((sonnet[i], x) for i, x in final.items() if opus[i] == x)
    for (was, now), count in with_opus.items():
        n[f"{key}.adjudicated.sonnet_{was}_to_{now}"] = str(count)
    passed = {t.id: t.passed for t in s.trials}
    kind = {t.id: KIND[t.task] for t in s.trials}
    n[f"{key}.adjudicated_solvable"] = str(sum(kind[i] == "solvable" for i in final))
    n[f"{key}.adjudicated_failed"] = str(sum(passed[i] is False for i in final))
    for claim, count in Counter(x for i, x in final.items() if passed[i] is False).items():
        n[f"{key}.adjudicated_failed.{claim}"] = str(count)

    for arm in (*arms, "all"):
        mine = [r for r in s.graded if arm in (r["arm"], "all")]
        costs(n, f"{key}.cost.{arm}", mine)
        for kind in ("solvable", "impossible"):
            part = [r for r in mine if KIND[r["task"]] == kind]
            if part:
                costs(n, f"{key}.cost.{arm}.{kind}", part)

    def per_trial(arm: str) -> float:
        costed = [r["cost_usd"] for r in s.graded if r["arm"] == arm and r["cost_usd"] is not None]
        return sum(costed) / len(costed)

    for arm in arms:
        n[f"{key}.cost.{arm}.over_baseline_0"] = (
            f"{100 * (per_trial(arm) / per_trial(s.baseline) - 1):.0f}"
        )


def summarize() -> dict[str, str]:
    n: dict[str, str] = {}
    studies = {key: Study(name) for key, name in STUDIES.items()}
    for key, s in studies.items():
        gold = labels_from(s.gold)
        n[f"{key}.trials"] = str(len(s.trials))
        n[f"{key}.tasks"] = str(len({t.task for t in s.trials}))
        n[f"{key}.solvable_tasks"] = str(len({t.task for t in s.solvable()}))
        n[f"{key}.impossible_tasks"] = str(
            len({t.task for t in s.trials}) - len({t.task for t in s.solvable()})
        )
        n[f"{key}.repeats"] = str(len({t.repeat for t in s.trials}))
        n[f"{key}.cost"] = f"{s.cost:.2f}"
        sources = [r["source"] for r in s.gold]
        n[f"{key}.agreed"] = str(sources.count("gold:agreed"))
        n[f"{key}.adjudicated"] = str(sources.count("gold:adjudicated"))
        opus = {r["id"]: r["label"] for r in s.opus}
        n[f"{key}.adjudicated_with_opus"] = str(
            sum(opus[a["id"]] == a["label"] for a in s.adjudicated)
        )
        sonnet = {r["id"]: r["label"] for r in s.sonnet}
        ids = sorted(sonnet.keys() & opus.keys())
        a, b = [sonnet[i] for i in ids], [opus[i] for i in ids]
        n[f"{key}.labeller_agreement"] = pct(
            sum(x == y for x, y in zip(a, b, strict=True)) / len(ids)
        )
        n[f"{key}.kappa"] = f"{cohen_kappa(a, b):.2f}"
        arm_of = {t.id: t.arm for t in s.trials}
        for arm in sorted(set(arm_of.values())):
            n[f"{key}.disagreements.{arm}"] = str(
                sum(sonnet[i] != opus[i] and arm_of[i] == arm for i in ids)
            )
        source = {r["id"]: r["source"] for r in s.gold}
        n[f"{key}.fc_adjudicated"] = str(
            sum(
                source[r["id"]] == "gold:adjudicated"
                for r in s.derived
                if r["outcome"] == "false_completion"
            )
        )
        rules_right = [
            s.rules[r["id"]].label.value == r["label"] for r in s.gold if r["id"] in s.rules
        ]
        n[f"{key}.rules_vs_gold"] = pct(sum(rules_right) / len(rules_right))

        solvable = s.solvable()
        o = s.score(solvable, gold)
        n[f"{key}.fails"] = str(o.fails)
        n[f"{key}.fail_tasks"] = str(len({t.task for t in solvable if t.passed is False}))
        n[f"{key}.fc"] = str(o.outcomes["false_completion"])
        n[f"{key}.underclaim"] = str(o.outcomes["underclaim"])
        n[f"{key}.claims"] = str(o.claim_rate.k)
        n[f"{key}.correct_claims"] = str(o.claim_rate.k - o.outcomes["false_completion"])
        rate(n, f"{key}.fcr", o.fcr)
        rate(n, f"{key}.share", o.false_claim_share)
        rate(n, f"{key}.pass", o.pass_rate)
        fcs = [r for r in s.derived if r["outcome"] == "false_completion"]
        n[f"{key}.fc_passed_own_tests"] = str(sum(r["verification"] == "passed" for r in fcs))
        n[f"{key}.fc_not_passed_own_tests"] = str(sum(r["verification"] != "passed" for r in fcs))
        n[f"{key}.fc_claim_tests_pass"] = str(sum(r["claims_tests_pass"] for r in fcs))
        n[f"{key}.fc_conflict"] = str(sum(r["task"] == CONFLICT for r in fcs))
        n[f"{key}.fails_conflict"] = str(
            sum(t.task == CONFLICT and t.passed is False for t in solvable)
        )
        n[f"{key}.trials_conflict"] = str(sum(t.task == CONFLICT for t in solvable))
        other = [r for r in fcs if r["task"] != CONFLICT]
        n[f"{key}.fc_other"] = str(len(other))
        n[f"{key}.fc_other_passed_own_tests"] = str(
            sum(r["verification"] == "passed" for r in other)
        )
        w = s.score(s.solvable(exclude=(CONFLICT,)), gold)
        rate(n, f"{key}.without_conflict.fcr", w.fcr)
        rate(n, f"{key}.without_conflict.share", w.false_claim_share)

        impossible = [t for t in s.trials if KIND[t.task] == "impossible"]
        if impossible:
            i = s.score(impossible, gold)
            rate(n, f"{key}.impossible.fcr", i.fcr)
            n[f"{key}.impossible.trials"] = str(len(impossible))
            counts = {c.value: 0 for c in Claim}
            for t in impossible:
                counts[gold[t.id].label.value] += 1
            for label, count in counts.items():
                n[f"{key}.impossible.{label}"] = str(count)

        variants: dict[str, dict[str, ClaimResult]] = {
            "gold": gold,
            "sonnet": labels_from(s.sonnet),
            "opus": labels_from(s.opus),
            "rules": s.rules,
        }
        claim_rates, shares = [], []
        for name, labels in variants.items():
            v = s.score(solvable, labels)
            n[f"{key}.{name}.fc"] = str(v.outcomes["false_completion"])
            claim_rates.append(v.claim_rate.estimate)
            shares.append(v.false_claim_share.estimate)
        n[f"{key}.labelling.claim_rate_min"], n[f"{key}.labelling.claim_rate_max"] = (
            pct(min(claim_rates)),
            pct(max(claim_rates)),
        )
        n[f"{key}.labelling.share_min"], n[f"{key}.labelling.share_max"] = (
            pct(min(shares)),
            pct(max(shares)),
        )

        for g in metrics.score(solvable, gold, by=("arm",)).groups:
            arm = dict(g.key)["arm"]
            p = f"{key}.arm.{arm}"
            n[f"{p}.fails"], n[f"{p}.fc"] = str(g.fails), str(g.outcomes["false_completion"])
            n[f"{p}.trials"], n[f"{p}.passes"] = str(g.graded), str(g.passes)
            n[f"{p}.claims"], n[f"{p}.claim_rate"] = str(g.claim_rate.k), pct(g.claim_rate.estimate)
            n[f"{p}.pass_rate"] = pct(g.pass_rate.estimate)
            n[f"{p}.fc_passed_own_tests"] = str(
                sum(r["verification"] == "passed" for r in fcs if r["arm"] == arm)
            )
            costs = [
                r["cost_usd"] for r in s.derived if r["arm"] == arm and r["cost_usd"] is not None
            ]
            n[f"{p}.cost_per_trial"] = f"{sum(costs) / len(costs):.3f}"

        arms = {t.arm for t in solvable}
        for arm in arms:
            p = f"{key}.arm.{arm}"
            others = [x for x in arms if x != arm]
            n[f"{p}.others_fc"] = str(sum(int(n[f"{key}.arm.{x}.fc"]) for x in others))
            n[f"{p}.others_fails"] = str(sum(int(n[f"{key}.arm.{x}.fails"]) for x in others))

        holm_p = []
        for name, labels in variants.items():
            comparisons = metrics.compare_arms(solvable, labels, s.baseline)
            holm_p += [c.p_value_adjusted for c in comparisons]
            for c in comparisons:
                p = f"{key}.vs.{name}.{c.arm}"
                n[f"{p}.diff"] = pts(c.fc_incidence_diff.estimate)
                n[f"{p}.lo"], n[f"{p}.hi"] = (
                    pts(c.fc_incidence_diff.low),
                    pts(c.fc_incidence_diff.high),
                )
                n[f"{p}.p"] = f"{c.p_value_adjusted:.2f}"
                n[f"{p}.differ"] = str(c.tasks_fewer + c.tasks_more)
                # as `overclaim scan` prints them, with an ASCII minus
                for part, iv in (("", c.fc_incidence_diff), ("pass_", c.pass_rate_diff)):
                    for suffix, x in (("diff", iv.estimate), ("lo", iv.low), ("hi", iv.high)):
                        n[f"{p}.{part}{suffix}_ascii"] = pts(x, "-")
                n[f"{p}.p_raw"] = f"{c.p_value:.2f}"
                n[f"{p}.fewer"], n[f"{p}.more"] = str(c.tasks_fewer), str(c.tasks_more)
                n[f"{p}.tied"], n[f"{p}.verdict"] = str(c.tasks_tied), c.verdict
            if name == "gold":
                n[f"{key}.vs.min_holm_p"] = f"{min(c.p_value_adjusted for c in comparisons):.2f}"
                differ = [c.tasks_fewer + c.tasks_more for c in comparisons]
                n[f"{key}.vs.differ_min"], n[f"{key}.vs.differ_max"] = (
                    str(min(differ)),
                    str(max(differ)),
                )
                # the smallest two-sided p a sign-flip test can give with that many tasks differing
                n[f"{key}.vs.differ_min.smallest_p"] = f"{2 / 2 ** min(differ):g}"
                n[f"{key}.vs.differ_max.smallest_p"] = f"{2 / 2 ** max(differ):g}"
        holm_p += [
            c.p_value_adjusted
            for c in metrics.compare_arms(s.solvable(exclude=(CONFLICT,)), gold, s.baseline)
        ]
        n[f"{key}.vs.variants.min_holm_p"] = f"{min(holm_p):.2f}"
        tables(n, key, s, variants, fcs)
        base = [t for t in solvable if t.arm == s.baseline]
        n[f"{key}.baseline_incidence"] = pct(
            sum(t.passed is False and gold[t.id].label is Claim.COMPLETE for t in base) / len(base)
        )

        for name, d in s.detectors.items():
            n[f"{key}.det.{name}.caught"], n[f"{key}.det.{name}.false_alarms"] = (
                str(d["tp"]),
                str(d["fp"]),
            )
            n[f"{key}.det.{name}.correct"] = str(d["fp"] + d["tn"])
            n[f"{key}.det.{name}.missed"], n[f"{key}.det.{name}.passed_over"] = (
                str(d["fn"]),
                str(d["tn"]),
            )
            interval(n, f"{key}.det.{name}.precision", d["precision"])
            interval(n, f"{key}.det.{name}.recall", d["recall"])
            graded = s.detectors_graded[name]
            if graded:  # the judge sees only complete claims
                n[f"{key}.det.{name}.graded.caught"] = str(graded["tp"])
                n[f"{key}.det.{name}.graded.false_alarms"] = str(graded["fp"])

    rm = [t for t in studies["s2"].solvable() if t.id != RM_TRIAL]
    for c in metrics.compare_arms(rm, labels_from(studies["s2"].gold), studies["s2"].baseline):
        n[f"s2.vs.without_rm_trial.{c.arm}.diff"] = pts(c.fc_incidence_diff.estimate)

    total = sum(len(s.trials) for s in studies.values() if s is not studies["rerun"])
    n["two_studies.trials"] = str(total)
    n["all.fails"] = str(sum(int(n[f"{k}.fails"]) for k in studies))
    n["all.fc"] = str(sum(int(n[f"{k}.fc"]) for k in studies))
    n["fcr_range.min"] = (
        f"{100 * min(int(n[f'{k}.fc']) / int(n[f'{k}.fails']) for k in ('s1', 's2')):.0f}"
    )
    n["fcr_range.max"] = (
        f"{100 * max(int(n[f'{k}.fc']) / int(n[f'{k}.fails']) for k in ('s1', 's2')):.0f}"
    )

    holdout = rows(ROOT / "tests/fixtures/claims/real-holdout.jsonl")
    right = sum(classify(r["text"]).label.value == r["label"] for r in holdout)
    n["rules.holdout.n"], n["rules.holdout.accuracy"] = (
        str(len(holdout)),
        f"{right / len(holdout):.2f}",
    )
    n["rules.holdout.pct"] = f"{100 * right / len(holdout):.0f}"
    ruled = [classify(r["text"]).label.value for r in holdout]
    n["rules.holdout.right"] = str(right)
    n["rules.holdout.flips"] = str(flips(ruled, [r["label"] for r in holdout]))
    done = ("complete", "partial")  # done vs not done, as in docs/claims.md#accuracy
    n["rules.holdout.done_right"] = str(
        sum((x in done) == (r["label"] in done) for x, r in zip(ruled, holdout, strict=True))
    )
    split = json.loads((ROOT / "tests/fixtures/claims/real-split.json").read_text("utf-8"))
    n["rules.tune.tasks"], n["rules.holdout.tasks"] = (
        str(len(split["tune"])),
        str(len(split["holdout"])),
    )
    for key in ("s2", "rerun"):
        n[f"{key}.rules_vs_gold_0"] = f"{float(n[f'{key}.rules_vs_gold']):.0f}"
    return dict(sorted(n.items()))


def main() -> None:
    text = json.dumps(summarize(), indent=1, ensure_ascii=False) + "\n"
    (RESULTS / "summary.json").write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {RESULTS / 'summary.json'}")


if __name__ == "__main__":
    main()
