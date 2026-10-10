from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from overclaim.transcript import TranscriptError, load, parse_lines, sniff, truncate, unwrap

FIX = Path(__file__).parent / "fixtures" / "transcripts"
RUNS = ("pass", "fail", "pipe", "editafter", "bash")


# --- helpers for synthetic session JSONL ---------------------------------------------------


def use(tid: str, name: str, inp: dict[str, Any], **rec: Any) -> dict[str, Any]:
    content = [{"type": "tool_use", "id": tid, "name": name, "input": inp}]
    msg = {"id": f"m-{tid}", "model": "claude-test", "content": content}
    return {"type": "assistant", "sessionId": "s1", "message": msg, **rec}


def result(tid: str, content: Any, is_error: bool | None = None, extra: Any = None) -> dict:
    block: dict[str, Any] = {"type": "tool_result", "tool_use_id": tid, "content": content}
    if is_error is not None:
        block["is_error"] = is_error
    rec: dict[str, Any] = {"type": "user", "sessionId": "s1", "message": {"content": [block]}}
    if extra is not None:
        rec["toolUseResult"] = extra
    return rec


def say(text: str, msg_id: str = "m-text", **rec: Any) -> dict[str, Any]:
    msg = {"id": msg_id, "model": "claude-test", "content": [{"type": "text", "text": text}]}
    return {"type": "assistant", "sessionId": "s1", "message": msg, **rec}


def lines(*records: Any) -> list[str]:
    return [r if isinstance(r, str) else json.dumps(r) for r in records]


# --- real Claude Code transcripts ---------------------------------------------------------


@pytest.mark.parametrize("run", RUNS)
def test_stream_and_session_agree(run: str) -> None:
    stream = load(FIX / f"claude-stream-{run}.jsonl")
    session = load(FIX / f"claude-session-{run}.jsonl")
    assert stream.format == "claude-stream-json"
    assert session.format == "claude-session"
    assert [(c.text, c.exit_code, c.is_error) for c in stream.commands] == [
        (c.text, c.exit_code, c.is_error) for c in session.commands
    ]
    assert [(e.path, e.tool) for e in stream.edits] == [(e.path, e.tool) for e in session.edits]
    assert stream.final_message == session.final_message
    assert stream.final_message
    assert stream.meta["session_id"] == session.meta["session_id"]


def test_nonzero_exits_come_from_the_tool_result() -> None:
    t = load(FIX / "claude-stream-fail.jsonl")
    assert [(c.exit_code, c.is_error) for c in t.commands] == [(1, True), (3, True)]
    assert "FAIL: test_add" in t.commands[0].output
    assert t.meta["model"] == "claude-haiku-4-5-20251001"
    assert t.meta["agent_version"] == "2.1.287"
    assert t.meta["cost_usd"] > 0
    assert t.meta["is_error"] is False
    assert "\r\n" not in t.commands[0].output


def test_pipe_hides_exit_status() -> None:
    t = load(FIX / "claude-session-bash.jsonl")
    piped = t.commands[1]
    assert piped.text.endswith("python -m unittest 2>&1 | tail -n 3")
    assert (piped.exit_code, piped.is_error) == (0, False)
    assert "FAILED (failures=1)" in piped.output


def test_edits_and_writes() -> None:
    t = load(FIX / "claude-session-editafter.jsonl")
    assert [(e.tool, Path(e.path.replace("\\", "/")).name) for e in t.edits] == [
        ("Edit", "calc.py"),
        ("Write", "NOTES.md"),
    ]
    assert t.final_message.startswith("Done.")
    kinds = [e.kind for e in t.events]
    assert kinds.count("command") == 1 and kinds.count("edit") == 2
    assert all(e.index == i for i, e in enumerate(t.events))


def test_other_tools_become_tool_events() -> None:
    t = load(FIX / "claude-stream-pass.jsonl")
    reads = [e for e in t.events if e.kind == "tool" and e.name == "Read"]
    assert reads and reads[0].text.endswith("calc.py")


# --- synthetic edge cases -----------------------------------------------------------------


