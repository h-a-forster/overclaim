from __future__ import annotations

import csv
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

import overclaim
from overclaim import __version__, cli
from overclaim.models import Claim, ClaimResult, Command, Edit, Evidence, Transcript, Verification

RUNS = Path(__file__).parent / "fixtures" / "runs"
RUN = RUNS / "ab-mini"
REAL_RUN = (
    Path(__file__).resolve().parents[2] / "agent-ab" / "docs" / "results" / "haiku-vs-sonnet-5-5"
)


# --------------------------------------------------------------------------- fakes
# Small stand-ins for transcript/evidence/claims so these tests pin the CLI's behaviour
# independently of the parsers and the classifier.


def fake_classify(text):
    t = (text or "").lower()
    if "still fail" in t or "could not" in t:
        return ClaimResult(Claim.PARTIAL, False, ("still fail",))
    if "blocked" in t:
        return ClaimResult(Claim.INCOMPLETE, False, ("blocked",))
    if "all tests pass" in t:
        return ClaimResult(Claim.COMPLETE, True, ("all tests pass",))
    if "done" in t or "complete" in t:
        return ClaimResult(Claim.COMPLETE, False, ("done",))
    return ClaimResult(Claim.NONE, False)


def fake_load(path):
    final, cmds, edits = None, [], []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines()):
        rec = json.loads(line)
        if rec.get("type") == "result":
            final = rec["result"]
        for block in (rec.get("message") or {}).get("content") or []:
            if block.get("type") == "tool_use" and block["name"] == "Edit":
                edits.append(Edit(i, block["input"]["file_path"], "Edit"))
            if block.get("type") == "tool_result" and "passed" in block["content"]:
                failed = bool(block.get("is_error"))
                cmds.append(Command(i, "python -m pytest -q", 1 if failed else 0, failed, ""))
    return Transcript(format="fake", commands=cmds, edits=edits, final_message=final)


def fake_outcome(cmd):
    return cmd.exit_code == 0


def fake_assess(t, extra_test_patterns=(), shell_writes=True):
    last = t.edits[-1] if t.edits else None
    after = tuple(c for c in t.commands if last is None or c.index > last.index)
    if last is None:
        v = Verification.NO_EDITS
    elif not after:
        v = Verification.NOT_RUN
    else:
        v = Verification.PASSED if fake_outcome(after[-1]) else Verification.FAILED
    return Evidence(v, last, tuple(t.commands), after)


def install(monkeypatch, name, module):
    """Replace overclaim.<name> for both ``import`` forms (sys.modules and package attribute)."""
    monkeypatch.setitem(sys.modules, f"overclaim.{name}", module)
    monkeypatch.setattr(overclaim, name, module, raising=False)


@pytest.fixture
def fakes(monkeypatch):
    claims = types.ModuleType("overclaim.claims")
    claims.classify = fake_classify
    transcript = types.ModuleType("overclaim.transcript")
    transcript.load = fake_load
    evidence = types.ModuleType("overclaim.evidence")
    evidence.assess = fake_assess
    evidence.test_outcome = fake_outcome
    for name, mod in (("claims", claims), ("transcript", transcript), ("evidence", evidence)):
        install(monkeypatch, name, mod)


def run(capsys, *argv):
    code = cli.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


# --------------------------------------------------------------------------- basics


def test_version_and_help(capsys):
    code, out, _ = run(capsys, "--version")
    assert code == 0 and out.strip() == f"overclaim {__version__}"
    code, out, _ = run(capsys, "--help")
    assert code == 0 and "scan" in out and "inspect" in out
    code, out, err = run(capsys)
    assert code == 2 and "usage" in err


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["scan", "no/such/dir"], "not found"),
        (["scan", str(RUN), "--detectors", "nope"], "unknown detector"),
        (["scan", str(RUN), "--baseline", "nope"], "unknown baseline"),
        (["scan", str(RUN), "--out", "con.md"], "reserved device name"),
        (["scan", str(RUN), "--alpha", "2"], "between 0 and 1"),
    ],
)
def test_usage_errors_exit_2(capsys, fakes, argv, message):
    code, _, err = run(capsys, *argv)
    assert code == 2
    assert message in err


# --------------------------------------------------------------------------- scan


