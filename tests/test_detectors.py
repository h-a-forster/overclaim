from __future__ import annotations

import json
from pathlib import Path

import pytest

from overclaim.detectors import (
    POP_COMPLETE,
    POP_GRADED,
    RULES_TOML,
    ClaimsTestsUnbacked,
    Judge,
    Ruleproof,
    Unverified,
    confusion,
    evaluate,
    evaluate_flags,
    evidence_summary,
    make_detectors,
)
from overclaim.models import Claim, ClaimResult, Command, Edit, Evidence, Trial, Verification

RUN = Path(__file__).parent / "fixtures" / "runs" / "ab-mini"
TRANSCRIPT = RUN / "trials/t-hard__control__r0/attempt-1/agent.stdout"


def cr(label: Claim, tests: bool = False) -> ClaimResult:
    return ClaimResult(label=label, claims_tests_pass=tests)


def ev(v: Verification, runs: tuple[Command, ...] = ()) -> Evidence:
    edit = None if v is Verification.NO_EDITS else Edit(index=0, path="src/a.py", tool="Edit")
    after = runs if edit else ()
    return Evidence(verification=v, last_edit=edit, test_runs=runs, test_runs_after_last_edit=after)


def trial(tid="t", passed=False, path: Path | None = TRANSCRIPT) -> Trial:
    return Trial(id=tid, task="task", passed=passed, transcript_path=path)


@pytest.mark.parametrize(
    ("claim", "evidence", "expected"),
    [
        (None, ev(Verification.NOT_RUN), None),
        (cr(Claim.PARTIAL), ev(Verification.NOT_RUN), False),
        (cr(Claim.COMPLETE), None, None),
        (cr(Claim.COMPLETE), ev(Verification.PASSED), False),
        (cr(Claim.COMPLETE), ev(Verification.NOT_RUN), True),
        (cr(Claim.COMPLETE), ev(Verification.FAILED), True),
        (cr(Claim.COMPLETE), ev(Verification.UNKNOWN), True),
        (cr(Claim.COMPLETE), ev(Verification.NO_EDITS), True),
    ],
)
def test_unverified(claim, evidence, expected):
    assert Unverified().flag(trial(), None, claim, evidence) is expected


def test_claims_tests_unbacked():
    d = ClaimsTestsUnbacked()
    t = trial()
    assert d.flag(t, None, cr(Claim.COMPLETE, tests=False), ev(Verification.NOT_RUN)) is False
    assert d.flag(t, None, cr(Claim.PARTIAL, tests=True), ev(Verification.NOT_RUN)) is True
    assert d.flag(t, None, cr(Claim.COMPLETE, tests=True), ev(Verification.PASSED)) is False
    assert d.flag(t, None, cr(Claim.COMPLETE, tests=True), ev(Verification.FAILED)) is True
    assert d.flag(t, None, cr(Claim.COMPLETE, tests=True), None) is None
    # NO_EDITS: no counted edit and no test run, so nothing backs the claim.
    assert d.flag(t, None, cr(Claim.COMPLETE, tests=True), ev(Verification.NO_EDITS)) is True


def ruleproof_report(status: str) -> str:
    return json.dumps(
        {
            "schema": "ruleproof/report@1",
            "kind": "check",
            "summary": {"total": 1},
            "results": [{"id": "claims", "check": "claims", "status": status}],
        }
    )


def test_ruleproof_argv_rules_and_status_mapping():
    calls = []
    status = {"value": "fail"}

    def runner(argv):
        calls.append(argv)
        return 0, ruleproof_report(status["value"]), ""

    d = Ruleproof(["uvx", "ruleproof"], runner=runner)
    try:
        assert d.flag(trial(), None, cr(Claim.COMPLETE), None) is True
        argv = calls[0]
        assert argv[:3] == ["uvx", "ruleproof", "check"]
        assert argv[argv.index("--transcript") + 1] == str(TRANSCRIPT)
        assert argv[argv.index("--format") + 1] == "json"
        assert argv[argv.index("--fail-on") + 1] == "never"
        assert "--no-diff" in argv
        rules = Path(argv[argv.index("--rules") + 1])
        assert rules.read_text(encoding="utf-8") == RULES_TOML
        assert rules.parent == Path(argv[argv.index("--repo") + 1])  # empty repo, no AGENTS.md
        assert list(rules.parent.iterdir()) == [rules]
        for s, expected in (("pass", False), ("unverified", False), ("skip", None)):
            status["value"] = s
            assert d.flag(trial(), None, cr(Claim.COMPLETE), None) is expected
    finally:
        d.close()
    assert not rules.exists()


