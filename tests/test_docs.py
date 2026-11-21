"""Every number in README.md and CITATION.cff is copied from results/summary.json.

`scripts/summarize_results.py` rebuilds summary.json from the committed result files (no
transcripts, no model calls); CI runs it and fails on any diff. A claim below is a fragment of
the README with `{key}` placeholders. A number that does not come from those files (a version,
a design constant, a figure quoted from another paper, a count read from the transcript
archive) is listed as fixed, and the README says where it comes from.
"""

import json
import re
import subprocess
from pathlib import Path

import pytest
from docnumbers import check

ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "results" / "summary.json"


def ci(key: str) -> str:
    return f"{{{key}}}% [{{{key}.lo}}, {{{key}.hi}}]"


S2_ARMS = ("control", "ask-verify", "stop-hook", "stop-audit")

README = [
    "Two studies with Claude Code, {two_studies.trials} trials",
    "claimed success {fcr_range.min}% to {fcr_range.max}% of the time ("
    "{s1.without_conflict.fcr.k} of {s1.without_conflict.fcr.n} and {s2.without_conflict.fcr.k} "
    "of {s2.without_conflict.fcr.n} without one task",
    "gave {rerun.fcr.k} of {rerun.fcr.n} ({rerun.fcr_0}%, interval {rerun.fcr.lo_0} to "
    "{rerun.fcr.hi}%)",
    "{s1.tasks} tasks, {s1.trials} trials. Study 2",
    "{s2.tasks} tasks, {s2.trials} trials. A",
    "with a fixed hidden check: {rerun.tasks} tasks, {rerun.trials} trials",
    "The rates rest on few failures: {s1.fails} failed solvable runs in study 1, {s2.fails} in "
    "study 2 and {rerun.fails} in the rerun. Of study 2's {s2.fails}, {s2.fails_conflict} come "
    "from one task with a contradictory check, and {s2.fc_conflict} of its {s2.fc} false",
    "({all.fc} of the {all.fails} failed solvable runs across the three",
    "({s1.impossible.fcr.k} of {s1.impossible.fcr.n})",
    "study 1's FCR interval is {s1.fcr.lo_0}% to {s1.fcr.hi_0}%",
    "kappa {s1.kappa} in study 1 and {s2.kappa} in study 2",
    "({s1.underclaim} against {s1.fc} in study 1, {s2.underclaim} against {s2.fc} in study 2, "
    "{rerun.underclaim} against {rerun.fc} in the rerun",
    "{s1.solvable_tasks} solvable and {s1.impossible_tasks} impossible Python tasks, "
    "{s1.repeats} repeats, {s1.trials} trials, ${s1.cost}",
    "Sonnet and Opus agreed on {s1.agreed}; the {s1.adjudicated} disagreements",
    "Only {s1.fails} solvable trials failed",
    "no agent claimed success: {s1.impossible.fcr.k} of {s1.impossible.fcr.n}.** "
    "{s1.impossible.incomplete} messages said the task could not be done as asked, "
    "{s1.impossible.partial} delivered with a named caveat. FCR " + ci("s1.impossible.fcr"),
    "failed runs were reported as done {s1.fcr.k} of {s1.fcr.n} times.** FCR " + ci("s1.fcr"),
    'Of {s1.share.n} "done" messages, {s1.share.k} were wrong: false-claim share ' + ci("s1.share"),
    "Pass rate " + ci("s1.pass"),
    "In {s1.fc_passed_own_tests} of the {s1.fc} false completions",
    "and all {s1.fc_claim_tests_pass} messages said the tests pass",
    "Outside `feature-uri-resolve`, {s1.fc_other_passed_own_tests} of the {s1.fc_other} false "
    "completions had a passing own test run",
    "**Six of the {s1.fc} come from one task",
    "FCR {s1.without_conflict.fcr.k}/{s1.without_conflict.fcr.n} ("
    + ci("s1.without_conflict.fcr")
    + "), false-claim share "
    + ci("s1.without_conflict.share"),
    "edit caught {s1.det.unverified.caught} of {s1.fc}, with {s1.det.unverified.false_alarms} "
    "false alarms among the {s1.det.unverified.correct} correct",
    "caught {s1.det.judge.caught} of {s1.fc} with {s1.det.judge.false_alarms} false alarms",
    "claims check caught {s1.det.ruleproof.caught} of {s1.fc} with "
    "{s1.det.ruleproof.false_alarms}.",
    "It claimed completion in {s1.arm.sonnet-low.claims} of {s1.arm.sonnet-low.trials} solvable "
    "trials while passing {s1.arm.sonnet-low.passes}; its {s1.arm.sonnet-low.fails} failures",
    "claimed completion on every failure ({s1.arm.sonnet-low.others_fc}/"
    "{s1.arm.sonnet-low.others_fails})",
    "(smallest Holm p {s1.vs.min_holm_p})",
    "same ({s1.fc}/{s1.fcr.n}) under every labelling",
    "The claim rate ({s1.labelling.claim_rate_min}% to {s1.labelling.claim_rate_max}%) and the "
    "false-claim share ({s1.labelling.share_min}% to {s1.labelling.share_max}%)",
    "on {s1.labeller_agreement}% of messages (kappa {s1.kappa})",
    "at default effort, {s2.solvable_tasks} solvable tasks",
    "{s2.repeats} repeats, {s2.trials} trials, ${s2.cost}. Gold labels as in study 1 "
    "({s2.agreed} agreed, {s2.adjudicated} adjudicated). Only {s2.fails} trials failed",
    "FCR: "
    + ", ".join(f"`{a}` {{s2.arm.{a}.fc}}/{{s2.arm.{a}.fails}}" for a in S2_ARMS[:3])
    + ", `stop-audit` {s2.arm.stop-audit.fc}/{s2.arm.stop-audit.fails}",
    "false-completion incidence are {s2.vs.gold.ask-verify.diff}, {s2.vs.gold.stop-hook.diff} and "
    "{s2.vs.gold.stop-audit.diff} points, all p = {s2.vs.min_holm_p}",
    "{s2.vs.sonnet.ask-verify.diff} for `ask-verify` and `stop-audit` with Sonnet's labels",
    "All {s2.arm.stop-hook.fc_passed_own_tests} false completions in its arm had a passing own "
    "test run",
    "the pass rate stayed at {s2.arm.stop-audit.pass_rate}% (`control` "
    "{s2.arm.control.pass_rate}%) and {s2.arm.stop-audit.fc} of {s2.arm.stop-audit.fails} "
    "failures",
    "fell from {s2.arm.control.claim_rate}% to {s2.arm.stop-audit.claim_rate}%. Cost per trial "
    "rose from ${s2.arm.control.cost_per_trial} to ${s2.arm.stop-audit.cost_per_trial}",
    "failed all {s2.fails_conflict} trials on the same prompt/check conflict and gave "
    "{s2.fc_conflict} of the {s2.fc} false completions. Without it: {s2.without_conflict.fcr.k} of "
    "{s2.without_conflict.fcr.n}",
    "agreed on {s2.labeller_agreement}% (kappa {s2.kappa}); {s2.disagreements.stop-audit} of the "
    "{s2.adjudicated} disagreements",
    "false-completion count is {s2.gold.fc} with gold or Sonnet labels, {s2.opus.fc} with Opus "
    "labels and {s2.rules.fc} with the rule classifier",
    "study 1's {rerun.solvable_tasks} solvable tasks and four arms again, {rerun.trials} trials, "
    "${rerun.cost}",
    "({rerun.agreed} agreed, {rerun.adjudicated} adjudicated)",
    "{rerun.fcr.k} of {rerun.fcr.n} failures were reported as done: FCR " + ci("rerun.fcr"),
    "against study 1's " + ci("s1.fcr"),
    "The false-claim share was " + ci("rerun.share"),
    "(study 1 without `feature-uri-resolve`: {s1.without_conflict.share}%)",
    "failed {rerun.fails_conflict} of {rerun.trials_conflict} trials instead of "
    "{s1.fails_conflict} of {s1.trials_conflict}",
    "least ({rerun.arm.sonnet-low.claims} of {rerun.arm.sonnet-low.trials}) and gave "
    "{rerun.arm.sonnet-low.fc} of its {rerun.arm.sonnet-low.fails} failures",
    "on all {rerun.arm.haiku-low.fc} of its failures",
    "flagged {rerun.det.unverified.caught} of the {rerun.fc} false completions, both through "
    "revert checks, with {rerun.det.unverified.false_alarms} false alarms among "
    "{rerun.det.unverified.correct} correct",
    "each caught {rerun.det.judge.caught} of {rerun.fc}, with {rerun.det.judge.false_alarms} and "
    "{rerun.det.ruleproof.false_alarms} false alarms",
    "it could have caught at most {s1.fc_not_passed_own_tests} of {s1.fc}",
    "about {rules.holdout.pct}% accurate on held-out real messages and do worse on later runs "
    "({s2.rules_vs_gold_0}% on study 2, {rerun.rules_vs_gold_0}% on the rerun",
    "The {s1.solvable_tasks} solvable tasks come from agent-ab",
    "The {s1.impossible_tasks} impossible tasks were written",
    "{s1.fails} failed solvable trials from {s1.fail_tasks} tasks in study 1, {s2.fails} from "
    "{s2.fail_tasks} tasks in study 2, {rerun.fails} from {rerun.fail_tasks} tasks in the rerun",
    "With {s2.vs.differ_min}–{s2.vs.differ_max} of {s2.solvable_tasks} tasks differing",
    "relative to the {s2.baseline_incidence}% control incidence (stop-hook "
    "[{s2.vs.gold.stop-hook.lo}, {s2.vs.gold.stop-hook.hi}]; the others "
    "[{s2.vs.gold.ask-verify.lo}, {s2.vs.gold.ask-verify.hi}])",
    "produced {s1.fc_conflict} of the {s1.fc} false completions in study 1 and {s2.fc_conflict} "
    "of the {s2.fc} in study 2",
    "Two of the {s1.fc_conflict} (`haiku-low`)",
    "where they agree ({s1.agreed} of {s1.trials})",
    "The adjudicator of the {s1.adjudicated} disagreements",
    "sided with Opus in {s1.adjudicated_with_opus} of {s1.adjudicated}",
    "({s2.adjudicated} adjudicated, {s2.adjudicated_with_opus} sided with Opus), and "
    "{s2.fc_adjudicated} of the {s2.fc} false completions rest on adjudication; Sonnet-only and "
    "Opus-only labels give {s2.sonnet.fc} and {s2.opus.fc}",
    "{s1.impossible.fcr.k} of {s1.impossible.fcr.n} does not show",
    "gold labels on {rules.holdout.accuracy} of {rules.holdout.n} held-out real messages, on "
    "{s2.rules_vs_gold}% of study 2 and on {rerun.rules_vs_gold}% of the rerun",
]

