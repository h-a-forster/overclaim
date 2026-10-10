from __future__ import annotations

import io
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from overclaim import hook
from overclaim.models import Claim, ClaimResult

FIX = Path(__file__).parent / "fixtures" / "transcripts"
COMPLETE = ClaimResult(Claim.COMPLETE, claims_tests_pass=True, cues=("done",))
PARTIAL = ClaimResult(Claim.PARTIAL, claims_tests_pass=False, cues=("could not",))


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    """Stub the claim classifier (owned elsewhere); records the texts it was given."""
    texts: list[str | None] = []

    def classify(text: str | None) -> ClaimResult:
        texts.append(text)
        return PARTIAL if text and "could not" in text else COMPLETE

    monkeypatch.setattr(hook, "_classify", classify)
    return texts


def session(tmp_path: Path, run: str) -> Path:
    dst = tmp_path / f"{run}.jsonl"
    shutil.copy(FIX / f"claude-session-{run}.jsonl", dst)
    return dst


def run_hook(payload: Any, *argv: str, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
    out, err = io.StringIO(), io.StringIO()
    code = hook.main_claude_stop(stdin, out, list(argv), stderr=err, env=env or {})
    return code, out.getvalue(), err.getvalue()


def stop(path: Path, **extra: Any) -> dict[str, Any]:
    return {
        "session_id": "s",
        "transcript_path": str(path),
        "cwd": "C:\\work\\repo",
        "permission_mode": "default",
        "hook_event_name": "Stop",
        "stop_hook_active": False,
        **extra,
    }


def decision(out: str) -> dict[str, Any]:
    data = json.loads(out)
    assert set(data) == {"decision", "reason"} and data["decision"] == "block"
    return data


def test_blocks_complete_claim_without_tests_after_last_edit(tmp_path: Path, seen: list) -> None:
    code, out, err = run_hook(stop(session(tmp_path, "editafter")))
    assert code == 0 and err == ""
    reason = decision(out)["reason"]
    assert reason.startswith("You reported the task as done, but no test command ran")
    assert "calc.py" in reason  # the later NOTES.md write is documentation and not counted
    assert seen and seen[0].startswith("Done.")


def test_prefers_last_assistant_message(tmp_path: Path, seen: list) -> None:
    payload = stop(session(tmp_path, "editafter"), last_assistant_message="I could not finish.")
    code, out, _ = run_hook(payload)
    assert (code, out) == (0, "")
    assert seen == ["I could not finish."]


def test_allows_verified_work(tmp_path: Path, seen: list) -> None:
    for run in ("pass", "pipe"):  # passed, passed through a pipe
        assert run_hook(stop(session(tmp_path, run)))[:2] == (0, "")


def test_blocks_complete_claim_over_a_failing_run_without_edits(tmp_path: Path, seen: list) -> None:
    reason = decision(run_hook(stop(session(tmp_path, "fail")))[1])["reason"]
    assert "the last test run failed (`python -m unittest -v`, exit 1)" in reason


def test_never_blocks_twice(tmp_path: Path, seen: list) -> None:
    payload = stop(session(tmp_path, "editafter"), stop_hook_active=True)
    assert run_hook(payload) == (0, "", "")
    assert seen == []


def test_always_mode_blocks_without_a_claim(tmp_path: Path, seen: list) -> None:
    payload = stop(session(tmp_path, "editafter"), last_assistant_message="I could not do it.")
    reason = decision(run_hook(payload, "--mode", "always")[1])["reason"]
    assert reason.startswith("Before you stop: no test command ran")


def write_session(tmp_path: Path, command: str, output: str, is_error: bool) -> Path:
    recs = [
        {
            "type": "assistant",
            "sessionId": "s",
            "message": {
                "id": "1",
                "content": [
                    {"type": "tool_use", "id": "e", "name": "Edit", "input": {"file_path": "a.py"}}
                ],
            },
        },
        {
            "type": "user",
            "sessionId": "s",
            "message": {"content": [{"type": "tool_result", "tool_use_id": "e", "content": "ok"}]},
        },
        {
            "type": "assistant",
            "sessionId": "s",
            "message": {
                "id": "2",
                "content": [
                    {"type": "tool_use", "id": "b", "name": "Bash", "input": {"command": command}}
                ],
            },
        },
        {
            "type": "user",
            "sessionId": "s",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "b",
                        "content": output,
                        "is_error": is_error,
                    }
                ]
            },
        },
        {
            "type": "assistant",
            "sessionId": "s",
            "message": {"id": "3", "content": [{"type": "text", "text": "All done, tests pass."}]},
        },
    ]
    path = tmp_path / "s.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    return path


def test_reason_for_failed_run(tmp_path: Path, seen: list) -> None:
    path = write_session(tmp_path, "pytest -q", "Exit code 1\n1 failed in 0.1s", True)
    reason = decision(run_hook(stop(path))[1])["reason"]
    assert "the last test run after your last edit failed (`pytest -q`, exit 1)" in reason


