"""Write results/summary.json: every figure the README quotes, from the committed result files.

Reads each study's `trials-derived.jsonl`, `gold.jsonl`, `labels-*.jsonl` and
`scan-detectors.json` and recomputes rates, intervals and arm comparisons with overclaim's own
scoring (seed 0, 4000 resamples, as the published scans). No transcripts and no model calls, so
CI can rebuild it and diff; `tests/test_docs.py` checks the README against it.

    uv run python scripts/summarize_results.py
"""

from __future__ import annotations

import json
from pathlib import Path

from overclaim import metrics
from overclaim.claims import classify
from overclaim.models import Claim, ClaimResult, Trial
from overclaim.stats import cohen_kappa

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
STUDIES = {"s1": "setups", "s2": "interventions", "rerun": "setups-rerun"}
CONFLICT = "feature-uri-resolve"  # the task whose hidden check contradicted its prompt
KIND = {
    task: "impossible" if band == "impossible" else "solvable"
    for task, band in json.loads((ROOT / "tasks/difficulty.json").read_text("utf-8")).items()
}


def rows(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}"


def pts(x: float) -> str:
    v = round(100 * x, 1)
    return "0.0" if v == 0 else f"{v:+.1f}".replace("-", "\N{MINUS SIGN}")


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
        self.detectors = {
            d["name"]: d["complete"]
            for d in json.loads((folder / "scan-detectors.json").read_text("utf-8"))["detectors"]
        }
        self.baseline = json.loads((folder / "scan-detectors.json").read_text("utf-8"))["baseline"]
        # A trial without a final message is classified `none`, as in docs/claims.md.
        self.rules = {r["id"]: classify(r["final_message"]) for r in self.derived}
        self.cost = sum(
            r["cost_usd"] or 0 for r in rows(folder / "trials.jsonl")
        )  # 1 missing in s2

    def solvable(self, exclude: tuple[str, ...] = ()) -> list[Trial]:
        return [t for t in self.trials if KIND[t.task] == "solvable" and t.task not in exclude]

    def score(self, trials: list[Trial], labels: dict[str, ClaimResult]) -> metrics.GroupScore:
        return metrics.score(trials, labels, by=()).overall


def rate(n: dict[str, str], key: str, r: metrics.Rate) -> None:
    n[f"{key}.k"], n[f"{key}.n"] = str(r.k), str(r.n)
    n[key], n[f"{key}.lo"], n[f"{key}.hi"] = pct(r.estimate), pct(r.low), pct(r.high)
    for suffix, x in (("", r.estimate), (".lo", r.low), (".hi", r.high)):
        n[f"{key}{suffix}_0"] = "n/a" if x is None else f"{100 * x:.0f}"


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

        for name, labels in (("gold", gold), ("sonnet", variants["sonnet"])):
            comparisons = metrics.compare_arms(solvable, labels, s.baseline)
            for c in comparisons:
                p = f"{key}.vs.{name}.{c.arm}"
                n[f"{p}.diff"] = pts(c.fc_incidence_diff.estimate)
                n[f"{p}.lo"], n[f"{p}.hi"] = (
                    pts(c.fc_incidence_diff.low),
                    pts(c.fc_incidence_diff.high),
                )
                n[f"{p}.p"] = f"{c.p_value_adjusted:.2f}"
                n[f"{p}.differ"] = str(c.tasks_fewer + c.tasks_more)
            if name == "gold":
                n[f"{key}.vs.min_holm_p"] = f"{min(c.p_value_adjusted for c in comparisons):.2f}"
                differ = [c.tasks_fewer + c.tasks_more for c in comparisons]
                n[f"{key}.vs.differ_min"], n[f"{key}.vs.differ_max"] = (
                    str(min(differ)),
                    str(max(differ)),
                )
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
    for key in ("s2", "rerun"):
        n[f"{key}.rules_vs_gold_0"] = f"{float(n[f'{key}.rules_vs_gold']):.0f}"
    return dict(sorted(n.items()))


def main() -> None:
    text = json.dumps(summarize(), indent=1, ensure_ascii=False) + "\n"
    (RESULTS / "summary.json").write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {RESULTS / 'summary.json'}")


if __name__ == "__main__":
    main()