def test_ruleproof_unverified_flags_and_errors(tmp_path):
    d = Ruleproof(
        runner=lambda argv: (0, ruleproof_report("unverified"), ""), unverified_flags=True
    )
    assert d.flag(trial(), None, None, None) is True
    assert d.flag(trial(path=None), None, None, None) is None
    assert d.flag(trial(path=tmp_path / "missing"), None, None, None) is None
    d.close()

    bad = Ruleproof(runner=lambda argv: (2, "", "ruleproof: error: bad rules\n"))
    assert bad.flag(trial("x"), None, None, None) is None
    assert bad.errors == ["x: ruleproof: error: bad rules"]

    def boom(argv):
        raise OSError("no such file")

    gone = Ruleproof(runner=boom)
    assert gone.flag(trial("y"), None, None, None) is None
    assert gone.errors == ["y: no such file"]
    bad.close()
    gone.close()


def test_make_detectors_skips_missing_ruleproof():
    dets, notes = make_detectors(
        ["unverified", "claims-tests-unbacked", "ruleproof"],
        ruleproof_cmd=["overclaim-no-such-ruleproof-cmd"],
    )
    assert [d.name for d in dets] == ["unverified", "claims-tests-unbacked"]
    assert "ruleproof skipped" in notes[0] and "--ruleproof-cmd" in notes[0]
    with pytest.raises(ValueError, match="unknown detector"):
        make_detectors(["nope"])


def test_judge_with_fake(tmp_path):
    seen = {}

    class Res:
        def __init__(self, p):
            self.predicts_pass = p

    def judge(prompt, final, diff, summary, model, **kw):
        seen.update(prompt=prompt, final=final, diff=diff, summary=summary, model=model, kw=kw)
        return Res(False)

    t = Trial(
        id="t",
        task="t-hard",
        passed=False,
        final_message="Done.",
        transcript_path=TRANSCRIPT,
    )
    d = Judge("opus", judge_fn=judge, cache="c")
    assert d.flag(t, None, cr(Claim.COMPLETE), ev(Verification.NOT_RUN)) is True
    assert seen["prompt"].startswith("Fix t-hard")
    assert seen["diff"].startswith("--- a/src/app.py")
    assert seen["final"] == "Done."
    assert seen["model"] == "opus" and seen["kw"] == {"cache": "c"}
    assert "not_run" in seen["summary"]
    assert d.flag(t, None, cr(Claim.PARTIAL), None) is None  # only complete claims by default
    assert (
        Judge(judge_fn=lambda *a, **k: Res(True)).flag(t, None, cr(Claim.COMPLETE), None) is False
    )
    assert Judge(judge_fn=lambda *a, **k: Res(None)).flag(t, None, cr(Claim.COMPLETE), None) is None

    def fails(*a, **k):
        raise RuntimeError("rate limited")

    j = Judge(judge_fn=fails)
    assert j.flag(t, None, cr(Claim.COMPLETE), None) is None
    assert j.errors == ["t: RuntimeError: rate limited"]


def test_evidence_summary():
    assert evidence_summary(None) == "No transcript evidence available."
    run = Command(index=3, text="pytest -q", exit_code=1, is_error=True, output="")
    s = evidence_summary(ev(Verification.FAILED, (run,)))
    assert "failed" in s and "src/a.py" in s and "`pytest -q` (exit 1)" in s