def test_exit_code_rules() -> None:
    t = parse_lines(
        lines(
            use("a", "Bash", {"command": "ok"}),
            result("a", "fine", is_error=False),
            use("b", "Bash", {"command": "bad"}),
            result("b", "Exit code 2\nboom", is_error=True, extra="Error: Exit code 2\nboom"),
            use("c", "Bash", {"command": "slow"}),
            result("c", "Command timed out after 2m 0s", is_error=True),
            use("d", "Bash", {"command": "serve", "run_in_background": True}),
            result("d", "Command running in background with ID: x", is_error=False),
            use("e", "PowerShell", {"command": "stopped"}),
            result("e", "partial", is_error=False, extra={"stdout": "", "interrupted": True}),
            use("f", "Bash", {"command": "legacy"}),
            result("f", "out", extra={"stdout": "out", "stderr": ""}),
            use("g", "Bash", {"command": "unknown"}),
            result("g", [{"type": "text", "text": "list"}, {"type": "image"}]),
            use("h", "Bash", {"command": "never answered"}),
        )
    )
    got = {c.text: (c.exit_code, c.is_error) for c in t.commands}
    assert got == {
        "ok": (0, False),
        "bad": (2, True),
        "slow": (None, True),
        "serve": (None, False),
        "stopped": (None, False),
        "legacy": (0, None),
        "unknown": (None, None),
        "never answered": (None, None),
    }
    assert t.commands[-2].output == "list"


def test_failed_edit_is_not_an_edit() -> None:
    t = parse_lines(
        lines(
            use("a", "Edit", {"file_path": "a.py"}),
            result("a", "String to replace not found in file.", is_error=True),
            use("b", "MultiEdit", {"file_path": "b.py"}),
            result("b", "ok"),
            use("c", "NotebookEdit", {"notebook_path": "n.ipynb"}),
        )
    )
    assert [(e.path, e.tool) for e in t.edits] == [
        ("b.py", "MultiEdit"),
        ("n.ipynb", "NotebookEdit"),
    ]
    assert [e.kind for e in t.events] == ["edit", "edit", "edit"]


def test_final_message_ignores_sidechains_and_synthetic_text() -> None:
    synthetic = say("API Error: overloaded", msg_id="syn")
    synthetic["message"]["model"] = "<synthetic>"
    t = parse_lines(
        lines(
            say("Part one.", msg_id="m1"),
            say("Part two.", msg_id="m1"),
            say("Part two.", msg_id="m1"),  # writers repeat blocks
            say("Subagent says all done.", msg_id="m2", isSidechain=True),
            synthetic,
        )
    )
    assert t.final_message == "Part one.\n\nPart two."
    assert [m.text for m in t.messages] == ["Part one.", "Part two."]
    assert [(e.kind, e.name) for e in t.events][-1] == ("message", "subagent")


def test_stream_json_result_text_wins_and_subagent_commands_count() -> None:
    sub = use("x", "Bash", {"command": "pytest"})
    del sub["sessionId"]
    sub["parent_tool_use_id"] = "task1"
    t = parse_lines(
        lines(
            {
                "type": "system",
                "subtype": "init",
                "session_id": "s",
                "model": "m",
                "claude_code_version": "9.9",
            },
            {
                "type": "assistant",
                "session_id": "s",
                "parent_tool_use_id": None,
                "message": {"id": "a", "content": [{"type": "text", "text": "Working."}]},
            },
            sub,
            {
                "type": "result",
                "subtype": "success",
                "result": "All done.",
                "num_turns": 2,
                "total_cost_usd": 0.5,
                "is_error": False,
            },
        )
    )
    assert t.format == "claude-stream-json"
    assert t.final_message == "All done."
    assert [c.text for c in t.commands] == ["pytest"]
    assert t.meta == {
        "session_id": "s",
        "model": "m",
        "agent_version": "9.9",
        "is_error": False,
        "subtype": "success",
        "num_turns": 2,
        "cost_usd": 0.5,
        "last_text": "Working.",
        "stop_reason": "success",
    }


STREAM_TEXT = {
    "type": "assistant",
    "session_id": "s",
    "message": {"id": "a", "content": [{"type": "text", "text": "All fixed."}]},
}


