"""Claude Code hooks: keep the agent working when it claims completion it has not verified.

``main_claude_stop`` is the Stop hook. Claude Code runs it when the agent is about to end its
turn and passes a JSON payload on stdin (``session_id``, ``transcript_path``, ``cwd``,
``stop_hook_active``, ``last_assistant_message``, ...). Printing ``{"decision": "block",
"reason": ...}`` makes the agent continue with ``reason`` as feedback; printing nothing lets it
stop. See docs/hook.md.

``main_claude_post_tool`` is a PostToolUse / PostToolUseFailure hook that appends each shell
command and file edit to a per-session log in the temp directory. The Stop hook reads that log
when the session transcript does not exist (``claude -p --no-session-persistence``).

The hooks never loop (``stop_hook_active`` true means the Stop hook already blocked once) and
never get in the way: any internal problem exits 0 without a decision and with one line on
stderr.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, TextIO

from overclaim.models import Claim, ClaimResult, Evidence, Transcript, Verification

DISABLE_ENV = "OVERCLAIM_HOOK_DISABLE"
LOG_DIR_ENV = "OVERCLAIM_HOOK_LOG_DIR"
"""Overrides the session-log directory (default ``<tempdir>/overclaim-hooks``)."""
BLOCKING = frozenset({Verification.NOT_RUN, Verification.FAILED, Verification.UNKNOWN})
_EVENTS = frozenset({"Stop", "SubagentStop"})
MODES = ("claim", "always", "audit")
AUDIT_REASON = (
    "Before you finish, audit your work against the request. Re-read the task and list each "
    "requirement it states, including edge cases and error behaviour. For each one, point to a "
    "test or command you ran that shows it works; where none exists, write a quick check and "
    "run it. Fix anything that fails. Then report which requirements you verified and which "
    "you could not."
)
_CLIP = 80


class _Skip(Exception):
    """Nothing to decide; the message says why."""


class _ArgParser(argparse.ArgumentParser):
    def error(self, message: str) -> Any:
        raise _Skip(f"bad hook options: {message}")


def _parser() -> argparse.ArgumentParser:
    p = _ArgParser(prog="overclaim hook claude-stop", add_help=False)
    p.add_argument("--mode", choices=MODES, default="claim")
    p.add_argument("--test-cmd", action="append", default=[], metavar="REGEX")
    p.add_argument("--count-all-edits", action="store_true")
    return p


def main_claude_stop(
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    argv: Sequence[str] | None = None,
    stderr: TextIO | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Entry point for ``overclaim hook claude-stop``. Always returns 0."""
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    stderr = stderr or sys.stderr
    env = os.environ if env is None else env
    if env.get(DISABLE_ENV, "") not in ("", "0"):
        return 0
    try:
        args = _parser().parse_args(list(argv or ()))
        extra = tuple(_compile(p) for p in args.test_cmd)
        reason = decide(
            _payload(_read(stdin)),
            mode=args.mode,
            extra_test_patterns=extra,
            count_all_edits=args.count_all_edits,
            log_dir=log_dir(env),
        )
    except _Skip as exc:
        print(f"overclaim hook: {exc}", file=stderr)
        return 0
    except Exception as exc:  # fail open: a bug here must never trap the agent
        print(f"overclaim hook: internal error: {type(exc).__name__}: {exc}", file=stderr)
        return 0
    if reason:
        stdout.write(json.dumps({"decision": "block", "reason": reason}) + "\n")
        stdout.flush()
    return 0


def decide(
    payload: Mapping[str, Any],
    mode: str = "claim",
    extra_test_patterns: Sequence[re.Pattern[str]] = (),
    count_all_edits: bool = False,
    log_dir: Path | None = None,
) -> str | None:
    """The block reason for a Stop payload, or None to let the agent stop.

    Evidence comes from the session transcript, or, when that file does not exist, from the
    post-tool session log in ``log_dir``. With neither, audit mode still judges the final
    message (without an evidence note) and the other modes skip. Edits to documentation
    (``evidence.DOC_GLOBS``) do not need tests unless ``count_all_edits``.
    """
    from overclaim.evidence import DOC_GLOBS, assess

    if payload.get("stop_hook_active") is True:
        return None
    event = payload.get("hook_event_name")
    if event is not None and event not in _EVENTS:
        raise _Skip(f"unsupported hook event {event!r}")
    transcript, missing = _transcript(payload, event, log_dir)
    if transcript is None and mode != "audit":
        raise _Skip(f"{missing}; nothing checked")
    # The transcript may not hold the final message yet at Stop time; the payload does.
    final = payload.get("last_assistant_message")
    if (not isinstance(final, str) or not final.strip()) and transcript is not None:
        final = transcript.final_message
    ignore = () if count_all_edits else DOC_GLOBS
    evidence = None
    if transcript is not None:
        evidence = assess(transcript, extra_test_patterns, ignore_edits=ignore)
    claim = _classify(final if isinstance(final, str) else None)
    return block_reason(claim, evidence, mode, payload.get("cwd"))


