"""Read agent transcripts into a normalised ``Transcript``.

Formats (see docs/formats.md): ``claude-stream-json`` (``claude -p --output-format stream-json
--verbose``), ``claude-session`` (Claude Code's session JSONL), ``codex-jsonl`` (``codex exec
--json``) and ``generic-jsonl``. Parsing is lenient: lines that are not JSON objects, records of
unknown types and malformed records are skipped, never fatal.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from overclaim.models import Command, Edit, Event, Message, Transcript

FORMATS = ("claude-stream-json", "claude-session", "codex-jsonl", "generic-jsonl")
OUTPUT_LIMIT = 8 * 1024
SHELL_TOOLS = frozenset({"Bash", "PowerShell"})
EDIT_TOOLS = {
    "Edit": "file_path",
    "Write": "file_path",
    "MultiEdit": "file_path",
    "NotebookEdit": "notebook_path",
}
"""Claude Code file tools and the input key that names the file."""

_SNIFF_RECORDS = 200
_SUMMARY = 200
_BOM = "﻿"
# Claude Code reports a non-zero exit as the first line of the tool result ("Exit code 1");
# the session's toolUseResult carries the same text prefixed with "Error: ".
_EXIT = re.compile(r"^(?:Error: )?Exit code (-?\d+)\b")
_BACKGROUND = re.compile(r"^Command running in background with ID", re.IGNORECASE)
_RECORD_ERRORS = (AttributeError, TypeError, LookupError, ValueError)
_CODEX_TYPES = ("thread.", "turn.", "item.")
_GENERIC_TYPES = frozenset({"message", "command", "edit", "tool", "meta"})


class TranscriptError(ValueError):
    """The file is not a transcript in any supported format."""


def load(path: Path | str, format: str | None = None) -> Transcript:
    """Parse the transcript at ``path``, sniffing the format unless ``format`` is given."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return parse_lines(fh, format)


def parse_lines(lines: Iterable[str], format: str | None = None) -> Transcript:
    """Parse transcript lines (JSONL). Non-JSON lines are skipped."""
    if format is not None and format not in FORMATS:
        raise ValueError(f"unknown transcript format {format!r}; expected one of {FORMATS}")
    records = list(_records(lines))
    fmt = format or sniff(records)
    if fmt is None:
        raise TranscriptError("not a recognised transcript (no known records found)")
    parser: _ClaudeParser | _CodexParser | _GenericParser
    if fmt == "codex-jsonl":
        parser = _CodexParser()
    elif fmt == "generic-jsonl":
        parser = _GenericParser()
    else:
        parser = _ClaudeParser(fmt, records)
    for rec in records:
        try:
            parser.record(rec)
        except _RECORD_ERRORS:
            continue  # one malformed record must not lose the rest of the transcript
    return parser.finish()


def sniff(records: Iterable[dict[str, Any]]) -> str | None:
    """The format of a sequence of records, judged from the first few, or None."""
    for n, rec in enumerate(records):
        if n >= _SNIFF_RECORDS:
            break
        t = rec.get("type")
        if not isinstance(t, str):
            continue
        if "sessionId" in rec or "parentUuid" in rec:
            return "claude-session"
        if "session_id" in rec or "parent_tool_use_id" in rec or t == "result":
            return "claude-stream-json"
        if t.startswith(_CODEX_TYPES):
            return "codex-jsonl"
        if t in _GENERIC_TYPES and not isinstance(rec.get("message"), dict):
            return "generic-jsonl"
    return None


def truncate(text: str, limit: int = OUTPUT_LIMIT) -> str:
    """Cap ``text`` at about ``limit`` characters, keeping its head and its tail.

    The tail matters most: test runners print their summary last.
    """
    if len(text) <= limit:
        return text
    marker = f"\n[... {len(text) - limit} characters truncated ...]\n"
    head = limit // 4
    return text[:head] + marker + text[len(text) - (limit - head) :]


# --- shared helpers ----------------------------------------------------------------------


def _records(lines: Iterable[str]) -> Iterator[dict[str, Any]]:
    for line in lines:
        line = line.strip().lstrip(_BOM)
        if not line.startswith("{"):
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            yield rec


