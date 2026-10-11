"""Package an agent-ab run directory for publication under results/<study>/.

    python scripts/package_results.py runs/setups results/setups [--deny-list FILE]

Copies run.json and trials.jsonl, and writes transcripts.tar.gz with each trial's prompt,
transcript, diff and hidden-check output. Two privacy steps run on every packaged file:

- Tool outputs are kept only where the scan needs them or they are clearly part of the trial:
  test commands (as `overclaim.evidence.is_test_command` recognises them) that do not also
  inspect the host or read outside the workspace, and file tools (`Read`, `Edit`, `Grep`, ...)
  on paths inside the trial workspace. Every other tool output (other shell commands, subagent
  reports, web fetches, reads outside the workspace) is replaced with a redaction note. Agents
  run with full permissions and sometimes list directories, print PATH or search the disk;
  what they see there is not part of the study. Redaction changes no evidence field.
- Absolute home-directory paths and the local user name become neutral placeholders.

`--deny-list FILE` (one word per line) makes packaging fail if any listed word survives, as a
final check for private names. The archive is deterministic (sorted entries, fixed mtimes).

Extract the archive inside results/<study>/ and `overclaim scan results/<study>` reads it like
the original run directory.
"""

from __future__ import annotations

import argparse
import getpass
import gzip
import io
import json
import re
import sys
import tarfile
from collections.abc import Callable
from pathlib import Path, PurePath

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from overclaim.evidence import is_test_command  # noqa: E402

FILES = ("prompt.md", "agent.stdout", "diff.patch", "check.stdout", "check.stderr", "record.json")
REDACTED = "[redacted: tool output other than a test run or a file operation in the workspace]"
SHELL_TOOLS = {"Bash", "PowerShell"}
FILE_TOOLS = {"Read", "Edit", "Write", "MultiEdit", "NotebookEdit", "Grep", "Glob", "LS"}
PATH_KEYS = ("file_path", "path", "notebook_path")
# Commands that print host state (installed programs, processes, environment), matched in
# command position after heredoc bodies are removed, so code that mentions `where` does not count.
HOST_INSPECT = re.compile(
    r"(?:^|[;&|(`]|\$\()\s*(?:sudo\s+)?"
    r"(?:which|where|where\.exe|whereis|ps|tasklist|printenv|Get-Process|uname|whoami|hostname"
    r"|systeminfo|history|pip\s+(?:list|freeze)|uv\s+python\s+list|Get-Command"
    r"|env\s*(?:$|[|;&>])|echo\b[^|;&\n]*(?:\$PATH|\$env:PATH|%PATH%))(?![\w-])",
    re.MULTILINE,
)
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?^\s*\1\s*$", re.DOTALL | re.MULTILINE)
ABSOLUTE = re.compile(r"^(?:[A-Za-z]:|/|~|\$HOME|\$env:|%)")
# Paths inside a temp directory (the trial workspace, the agent's scratchpad, /tmp/x) are part
# of the trial; running an installed interpreter and a bare `cd ~` read nothing. The temp root
# itself is not: listing it shows other programs' directories.
TEMP_ROOT = r"(?:AppData[\\/]Local[\\/]Temp|\$TEMP|\$env:TEMP|%TEMP%|(?<![\w.])/tmp)"
TEMP = re.compile(
    r"\bcd\s+~(?=[\s;&|]|$)"
    rf"|\S*(?:{TEMP_ROOT}[\\/]+[^\s'\"\\/]|AppData[\\/]Local[\\/]Programs"
    r"|AppData[\\/]Roaming[\\/]uv[\\/]python|[\\/]\.venv[\\/])\S*",
    re.IGNORECASE,
)
OUTSIDE = re.compile(
    r"\b(?:ls|dir|find|tree|du|cd|Get-ChildItem|gci|rg|grep\s+-\w*r\w*)\s+"
    r"(?:-\S+(?:\s+[^\s'\"-]\S*)?\s+)*"
    rf"['\"]?{TEMP_ROOT}[\\/]*['\"]?(?=[\s)|;&]|$)"
    r"|(?:^|[\s'\"=(])(?:~|\$HOME|\$env:USERPROFILE|%USERPROFILE%)(?=[\\/\s'\")]|$)"
    r"|(?:^|[\s'\"=(])(?:[A-Za-z]:[\\/]|/(?:[a-z]/|mnt/[a-z]/)?)(?:Users|home|ProgramData)\b"
    r"|\b(?:find|ls|dir|du|tree|Get-ChildItem|gci|rg|grep\s+-\w*r\w*)\s+(?:-\S+\s+)*"
    r"['\"]?(?:/|[A-Za-z]:[\\/]?|/mnt/[a-z]/?)['\"]?(?=\s|$)",
    re.IGNORECASE,
)