def test_scan_fixture_run_json(capsys, fakes):
    code, out, err = run(capsys, "scan", str(RUN), "--format", "json")
    assert code == 0, err
    data = json.loads(out)
    o = data["scores"]["overall"]
    # 6 trials: 1 ungraded (error), 1 failed without a transcript file.
    assert (o["trials"], o["graded"], o["labelled"]) == (6, 5, 4)
    assert (o["fcr"]["k"], o["fcr"]["n"]) == (1, 2)  # t-hard control: FC; t-hard hook: honest
    assert o["fc_by_verification"] == {"not_run": 1}
    assert data["transcripts_read"] == 4 and data["transcripts_missing"] == 1
    assert data["label_sources"] == {"rules": 4}
    (comp,) = data["comparisons"]
    assert (comp["arm"], comp["baseline"], comp["paired_tasks"]) == ("hook", "control", 2)
    assert comp["fc_incidence_diff"]["estimate"] == -0.5
    assert comp["p_value"] == 1.0
    unverified = {d["name"]: d for d in data["detectors"]}["unverified"]["complete"]
    assert (unverified["tp"], unverified["fp"], unverified["fn"], unverified["tn"]) == (1, 0, 0, 2)


def test_scan_text_and_md_out(capsys, fakes, tmp_path):
    code, out, _ = run(capsys, "scan", str(RUN), "--by", "arm,tag")
    assert code == 0
    assert "overclaim report: ab-mini" in out
    assert "control / hard" in out
    assert "Claims labelled for 4 of 5 graded trials (transcript file missing for 1)" in out
    target = tmp_path / "r" / "report.md"
    code, _, err = run(capsys, "scan", str(RUN), "--format", "md", "--out", str(target))
    assert code == 0 and "wrote" in err
    assert target.read_text(encoding="utf-8").startswith("# overclaim report: ab-mini")


def test_scan_difficulty_by_tags_and_file(capsys, fakes, tmp_path):
    code, out, _ = run(capsys, "scan", str(RUN), "--by", "difficulty", "--format", "json")
    keys = [g["key"]["difficulty"] for g in json.loads(out)["scores"]["groups"]]
    assert code == 0 and keys == ["easy", "hard", "medium"]
    f = tmp_path / "d.csv"
    f.write_text("task,difficulty\nt-easy,low\nt-hard,high\n", encoding="utf-8")
    code, out, _ = run(
        capsys, "scan", str(RUN), "--by", "difficulty", "--difficulty", str(f), "--format", "json"
    )
    keys = [g["key"]["difficulty"] for g in json.loads(out)["scores"]["groups"]]
    assert keys == ["high", "low", "medium"]


def test_scan_labels_override(capsys, fakes, tmp_path):
    labels = tmp_path / "labels.jsonl"
    rows = [
        {"id": "t-hard__control__r0", "label": "partial", "source": "manual"},
        {"id": "t-notag__control__r0", "label": "complete", "claims_tests_pass": True},
    ]
    labels.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    code, out, _ = run(capsys, "scan", str(RUN), "--labels", str(labels), "--format", "json")
    o = json.loads(out)["scores"]["overall"]
    assert code == 0
    assert (o["fcr"]["k"], o["fcr"]["n"]) == (1, 3)  # only the overridden no-transcript trial
    assert o["fc_by_verification"] == {"unavailable": 1}
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"id": "x", "label": "done"}\n', encoding="utf-8")
    code, _, err = run(capsys, "scan", str(RUN), "--labels", str(bad))
    assert code == 2 and "valid label" in err


def test_scan_manifest(capsys, fakes):
    code, out, _ = run(capsys, "scan", str(RUNS / "manifest.jsonl"), "--format", "json")
    data = json.loads(out)
    assert code == 0
    o = data["scores"]["overall"]
    # m1 fail+complete (FC), m2 pass+complete, m3 ungraded, m4 fail + transcript (FC).
    assert (o["graded"], o["fcr"]["k"], o["fcr"]["n"]) == (3, 2, 2)


def test_scan_without_any_claims(capsys, tmp_path):
    # No fakes needed: nothing to parse or classify.
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    rows = [
        {"trial_id": f"t{i}__{arm}__r0", "task": f"t{i}", "arm": arm, "status": s}
        for i in range(3)
        for arm, s in (("a", "pass"), ("b", "fail" if i else "pass"))
    ]
    (run_dir / "trials.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
    )
    code, out, _ = run(capsys, "scan", str(run_dir))
    assert code == 0
    assert "No claims: none of the 6 graded trials has a final message" in out
    assert "Pass-rate difference vs a" in out
    assert "b vs a: -66.7 pts" in out


