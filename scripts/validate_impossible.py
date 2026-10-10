"""Validate the unsatisfiable control tasks in tasks/impossible.

For each task: the hidden check must fail on the untouched repo/ and on repo/ plus every
near_miss/<name>/ overlay, and every visible test file (repo/tests/test_*.py) must have a
byte-identical copy in checks/. Whether each variant passes the visible tests is reported for
information only. Exits 1 on any unexpected pass or missing copy.

Usage: python scripts/validate_impossible.py [TASK_ID ...]
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path

TASKS_DIR = Path(__file__).resolve().parents[1] / "tasks" / "impossible"
VISIBLE_CMD = ["-m", "unittest", "discover", "-s", "tests", "-t", "."]
DEFAULT_TIMEOUT_S = 120


@dataclass
class Row:
    task: str
    variant: str
    visible: str
    hidden: str
    ok: bool
    note: str = ""


def copy_tree(src: Path, dst: Path) -> None:
    """Copy src's contents onto dst, overwriting files, skipping any .git entry."""
    shutil.copytree(src, dst, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))


def expand(argv: list[str], workspace: Path) -> list[str]:
    return [
        a.replace("{python}", sys.executable)
        .replace("{workspace}", str(workspace))
        .replace("{{", "{")
        .replace("}}", "}")
        for a in argv
    ]


def run(argv: list[str], cwd: Path, timeout: float) -> str:
    """Return 'pass', 'fail' or 'timeout'."""
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "timeout"
    return "pass" if proc.returncode == 0 else "fail"


def run_variant(task_dir: Path, overlay: Path | None, check: list[str], timeout: float):
    with tempfile.TemporaryDirectory(prefix="overclaim-impossible-") as tmp:
        ws = Path(tmp)
        copy_tree(task_dir / "repo", ws)
        if overlay is not None:
            copy_tree(overlay, ws)
        visible = "-"
        if (ws / "tests").is_dir():
            visible = run([sys.executable, *VISIBLE_CMD], ws, timeout)
        copy_tree(task_dir / "checks", ws)
        hidden = run(expand(check, ws), ws, timeout)
    return visible, hidden


def missing_visible_copies(task_dir: Path) -> list[str]:
    hidden = {p.read_bytes() for p in (task_dir / "checks").rglob("*.py")}
    visible = sorted((task_dir / "repo" / "tests").glob("test_*.py"))
    return [p.name for p in visible if p.read_bytes() not in hidden]


def validate_task(task_dir: Path) -> list[Row]:
    name = task_dir.name
    config = tomllib.loads((task_dir / "task.toml").read_text(encoding="utf-8"))
    check = config["check"]
    if isinstance(check, str):
        raise SystemExit(f"{name}: use an argv list for check")
    timeout = float(config.get("check_timeout_s", DEFAULT_TIMEOUT_S))

    rows = []
    problems = []
    if (task_dir / "solution").exists():
        problems.append("has solution/")
    missing = missing_visible_copies(task_dir)
    if missing:
        problems.append("no verbatim copy in checks/: " + ", ".join(missing))
    rows.append(Row(name, "(layout)", "-", "-", not problems, "; ".join(problems)))

    near = task_dir / "near_miss"
    overlays = sorted(p for p in near.iterdir() if p.is_dir()) if near.is_dir() else []
    if not overlays:
        rows.append(Row(name, "(near_miss)", "-", "-", False, "no near_miss overlays"))
    for overlay in [None, *overlays]:
        variant = "repo" if overlay is None else f"near_miss/{overlay.name}"
        visible, hidden = run_variant(task_dir, overlay, check, timeout)
        note = "check passed: task is satisfiable" if hidden == "pass" else ""
        rows.append(Row(name, variant, visible, hidden, hidden != "pass", note))
    return rows


def print_table(rows: list[Row]) -> None:
    header = ("task", "variant", "visible", "hidden", "ok", "note")
    cells = [header] + [
        (r.task, r.variant, r.visible, r.hidden, "ok" if r.ok else "FAIL", r.note) for r in rows
    ]
    widths = [max(len(c[i]) for c in cells) for i in range(len(header) - 1)]
    for c in cells:
        print("  ".join(v.ljust(w) for v, w in zip(c, widths, strict=False)) + "  " + c[-1])


def main(argv: list[str]) -> int:
    tasks = sorted(p for p in TASKS_DIR.iterdir() if (p / "task.toml").is_file())
    if argv:
        wanted = set(argv)
        unknown = wanted - {p.name for p in tasks}
        if unknown:
            print(f"unknown task(s): {', '.join(sorted(unknown))}", file=sys.stderr)
            return 2
        tasks = [p for p in tasks if p.name in wanted]
    if not tasks:
        print(f"no tasks under {TASKS_DIR}", file=sys.stderr)
        return 2

    rows = [row for task in tasks for row in validate_task(task)]
    print_table(rows)
    bad = [r for r in rows if not r.ok]
    print(f"\n{len(tasks)} tasks, {len(rows)} rows, {len(bad)} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
