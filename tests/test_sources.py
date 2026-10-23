from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from overclaim.sources import (
    SourceError,
    artifact_file,
    load,
    load_agent_ab,
    load_manifest,
    load_many,
    prompt_sha256,
)

RUNS = Path(__file__).parent / "fixtures" / "runs"
RUN = RUNS / "ab-mini"
AGENT_AB_RESULTS = Path(__file__).resolve().parents[2] / "agent-ab" / "docs" / "results"


def by_id(trials):
    return {t.id: t for t in trials}


def test_agent_ab_final_attempt_status_and_metadata():
    trials = by_id(load_agent_ab(RUN))
    assert sorted(trials) == [
        "t-easy__control__r0",
        "t-easy__hook__r0",
        "t-hard__control__r0",
        "t-hard__hook__r0",
        "t-notag__control__r0",
        "t-notag__hook__r0",
    ]
    hard = trials["t-hard__control__r0"]
    assert hard.passed is False  # attempt 1 (fail) supersedes attempt 0 (error)
    assert hard.transcript_path == RUN / "trials/t-hard__control__r0/attempt-1/agent.stdout"
    assert hard.transcript_path.is_file()
    assert hard.model == "claude-haiku-5-5"
    assert hard.effort is None
    assert hard.agent_version == "2.1.296"
    assert hard.cost_usd == 0.02
    assert hard.tags == ("hard", "parser")
    assert hard.group == {"experiment": "ab-mini"}
    assert trials["t-easy__control__r0"].passed is True
    assert trials["t-notag__hook__r0"].passed is None  # infrastructure error: ungraded
    assert trials["t-notag__hook__r0"].transcript_path is None


def test_agent_ab_effort_model_fallback_and_toml_tags():
    trials = by_id(load_agent_ab(RUN))
    hook = trials["t-easy__hook__r0"]
    assert hook.effort == "low"
    assert hook.model == "claude-haiku-5-5"  # arm config has none; reported model is used
    # t-notag has no tags in run.json; they come from its task.toml.
    assert trials["t-notag__control__r0"].tags == ("medium", "from-toml")


def test_agent_ab_missing_transcript_is_not_an_error():
    t = by_id(load_agent_ab(RUN))["t-notag__control__r0"]
    assert t.transcript_path is not None and not t.transcript_path.exists()
    assert artifact_file(t, "prompt.md") is None


def test_artifact_file():
    t = by_id(load_agent_ab(RUN))["t-easy__control__r0"]
    assert artifact_file(t, "prompt.md").read_text(encoding="utf-8").startswith("Fix t-easy")
    assert artifact_file(t, "nope.txt") is None


def test_agent_ab_without_run_json(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "trials.jsonl").write_text(
        json.dumps({"trial_id": "a__x__r0", "task": "a", "arm": "x", "status": "fail"}) + "\n",
        encoding="utf-8",
    )
    (t,) = load_agent_ab(run)
    assert (t.task, t.arm, t.passed, t.tags, t.transcript_path) == ("a", "x", False, (), None)
    assert t.group == {"experiment": "run"}


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_agent_ab_prompt_sha256_from_prompt_file():
    trials = by_id(load_agent_ab(RUN))
    prompt = RUN / "trials/t-easy__control__r0/attempt-0/prompt.md"
    data = prompt.read_bytes().replace(b"\r\n", b"\n")
    assert trials["t-easy__control__r0"].prompt_sha256 == hashlib.sha256(data).hexdigest()
    assert trials["t-notag__control__r0"].prompt_sha256 is None  # no artifacts on disk
    assert trials["t-notag__hook__r0"].prompt_sha256 is None  # no artifacts recorded


def test_prompt_sha256_ignores_line_endings(tmp_path):
    lf, crlf = tmp_path / "lf.md", tmp_path / "crlf.md"
    lf.write_bytes(b"Fix it.\nThen test.\n")
    crlf.write_bytes(b"Fix it.\r\nThen test.\r\n")
    assert prompt_sha256(lf) == prompt_sha256(crlf)
    assert prompt_sha256(lf) == hashlib.sha256(b"Fix it.\nThen test.\n").hexdigest()
    assert prompt_sha256(tmp_path / "missing.md") is None