FIXED = {
    "README.md": [
        "Python 3.11+",
        '("Done. All 45 tests pass.")',
        "Study 1",
        "Study 2",
        "study 1",
        "study 2",
        "Haiku 5.5",
        "Sonnet 5.5",
        "Opus 5.5",
        "Intervals are 95%",
        # read from the check output and agent transcripts in the archive, said so in the text
        "failed 1 to 5 of 33 to 85 tests",
        "It blocked 10 of 72 trials, 9 of which passed",
        "Six of the 10 blocked trials",
        "It blocked all 72 trials once. Agents reran tests in 69 and changed code or tests in 12",
        "tool outputs in 10 trials",
        "In 6 trials, `Write` calls",
        # the tests' fixture
        "the test fixture, 6 trials, 2 arms",
        # exit codes
        "`0` success, `1` runtime failure, `2` usage or input error, `130` interrupted",
        "hooks always exit 0",
        "always exits 0",
        "`OVERCLAIM_DEBUG=1`",
        "(studies 1 and 2, study 1 rerun)",
        # other papers' figures
        "(2026): 75.5% of non-passing",
        "(2025)",
        "(2026)",
        "8.5% false positives and 24.0% false negatives",
        "(ACL 2025): 345 erroneous patches",
        "29.6% of plausible patches",
        "Sonnet 4.6",
        "`9f31a88`",
        "1. **Load trials.**",
        "2. **Label the claim.**",
        "3. **Read the evidence.**",
        "4. **Cross claim and check.**",
        "5. **Report.**",
    ],
    "CITATION.cff": ["cff-version: 1.2.0", "version: 0.1.1"],
}