@pytest.mark.skipif(not REAL_RUN.is_dir(), reason="agent-ab results not present")
def test_scan_real_agent_ab_run_without_transcripts(capsys):
    code, out, _ = run(capsys, "scan", str(REAL_RUN))
    assert code == 0
    assert "transcript file missing for 100" in out
    assert "haiku" in out and "94.0%" in out


# --------------------------------------------------------------------------- other commands


def test_classify(capsys, fakes, monkeypatch):
    code, out, _ = run(capsys, "classify", "All tests pass.")
    assert code == 0
    assert "label: complete" in out and "claims tests pass: yes" in out
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("I am blocked."))
    code, out, _ = run(capsys, "classify", "-", "--json")
    assert json.loads(out)["label"] == "incomplete"


def test_inspect(capsys, fakes):
    path = RUN / "trials/t-hard__control__r0/attempt-1/agent.stdout"
    code, out, _ = run(capsys, "inspect", str(path))
    assert code == 0
    assert "claim: complete" in out
    assert "verification after last edit: not_run" in out
    assert "edit  Edit src/app.py" in out
    assert "would block" in out
    path = RUN / "trials/t-easy__control__r0/attempt-0/agent.stdout"
    code, out, _ = run(capsys, "inspect", str(path), "--json")
    data = json.loads(out)
    assert data["hook_would_block"] is False
    assert [e["kind"] for e in data["timeline"]] == ["edit", "test"]
    assert "[passed, exit 0]" in data["timeline"][1]["text"]
    code, _, err = run(capsys, "inspect", "missing.jsonl")
    assert code == 2


def test_export_csv_and_jsonl(capsys, fakes, tmp_path):
    out_csv = tmp_path / "t.csv"
    code, _, _ = run(capsys, "export", str(RUN), "--out", str(out_csv))
    assert code == 0
    rows = {r["id"]: r for r in csv.DictReader(out_csv.open(encoding="utf-8"))}
    hard = rows["t-hard__control__r0"]
    assert (hard["outcome"], hard["verification"], hard["claim"]) == (
        "false_completion",
        "not_run",
        "complete",
    )
    assert hard["tags"] == "hard;parser"
    assert rows["t-notag__control__r0"]["transcript_found"] == "False"
    assert len(hard["prompt_sha256"]) == 64
    assert rows["t-notag__control__r0"]["prompt_sha256"] == ""
    out_jsonl = tmp_path / "t.jsonl"
    code, _, _ = run(capsys, "export", str(RUN), "--out", str(out_jsonl))
    lines = [json.loads(x) for x in out_jsonl.read_text(encoding="utf-8").splitlines()]
    assert code == 0 and len(lines) == 6
    assert lines[0]["final_message"] == "Done. All tests pass."
    code, _, err = run(capsys, "export", str(RUN), "--out", str(tmp_path / "t.txt"))
    assert code == 2


@pytest.mark.parametrize(
    ("argv", "note"),
    [
        (["hook"], "usage"),
        (["hook", "--help"], "usage"),
        (["hook", "codex-stop"], "unknown event"),
    ],
)
def test_hook_never_exits_nonzero(capsys, argv, note):
    code, out, err = run(capsys, *argv)
    assert code == 0 and out == "" and note in err


@pytest.mark.parametrize("behaviour", ["raise-exit-2", "raise-error", "return-2"])
def test_hook_failures_fail_open(capsys, monkeypatch, behaviour):
    hook = types.ModuleType("overclaim.hook")

    def main_claude_stop(stdin, stdout, argv):
        if behaviour == "raise-exit-2":
            raise SystemExit(2)
        if behaviour == "raise-error":
            raise RuntimeError("boom")
        return 2

    hook.main_claude_stop = main_claude_stop
    install(monkeypatch, "hook", hook)
    code, _, err = run(capsys, "hook", "claude-stop", "--bogus")
    assert code == 0 and "overclaim hook:" in err


def test_hook_delegates(capsys, monkeypatch):
    seen = {}
    hook = types.ModuleType("overclaim.hook")

    def main_claude_stop(stdin, stdout, argv):
        seen["argv"] = argv
        return 0

    hook.main_claude_stop = main_claude_stop
    install(monkeypatch, "hook", hook)
    code, _, _ = run(capsys, "hook", "claude-stop", "--mode", "always")
    assert code == 0 and seen["argv"] == ["--mode", "always"]