@pytest.mark.parametrize(
    ("ending", "final", "reason"),
    [
        ({"type": "result", "subtype": "success", "is_error": False}, "All fixed.", "success"),
        ({"type": "result", "subtype": "success", "result": ""}, "All fixed.", "success"),
        (
            {"type": "result", "subtype": "error_max_turns", "is_error": True},
            None,
            "error_max_turns",
        ),
        (
            {"type": "result", "subtype": "error_max_budget_usd", "is_error": True},
            None,
            "error_max_budget_usd",
        ),
        (
            {"type": "result", "subtype": "success", "is_error": True, "result": "API Error"},
            None,
            "error",
        ),
        (None, None, "no_result"),
    ],
)
def test_stream_json_endings(ending: dict | None, final: str | None, reason: str) -> None:
    t = parse_lines(lines(STREAM_TEXT, *([ending] if ending else [])))
    assert t.final_message == final
    assert t.meta["stop_reason"] == reason
    assert t.meta["last_text"] == "All fixed."


def test_tool_use_after_last_text_means_no_final_message() -> None:
    t = parse_lines(lines(say("Running the tests now."), use("a", "Bash", {"command": "pytest"})))
    assert t.final_message is None
    assert t.meta["stop_reason"] == "tool_use_after_text"
    assert t.meta["last_text"] == "Running the tests now."
    done = parse_lines(
        lines(say("Running."), use("a", "Bash", {"command": "pytest"}), say("Done."))
    )
    assert done.final_message == "Done." and done.meta["stop_reason"] == "end_turn"


def test_subagent_tool_use_does_not_truncate_the_main_agent() -> None:
    t = parse_lines(lines(say("Done."), use("a", "Bash", {"command": "ls"}, isSidechain=True)))
    assert t.final_message == "Done."


def test_subagent_transcript_file_has_a_final_message() -> None:
    t = parse_lines(
        lines(
            use("a", "Bash", {"command": "pytest"}, isSidechain=True),
            say("Subagent finished.", isSidechain=True),
        )
    )
    assert t.final_message == "Subagent finished."
    assert [m.text for m in t.messages] == ["Subagent finished."]


@pytest.mark.parametrize(
    ("run", "reason"), [("maxturns", "error_max_turns"), ("noresult", "no_result")]
)
def test_truncated_real_runs(run: str, reason: str) -> None:
    t = load(FIX / f"claude-stream-{run}.jsonl")
    assert t.final_message is None
    assert t.meta["stop_reason"] == reason
    assert t.meta["last_text"].startswith("The bug is on line 2")
    assert [e.tool for e in t.edits] == ["Edit"]


def test_tolerates_noise_and_malformed_records() -> None:
    t = parse_lines(
        [
            "\ufeffwarning: something on stdout",
            "{not json",
            "[1, 2]",
            "",
            json.dumps({"type": "assistant", "sessionId": "s", "message": "oops"}),
            json.dumps({"type": "assistant", "sessionId": "s", "message": {"content": [1, None]}}),
            json.dumps({"type": "user", "sessionId": "s", "message": {"content": "a prompt"}}),
            json.dumps({"type": "file-history-snapshot", "snapshot": {}}),
            json.dumps({"type": "brand-new-event", "sessionId": "s"}),
            json.dumps(use("a", "Bash", {"command": ["pytest", "-q"]})),
            json.dumps(use("b", "Bash", "not a dict")),
            json.dumps(say("Done.")),
        ]
    )
    assert t.format == "claude-session"
    assert [c.text for c in t.commands] == ["pytest -q", ""]
    assert t.final_message == "Done."


def test_load_handles_crlf_and_bom(tmp_path: Path) -> None:
    path = tmp_path / "t.jsonl"
    path.write_bytes(("\ufeff" + "\r\n".join(lines(say("Hi.")))).encode("utf-8"))
    assert load(path).final_message == "Hi."


def test_huge_output_is_truncated_keeping_the_tail() -> None:
    big = "x" * 100_000 + "\n5 passed in 0.1s"
    t = parse_lines(lines(use("a", "Bash", {"command": "pytest"}), result("a", big, False)))
    out = t.commands[0].output
    assert len(out) < 9 * 1024
    assert out.endswith("5 passed in 0.1s")
    assert "truncated" in out


def test_truncate() -> None:
    assert truncate("short") == "short"
    text = "".join(str(i % 10) for i in range(50_000))
    cut = truncate(text, 1000)
    assert cut.startswith(text[:250]) and cut.endswith(text[-750:])


def test_unknown_input_raises() -> None:
    with pytest.raises(TranscriptError):
        parse_lines(["hello", json.dumps({"no": "type"})])
    with pytest.raises(ValueError):
        parse_lines([], format="nope")


