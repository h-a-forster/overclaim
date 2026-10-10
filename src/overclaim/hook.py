"""Claude Code Stop hook: keep the agent working when it claims completion it has not verified.

Claude Code runs the hook when the agent is about to end its turn and passes a JSON payload
on stdin (``session_id``, ``transcript_path``, ``cwd``, ``stop_hook_active``,
``last_assistant_message``, ...). Printing ``{"decision": "block", "reason": ...}`` makes the
agent continue with ``reason`` as feedback; printing nothing lets it stop. See docs/hook.md.

The hook never loops (``stop_hook_active`` true means it already blocked once) and never gets
in the way: any internal problem exits 0 without a decision and with one line on stderr.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, TextIO

from overclaim.models import Claim, ClaimResult, Evidence, Verification

DISABLE_ENV = "OVERCLAIM_HOOK_DISABLE"
BLOCKING = frozenset({Verification.NOT_RUN, Verification.FAILED, Verification.UNKNOWN})
_EVENTS = frozenset({"Stop", "SubagentStop"})
_CLIP = 80


class _Skip(Exception):
    """Nothing to decide; the message says why."""


class _ArgParser(argparse.ArgumentParser):
    def error(self, message: str) -> Any:
        raise _Skip(f"bad hook options: {message}")


def _parser() -> argparse.ArgumentParser:
    p = _ArgParser(prog="overclaim hook claude-stop", add_help=False)
    p.add_argument("--mode", choices=("claim", "always"), default="claim")
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
) -> str | None:
    """The block reason for a Stop payload, or None to let the agent stop.

    Edits to documentation (``evidence.DOC_GLOBS``) do not need tests unless
    ``count_all_edits``.
    """
    from overclaim.evidence import DOC_GLOBS, assess
    from overclaim.transcript import load

    if payload.get("stop_hook_active") is True:
        return None
    event = payload.get("hook_event_name")
    if event is not None and event not in _EVENTS:
        raise _Skip(f"unsupported hook event {event!r}")
    # For a subagent, transcript_path is the main session; the subagent has its own file.
    key = "agent_transcript_path" if event == "SubagentStop" else "transcript_path"
    path = payload.get(key) or payload.get("transcript_path")
    if not isinstance(path, str) or not path:
        raise _Skip("payload has no transcript_path; nothing checked")
    file = Path(os.path.expanduser(path))
    if not file.is_file():
        raise _Skip(f"transcript {path} not found; nothing checked")
    transcript = load(file, format="claude-session")
    # The transcript may not hold the final message yet at Stop time; the payload does.
    final = payload.get("last_assistant_message")
    if not isinstance(final, str) or not final.strip():
        final = transcript.final_message
    ignore = () if count_all_edits else DOC_GLOBS
    evidence = assess(transcript, extra_test_patterns, ignore_edits=ignore)
    claim = _classify(final)
    return block_reason(claim, evidence, mode, payload.get("cwd"))


def block_reason(
    claim: ClaimResult,
    evidence: Evidence,
    mode: str = "claim",
    cwd: object = None,
) -> str | None:
    """Why the agent should not stop yet, or None. Pure: no I/O."""
    complete = claim.label is Claim.COMPLETE
    if evidence.verification not in BLOCKING or not (complete or mode == "always"):
        return None
    lead = "You reported the task as done, but " if complete else "Before you stop: "
    if evidence.verification is Verification.NOT_RUN:
        where = _where(evidence, cwd)
        return (
            f"{lead}no test command ran after your last edit{where}. Run the tests now, fix "
            "what fails, then report exactly what passed and what you could not verify. If "
            "the project has no tests, say so plainly instead of claiming it works."
        )
    last = evidence.test_runs_after_last_edit[-1]
    run = "test run after your last edit" if evidence.last_edit else "test run"
    cmd = _clip(last.text)
    if evidence.verification is Verification.FAILED:
        how = "output shows failures" if last.exit_code in (None, 0) else f"exit {last.exit_code}"
        return (
            f"{lead}the last {run} failed (`{cmd}`, {how}). Fix the "
            "failures and run the tests again, or report plainly what still fails."
        )
    hidden = "a pipe hides its exit status" if "|" in last.text else "no exit status or summary"
    return (
        f"{lead}the outcome of the last {run} is unknown (`{cmd}`: "
        f"{hidden}). Run the tests so that pass or fail is visible, then report exactly what "
        "passed and what you could not verify."
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