def scrubber(user: str, home: PurePath) -> Callable[[str], str]:
    """A function that removes the home directory and user name from text."""
    posix = home.as_posix()
    homes = {str(home), posix, str(home).replace("\\", "\\\\")}
    if re.match(r"^[A-Za-z]:", posix):
        drive, rest = posix[0].lower(), posix[2:]
        homes |= {f"/{drive}{rest}", f"/mnt/{drive}{rest}"}
    patterns = [
        re.compile(re.escape(h), re.IGNORECASE) for h in sorted(homes, key=len, reverse=True)
    ]
    name = re.compile(rf"\b{re.escape(user)}\b", re.IGNORECASE) if len(user) >= 3 else None

    def scrub(text: str) -> str:
        for p in patterns:
            text = p.sub("~", text)
        return name.sub("user", text) if name else text

    return scrub


def reads_outside(name: str, tool_input: dict, workspace: str) -> bool:
    """Whether a tool call reads paths outside the trial workspace."""
    texts = [str(tool_input.get("command", ""))] if name in SHELL_TOOLS else []
    texts += [str(tool_input[k]) for k in PATH_KEYS if k in tool_input]
    for text in texts:
        if workspace:
            text = text.replace(workspace, "").replace(workspace.replace("\\", "/"), "")
        if OUTSIDE.search(TEMP.sub("", text)):
            return True
    return False


def path_outside(tool_input: dict, workspace: str) -> bool:
    """Whether a file tool names an absolute path outside the trial workspace."""
    ws = workspace.replace("\\", "/").lower().rstrip("/")
    for key in (*PATH_KEYS, "pattern"):
        value = str(tool_input.get(key, "")).replace("\\", "/").lower()
        if ABSOLUTE.match(value) and not (ws and value.startswith(ws)):
            return True
    return False


def keep_output(name: str, tool_input: dict, workspace: str) -> bool:
    """Whether a tool call's output may be published (see the module docstring)."""
    if name in SHELL_TOOLS:
        command = str(tool_input.get("command", ""))
        return (
            is_test_command(command)
            and not HOST_INSPECT.search(HEREDOC.sub("<<heredoc", command))
            and not reads_outside(name, tool_input, workspace)
        )
    if name in FILE_TOOLS:
        return not path_outside(tool_input, workspace)
    return name == "TodoWrite"


def _content(event: dict) -> object:
    message = event.get("message")
    return message.get("content") if isinstance(message, dict) else None


def redact_stream(text: str) -> tuple[str, int]:
    """Blank the results of tool calls whose output may not be published: (text, redactions)."""
    events: list[object] = []
    flagged: set[str] = set()
    workspace = ""
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            events.append(line)
            continue
        events.append(event)
        if not isinstance(event, dict):
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            workspace = str(event.get("cwd") or "")
        content = _content(event)
        if event.get("type") == "assistant" and isinstance(content, list):
            for block in content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_use"
                    and not keep_output(block.get("name", ""), block.get("input") or {}, workspace)
                ):
                    flagged.add(block.get("id"))
    count, out = 0, []
    for event in events:
        if isinstance(event, dict) and event.get("type") == "user":
            content = _content(event)
            for block in content if isinstance(content, list) else []:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_result"
                    and block.get("tool_use_id") in flagged
                ):
                    block["content"] = REDACTED
                    for key in ("tool_use_result", "toolUseResult"):
                        if key in event:
                            event[key] = REDACTED
                    count += 1
        out.append(json.dumps(event, ensure_ascii=False) if isinstance(event, dict) else event)
    return "\n".join(map(str, out)) + "\n", count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--user", default=getpass.getuser())
    parser.add_argument("--deny-list", type=Path)
    args = parser.parse_args()
    scrub = scrubber(args.user, Path.home())
    deny = []
    if args.deny_list:
        deny = [w.strip() for w in args.deny_list.read_text("utf-8").splitlines() if w.strip()]

    buf = io.BytesIO()
    count = redactions = 0
    leaks: list[str] = []
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path in sorted((args.run_dir / "trials").glob("*/attempt-*/*")):
            if path.name not in FILES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if path.name == "agent.stdout":
                text, n = redact_stream(text)
                redactions += n
            text = scrub(text)
            leaks += [f"{path}: {w}" for w in deny if re.search(rf"\b{re.escape(w)}\b", text, re.I)]
            data = text.encode("utf-8")
            info = tarfile.TarInfo(path.relative_to(args.run_dir).as_posix())
            info.size, info.mtime, info.mode = len(data), 0, 0o644
            tar.addfile(info, io.BytesIO(data))
            count += 1
    if leaks:
        print("deny-listed words survived; nothing written:", *leaks[:20], sep="\n  ")
        sys.exit(1)

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    for name in ("run.json", "trials.jsonl"):
        text = (args.run_dir / name).read_text(encoding="utf-8")
        (out / name).write_text(scrub(text), encoding="utf-8", newline="\n")
    with (
        (out / "transcripts.tar.gz").open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as gz,
    ):
        gz.write(buf.getvalue())
    size = (out / "transcripts.tar.gz").stat().st_size
    print(
        f"packaged {count} files into {out / 'transcripts.tar.gz'} ({size / 1e6:.1f} MB), "
        f"{redactions} tool outputs redacted"
    )


if __name__ == "__main__":
    main()