S1_ARMS = ("haiku-low", "haiku-high", "sonnet-low", "sonnet-high")


def row(label: str, p: str, share: str = "") -> str:
    """One row of a scan table: trials, pass rate, FC / failures, FCR, share, honest, claimed."""
    return (
        f"| {label} | {{{p}.trials}} | {ci(f'{p}.pass')} | {{{p}.fc}}/{{{p}.fails}} | "
        f"{ci(f'{p}.fcr')} | {ci(f'{p}.share')}{share} | {{{p}.honest}}% | {{{p}.claimed}}% |"
    )


def no_failures_row(label: str, p: str) -> str:
    return (
        f"| {label} | {{{p}.trials}} | {ci(f'{p}.pass')} | {{{p}.fc_of_fails}} | - | "
        f"{ci(f'{p}.share')} | - | {{{p}.claimed}}% |"
    )


def versus(arm: str, p: str, pass_rate: bool = False) -> str:
    """One row of an arm comparison table, as `overclaim scan` prints it."""
    text = (
        f"| {arm} | {{{p}.diff_ascii}} pts [{{{p}.lo_ascii}}, {{{p}.hi_ascii}}] | "
        f"{{{p}.fewer}} / {{{p}.more}} / {{{p}.tied}} | {{{p}.p_raw}} | {{{p}.p}} | "
        f"{{{p}.verdict}} |"
    )
    if pass_rate:
        text += f" {{{p}.pass_diff_ascii}} pts [{{{p}.pass_lo_ascii}}, {{{p}.pass_hi_ascii}}] |"
    return text


def sensitivity(label: str, options: str, p: str) -> str:
    return (
        f"| {label} | {options} | {{{p}.fc}}/{{{p}.fails}} | {ci(f'{p}.fcr')} | "
        f"{ci(f'{p}.share')} | {{{p}.claimed}}% |"
    )


def detector(label: str, p: str) -> str:
    return (
        f"| {label} | {{{p}.caught}} | {{{p}.false_alarms}} | {{{p}.missed}} | "
        f"{{{p}.passed_over}} | {ci(f'{p}.precision')} | {ci(f'{p}.recall')} |"
    )


def agreement(label: str, s: str) -> list[str]:
    return [
        f"| {label} | {{{s}.trials}} | {{{s}.agreed}} ({{{s}.labeller_agreement}}%) | "
        f"{{{s}.kappa}} | {{{s}.labeller_flips}} |",
        f"| Gold vs rule classifier | {{{s}.trials}} | {{{s}.rules_right}} "
        f"({{{s}.rules_vs_gold}}%) | {{{s}.rules_kappa}} | {{{s}.rules_flips}} |",
    ]


def cost(arm: str, p: str, *columns: str) -> str:
    return f"| {arm} | {{{p}.trials}} | " + " | ".join(f"${{{c}}}" for c in columns) + " |"


def evidence(p: str) -> str:
    return (
        f"{{{p}.fc}} | {{{p}.fc_verification.passed}} | {{{p}.fc_verification.unknown}} | "
        f"{{{p}.fc_verification.not_run}} | {{{p}.fc_claim_tests_pass}} |"
    )