def _str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _text(content: object) -> str:
    """The text of message or tool-result content: a string or a list of parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                if isinstance(part.get("text"), str):
                    parts.append(part["text"])
                elif isinstance(part.get("content"), str | list):
                    parts.append(_text(part["content"]))
        return "\n".join(p for p in parts if p)
    return ""


def _output(text: str) -> str:
    return truncate(text.replace("\r\n", "\n"))


def _summary(value: object) -> str:
    if isinstance(value, dict):
        for key in ("command", "file_path", "path", "pattern", "url", "query", "description"):
            if isinstance(value.get(key), str) and value[key].strip():
                value = value[key]
                break
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError):
            value = str(value)
    flat = " ".join(value.split())
    return flat if len(flat) <= _SUMMARY else flat[: _SUMMARY - 3] + "..."


@dataclass(slots=True)
class _Call:
    """A command or edit whose result may arrive later."""

    index: int
    kind: str  # "command" | "edit"
    name: str
    text: str
    exit_code: int | None = None
    is_error: bool | None = None
    output: str = ""
    applied: bool = True  # False for an edit that failed (it changed nothing)


@dataclass(slots=True)
class _Builder:
    fmt: str
    events: list[Event] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    calls: list[_Call] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    final: str | None = None

    def event(self, kind: str, name: str = "", text: str = "") -> int:
        index = len(self.events)
        self.events.append(Event(index, kind, name, text))
        return index

    def message(self, text: str) -> int:
        index = self.event("message", text=text)
        self.messages.append(Message(index, text))
        return index

    def call(self, kind: str, name: str, text: str) -> _Call:
        c = _Call(self.event(kind, name, text), kind, name, text)
        self.calls.append(c)
        return c

    def build(self) -> Transcript:
        commands = [
            Command(c.index, c.text, c.exit_code, c.is_error, c.output)
            for c in self.calls
            if c.kind == "command"
        ]
        edits = [
            Edit(c.index, c.text, c.name) for c in self.calls if c.kind == "edit" and c.applied
        ]
        return Transcript(
            format=self.fmt,
            events=self.events,
            messages=self.messages,
            commands=commands,
            edits=edits,
            final_message=self.final,
            meta={k: v for k, v in self.meta.items() if v is not None},
        )


# --- Claude Code -------------------------------------------------------------------------


class _ClaudeParser:
    """Claude Code stream-json and session JSONL: the same message blocks in two envelopes.

    Both writers may emit one record per content block of a message and may repeat a block,
    so text is de-duplicated per message id and tool calls per tool_use id. Subagent records
    (``isSidechain``, or ``parent_tool_use_id`` in stream-json) keep their commands and edits,
    but their text never becomes the final message, except in a subagent's own transcript,
    where every record is a sidechain record.

    The final message is None when the run did not end with text: a tool call came after the
    last text, or (stream-json) the ``result`` record reports an error or is missing.
    """

    def __init__(self, fmt: str, records: Sequence[dict[str, Any]] = ()) -> None:
        self.b = _Builder(fmt)
        self.pending: dict[str, tuple[_Call, bool]] = {}  # tool_use id -> (call, backgrounded)
        self.seen_text: set[tuple[str, str]] = set()
        self.final_id: str | None = None
        self.final_parts: list[str] = []
        self.tool_after_text = False
        self.result: dict[str, Any] | None = None
        assistants = [r for r in records if r.get("type") == "assistant"]
        self.subagent_file = bool(assistants) and all(
            r.get("isSidechain") is True for r in assistants
        )

    def record(self, rec: dict[str, Any]) -> None:
        t = rec.get("type")
        self._meta(rec)
        if t == "assistant":
            self._assistant(rec)
        elif t == "user":
            self._user(rec)
        elif t == "result":
            self.result = rec
            self.b.event("result", text=_result_text(rec) or str(rec.get("subtype") or ""))
            meta = self.b.meta
            meta["is_error"] = (
                rec.get("is_error") if isinstance(rec.get("is_error"), bool) else None
            )
            meta["subtype"] = _str(rec.get("subtype"))
            meta["num_turns"] = _int(rec.get("num_turns"))
            cost = rec.get("total_cost_usd")
            meta["cost_usd"] = cost if isinstance(cost, int | float) and cost >= 0 else None

    def _meta(self, rec: dict[str, Any]) -> None:
        meta = self.b.meta
        if meta.get("session_id") is None:
            meta["session_id"] = _str(rec.get("session_id")) or _str(rec.get("sessionId"))
        if meta.get("cwd") is None:
            meta["cwd"] = _str(rec.get("cwd"))
        if rec.get("type") == "system" and rec.get("subtype") == "init":
            meta["model"] = _str(rec.get("model")) or meta.get("model")
            meta["agent_version"] = _str(rec.get("claude_code_version"))
        if meta.get("agent_version") is None:
            meta["agent_version"] = _str(rec.get("version"))
        if meta.get("model") is None and rec.get("type") == "assistant":
            model = _str((rec.get("message") or {}).get("model"))
            if model and not model.startswith("<"):
                meta["model"] = model

    def _sidechain(self, rec: dict[str, Any]) -> bool:
        if _str(rec.get("parent_tool_use_id")):
            return True
        return rec.get("isSidechain") is True and not self.subagent_file

    def _assistant(self, rec: dict[str, Any]) -> None:
        msg = rec.get("message")
        if not isinstance(msg, dict):
            return
        if str(msg.get("model") or "").startswith("<synthetic"):
            return  # inserted by Claude Code (API errors, interrupts), not written by the model
        content = msg.get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        if not isinstance(content, list):
            return
        msg_id = str(msg.get("id") or rec.get("uuid") or "")
        side = self._sidechain(rec)
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                self._text(block, msg_id, side)
            elif block.get("type") == "tool_use":
                self._tool_use(block, side)

    def _text(self, block: dict[str, Any], msg_id: str, side: bool) -> None:
        text = str(block.get("text") or "").strip()
        if not text:
            return
        key = (msg_id, text)
        if msg_id and key in self.seen_text:
            return
        self.seen_text.add(key)
        if side:
            self.b.event("message", "subagent", text)
            return
        self.b.message(text)
        if msg_id and msg_id == self.final_id and not self.tool_after_text:
            self.final_parts.append(text)
        else:
            self.final_id, self.final_parts = msg_id or None, [text]
        self.tool_after_text = False

    def _tool_use(self, block: dict[str, Any], side: bool) -> None:
        tool_id = str(block.get("id") or "")
        if tool_id and tool_id in self.pending:
            return
        if not side:
            self.tool_after_text = True
        name = str(block.get("name") or "")
        inp = block.get("input") if isinstance(block.get("input"), dict) else {}
        if name in SHELL_TOOLS:
            cmd = inp.get("command")
            text = cmd if isinstance(cmd, str) else " ".join(map(str, cmd or ()))
            call = self.b.call("command", name, text.strip())
            background = inp.get("run_in_background") is True
        elif name in EDIT_TOOLS:
            call = self.b.call("edit", name, str(inp.get(EDIT_TOOLS[name]) or ""))
            background = False
        else:
            self.b.event("tool", name, _summary(inp))
            return
        if tool_id:
            self.pending[tool_id] = (call, background)

    def _user(self, rec: dict[str, Any]) -> None:
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            return
        results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
        extra = rec.get("toolUseResult", rec.get("tool_use_result")) if len(results) == 1 else None
        for block in results:
            entry = self.pending.get(str(block.get("tool_use_id") or ""))
            if entry is not None:
                _claude_result(*entry, block, extra)

    def finish(self) -> Transcript:
        last_text = "\n\n".join(self.final_parts) or None
        reason, final = self._ending(last_text)
        self.b.meta["last_text"] = last_text
        self.b.meta["stop_reason"] = reason
        self.b.final = final
        return self.b.build()

    def _ending(self, last_text: str | None) -> tuple[str, str | None]:
        """(stop reason, final message)."""
        if self.b.fmt == "claude-stream-json":
            if self.result is None:
                return "no_result", None  # killed, timed out or crashed before the end
            reason = _str(self.result.get("subtype")) or "success"
            if reason == "success" and self.result.get("is_error") is True:
                reason = "error"
            if reason != "success":
                return reason, None
            text = _result_text(self.result)
            if text:
                return reason, text
        if self.tool_after_text:
            return "tool_use_after_text", None
        return ("success" if self.b.fmt == "claude-stream-json" else "end_turn"), last_text


def _result_text(rec: dict[str, Any]) -> str | None:
    text = rec.get("result")
    return text.strip() or None if isinstance(text, str) else None


def _claude_result(call: _Call, background: bool, block: dict[str, Any], extra: object) -> None:
    flag = block.get("is_error")
    is_error = flag if isinstance(flag, bool) else None
    text = _text(block.get("content"))
    call.is_error = is_error
    if call.kind == "edit":
        call.applied = is_error is not True  # "String to replace not found", denied, ...
        return
    call.output = _output(text)
    call.exit_code = shell_exit_code(text, is_error, extra, background)


def shell_exit_code(
    text: str, is_error: bool | None, extra: object, background: bool
) -> int | None:
    """The exit code, only when the transcript makes it knowable.

    Claude Code (checked on 2.1.x) marks a non-zero exit with ``is_error: true`` and a first
    line ``Exit code N``; a zero exit has ``is_error: false`` and, in session files, a
    ``toolUseResult`` object with ``stdout``. Errors without that line (timeouts, denied
    permissions) and backgrounded or interrupted commands have no exit code.
    """
    m = _EXIT.match(text.lstrip())
    if m is None and isinstance(extra, str):
        m = _EXIT.match(extra.lstrip())
    if m:
        return int(m.group(1))
    if background or _BACKGROUND.match(text.lstrip()):
        return None
    if isinstance(extra, dict) and (
        extra.get("interrupted") is True or extra.get("backgroundTaskId")
    ):
        return None
    if is_error is False:
        return 0
    if is_error is None and isinstance(extra, dict) and "stdout" in extra:
        return 0
    return None


# --- Codex -------------------------------------------------------------------------------

_POSIX_WRAP = re.compile(r"^\s*(?:\S*/)?(?:ba|z|da|k)?sh(?:\.exe)?\s+-[a-z]*c\s+(.*)$", re.S)
_PS_WRAP = re.compile(
    r"^\s*(?:\"[^\"]*(?:powershell|pwsh)(?:\.exe)?\"|\S*(?:powershell|pwsh)(?:\.exe)?)"
    r"(?:\s+-(?!c(?:ommand)?\s)\w+(?:\s+(?:Bypass|RemoteSigned|Unrestricted|Hidden))?)*"
    r"\s+-c(?:ommand)?\s+(.*)$",
    re.S | re.IGNORECASE,
)


def unwrap(command: str | list[Any]) -> str:
    """The script inside ``bash -lc '...'`` or ``powershell -Command ...``; else unchanged."""
    if isinstance(command, list):
        argv = [str(a) for a in command]
        if len(argv) >= 3 and re.fullmatch(r"-[a-z]*c|-command", argv[-2], re.IGNORECASE):
            return argv[-1].strip()
        command = " ".join(argv)
    text = command.strip()
    m = _POSIX_WRAP.match(text) or _PS_WRAP.match(text)
    if m is None:
        return text
    inner = m.group(1).strip()
    if len(inner) >= 2 and inner[0] == inner[-1] and inner[0] in "'\"":
        inner = inner[1:-1]
        inner = (
            inner.replace("'\\''", "'") if text[m.start(1)] == "'" else inner.replace('\\"', '"')
        )
    return inner.strip()


class _CodexParser:
    """``codex exec --json``: ``item.completed`` events carry messages, commands and patches."""

    def __init__(self) -> None:
        self.b = _Builder("codex-jsonl")
        self.stop_reason: str | None = None  # None: no turn events (older output), not judged

    def record(self, rec: dict[str, Any]) -> None:
        t = rec.get("type")
        if t == "thread.started":
            self.b.meta.setdefault("session_id", _str(rec.get("thread_id")))
            return
        if t == "turn.started":
            self.stop_reason = "no_result"
        elif t == "turn.completed":
            self.stop_reason = "success"
        elif t in ("turn.failed", "error"):
            self.stop_reason = "error"
        if t != "item.completed" or not isinstance(rec.get("item"), dict):
            return
        item = rec["item"]
        itype = item.get("type", item.get("item_type"))
        if itype in ("agent_message", "assistant_message"):
            text = str(item.get("text") or "").strip()
            if text:
                self.b.message(text)
                self.b.final = text
        elif itype == "command_execution":
            cmd = item.get("command")
            call = self.b.call(
                "command", "shell", unwrap(cmd if isinstance(cmd, list) else str(cmd or ""))
            )
            call.exit_code = _int(item.get("exit_code"))
            call.output = _output(str(item.get("aggregated_output") or ""))
            status = item.get("status")
            call.is_error = (
                None if status is None else status != "completed" or bool(call.exit_code)
            )
        elif itype == "file_change":
            failed = item.get("status") == "failed"
            for change in item.get("changes") or ():
                if isinstance(change, dict) and _str(change.get("path")):
                    call = self.b.call("edit", "apply_patch", change["path"])
                    call.applied = not failed
        elif isinstance(itype, str) and itype != "reasoning":
            self.b.event("tool", itype, _summary(item.get("tool") or item.get("query") or ""))

    def finish(self) -> Transcript:
        meta = self.b.meta
        meta["last_text"] = self.b.final
        meta["stop_reason"] = self.stop_reason
        if self.stop_reason not in (None, "success"):
            self.b.final = None
        return self.b.build()


# --- generic -----------------------------------------------------------------------------


class _GenericParser:
    """One event per line; see docs/formats.md."""

    def __init__(self) -> None:
        self.b = _Builder("generic-jsonl")

    def record(self, rec: dict[str, Any]) -> None:
        t = rec.get("type")
        if t == "meta":
            self.b.meta.update({k: v for k, v in rec.items() if k != "type"})
        elif t == "message":
            text = str(rec.get("text") or "").strip()
            if text and rec.get("role", "assistant") == "assistant":
                self.b.message(text)
                self.b.final = text
        elif t == "command":
            call = self.b.call(
                "command", str(rec.get("tool") or "shell"), str(rec.get("command") or "")
            )
            call.exit_code = _int(rec.get("exit_code"))
            err = rec.get("is_error")
            call.is_error = err if isinstance(err, bool) else None
            call.output = _output(str(rec.get("output") or ""))
        elif t == "edit" and _str(rec.get("path")):
            self.b.call("edit", str(rec.get("tool") or "edit"), rec["path"])
        elif t == "tool":
            self.b.event("tool", str(rec.get("name") or ""), _summary(rec.get("input") or ""))

    def finish(self) -> Transcript:
        return self.b.build()