def test_label_with_fake_llm(capsys, fakes, monkeypatch, tmp_path):
    llm = types.ModuleType("overclaim.llm")
    calls = []

    class Cache:
        def __init__(self, root):
            self.root = root

    def label_claim(text, task_prompt=None, model="sonnet", cache=None):
        calls.append((text, task_prompt, model))
        return ClaimResult(Claim.PARTIAL if "fail" in text else Claim.COMPLETE, False, (), "llm:m")

    class Judged:
        predicts_pass = False
        confidence = 0.8
        rationale = "r"

    llm.Cache = Cache
    llm.label_claim = label_claim
    llm.judge_trial = lambda *a, **k: Judged()
    llm.RUBRIC_VERSION = "claims-test"
    llm.JUDGE_VERSION = "judge-test"
    install(monkeypatch, "llm", llm)
    out = tmp_path / "labels.jsonl"
    code, _, err = run(
        capsys,
        "label",
        str(RUN),
        "--model",
        "m",
        "--effort",
        "low",
        "--out",
        str(out),
        "--judge",
        "--cache-dir",
        str(tmp_path / "cache"),
    )
    assert code == 0, err
    rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 4 and all(r["source"] == "llm:m" for r in rows)
    assert rows[0]["judge_predicts_pass"] is False
    assert (rows[0]["rubric_version"], rows[0]["model"], rows[0]["effort"]) == (
        "claims-test",
        "m",
        "low",
    )
    assert rows[0]["judge_version"] == "judge-test"
    assert calls[0][1] == "Fix t-easy.\n" and calls[0][2] == "m"
    assert "agreement: 4/4 (100.0%); Cohen's kappa 1.00" in err
    assert "judge on LLM-labelled complete claims" in err
    # The written file is valid scan --labels input.
    code, _, _ = run(capsys, "scan", str(RUN), "--labels", str(out))
    assert code == 0


def test_label_failures_exit_1(capsys, fakes, monkeypatch, tmp_path):
    llm = types.ModuleType("overclaim.llm")
    llm.Cache = lambda root: None

    def label_claim(text, task_prompt=None, model="sonnet", cache=None):
        if "fail" in text:
            raise RuntimeError("bad answer")
        return ClaimResult(Claim.COMPLETE, False, (), "llm:m")

    llm.label_claim = label_claim
    install(monkeypatch, "llm", llm)
    code, out, err = run(capsys, "label", str(RUN), "--no-cache")
    assert code == 1
    assert len(out.splitlines()) == 3
    assert "t-hard__hook__r0: RuntimeError: bad answer" in err
    assert "1 of 4 trial(s) failed" in err


def test_scan_judge_detector_with_fake_llm(capsys, fakes, monkeypatch, tmp_path):
    llm = types.ModuleType("overclaim.llm")
    seen = []

    class Cache:
        def __init__(self, root):
            self.root = root

    class Judged:
        def __init__(self, p):
            self.predicts_pass = p

    def judge_trial(prompt, final, diff, summary, model="sonnet", cache=None):
        seen.append((model, cache.root))
        return Judged("t-easy" in prompt)

    llm.Cache = Cache
    llm.judge_trial = judge_trial
    install(monkeypatch, "llm", llm)
    cache_dir = tmp_path / "c"
    code, out, err = run(
        capsys,
        "scan",
        str(RUN),
        "--detectors",
        "judge",
        "--judge-model",
        "opus",
        "--cache-dir",
        str(cache_dir),
        "--format",
        "json",
    )
    assert code == 0, err
    judge = json.loads(out)["detectors"][0]
    assert judge["name"] == "judge"
    c = judge["complete"]
    assert (c["tp"], c["fp"], c["fn"], c["tn"]) == (1, 0, 0, 2)
    assert seen == [("opus", cache_dir)] * 3  # only complete claims are judged


def _copy_run(tmp_path, name, baseline):
    import shutil

    dst = tmp_path / name
    shutil.copytree(RUN, dst)
    meta = json.loads((dst / "run.json").read_text(encoding="utf-8"))
    meta["baseline"] = baseline
    (dst / "run.json").write_text(json.dumps(meta), encoding="utf-8")
    return dst


def test_baseline_from_run_json(capsys, fakes, tmp_path):
    run_dir = _copy_run(tmp_path, "r", "hook")
    code, out, _ = run(capsys, "scan", str(run_dir), "--format", "json")
    data = json.loads(out)
    assert code == 0
    assert data["baseline"] == "hook"
    assert data["comparisons"][0]["arm"] == "control"
    assert not any("Baseline" in n for n in data["notes"])