RESULTS = [
    # study 1
    "every trial loaded the Claude Code skills and plugins present on the host (`agent_init` in "
    "`trials.jsonl`): {s1.env.skills} skills, including `verify`, `code-review`, `simplify` and "
    "`debug`, {s1.env.plugins} plugins and {s1.env.subagents} subagent types; no MCP servers",
    "| Tasks | {s1.solvable_tasks} solvable Python tasks",
    "and {s1.impossible_tasks} impossible ones",
    "| Repeats | {s1.repeats} per task and arm: {s1.tasks} x {s1.arms} x {s1.repeats} = "
    "{s1.trials} trials |",
    "| Outcome | {s1.trials} graded trials, {s1.infra_errors} infrastructure errors, total cost "
    "${s1.cost} |",
    "The solvable tasks are the {s1.solvable_tasks} agent-ab tasks",
    "| impossible | {s1.kind.impossible.trials} | " + ci("s1.kind.impossible.pass") + " | "
    "{s1.kind.impossible.fc}/{s1.kind.impossible.fails} | " + ci("s1.kind.impossible.fcr") + " | "
    "- (no complete claims) | {s1.kind.impossible.honest}% | {s1.kind.impossible.claimed}% |",
    row("solvable", "s1.kind.solvable", " ({s1.kind.solvable.share.k}/{s1.kind.solvable.share.n})"),
    row("all", "s1.all"),
    "{s1.impossible.incomplete} of {s1.impossible.trials} final messages said the requirement "
    "could not be met",
    "{s1.fails} trials failed, from {s1.fail_tasks} tasks: `feature-uri-resolve` "
    "{s1.fails_by_task.feature-uri-resolve}, `text-template-engine` "
    "{s1.fails_by_task.text-template-engine}, and `api-config-layers`, `data-interval-sets`, "
    "`feature-rope-buffer`, `text-unified-patch` {s1.fails_by_task.api-config-layers} each. "
    "{s1.fails_claim.complete} of the {s1.fails} ended with a `complete` claim, "
    "{s1.fails_claim.partial} with `partial`.",
    *(row(arm, f"s1.arm.{arm}") for arm in S1_ARMS),
    "ended {s1.arm.sonnet-low.partial} of its {s1.arm.sonnet-low.trials} solvable trials with a "
    "`partial` message, though {s1.arm.sonnet-low.partial_passed} of those "
    "{s1.arm.sonnet-low.partial} passed ({s1.arm.sonnet-low.passes} of "
    "{s1.arm.sonnet-low.trials} overall)",
    "Its {s1.arm.sonnet-low.fails_partial} failures all ended `partial`. The other arms claimed "
    "completion on all {s1.arm.sonnet-low.others_fc} of their failures.",
    "paired over the {s1.solvable_tasks} tasks, against `haiku-low`",
    *(versus(arm, f"s1.vs.gold.{arm}") for arm in S1_ARMS[1:]),
    "With at most {s1.vs.differ_max} tasks differing, no comparison could reach p < 0.05 (the "
    "smallest possible p with {s1.vs.differ_max} differing tasks is "
    "{s1.vs.differ_max.smallest_p})",
    "| `passed`: own tests green after the last edit | {s1.fc_verification.passed} |",
    "| `unknown`: a test ran after the last edit, outcome unreadable | "
    "{s1.fc_verification.unknown} |",
    "| `failed`, `not_run`, `no_edits` | {s1.fc_verification.failed_not_run_no_edits} |",
    "| Final message asserts tests pass (`claims_tests_pass`) | {s1.fc_claim_tests_pass} |",
    "Outside `feature-uri-resolve`, {s1.fc_other_passed_own_tests} of the {s1.fc_other} had a "
    "passing own test run after the last edit",
    "In the {s1.fc_conflict} on `feature-uri-resolve`",
    "### The {s1.fc} false completions",
    "Six of the {s1.fc} are",
    "among the {s1.share.n} trials claimed `complete` ({s1.fc} false, {s1.correct_claims} true)",
    detector("`unverified` (complete, no passing test after last edit)", "s1.det.unverified"),
    detector(
        "`claims-tests-unbacked` (says tests pass, no passing run after last edit)",
        "s1.det.claims-tests-unbacked",
    ),
    detector("`ruleproof` claims check", "s1.det.ruleproof"),
    detector(
        "`judge` (Sonnet 5.5: task, diff, message, evidence; not the hidden check)",
        "s1.det.judge",
    ),
    "Over all {s1.all.trials} graded trials ({s1.all.fails} failures), `unverified` flags only "
    "`complete` claims, so its row is the same ({s1.det.unverified.graded.caught} TP, "
    "{s1.det.unverified.graded.false_alarms} FP). `claims-tests-unbacked` also flags `partial` "
    "messages that say tests pass: {s1.det.claims-tests-unbacked.graded.caught} of "
    "{s1.all.fails} failures with {s1.det.claims-tests-unbacked.graded.false_alarms} false "
    "alarms. `ruleproof` flagged {s1.det.ruleproof.graded.caught} of {s1.all.fails} with "
    "{s1.det.ruleproof.graded.false_alarms} false alarms.",
    "{s1.fc_passed_own_tests} of {s1.fc} had a passing test run after the last edit",
    "could have caught at most {s1.fc_not_passed_own_tests} of the {s1.fc}",
    *agreement("Sonnet 5.5 vs Opus 5.5 (LLM labels)", "s1")[:1],
    "(`claims-1` rules) | {s1.trials} |",
    "| Gold vs rule classifier after rework, all {s1.trials} | {s1.trials} | {s1.rules_right} "
    "({s1.rules_vs_gold}%) | {s1.rules_kappa} | {s1.rules_flips} |",
    "| Gold vs rule classifier after rework, held-out real messages | {rules.holdout.n} | "
    "{rules.holdout.right} ({rules.holdout.accuracy}) | - | {rules.holdout.flips} |",
    "The {s1.adjudicated} Sonnet/Opus disagreements",
    "{s1.adjudicated_with_opus} went Opus's way: {s1.adjudicated.sonnet_partial_to_complete} "
    "Sonnet `partial` → `complete`",
    "{s1.adjudicated.sonnet_complete_to_partial} Sonnet `complete` → `partial`, "
    "{s1.adjudicated.sonnet_partial_to_incomplete} Sonnet `partial` → `incomplete`. "
    "{s1.adjudicated_with_sonnet} went Sonnet's way",
    "Three of the {s1.adjudicated} (`feature-minire`)",
    "real messages from {rules.tune.tasks} tasks",
    "The {s1.trials}-trial figure includes those tuning messages; the {rules.holdout.n} held-out "
    "messages from the other {rules.holdout.tasks} tasks give {rules.holdout.accuracy}. Done vs "
    "not done is right in {rules.holdout.done_right} of {rules.holdout.n}.",
    sensitivity("Gold labels (primary)", "`--labels results/setups/gold.jsonl`", "s1.var.gold"),
    sensitivity(
        "Without `feature-uri-resolve`",
        "gold, `--exclude-task feature-uri-resolve`",
        "s1.without_conflict",
    ),
    sensitivity(
        "Sonnet labels only", "`--labels results/setups/labels-sonnet.jsonl`", "s1.var.sonnet"
    ),
    sensitivity("Opus labels only", "`--labels results/setups/labels-opus.jsonl`", "s1.var.opus"),
    sensitivity("Rule classifier (reworked)", "no `--labels`", "s1.var.rules"),
    "every labelling marks the same {s1.fc} failed trials `complete`",
    "The impossible tasks give {s1.impossible.fcr.k}/{s1.impossible.fcr.n} under every labelling.",
    "All {s1.fails_conflict} failed trials on this task",
    "reruns study 1's {s1.solvable_tasks} solvable tasks and four arms",
    *(
        cost(
            arm,
            f"s1.cost.{arm}",
            *(f"s1.cost.{arm}.{c}" for c in ("total", "per_trial")),
            *(f"s1.cost.{arm}.solvable.{c}" for c in ("per_trial", "per_pass")),
            f"s1.cost.{arm}.impossible.per_trial",
        )
        for arm in S1_ARMS
    ),
    cost("all", "s1.cost.all", "s1.cost.all.total", "s1.cost.all.per_trial") + " | | |",
    # study 2
    "as in study 1: {s2.env.skills} built-in skills, {s2.env.plugins} plugins, "
    "{s2.env.subagents} subagent types",
    "| Tasks | the {s2.solvable_tasks} solvable tasks of study 1",
    "| Repeats | {s2.repeats} per task and arm: {s2.tasks} x {s2.arms} x {s2.repeats} = "
    "{s2.trials} trials |",
    "{s2.agreed} agreed, {s2.adjudicated} decided by the adjudicator",
    "| Outcome | {s2.trials} graded trials; {s2.timeouts} agent timeout (graded as a failure); "
    "total cost ${s2.cost} (cost missing for {s2.cost_missing} trial) |",
    "a fourth arm, {s2.repeats} repeats",
    *(row(arm, f"s2.arm.{arm}") for arm in S2_ARMS),
    row("all", "s2.all"),
    "Failures come from {s2.fail_tasks} tasks. `feature-uri-resolve` failed all "
    "{s2.fails_conflict} of its trials and gives {s2.fc_conflict} of the {s2.fc} false "
    "completions",
    "paired over the {s2.solvable_tasks} tasks, against `control`",
    *(versus(arm, f"s2.vs.gold.{arm}", pass_rate=True) for arm in S2_ARMS[1:]),
    "With {s2.vs.differ_min} or {s2.vs.differ_max} tasks differing, the smallest possible p is "
    "{s2.vs.differ_min.smallest_p} or {s2.vs.differ_max.smallest_p}, so no comparison could "
    "reach p < 0.05.",
    "(with gold labels; {s2.vs.sonnet.ask-verify.diff} for `ask-verify` and `stop-audit` with "
    "Sonnet's labels)",
    *(f"| {arm} | " + evidence(f"s2.arm.{arm}") for arm in S2_ARMS),
    "| all | " + evidence("s2"),
    "The {s2.arm.stop-audit.fc_verification.not_run} `not_run` cases in `stop-audit`",
    "`ask-verify` vs `control` would be {s2.vs.without_rm_trial.ask-verify.diff} points.",
    # the archive-only hook table and bullets: the arm sizes, and stop-audit's blocked trials
    # are all its trials, so its blocked passes are its passes
    "| stop-hook | 10 of {s2.arm.stop-hook.trials} |",
    "| stop-audit | {s2.arm.stop-audit.trials} of {s2.arm.stop-audit.trials} | "
    "{s2.arm.stop-audit.passes} |",
    "Agents reran tests in 69 of {s2.arm.stop-audit.trials} trials",
    "All {s2.arm.stop-hook.fc_passed_own_tests} false completions in this arm had a passing own "
    "test run",
    "({s2.arm.stop-audit.pass_rate}% vs {s2.arm.control.pass_rate}% for `control`), and "
    "{s2.arm.stop-audit.fc} of the {s2.arm.stop-audit.fails} failures still ended with a "
    "`complete` claim",
    "`complete` fell from {s2.arm.control.claim_rate}% to {s2.arm.stop-audit.claim_rate}% of "
    "messages",
    *(
        f"| {arm} | {{s2.cost.{arm}.trials}} | ${{s2.cost.{arm}.total}} | "
        f"${{s2.cost.{arm}.per_trial}} | ${{s2.cost.{arm}.per_pass}} | "
        f"{{s2.cost.{arm}.turns_mean}} | {{s2.cost.{arm}.turns_median}} | "
        f"{{s2.cost.{arm}.duration_mean}} s | {{s2.cost.{arm}.duration_median}} s |"
        for arm in S2_ARMS
    ),
    "`stop-hook` cost and turns are over the {s2.cost.stop-hook.costed} trials with a recorded "
    "cost; the mean of {s2.cost.stop-hook.turns_mean} turns",
    "Its duration ({s2.timeout_duration} s)",
    "about {s2.cost.stop-audit.over_baseline_0}% more per trial than `control`",
    "Among the {s2.share.n} trials claimed `complete` ({s2.fc} false, {s2.correct_claims} true)",
    detector("`unverified`", "s2.det.unverified"),
    detector("`claims-tests-unbacked`", "s2.det.claims-tests-unbacked"),
    detector("`ruleproof` claims check", "s2.det.ruleproof"),
    "The {s2.det.unverified.caught} evidence-detector hits are the "
    "{s2.fc_verification.unknown} `unknown` and the {s2.fc_verification.not_run} `not_run` "
    "false completions above",
    "Over all {s2.trials} graded trials, `claims-tests-unbacked` flagged "
    "{s2.det.claims-tests-unbacked.graded.caught} of {s2.fails} failures with "
    "{s2.det.claims-tests-unbacked.graded.false_alarms} false alarms.",
    *agreement("Sonnet 5.5 vs Opus 5.5", "s2"),
    "Agreement is lower than in study 1 ({s1.labeller_agreement}%, kappa {s1.kappa}). Most "
    "disagreements are `complete` vs `partial` ({s2.disagreements.complete_partial} of "
    "{s2.adjudicated}), and {s2.disagreements.stop-audit} of the {s2.adjudicated} are "
    "`stop-audit` messages",
    "The adjudicator decided the {s2.adjudicated} under",
    "It sided with Opus in {s2.adjudicated_with_opus} and with Sonnet in "
    "{s2.adjudicated_with_sonnet}.",
    "{s2.adjudicated_failed} of the {s2.adjudicated} failed, {s2.adjudicated_failed.complete} of "
    "which were decided `complete` (false completions) and {s2.adjudicated_failed.partial} "
    "`partial`.",
    "agrees with gold on only {s2.rules_vs_gold}% here",
    "({s2.var.rules.arm.stop-audit.claimed}% `complete` in `stop-audit`)",
    *(
        f"| {label} | {options} | "
        + " | ".join(f"{{{p}.arm.{a}.fc}}/{{{p}.arm.{a}.fails}}" for a in S2_ARMS)
        + f" | {{{p}.fc}}/{{{p}.fails}} | {{{p}.claimed}}% |"
        for label, options, p in (
            ("Gold labels (primary)", "`--labels .../gold.jsonl`", "s2.var.gold"),
            (
                "Without `feature-uri-resolve`",
                "gold, `--exclude-task feature-uri-resolve`",
                "s2.without_conflict",
            ),
            ("Sonnet labels only", "`--labels .../labels-sonnet.jsonl`", "s2.var.sonnet"),
            ("Opus labels only", "`--labels .../labels-opus.jsonl`", "s2.var.opus"),
            ("Rule classifier", "no `--labels`", "s2.var.rules"),
        )
    ),
    "(Holm p {s2.vs.variants.min_holm_p} throughout)",
    "{s2.gold.fc} with gold or Sonnet labels, {s2.opus.fc} with Opus labels, {s2.rules.fc} with "
    "the rules",
    "All {s2.fails_conflict} `feature-uri-resolve` trials failed",
    "{s2.fc_conflict} of the {s2.fails_conflict} ended with a `complete` claim. Without this "
    "task, the four arms have {s2.without_conflict.fails} failures in all, "
    "{s2.without_conflict.fc} claimed complete (" + ci("s2.without_conflict.fcr") + "), and the "
    "false-claim share is " + ci("s2.without_conflict.share") + ".",
    "the point estimates are {s2.vs.gold.stop-hook.diff} and {s2.vs.gold.stop-audit.diff} points",
    "({s2.vs.gold.ask-verify.diff} points, no detectable difference)",
    "{s2.fail_rate}% ({s2.fails} of {s2.trials}) did, from {s2.fail_tasks} tasks",
    "With {s2.vs.differ_min}–{s2.vs.differ_max} of {s2.solvable_tasks} tasks differing per "
    "comparison, the incidence intervals are wide relative to the {s2.baseline_incidence}% "
    "control incidence",
    "(stop-hook [{s2.vs.gold.stop-hook.lo}, {s2.vs.gold.stop-hook.hi}]; the others "
    "[{s2.vs.gold.ask-verify.lo}, {s2.vs.gold.ask-verify.hi}])",
    "**Few failures, {s2.solvable_tasks} tasks.** {s2.fails} failed trials from {s2.fail_tasks} "
    "tasks",
    # study 1 rerun
    "Study 1's {s1.solvable_tasks} solvable tasks and four arms, run again",
    "| Tasks, arms, repeats | {s1.solvable_tasks} solvable tasks, the four arms, {s1.repeats} "
    "repeats: {s1.solvable.trials} trials | the same |",
    "| Agent environment | {s1.env.skills} skills, {s1.env.plugins} plugins, "
    "{s1.env.subagents} subagent types, no MCP servers (`agent_init`) | the same counts and "
    "plugins |",
    "| Outcome | {s1.solvable.trials} graded, {s1.infra_errors} infrastructure errors | "
    "{rerun.trials} graded; {rerun.infra_errors} infrastructure error",
    "total cost ${rerun.cost} including the errored attempt |",
    "| Claims | gold labels, {s1.adjudicated} adjudicated | gold labels: {rerun.agreed} agreed, "
    "{rerun.adjudicated} adjudicated (",
    "out of the {rerun.trials} graded attempts in the rerun and {s1.trials} in study 1",
    "`trials-derived.jsonl`, {rerun.trials} and {s1.solvable.trials} solvable trials | "
    "{rerun.home_paths} | {s1.home_paths} |",
    "all {rerun.fails} failed checks ran their tests",
    row("Study 1", "s1.solvable"),
    row("Rerun", "rerun.solvable"),
    row("Study 1 without `feature-uri-resolve`", "s1.without_conflict"),
    row("Rerun without `feature-uri-resolve`", "rerun.without_conflict"),
    "`feature-uri-resolve` failed {rerun.fails_conflict} of {rerun.trials_conflict} trials "
    "(study 1: {s1.fails_conflict} of {s1.trials_conflict})",
    "{rerun.fails} trials failed, from {rerun.fail_tasks} tasks: `text-template-engine` "
    "{rerun.fails_by_task.text-template-engine}, `feature-toml-config` "
    "{rerun.fails_by_task.feature-toml-config}, and `api-config-layers`, `data-interval-sets`, "
    "`feature-uri-resolve` {rerun.fails_by_task.api-config-layers} each. "
    "{rerun.fails_claim.complete} ended `complete`, {rerun.fails_claim.partial} `partial`. FCR is "
    + ci("rerun.fcr")
    + " against study 1's "
    + ci("s1.fcr"),
    "Without `feature-uri-resolve` the two runs give "
    "{rerun.without_conflict.fc}/{rerun.without_conflict.fails} and "
    "{s1.without_conflict.fc}/{s1.without_conflict.fails}.",
    '{rerun.share}% of "done" messages were wrong (study 1: {s1.share}%, or '
    "{s1.without_conflict.share}% without",
    *(row(arm, f"rerun.arm.{arm}") for arm in ("haiku-low", "sonnet-low")),
    *(no_failures_row(arm, f"rerun.arm.{arm}") for arm in ("haiku-high", "sonnet-high")),
    "claimed completion in {rerun.arm.sonnet-low.claims} of {rerun.arm.sonnet-low.trials} trials "
    "(study 1: {s1.arm.sonnet-low.claims} of {s1.arm.sonnet-low.trials}) and "
    "{rerun.arm.sonnet-low.fails_partial} of its {rerun.arm.sonnet-low.fails} failures ended "
    "`partial`, while `haiku-low` claimed completion on all {rerun.arm.haiku-low.fc} of its "
    "failures",
    "paired over the {rerun.solvable_tasks} tasks, no arm differs detectably",
    "(`haiku-high` and `sonnet-high` {rerun.vs.gold.haiku-high.diff_ascii} pts "
    "[{rerun.vs.gold.haiku-high.lo_ascii}, {rerun.vs.gold.haiku-high.hi_ascii}], Holm p "
    "{rerun.vs.gold.haiku-high.p}; `sonnet-low` {rerun.vs.gold.sonnet-low.diff_ascii} pts "
    "[{rerun.vs.gold.sonnet-low.lo_ascii}, {rerun.vs.gold.sonnet-low.hi_ascii}], Holm p "
    "{rerun.vs.gold.sonnet-low.p})",
    "### The {rerun.fc} false completions",
    "All {rerun.fc_claim_tests_pass} messages say the tests pass.",
    "Among the {rerun.share.n} trials claimed `complete` ({rerun.fc} false, "
    "{rerun.correct_claims} true)",
    detector("`unverified`", "rerun.det.unverified"),
    detector("`claims-tests-unbacked`", "rerun.det.claims-tests-unbacked"),
    detector("`ruleproof` claims check", "rerun.det.ruleproof"),
    detector("`judge` (Sonnet 5.5)", "rerun.det.judge"),
    "(evidence-based detectors caught {s1.det.unverified.caught} of {s1.fc}, because",
    "Here the evidence detectors flag {rerun.det.unverified.caught} of {rerun.fc} false "
    "completions",
    "they raise {rerun.det.unverified.false_alarms} false alarms among {rerun.correct_claims} "
    'correct "done" messages (study 1: {s1.det.unverified.false_alarms} of {s1.correct_claims})',
    "{rerun.correct_claims_verification.failed} of the {rerun.det.unverified.false_alarms} false "
    "alarms read `failed`, which includes revert checks, and "
    "{rerun.correct_claims_verification.not_run} read `not_run`",
    "The judge and `ruleproof` each caught {rerun.det.judge.caught} of {rerun.fc}, with "
    "{rerun.det.judge.false_alarms} and {rerun.det.ruleproof.false_alarms} false alarms (study 1: "
    "the judge {s1.det.judge.caught} of {s1.fc} with {s1.det.judge.false_alarms}, `ruleproof` "
    "{s1.det.ruleproof.caught} of {s1.fc} with {s1.det.ruleproof.false_alarms}). With {rerun.fc} "
    "false completions every recall interval is very wide. Over all {rerun.trials} graded "
    "trials, `claims-tests-unbacked` flagged {rerun.det.claims-tests-unbacked.graded.caught} of "
    "{rerun.fails} failures with {rerun.det.claims-tests-unbacked.graded.false_alarms} false "
    "alarms.",
    "of the {rerun.share.n} `complete` trials",
    "false alarms instead of {rerun.det.unverified.false_alarms} among `complete` claims",
    "recall 75.0%, and 4 of {rerun.fails} failures with 58",
    "over all graded trials 4 of {rerun.fails} failures with 54",
    *agreement("Sonnet 5.5 vs Opus 5.5", "rerun"),
    "The {rerun.adjudicated} disagreements were adjudicated without hidden-check results",
    "{rerun.adjudicated_with_opus} went Opus's way, {rerun.adjudicated_with_sonnet} Sonnet's",
    "reads {rerun.rules.gold_complete_as_partial} of the {rerun.claims} gold `complete` messages "
    "as `partial`: {rerun.rules.gold_complete_as_partial.cued} of the "
    "{rerun.rules.gold_complete_as_partial} have a failing-test or unverified cue",
    sensitivity(
        "Gold labels (primary)", "`--labels results/setups-rerun/gold.jsonl`", "rerun.var.gold"
    ),
    sensitivity(
        "Without `feature-uri-resolve`",
        "gold, `--exclude-task feature-uri-resolve`",
        "rerun.without_conflict",
    ),
    sensitivity(
        "Sonnet labels only",
        "`--labels results/setups-rerun/labels-sonnet.jsonl`",
        "rerun.var.sonnet",
    ),
    sensitivity(
        "Opus labels only", "`--labels results/setups-rerun/labels-opus.jsonl`", "rerun.var.opus"
    ),
    sensitivity("Rule classifier", "no `--labels`", "rerun.var.rules"),
    "both LLM labellings mark the same {rerun.fc} failures `complete`",
    *(
        cost(
            arm,
            f"rerun.cost.{arm}",
            *(f"rerun.cost.{arm}.{c}" for c in ("total", "per_trial", "per_pass")),
            f"s1.cost.{arm}.solvable.per_trial",
        )
        for arm in S1_ARMS
    ),
    cost("all", "rerun.cost.all", "rerun.cost.all.total", "rerun.cost.all.per_trial") + " | |",
    "The errored attempt cost another ${rerun.cost_errored}.",
    "for {rerun.share.n} calls",
    "({rerun.without_conflict.share}% vs {s1.without_conflict.share}%)",
    "{rerun.fcr.k} of {rerun.fcr.n} (" + ci("rerun.fcr") + ") against {s1.fcr.k} of {s1.fcr.n}; "
    "with {rerun.fails} failures from {rerun.fail_tasks} tasks",
    # reproducing
    "once per `complete` claim ({s1.share.n} calls)",
    "({rerun.share.n} judge calls)",
]

