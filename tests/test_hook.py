from __future__ import annotations

import io
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

import pytest

from overclaim import hook
from overclaim.models import Claim, ClaimResult, Evidence, Verification

FIX = Path(__file__).parent / "fixtures" / "transcripts"
COMPLETE = ClaimResult(Claim.COMPLETE, claims_tests_pass=True, cues=("done",))
PARTIAL = ClaimResult(Claim.PARTIAL, claims_tests_pass=False, cues=("could not",))
INCOMPLETE = ClaimResult(Claim.INCOMPLETE, claims_tests_pass=False, cues=("gave up",))


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    """Stub the claim classifier (owned elsewhere); records the texts it was given."""
    texts: list[str | None] = []

    def classify(text: str | None) -> ClaimResult:
        texts.append(text)
        if text and "gave up" in text:
            return INCOMPLETE
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


def test_audit_mode_blocks_verified_complete_claims_once(tmp_path: Path, seen: list) -> None:
    path = session(tmp_path, "pass")  # tests passed after the last edit
    assert run_hook(stop(path))[1] == ""
    reason = decision(run_hook(stop(path), "--mode", "audit")[1])["reason"]
    assert reason == hook.AUDIT_REASON
    active = stop(path, stop_hook_active=True)
    assert run_hook(active, "--mode", "audit") == (0, "", "")


def test_audit_mode_adds_the_verification_problem(tmp_path: Path, seen: list) -> None:
    reason = decision(run_hook(stop(session(tmp_path, "editafter")), "--mode", "audit")[1])
    assert reason["reason"].startswith(hook.AUDIT_REASON + " Note: no test command ran after")
    assert reason["reason"].endswith("calc.py).")


def test_audit_mode_ignores_messages_that_do_not_claim_completion(
    tmp_path: Path, seen: list
) -> None:
    payload = stop(session(tmp_path, "editafter"), last_assistant_message="I gave up.")
    assert run_hook(payload, "--mode", "audit")[1] == ""


def test_audit_mode_also_audits_partial_reports(tmp_path: Path, seen: list) -> None:
    payload = stop(session(tmp_path, "editafter"), last_assistant_message="I could not do X.")
    reason = decision(run_hook(payload, "--mode", "audit")[1])
    assert reason["reason"].startswith(hook.AUDIT_REASON)


def test_block_reason_rejects_unknown_modes() -> None:
    ev = Evidence(Verification.PASSED, None, (), ())
    with pytest.raises(ValueError):
        hook.block_reason(COMPLETE, ev, "sometimes")
    assert hook.block_reason(COMPLETE, ev, "claim") is None
    assert hook.block_reason(PARTIAL, ev, "always") is None
    assert hook.block_reason(COMPLETE, ev, "audit") == hook.AUDIT_REASON


# --- post-tool log ------------------------------------------------------------------------


def post(tmp_path: Path, payload: Any) -> tuple[int, str, str]:
    stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
    out, err = io.StringIO(), io.StringIO()
    env = {hook.LOG_DIR_ENV: str(tmp_path / "logs")}
    code = hook.main_claude_post_tool(stdin, out, [], stderr=err, env=env)
    return code, out.getvalue(), err.getvalue()


def tool(event: str, name: str, inp: dict[str, Any], sid: str = "s-1", **extra: Any) -> dict:
    return {
        "session_id": sid,
        "cwd": "C:/work/repo",
        "hook_event_name": event,
        "tool_name": name,
        "tool_input": inp,
        "tool_use_id": "t",
        **extra,
    }


def logged(tmp_path: Path, sid: str = "s-1") -> list[dict[str, Any]]:
    log = hook.session_log(sid, tmp_path / "logs")
    return [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]