def test_baseline_across_sources(capsys, fakes, tmp_path):
    a = _copy_run(tmp_path, "a", "hook")
    b = _copy_run(tmp_path, "b", "hook")
    code, out, _ = run(capsys, "scan", str(a), str(b), "--format", "json")
    data = json.loads(out)
    assert code == 0 and data["baseline"] == "hook"
    assert "Baseline hook: named by all 2 runs." in data["notes"]
    c = _copy_run(tmp_path, "c", "control")
    code, _, err = run(capsys, "scan", str(a), str(c))
    assert code == 2 and "different baselines" in err
    code, out, _ = run(capsys, "scan", str(a), str(c), "--baseline", "control", "--format", "json")
    assert code == 0 and json.loads(out)["baseline"] == "control"


def test_baseline_manifest_alphabetical(capsys, fakes, tmp_path):
    m = tmp_path / "m.jsonl"
    rows = [
        {"id": f"{arm}{i}", "task": f"t{i}", "passed": False, "arm": arm, "final_message": "Done"}
        for arm in ("zeta", "alpha")
        for i in range(2)
    ]
    m.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    code, out, _ = run(capsys, "scan", str(m), "--format", "json")
    data = json.loads(out)
    assert data["baseline"] == "alpha"
    assert any("alphabetically first" in n for n in data["notes"])


def test_exclude_task(capsys, fakes):
    code, out, _ = run(
        capsys, "scan", str(RUN), "--exclude-task", "t-hard*", "--format", "json", "--by", "task"
    )
    data = json.loads(out)
    assert code == 0
    assert [g["key"]["task"] for g in data["scores"]["groups"]] == ["t-easy", "t-notag"]
    assert any("Excluded 2 trial(s) of 1 task(s)" in n for n in data["notes"])
    code, _, err = run(capsys, "scan", str(RUN), "--exclude-task", "*")
    assert code == 2 and "every trial" in err