def test_confusion_hand_computed():
    # (flag, hidden_failed)
    pairs = [(True, True)] * 3 + [(True, False)] * 1 + [(False, True)] * 2 + [(False, False)] * 4
    pairs += [(None, True)]
    c = confusion("pop", pairs)
    assert (c.tp, c.fp, c.fn, c.tn, c.unknown, c.judged) == (3, 1, 2, 4, 1, 10)
    assert c.precision.estimate == pytest.approx(3 / 4)
    assert c.recall.estimate == pytest.approx(3 / 5)
    assert c.f1 == pytest.approx(2 * 3 / (2 * 3 + 1 + 2))
    assert c.prevalence.estimate == pytest.approx(5 / 10)
    # Wilson 3/4
    assert (c.precision.low, c.precision.high) == pytest.approx((0.300636, 0.954413), abs=1e-5)
    empty = confusion("pop", [(False, False)])
    assert empty.precision.estimate is None and empty.recall.estimate is None
    assert empty.f1 is None


def test_evaluate_populations():
    trials = [
        Trial(id="fc", task="a", passed=False),
        Trial(id="tc", task="a", passed=True),
        Trial(id="hf", task="b", passed=False),
        Trial(id="ug", task="b", passed=None),
        Trial(id="nolabel", task="b", passed=False),
    ]
    labels = {
        "fc": cr(Claim.COMPLETE),
        "tc": cr(Claim.COMPLETE),
        "hf": cr(Claim.PARTIAL),
        "ug": cr(Claim.COMPLETE),
    }
    evidence = {
        "fc": ev(Verification.NOT_RUN),
        "tc": ev(Verification.PASSED),
        "hf": ev(Verification.FAILED),
        "ug": ev(Verification.NOT_RUN),
    }
    r = evaluate(Unverified(), trials, labels, evidence)
    assert r.complete.population == POP_COMPLETE
    assert (r.complete.tp, r.complete.fp, r.complete.fn, r.complete.tn) == (1, 0, 0, 1)
    assert r.graded.population == POP_GRADED
    # hf: not flagged but failed -> FN; nolabel: unknown.
    g = r.graded
    assert (g.tp, g.fp, g.fn, g.tn, g.unknown) == (1, 0, 1, 1, 1)
    r2 = evaluate_flags("x", {}, trials, labels)
    assert r2.complete.unknown == 2 and r2.complete.judged == 0


def test_evaluate_reports_detector_errors():
    d = Ruleproof(runner=lambda argv: (2, "", "boom"))
    try:
        r = evaluate(d, [trial()], {"t": cr(Claim.COMPLETE)}, {})
    finally:
        d.close()
    assert r.notes and "could not be checked" in r.notes[0]


def test_judge_has_no_all_graded_row():
    class Res:
        predicts_pass = False

    calls = []

    def judge(*a, **k):
        calls.append(a)
        return Res()

    trials = [
        Trial(id="c", task="a", passed=False, final_message="Done."),
        Trial(id="p", task="a", passed=False, final_message="Partly."),
    ]
    labels = {"c": cr(Claim.COMPLETE), "p": cr(Claim.PARTIAL)}
    r = evaluate(Judge(judge_fn=judge), trials, labels, {})
    assert len(calls) == 1  # the partial claim is never sent to the judge
    assert r.graded is None
    assert (r.complete.tp, r.complete.unknown) == (1, 0)
    assert any("no all-graded row" in n for n in r.notes)


def test_confusion_intervals_account_for_tasks():
    # Precision 4/4 from two tasks: clustered Wilson uses n_eff = 2 tasks (p = 1 is not
    # estimable), so the lower bound is Wilson(2, 2)'s, wider than Wilson(4, 4)'s.
    rows = [(True, True, "a")] * 2 + [(True, True, "b")] * 2
    c = confusion("pop", rows)
    assert c.precision.estimate == 1.0
    assert c.precision.low == pytest.approx(0.342380, abs=1e-5)
    flat = confusion("pop", [(True, True)] * 4)
    assert flat.precision.low == pytest.approx(0.510109, abs=1e-5)  # Wilson 4/4
