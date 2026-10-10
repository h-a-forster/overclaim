from __future__ import annotations

import json
import re

from overclaim.detectors import evaluate_flags
from overclaim.metrics import compare_arms, score
from overclaim.models import Claim, ClaimResult, Evidence, Trial, Verification
from overclaim.report import (
    Scan,
    fmt_p,
    fmt_pct,
    fmt_pts,
    render,
    render_json,
    render_markdown,
    render_text,
)


def build():
    trials, labels, evidence = [], {}, {}
    plan = {
        "control": [(False, Claim.COMPLETE), (True, Claim.COMPLETE), (False, Claim.COMPLETE)],
        "hook": [(False, Claim.PARTIAL), (True, Claim.COMPLETE), (False, Claim.COMPLETE)],
    }
    for arm, rows in plan.items():
        for i, (passed, claim) in enumerate(rows):
            tid = f"t{i}__{arm}"
            trials.append(Trial(id=tid, task=f"t{i}", passed=passed, arm=arm))
            labels[tid] = ClaimResult(label=claim, claims_tests_pass=i == 0)
            evidence[tid] = Evidence(Verification.NOT_RUN, None, (), ())
    return trials, labels, evidence


def make_scan(with_labels=True):
    trials, labels, evidence = build()
    if not with_labels:
        labels, evidence = {}, {}
    scores = score(trials, labels, evidence, by=("arm",))
    flags = {t.id: not t.passed for t in trials}
    return Scan(
        title="demo",
        sources=["runs/demo"],
        scores=scores,
        comparisons=compare_arms(trials, labels, "control"),
        baseline="control",
        detectors=[evaluate_flags("oracle", flags, trials, labels)] if with_labels else [],
        transcripts_read=6 if with_labels else 0,
        transcripts_missing=0 if with_labels else 6,
        label_sources={"rules": 6} if with_labels else {},
    )


def test_formatters():
    assert fmt_pct(0.4167) == "41.7%"
    assert fmt_pct(None) == "-"
    assert fmt_pts(0.042) == "+4.2 pts"
    assert fmt_pts(-0.0001) == "0.0 pts"
    assert fmt_p(0.0004) == "<0.001"
    assert fmt_p(0.5) == "0.50"
    assert fmt_p(0.012) == "0.012"
    assert fmt_p(float("nan")) == "-"


def test_text_report_sections():
    text = render_text(make_scan())
    assert text.startswith("overclaim report: demo\n")
    assert "By arm (95% CI" in text
    assert "FCR" in text and "false-claim share" in text
    assert "False completions by the agent's own verification" in text
    assert "hook vs control:" in text and "no detectable difference" in text
    assert "Detectors (positive = hidden check failed" in text
    assert re.search(r"oracle +claimed complete +5 +0 +3 +0 +0 +2 +100\.0%", text)
    assert text.isascii()
    # control: 2 failures, both claimed complete -> FCR 100%; hook: 1 of 2.
    control = next(ln for ln in text.splitlines() if ln.startswith("  control"))
    assert "2/2" in control and "100.0%" in control
    hook = next(ln for ln in text.splitlines() if ln.startswith("  hook"))
    assert "1/2" in hook and "50.0%" in hook


def test_text_report_without_claims():
    text = render_text(make_scan(with_labels=False))
    assert "No claims: none of the 6 graded trials has a final message" in text
    assert "transcript file missing for 6" in text
    assert "Pass-rate difference vs control" in text
    assert "False completions are not compared" in text
    assert "FCR" not in text
    assert text.count("final message") == 1  # stated once, not repeated in the notes


def test_markdown_report():
    md = render_markdown(make_scan())
    assert md.startswith("# overclaim report: demo\n")
    assert "## By arm" in md
    assert "| control |" in md
    assert "## False-completion incidence vs control" in md
    assert "## Detectors" in md
    assert "## Notes" in md


def test_json_report_round_trips():
    data = json.loads(render_json(make_scan()))
    assert data["schema"] == 1 and data["tool"] == "overclaim"
    assert data["scores"]["by"] == ["arm"]
    assert data["scores"]["overall"]["key"] == {}
    groups = {g["key"]["arm"]: g for g in data["scores"]["groups"]}
    assert groups["control"]["fcr"]["k"] == 2 and groups["control"]["fcr"]["n"] == 2
    assert data["comparisons"][0]["verdict"] == "no detectable difference"
    assert data["detectors"][0]["complete"]["tp"] == 3
    assert isinstance(data["notes"], list)


def test_render_is_deterministic():
    assert render(make_scan(), "text") == render(make_scan(), "text")
    assert render(make_scan(), "json") == render(make_scan(), "json")