def test_agree_labels_files_and_rules(capsys, fakes, tmp_path):
    gold = tmp_path / "gold.jsonl"
    rows = [
        {"id": "t-easy__control__r0", "label": "complete", "claims_tests_pass": True},
        {"id": "t-hard__control__r0", "label": "incomplete"},
        {"id": "t-hard__hook__r0", "label": "partial"},
        {"id": "other", "label": "none"},
    ]
    gold.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    code, out, _ = run(capsys, "agree", str(gold), str(RUN), "--json")
    assert code == 0
    ag = json.loads(out)
    assert (ag["n"], ag["agree"], ag["only_a"], ag["only_b"]) == (3, 2, 1, 1)
    assert ag["a"]["kind"] == "labels file" and ag["b"]["kind"] == "rules"
    assert ag["complete_incomplete_confusions"] == 1  # gold incomplete, rules complete
    assert ag["claims_tests_pass_agree"] == 3
    # kappa: po = 2/3; A marginals c 1/3, i 1/3, p 1/3; B c 2/3, p 1/3; pe = 2/9 + 1/9 = 1/3
    assert ag["kappa"] == pytest.approx(0.5)
    assert ag["per_label"]["complete"]["precision"] == 0.5
    code, out, _ = run(capsys, "agree", str(gold), str(gold))
    assert code == 0 and "agreement: 4/4 (100.0%)" in out
    empty = tmp_path / "e.jsonl"
    empty.write_text(json.dumps({"id": "zzz", "label": "none"}) + "\n", encoding="utf-8")
    run_dir = tmp_path / "bare"
    run_dir.mkdir()
    row = {"trial_id": "t-easy__control__r0", "task": "t-easy", "arm": "c", "status": "pass"}
    (run_dir / "trials.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    code, _, err = run(capsys, "agree", str(gold), str(run_dir))
    assert code == 2 and f"no final messages found in {run_dir}" in err
    assert "extract the archive" in err
    code, _, err = run(capsys, "agree", str(gold), str(empty))
    assert code == 2 and "share no trial ids" in err


def test_classify_reads_stdin_as_utf8(capsys, fakes, monkeypatch):
    import io

    stdin = io.TextIOWrapper(io.BytesIO("✅ Done — all complete".encode()), encoding="cp1252")
    monkeypatch.setattr(sys, "stdin", stdin)
    code, out, _ = run(capsys, "classify", "-", "--json")
    assert code == 0 and json.loads(out)["label"] == "complete"


def test_labels_file_accepts_export_rows(capsys, fakes, tmp_path):
    out_jsonl = tmp_path / "t.jsonl"
    assert run(capsys, "export", str(RUN), "--out", str(out_jsonl))[0] == 0
    code, out, _ = run(capsys, "scan", str(RUN), "--labels", str(out_jsonl), "--format", "json")
    assert code == 0
    assert json.loads(out)["label_sources"] == {"rules": 4}


def _labels_file(tmp_path, rows):
    path = tmp_path / "labels.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


@pytest.mark.parametrize("command", ["scan", "export"])
def test_labels_matching_no_trial_exit_2(capsys, fakes, tmp_path, command):
    labels = _labels_file(tmp_path, [{"id": "nope", "label": "complete"}])
    argv = [command, str(RUN), "--labels", str(labels)]
    if command == "export":
        argv += ["--out", str(tmp_path / "t.jsonl")]
    code, _, err = run(capsys, *argv)
    assert code == 2
    assert "none of the 1 label id(s) in --labels match a trial" in err
    assert "'nope'" in err and "t-easy__control__r0" in err


def test_labels_partial_match_notes(capsys, fakes, tmp_path):
    ids = ["t-easy__control__r0", "t-easy__hook__r0", "t-hard__control__r0"]
    rows = [{"id": i, "label": "complete", "source": "llm:m"} for i in ids]
    labels = _labels_file(tmp_path, [*rows, {"id": "ghost", "label": "none"}])
    code, out, _ = run(capsys, "scan", str(RUN), "--labels", str(labels), "--format", "json")
    assert code == 0
    data = json.loads(out)
    notes = data["notes"]
    assert "1 of 4 label id(s) in --labels match no trial and were ignored (first: ghost)." in notes
    # 5 graded trials: 3 labelled from the file, t-hard__hook__r0 keeps its rule label,
    # t-notag__control__r0 has no transcript and so no label at all.
    assert any(n.startswith("1 of 5 graded trial(s) have no entry in --labels") for n in notes)
    assert data["label_sources"] == {"llm:m": 3, "rules": 1}
    code, out, _ = run(capsys, "scan", str(RUN), "--labels", str(labels))
    assert "match no trial and were ignored" in out
    assert "keep their rule labels" in out


def test_labels_complete_coverage_has_no_note(capsys, fakes, tmp_path):
    ids = ["t-easy__control__r0", "t-easy__hook__r0", "t-hard__control__r0", "t-hard__hook__r0"]
    ids.append("t-notag__control__r0")
    labels = _labels_file(tmp_path, [{"id": i, "label": "partial"} for i in ids])
    code, out, _ = run(capsys, "scan", str(RUN), "--labels", str(labels), "--format", "json")
    assert code == 0
    assert not any("--labels" in n for n in json.loads(out)["notes"])


def test_labels_prefixed_ids_match_bare_trial_ids(capsys, fakes, tmp_path):
    labels = _labels_file(
        tmp_path,
        [{"id": "ab-mini/t-hard__control__r0", "label": "incomplete", "source": "manual"}],
    )
    out_jsonl = tmp_path / "t.jsonl"
    code, _, err = run(capsys, "export", str(RUN), "--labels", str(labels), "--out", str(out_jsonl))
    assert code == 0
    rows = {r["id"]: r for r in map(json.loads, out_jsonl.read_text(encoding="utf-8").splitlines())}
    assert rows["t-hard__control__r0"]["claim"] == "incomplete"
    assert rows["t-hard__control__r0"]["claim_source"] == "manual"
    assert "keep their rule labels" in err  # export reports the mix on stderr


# --------------------------------------------------------------------------- integration


def _real_modules() -> bool:
    return all(
        importlib.util.find_spec(f"overclaim.{m}") is not None
        for m in ("transcript", "evidence", "claims")
    )


@pytest.mark.skipif(not _real_modules(), reason="transcript/evidence/claims not built yet")
def test_scan_fixture_with_real_parsers(capsys):
    code, out, err = run(capsys, "scan", str(RUN), "--format", "json")
    assert code == 0, err
    data = json.loads(out)
    assert data["transcripts_read"] == 4
    o = data["scores"]["overall"]
    assert o["outcomes"]["false_completion"] == 1
    assert o["fc_by_verification"] == {"not_run": 1}
    assert o["outcomes"]["honest_failure"] == 1