def _transcript(
    payload: Mapping[str, Any], event: object, logs: Path | None
) -> tuple[Transcript | None, str]:
    """The session transcript, else the post-tool log, else (None, why)."""
    from overclaim.transcript import TranscriptError, load

    # For a subagent, transcript_path is the main session; the subagent has its own file.
    key = "agent_transcript_path" if event == "SubagentStop" else "transcript_path"
    path = payload.get(key) or payload.get("transcript_path")
    if isinstance(path, str) and path:
        file = Path(os.path.expanduser(path))
        if file.is_file():
            return load(file, format="claude-session"), ""
        missing = f"transcript {path} not found"
    else:
        missing = "payload has no transcript_path"
    sid = payload.get("session_id")
    if isinstance(sid, str) and sid:
        log = session_log(sid, logs)
        if log.is_file():
            try:
                return load(log, format="generic-jsonl"), ""
            except TranscriptError:  # nothing logged yet: no edits and no commands
                return Transcript(format="generic-jsonl"), ""
        missing += " and no post-tool log"
    return None, missing


def block_reason(
    claim: ClaimResult,
    evidence: Evidence | None,
    mode: str = "claim",
    cwd: object = None,
) -> str | None:
    """Why the agent should not stop yet, or None. Pure: no I/O.

    ``claim``: a complete claim without passing verification. ``always``: missing or failing
    verification, whatever the message says. ``audit``: every complete or partial claim (any
    report of finished work), with the verification problem appended when there is one.
    ``evidence`` None (nothing recorded) blocks only in audit mode.
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")
    complete = claim.label is Claim.COMPLETE
    problem = _problem(evidence, cwd)
    if mode == "audit":
        # Partial counts too: the rule classifier confuses complete and partial far more often
        # than it confuses either with incomplete (docs/claims.md), and a partial report of
        # finished work benefits from the same audit.
        if claim.label not in (Claim.COMPLETE, Claim.PARTIAL):
            return None
        return AUDIT_REASON if problem is None else f"{AUDIT_REASON} Note: {problem[0]}."
    if problem is None or not (complete or mode == "always"):
        return None
    lead = "You reported the task as done, but " if complete else "Before you stop: "
    return f"{lead}{problem[0]}. {problem[1]}"


def _problem(evidence: Evidence | None, cwd: object) -> tuple[str, str] | None:
    """(what is wrong with the verification, what to do), or None when it passed or there
    was nothing to verify."""
    if evidence is None or evidence.verification not in BLOCKING:
        return None
    if evidence.verification is Verification.NOT_RUN:
        return (
            f"no test command ran after your last edit{_where(evidence, cwd)}",
            "Run the tests now, fix what fails, then report exactly what passed and what you "
            "could not verify. If the project has no tests, say so plainly instead of claiming "
            "it works.",
        )
    last = evidence.test_runs_after_last_edit[-1]
    run = "test run after your last edit" if evidence.last_edit else "test run"
    cmd = _clip(last.text)
    if evidence.verification is Verification.FAILED:
        how = "output shows failures" if last.exit_code in (None, 0) else f"exit {last.exit_code}"
        return (
            f"the last {run} failed (`{cmd}`, {how})",
            "Fix the failures and run the tests again, or report plainly what still fails.",
        )
    hidden = "a pipe hides its exit status" if "|" in last.text else "no exit status or summary"
    return (
        f"the outcome of the last {run} is unknown (`{cmd}`: {hidden})",
        "Run the tests so that pass or fail is visible, then report exactly what passed and "
        "what you could not verify.",
    )


def _classify(text: str | None) -> ClaimResult:
    from overclaim.claims import classify  # lazy: keeps this module importable on its own

    return classify(text)


def _read(stdin: TextIO) -> str:
    """Stdin as UTF-8 whatever the console code page (cp1252 on many Windows machines)."""
    buffer = getattr(stdin, "buffer", None)
    if buffer is None:
        return stdin.read()
    return buffer.read().decode("utf-8", errors="replace").lstrip("\ufeff")


def _payload(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise _Skip(f"stdin is not JSON ({exc}); nothing checked") from None
    if not isinstance(payload, dict):
        raise _Skip("stdin is not a JSON object; nothing checked")
    return payload


def _compile(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern)
    except re.error as exc:
        raise _Skip(f"bad --test-cmd regex {pattern!r}: {exc}") from None


def _where(evidence: Evidence, cwd: object) -> str:
    edit = evidence.last_edit
    if edit is None or not edit.path or edit.path == "?":
        return ""
    path = edit.path
    if isinstance(cwd, str) and cwd:
        with contextlib.suppress(ValueError):  # outside cwd: keep the path as written
            path = str(Path(path).relative_to(cwd))
    return f" ({_clip(path)})"


def _clip(text: str) -> str:
    flat = " ".join(text.split()).replace("`", "'")
    return flat if len(flat) <= _CLIP else flat[: _CLIP - 3] + "..."


# --- post-tool log ---------------------------------------------------------------------------

_SHELL_TOOLS = frozenset({"Bash", "PowerShell"})
_EDIT_KEYS = {"Edit": "file_path", "Write": "file_path", "MultiEdit": "file_path"}
_EDIT_KEYS["NotebookEdit"] = "notebook_path"
_POST_EVENTS = frozenset({"PostToolUse", "PostToolUseFailure"})


def log_dir(env: Mapping[str, str] | None = None) -> Path:
    """Where post-tool session logs go: never the project, always a temp directory."""
    env = os.environ if env is None else env
    return Path(env.get(LOG_DIR_ENV) or Path(tempfile.gettempdir()) / "overclaim-hooks")


def session_log(session_id: str, directory: Path | None = None) -> Path:
    """The post-tool log for a session (``session_id`` reduced to ``[A-Za-z0-9_-]``)."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id)[:120] or "session"
    return (directory or log_dir()) / f"{safe}.jsonl"


