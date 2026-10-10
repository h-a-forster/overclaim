from __future__ import annotations

import json
import sys
from collections.abc import Sequence
from pathlib import Path

import pytest

from overclaim import llm
from overclaim.llm import (
    Cache,
    LLMError,
    Spend,
    claude_argv,
    clip,
    judge_trial,
    label_claim,
    parse_envelope,
    parse_json_object,
    run_cli,
)
from overclaim.models import Claim


class FakeRunner:
    """Answers every call with ``result`` in the CLI's JSON envelope and records the calls."""

    def __init__(self, result: str, cost: float = 0.01, is_error: bool = False) -> None:
        self.result, self.cost, self.is_error = result, cost, is_error
        self.calls: list[tuple[list[str], str]] = []

    def __call__(self, argv: Sequence[str], stdin: str) -> str:
        self.calls.append((list(argv), stdin))
        envelope = {
            "type": "result",
            "subtype": "success",
            "is_error": self.is_error,
            "result": self.result,
            "total_cost_usd": self.cost,
            "num_turns": 1,
        }
        return json.dumps(envelope)


def _answer(**kw: object) -> str:
    return json.dumps(kw)


def test_argv_disables_tools_mcp_settings_and_sessions() -> None:
    argv = claude_argv("haiku", "low", "sys")
    assert argv[:2] == ["claude", "-p"]
    joined = " ".join(argv)
    for flag in (
        "--model haiku",
        "--output-format json",
        "--strict-mcp-config",
        "--no-session-persistence",
        "--effort low",
        "--system-prompt sys",
    ):
        assert flag in joined
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--setting-sources") + 1] == ""
    assert "--effort" not in claude_argv("haiku")


def test_label_claim_parses_fenced_answer_and_records_cost(tmp_path: Path) -> None:
    fenced = "```json\n" + _answer(label="partial", claims_tests_pass=True, rationale="x") + "\n```"
    runner, spend = FakeRunner(fenced, cost=0.02), Spend()
    result = label_claim(
        "Fixed it, one test fails.",
        "Fix the parser",
        model="haiku",
        cache=Cache(tmp_path),
        runner=runner,
        spend=spend,
    )
    assert (result.label, result.claims_tests_pass) == (Claim.PARTIAL, True)
    assert result.source == "llm:haiku" and result.cues == ("llm: x",)
    argv, stdin = runner.calls[0]
    assert "--model" in argv and argv[argv.index("--model") + 1] == "haiku"
    assert "<message>\nFixed it, one test fails.\n</message>" in stdin
    assert "<task>\nFix the parser\n</task>" in stdin
    assert (spend.calls, spend.cached, spend.cost_usd) == (1, 0, 0.02)


def test_cache_hit_skips_the_runner(tmp_path: Path) -> None:
    runner, spend = FakeRunner(_answer(label="complete", claims_tests_pass=False)), Spend()
    for _ in range(2):
        label_claim("Done.", cache=Cache(tmp_path), runner=runner, spend=spend)
    assert len(runner.calls) == 1 and (spend.calls, spend.cached) == (1, 1)
    label_claim("Done.", model="opus", cache=Cache(tmp_path), runner=runner)
    label_claim("Done.", effort="low", cache=Cache(tmp_path), runner=runner)
    assert len(runner.calls) == 3  # model and effort are part of the key


def test_rubric_version_is_part_of_the_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = FakeRunner(_answer(label="complete", claims_tests_pass=False))
    label_claim("Done.", cache=Cache(tmp_path), runner=runner)
    monkeypatch.setattr(llm, "RUBRIC_VERSION", "claims-test")
    label_claim("Done.", cache=Cache(tmp_path), runner=runner)
    assert len(runner.calls) == 2


def test_corrupt_cache_file_is_a_miss(tmp_path: Path) -> None:
    runner = FakeRunner(_answer(label="none", claims_tests_pass=False))
    label_claim("Hmm.", cache=Cache(tmp_path), runner=runner)
    for f in tmp_path.rglob("*.json"):
        f.write_text("{not json", encoding="utf-8")
    label_claim("Hmm.", cache=Cache(tmp_path), runner=runner)
    assert len(runner.calls) == 2


def test_empty_message_needs_no_call() -> None:
    runner = FakeRunner("")
    assert label_claim("  ", runner=runner).label == Claim.NONE
    assert runner.calls == []


@pytest.mark.parametrize(
    "runner",
    [
        FakeRunner(_answer(label="done", claims_tests_pass=True)),
        FakeRunner("I think it is complete."),
        FakeRunner("rate limited", is_error=True),
    ],
)
def test_unusable_answers_raise(runner: FakeRunner) -> None:
    with pytest.raises(LLMError):
        label_claim("Fixed.", runner=runner)


def test_judge_trial() -> None:
    runner = FakeRunner(
        "Looking at the diff...\n"
        + _answer(predicts_pass=False, confidence=1.7, rationale="hard-coded")
    )
    diff = "+ return KNOWN[x]"
    result = judge_trial("Make pack() short", "Done!", diff, "ok", model="haiku", runner=runner)
    assert (result.predicts_pass, result.confidence, result.rationale) == (False, 1.0, "hard-coded")
    assert result.source == "llm:haiku" and result.cost_usd == 0.01
    stdin = runner.calls[0][1]
    assert "<diff>\n+ return KNOWN[x]\n</diff>" in stdin and "<evidence>" in stdin


def test_judge_trial_tolerates_null_and_missing_fields() -> None:
    result = judge_trial("t", None, "", "", runner=FakeRunner(_answer(predicts_pass=None)))
    assert (result.predicts_pass, result.confidence, result.rationale) == (None, None, "")


def test_parse_json_object_skips_prose_and_braces() -> None:
    text = 'Sure {not json} here: {"label": "none", "x": {"y": 1}} trailing'
    assert parse_json_object(text) == {"label": "none", "x": {"y": 1}}
    with pytest.raises(LLMError):
        parse_json_object("no object")


def test_parse_envelope_tolerates_noise_lines() -> None:
    stdout = 'warning: something\n{"type": "result", "result": "{}", "total_cost_usd": 0.5}\n'
    assert parse_envelope(stdout) == ("{}", 0.5)
    with pytest.raises(LLMError):
        parse_envelope("not json")


def test_clip_keeps_head_and_tail() -> None:
    clipped = clip("a" * 50 + "b" * 50, 20)
    assert clipped.startswith("a" * 10) and clipped.endswith("b" * 10) and "omitted" in clipped
    assert clip("short", 20) == "short"


def test_run_cli_runs_a_real_process() -> None:
    echo = [sys.executable, "-c", "import sys; sys.stdout.write(sys.stdin.read().upper())"]
    assert run_cli(echo, "hi") == "HI"
    with pytest.raises(LLMError, match="exited 3"):
        run_cli([sys.executable, "-c", "import sys; sys.exit(3)"], "")
    with pytest.raises(LLMError):
        run_cli(["overclaim-no-such-program"], "")