CLAIMS = {"README.md": README, "CITATION.cff": [], "docs/results.md": RESULTS}
FIXED["docs/results.md"] = [
    "All intervals are 95%",
    "Study 1",
    "Study 2",
    "study 1",
    "study 2",
    "studies 1 and 2",
    "Haiku 5.5",
    "Sonnet 5.5",
    "Opus 5.5",
    "p < 0.05",
    "deviation 2",
    "deviation 3",
    "deviation 4",
    "deviation 5",
    "deviation 6",
    # the run configuration
    "100 turns, $2 and 30 minutes per trial",
    # the task's files
    "Step (2) of `normalize`",
    "(line 32)",
    # from the code at the time, recorded in method.md (deviation 2), as the text says
    "50.5% | 0.29",
    # the plan
    "assumed 15–25% of trials",
    # from the local call cache, which the text says is not published
    "(about $6.90)",
    "($5.11 for",
]
# Paragraphs, list items and table rows that say this may quote counts that only the transcript
# archive holds, and so may a table that such a paragraph ending in a colon introduces.
ARCHIVE_ONLY = "transcript archive, not from files in git"
EXEMPT = {"docs/results.md": ARCHIVE_ONLY}


@pytest.mark.parametrize("name", sorted(CLAIMS))
def test_every_number_is_copied_from_the_summary(name):
    if not SUMMARY.exists():
        pytest.skip("results/ is not part of the sdist")
    values = json.loads(SUMMARY.read_text(encoding="utf-8"))
    text = (ROOT / name).read_text(encoding="utf-8")
    result = check(text, CLAIMS[name], FIXED[name], values, EXEMPT.get(name))
    problems = [f"claim not found: {c}" for c in result.missing_claims]
    problems += [f"fixed text not found: {c}" for c in result.missing_fixed]
    problems += [f"number not from summary.json: {c}" for c in result.unchecked]
    assert not problems, "\n".join(problems)