def test_explicit_format_skips_sniffing() -> None:
    t = parse_lines(lines(say("Hi.")), format="claude-stream-json")
    assert t.format == "claude-stream-json"
    assert t.final_message is None and t.meta["stop_reason"] == "no_result"


# --- Codex and generic --------------------------------------------------------------------

CODEX = [
    {"type": "thread.started", "thread_id": "th1"},
    {"type": "turn.started"},
    {"type": "item.completed", "item": {"id": "0", "type": "reasoning", "text": "hmm"}},
    {
        "type": "item.started",
        "item": {
            "id": "1",
            "type": "command_execution",
            "command": "bash -lc 'pytest -q'",
            "status": "in_progress",
        },
    },
    {
        "type": "item.completed",
        "item": {
            "id": "1",
            "type": "command_execution",
            "command": "bash -lc 'pytest -q'",
            "exit_code": 1,
            "aggregated_output": "1 failed in 0.1s",
            "status": "failed",
        },
    },
    {
        "type": "item.completed",
        "item": {
            "id": "2",
            "type": "file_change",
            "status": "completed",
            "changes": [{"path": "src/a.py", "kind": "update"}],
        },
    },
    {
        "type": "item.completed",
        "item": {
            "id": "3",
            "type": "file_change",
            "status": "failed",
            "changes": [{"path": "src/b.py", "kind": "add"}],
        },
    },
    {"type": "item.completed", "item": {"id": "4", "type": "agent_message", "text": "Fixed."}},
    {"type": "turn.completed", "usage": {"input_tokens": 1}},
]


def test_codex_exec_json() -> None:
    t = parse_lines(lines(*CODEX))
    assert t.format == "codex-jsonl"
    assert [(c.text, c.exit_code, c.is_error) for c in t.commands] == [("pytest -q", 1, True)]
    assert [e.path for e in t.edits] == ["src/a.py"]
    assert t.final_message == "Fixed."
    assert t.meta["session_id"] == "th1"
    assert t.meta["stop_reason"] == "success"


def test_codex_failed_turn_has_no_final_message() -> None:
    failed = [*CODEX[:-1], {"type": "turn.failed", "error": {"message": "boom"}}]
    t = parse_lines(lines(*failed))
    assert t.final_message is None
    assert (t.meta["stop_reason"], t.meta["last_text"]) == ("error", "Fixed.")
    assert parse_lines(lines(*CODEX[:-1])).meta["stop_reason"] == "no_result"


@pytest.mark.parametrize(
    ("raw", "inner"),
    [
        ("bash -lc 'pytest -q'", "pytest -q"),
        ("/bin/zsh -c 'echo '\\''hi'\\'''", "echo 'hi'"),
        (
            '"C:\\Program Files\\PowerShell\\7\\pwsh.exe" -NoProfile -Command "pytest -q"',
            "pytest -q",
        ),
        ("powershell.exe -ExecutionPolicy Bypass -Command npm test", "npm test"),
        (["bash", "-lc", "go test ./..."], "go test ./..."),
        ("pytest -q", "pytest -q"),
    ],
)
def test_unwrap(raw: Any, inner: str) -> None:
    assert unwrap(raw) == inner


def test_generic_jsonl() -> None:
    t = parse_lines(
        lines(
            {"type": "meta", "model": "m1"},
            {"type": "message", "role": "user", "text": "Fix it."},
            {"type": "edit", "path": "a.py"},
            {"type": "command", "command": "pytest", "exit_code": 0, "output": "1 passed in 0.1s"},
            {"type": "tool", "name": "search", "input": {"query": "x"}},
            {"type": "message", "text": "Done, tests pass."},
        )
    )
    assert t.format == "generic-jsonl"
    assert t.meta == {"model": "m1"}
    assert [(c.text, c.exit_code) for c in t.commands] == [("pytest", 0)]
    assert [e.path for e in t.edits] == ["a.py"]
    assert t.final_message == "Done, tests pass."
    assert [m.text for m in t.messages] == ["Done, tests pass."]


def test_sniff() -> None:
    assert sniff([{"type": "user", "sessionId": "x"}]) == "claude-session"
    assert sniff([{"type": "system", "session_id": "x"}]) == "claude-stream-json"
    assert sniff([{"type": "item.completed"}]) == "codex-jsonl"
    assert sniff([{"type": "command", "command": "x"}]) == "generic-jsonl"
    assert sniff([{"type": 3}, {}]) is None
