"""Every number in README.md and CITATION.cff is copied from results/summary.json.

`scripts/summarize_results.py` rebuilds summary.json from the committed result files (no
transcripts, no model calls); CI runs it and fails on any diff. A claim below is a fragment of
the README with `{key}` placeholders. A number that does not come from those files (a version,
a design constant, a figure quoted from another paper, a count read from the transcript
archive) is listed as fixed, and the README says where it comes from.
"""

import json
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

CLAIMS = {"README.md": README, "CITATION.cff": []}


@pytest.mark.parametrize("name", sorted(CLAIMS))
def test_every_number_is_copied_from_the_summary(name):
    if not SUMMARY.exists():
        pytest.skip("results/ is not part of the sdist")
    values = json.loads(SUMMARY.read_text(encoding="utf-8"))
    result = check((ROOT / name).read_text(encoding="utf-8"), CLAIMS[name], FIXED[name], values)
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