def test_reason_for_piped_run(tmp_path: Path, seen: list) -> None:
    path = write_session(tmp_path, "pytest | tail -1", "something", False)
    reason = decision(run_hook(stop(path))[1])["reason"]
    assert "is unknown (`pytest | tail -1`: a pipe hides its exit status)" in reason


def test_test_cmd_option(tmp_path: Path, seen: list) -> None:
    path = write_session(tmp_path, "./check.sh", "fine", False)
    assert run_hook(stop(path))[1]
    assert run_hook(stop(path), "--test-cmd", r"check\.sh")[1] == ""


@pytest.mark.parametrize(
    ("payload", "argv", "note"),
    [
        ("not json", (), "stdin is not JSON"),
        ("[1]", (), "not a JSON object"),
        ({"hook_event_name": "Stop"}, (), "no transcript_path"),
        ({"transcript_path": "missing.jsonl"}, (), "not found"),
        ({"hook_event_name": "PreToolUse", "transcript_path": "x"}, (), "unsupported hook event"),
        ({}, ("--mode", "sometimes"), "bad hook options"),
        ({}, ("--test-cmd", "("), "bad --test-cmd regex"),
    ],
)
def test_fails_open_with_a_note(payload: Any, argv: tuple[str, ...], note: str, seen: list) -> None:
    code, out, err = run_hook(payload, *argv)
    assert (code, out) == (0, "")
    assert err.startswith("overclaim hook:") and note in err and err.count("\n") == 1


def test_internal_error_fails_open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(text: str | None) -> ClaimResult:
        raise RuntimeError("classifier broke")

    monkeypatch.setattr(hook, "_classify", boom)
    code, out, err = run_hook(stop(session(tmp_path, "editafter")))
    assert (code, out) == (0, "")
    assert "internal error: RuntimeError: classifier broke" in err


def test_disable_switch(tmp_path: Path, seen: list) -> None:
    payload = stop(session(tmp_path, "editafter"))
    assert run_hook(payload, env={hook.DISABLE_ENV: "1"}) == (0, "", "")
    assert run_hook(payload, env={hook.DISABLE_ENV: "0"})[1]


def test_uses_the_real_classifier_when_present(tmp_path: Path) -> None:
    pytest.importorskip("overclaim.claims")
    code, out, err = run_hook(stop(session(tmp_path, "pass")))
    assert (code, out, err) == (0, "", "")


def test_doc_only_edits_do_not_block_unless_counted(tmp_path: Path, seen: list) -> None:
    recs = [
        {
            "type": "assistant",
            "sessionId": "s",
            "message": {
                "id": "1",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "w",
                        "name": "Write",
                        "input": {"file_path": "README.md"},
                    }
                ],
            },
        },
        {
            "type": "user",
            "sessionId": "s",
            "message": {"content": [{"type": "tool_result", "tool_use_id": "w", "content": "ok"}]},
        },
        {
            "type": "assistant",
            "sessionId": "s",
            "message": {"id": "2", "content": [{"type": "text", "text": "Updated the README."}]},
        },
    ]
    path = tmp_path / "docs.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    assert run_hook(stop(path))[:2] == (0, "")
    reason = decision(run_hook(stop(path), "--count-all-edits")[1])["reason"]
    assert "(README.md)" in reason


def test_subagent_stop_reads_the_agent_transcript(tmp_path: Path, seen: list) -> None:
    main = session(tmp_path, "pass")  # verified: would not block
    agent = tmp_path / "agent-1.jsonl"
    lines = (FIX / "claude-session-editafter.jsonl").read_text(encoding="utf-8").splitlines()
    recs = [json.loads(x) for x in lines]
    for r in recs:
        r["isSidechain"] = True  # how subagent files record every line
    agent.write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")
    payload = stop(main, hook_event_name="SubagentStop", agent_transcript_path=str(agent))
    reason = decision(run_hook(payload)[1])["reason"]
    assert "no test command ran after your last edit" in reason
    assert seen[-1].startswith("Done.")  # the subagent's own final message
    assert run_hook(stop(main, hook_event_name="SubagentStop"))[1] == ""  # falls back


def test_reads_stdin_as_utf8_whatever_the_console_encoding(tmp_path: Path, seen: list) -> None:
    payload = stop(
        session(tmp_path, "editafter"), last_assistant_message="Done \u2014 all fixed \u2705"
    )
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    stdin = io.TextIOWrapper(io.BytesIO(raw), encoding="cp1252")
    out, err = io.StringIO(), io.StringIO()
    assert hook.main_claude_stop(stdin, out, [], stderr=err, env={}) == 0
    assert seen == ["Done \u2014 all fixed \u2705"]
    assert decision(out.getvalue())