def test_post_tool_logs_commands_and_edits(tmp_path: Path) -> None:
    calls = [
        tool("PostToolUse", "Edit", {"file_path": "src/a.py"}, tool_response={"filePath": "x"}),
        tool(
            "PostToolUse",
            "Bash",
            {"command": "pytest -q"},
            tool_response={"stdout": "3 passed in 0.1s", "stderr": "", "interrupted": False},
        ),
        tool(
            "PostToolUseFailure",
            "PowerShell",
            {"command": "python -m unittest"},
            error="Exit code 1\nFAILED (failures=1)",
            is_interrupt=False,
        ),
        tool("PostToolUseFailure", "Bash", {"command": "sleep 999"}, error="Command timed out"),
        tool(
            "PostToolUse",
            "Bash",
            {"command": "serve", "run_in_background": True},
            tool_response={"stdout": "", "backgroundTaskId": "b1"},
        ),
        tool("PostToolUseFailure", "Write", {"file_path": "b.py"}, error="denied"),
        tool("PostToolUse", "Read", {"file_path": "c.py"}, tool_response={}),
        tool("PostToolUse", "NotebookEdit", {"notebook_path": "n.ipynb"}, tool_response={}),
    ]
    for c in calls:
        assert post(tmp_path, c) == (0, "", "")
    got = logged(tmp_path)
    assert [(r["type"], r.get("command") or r.get("path"), r.get("exit_code")) for r in got] == [
        ("edit", "src/a.py", None),
        ("command", "pytest -q", 0),
        ("command", "python -m unittest", 1),
        ("command", "sleep 999", None),
        ("command", "serve", None),
        ("edit", "n.ipynb", None),
    ]
    assert got[2]["is_error"] is True and "FAILED (failures=1)" in got[2]["output"]


def test_post_tool_log_path_is_sanitised_and_in_temp(tmp_path: Path) -> None:
    post(tmp_path, tool("PostToolUse", "Edit", {"file_path": "a.py"}, sid="../x y"))
    assert [p.name for p in (tmp_path / "logs").iterdir()] == ["___x_y.jsonl"]
    assert hook.log_dir({}).parent == Path(tempfile.gettempdir())


def test_post_tool_fails_open(tmp_path: Path) -> None:
    for bad in ("nope", {"hook_event_name": "PostToolUse"}, tool("Stop", "Bash", {})):
        code, out, err = post(tmp_path, bad)
        assert (code, out) == (0, "") and err.startswith("overclaim hook:")


def test_stop_falls_back_to_the_post_tool_log(tmp_path: Path, seen: list) -> None:
    post(
        tmp_path,
        tool(
            "PostToolUse",
            "Bash",
            {"command": "pytest"},
            tool_response={"stdout": "1 passed in 0.1s"},
        ),
    )
    post(tmp_path, tool("PostToolUse", "Edit", {"file_path": "src/a.py"}, tool_response={}))
    payload = stop(tmp_path / "gone.jsonl", session_id="s-1", last_assistant_message="Done.")
    env = {hook.LOG_DIR_ENV: str(tmp_path / "logs")}
    reason = decision(run_hook(payload, env=env)[1])["reason"]
    assert "no test command ran after your last edit (src/a.py)" in reason
    post(
        tmp_path,
        tool(
            "PostToolUse",
            "Bash",
            {"command": "pytest"},
            tool_response={"stdout": "1 passed in 0.1s"},
        ),
    )
    assert run_hook(payload, env=env)[:2] == (0, "")


def test_without_transcript_or_log_only_audit_decides(tmp_path: Path, seen: list) -> None:
    payload = stop(tmp_path / "gone.jsonl", session_id="none", last_assistant_message="Done.")
    env = {hook.LOG_DIR_ENV: str(tmp_path / "logs")}
    code, out, err = run_hook(payload, env=env)
    assert (code, out) == (0, "") and "no post-tool log" in err
    assert decision(run_hook(payload, "--mode", "audit", env=env)[1])["reason"] == (
        hook.AUDIT_REASON
    )


def test_empty_post_tool_log_means_no_evidence(tmp_path: Path, seen: list) -> None:
    log = hook.session_log("s-1", tmp_path / "logs")
    log.parent.mkdir(parents=True)
    log.write_text("", encoding="utf-8")
    payload = stop(tmp_path / "gone.jsonl", session_id="s-1", last_assistant_message="Done.")
    assert run_hook(payload, env={hook.LOG_DIR_ENV: str(log.parent)}) == (0, "", "")