def test_agent_ab_recorded_prompt_sha256_and_loose_integers(tmp_path):
    digest = "AB" * 32
    rows = [
        {"trial_id": "a__x__r0", "task": "a", "status": "fail", "attempt": "x", "repeat": None},
        {
            "trial_id": "a__x__r0",
            "task": "a",
            "status": "pass",
            "attempt": "1",
            "repeat": "2",
            "prompt_sha256": digest,
        },
        {"trial_id": "b__x__r0", "task": "b", "status": "pass", "prompt_sha256": "not-a-hash"},
    ]
    _write_jsonl(tmp_path / "trials.jsonl", rows)
    (tmp_path / "run.json").write_text(json.dumps({"config": "not-an-object"}), encoding="utf-8")
    trials = by_id(load_agent_ab(tmp_path))
    a = trials["a__x__r0"]
    assert (a.passed, a.repeat, a.prompt_sha256) == (True, 2, digest.lower())
    assert trials["b__x__r0"].prompt_sha256 is None


def test_agent_ab_errors(tmp_path):
    with pytest.raises(SourceError, match="no trials.jsonl"):
        load_agent_ab(tmp_path)
    (tmp_path / "trials.jsonl").write_text('{"trial_id": 1}\nnot json\n{}\n', encoding="utf-8")
    with pytest.raises(SourceError, match=":2: not valid JSON"):
        load_agent_ab(tmp_path)


def test_manifest_fields_and_relative_transcript():
    trials = by_id(load_manifest(RUNS / "manifest.jsonl"))
    m1, m2, m3, m4 = (trials[k] for k in ("m1", "m2", "m3", "m4"))
    assert (m1.passed, m1.arm, m1.final_message, m1.tags) == (False, "x", "All done!", ("easy",))
    assert m1.group == {"suite": "s1"}
    assert (m2.model, m2.effort) == ("m", "high")
    assert m3.passed is None
    assert m4.group == {"group": "g2"}
    assert m4.transcript_path == RUNS / "ab-mini/trials/t-hard__control__r0/attempt-1/agent.stdout"
    assert m4.transcript_path.is_file()


@pytest.mark.parametrize(
    ("line", "error"),
    [
        ('{"task": "a", "passed": true}', "'id'"),
        ('{"id": "1", "passed": true}', "'task'"),
        ('{"id": "1", "task": "a", "passed": "yes"}', "'passed'"),
    ],
)
def test_manifest_validation(tmp_path, line, error):
    path = tmp_path / "m.jsonl"
    path.write_text(line + "\n", encoding="utf-8")
    with pytest.raises(SourceError, match=error):
        load_manifest(path)


def test_manifest_prompt_sha256(tmp_path):
    path = tmp_path / "m.jsonl"
    digest = "0f" * 32
    rows = [
        {"id": "1", "task": "a", "passed": True, "prompt_sha256": digest},
        {"id": "2", "task": "a", "passed": True},
    ]
    _write_jsonl(path, rows)
    trials = by_id(load_manifest(path))
    assert trials["1"].prompt_sha256 == digest
    assert trials["2"].prompt_sha256 is None
    _write_jsonl(path, [{**rows[0], "prompt_sha256": "abc"}])
    with pytest.raises(SourceError, match="'prompt_sha256'"):
        load_manifest(path)


def test_manifest_duplicate_ids(tmp_path):
    path = tmp_path / "m.jsonl"
    row = json.dumps({"id": "1", "task": "a", "passed": True})
    path.write_text(row + "\n" + row + "\n", encoding="utf-8")
    with pytest.raises(SourceError, match="duplicate"):
        load_manifest(path)


def test_load_dispatch(tmp_path):
    assert len(load(RUN)) == 6
    assert len(load(RUNS / "manifest.jsonl")) == 4
    with pytest.raises(SourceError, match="not found"):
        load(tmp_path / "missing.jsonl")
    other = tmp_path / "x.csv"
    other.write_text("", encoding="utf-8")
    with pytest.raises(SourceError, match="expected"):
        load(other)


def test_load_many_prefixes_colliding_ids(tmp_path):
    copy = tmp_path / "copy"
    shutil.copytree(RUN, copy)
    trials = load_many([RUN, copy])
    ids = {t.id for t in trials}
    assert len(ids) == 12
    assert "ab-mini/t-easy__control__r0" in ids
    assert "copy/t-easy__control__r0" in ids
    assert len(load_many([RUN, RUNS / "manifest.jsonl"])) == 10


@pytest.mark.skipif(not AGENT_AB_RESULTS.is_dir(), reason="agent-ab results not present")
def test_real_agent_ab_runs_load():
    for run in sorted(p for p in AGENT_AB_RESULTS.iterdir() if (p / "trials.jsonl").is_file()):
        trials = load_agent_ab(run)
        assert trials, run
        assert len({t.id for t in trials}) == len(trials)
        assert all(t.passed is not None for t in trials)
        assert all(t.tags for t in trials)  # tags come from the stored config