def post_tool_record(payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """The generic-jsonl event for one tool call, or None for calls that are not logged.

    Shell commands get the exit code the transcript parser would derive: N from a failure's
    ``Exit code N`` line, 0 from a success, None when unknowable (interrupted, backgrounded,
    a failure without the line). Failed file edits changed nothing and are not logged.
    """
    from overclaim.transcript import shell_exit_code, truncate

    tool = payload.get("tool_name")
    inp = payload.get("tool_input")
    inp = inp if isinstance(inp, dict) else {}
    failed = payload.get("hook_event_name") == "PostToolUseFailure"
    if tool in _EDIT_KEYS:
        path = inp.get(_EDIT_KEYS[tool])
        if failed or not isinstance(path, str) or not path:
            return None
        return {"type": "edit", "path": path, "tool": tool}
    if tool not in _SHELL_TOOLS or not isinstance(inp.get("command"), str):
        return None
    response = payload.get("tool_response")
    if failed:
        text, extra = str(payload.get("error") or ""), None
    elif isinstance(response, dict):
        parts = (response.get("stdout"), response.get("stderr"))
        text, extra = "\n".join(p for p in parts if isinstance(p, str) and p), response
    else:
        text, extra = (response if isinstance(response, str) else ""), None
    background = inp.get("run_in_background") is True
    code = shell_exit_code(text, failed, extra, background)
    if payload.get("is_interrupt") is True:
        code = None
    return {
        "type": "command",
        "tool": tool,
        "command": inp["command"].strip(),
        "exit_code": code,
        "is_error": failed,
        "output": truncate(text.replace("\r\n", "\n")),
    }


def main_claude_post_tool(
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    argv: Sequence[str] | None = None,
    stderr: TextIO | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Entry point for ``overclaim hook claude-post-tool``. Always returns 0, prints nothing.

    Appends one line per shell command or file edit to the session log (see ``session_log``).
    """
    del stdout, argv  # PostToolUse output would be shown to the agent; this hook says nothing
    stdin, stderr = stdin or sys.stdin, stderr or sys.stderr
    env = os.environ if env is None else env
    if env.get(DISABLE_ENV, "") not in ("", "0"):
        return 0
    try:
        payload = _payload(_read(stdin))
        event = payload.get("hook_event_name")
        if event is not None and event not in _POST_EVENTS:
            raise _Skip(f"unsupported hook event {event!r}")
        sid = payload.get("session_id")
        if not isinstance(sid, str) or not sid:
            raise _Skip("payload has no session_id; nothing logged")
        record = post_tool_record(payload)
        if record is None:
            return 0
        log = session_log(sid, log_dir(env))
        log.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with open(log, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line)  # one write per line: concurrent hooks do not interleave lines
    except _Skip as exc:
        print(f"overclaim hook: {exc}", file=stderr)
    except Exception as exc:  # fail open
        print(f"overclaim hook: internal error: {type(exc).__name__}: {exc}", file=stderr)
    return 0