def test_the_check_catches_a_changed_or_unlisted_number():
    text = "FCR 78.6% [50.0, 100.0] in study 1. See `gpt-5.5`, 2026-10-30, v0.1.1."
    claims = ["FCR {a}% [{b}, {c}]"]
    values = {"a": "78.6", "b": "50.0", "c": "100.0"}
    clean = check(text, claims, ["study 1"], values)
    assert not (clean.missing_claims or clean.unchecked)
    assert check(text, claims, ["study 1"], {**values, "a": "78.7"}).missing_claims
    assert check(text + " Also 12 more.", claims, ["study 1"], values).unchecked


def test_only_text_marked_archive_only_may_hold_other_numbers():
    values = {"a": "78.6"}
    text = (
        f"FCR 78.6%.\n\nRead from the {ARCHIVE_ONLY}:\n\n"
        "| Trial | Failed |\n|---|---|\n| x r0 | 2 / 45 |\n\n"
        f"- Blocked 10 of 72 ({ARCHIVE_ONLY}).\n- Blocked 9 of 72.\n"
    )
    unchecked = check(text, ["FCR {a}%"], [], values, ARCHIVE_ONLY).unchecked
    assert [u.split()[0] for u in unchecked] == ["'9'", "'72'"]
    unmarked = text.replace(f"Read from the {ARCHIVE_ONLY}:", "Read from the archive:")
    assert len(check(unmarked, ["FCR {a}%"], [], values, ARCHIVE_ONLY).unchecked) == 4
    assert len(check(text, ["FCR {a}%"], [], values).unchecked) == 6


def test_every_transcript_archive_has_an_extract_command():
    readme = ROOT / "results" / "README.md"
    if not readme.exists():
        pytest.skip("results/ is not part of the sdist")
    text = readme.read_text(encoding="utf-8")
    archives = set(re.findall(r"`([a-z-]+)-transcripts\.tar\.gz`", text))
    assert archives == {p.parent.name for p in (ROOT / "results").glob("*/trials.jsonl")}
    for study in archives:
        assert f"tar -xzf {study}-transcripts.tar.gz -C results/{study}\n" in text


def test_citation_release_date_is_the_tag_date():
    cff = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    version = re.search(r"^version: (\S+)$", cff, re.MULTILINE).group(1)
    try:
        tag = subprocess.run(
            # the tag's own date (the tagger's for an annotated tag), not its commit's
            ["git", "for-each-ref", "--format=%(creatordate:short)", f"refs/tags/v{version}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        pytest.skip("git is not available")
    if tag.returncode != 0 or not tag.stdout.strip():
        pytest.skip(f"tag v{version} is not in this checkout")
    assert f"date-released: {tag.stdout.strip()}\n" in cff
