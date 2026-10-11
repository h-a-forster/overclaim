"""Per-arm cost, turns, Stop-hook blocks and what agents did after a block, for an agent-ab run.

    python scripts/hook_activity.py runs/interventions
    python scripts/hook_activity.py results/interventions   # after extracting the archive there

A block is a user message starting with "Stop hook feedback". After the first block in a trial,
the script counts test commands (`overclaim.evidence.is_test_command`) and edits (`Edit`,
`Write`, `MultiEdit`), split into scratch edits (under a `tmp/` directory, or outside the trial
workspace, such as the agent's scratchpad) and all other edits. Shell writes are not counted.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from overclaim.evidence import is_test_command  # noqa: E402

EDIT_TOOLS = {"Edit", "Write", "MultiEdit"}
SHELL_TOOLS = {"Bash", "PowerShell"}
SCRATCH = re.compile(r"(?:^|[\\/])tmp[\\/]", re.IGNORECASE)
ABSOLUTE = re.compile(r"^(?:[a-z]:|/)")


def after_block(stdout: Path) -> dict[str, bool]:
    """What the agent did after its first Stop-hook block."""
    seen = {"blocked": False, "tests": False, "edits": False, "scratch_edits": False}
    workspace = ""
    if not stdout.exists():
        return seen
    for line in stdout.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "system" and event.get("subtype") == "init":
            workspace = str(event.get("cwd") or "").replace("\\", "/").lower()
        message = event.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), list):
            continue
        for block in message["content"]:
            if not isinstance(block, dict):
                continue
            if event.get("type") == "user" and block.get("type") == "text":
                if str(block.get("text", "")).startswith("Stop hook feedback"):
                    seen["blocked"] = True
            elif seen["blocked"] and block.get("type") == "tool_use":
                name, args = block.get("name"), block.get("input") or {}
                if name in SHELL_TOOLS and is_test_command(str(args.get("command", ""))):
                    seen["tests"] = True
                elif name in EDIT_TOOLS:
                    path = str(args.get("file_path", ""))
                    norm = path.replace("\\", "/").lower()
                    outside = workspace and ABSOLUTE.match(norm) and workspace not in norm
                    scratch = SCRATCH.search(path) or outside
                    seen["scratch_edits" if scratch else "edits"] = True
    return seen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    arms: dict[str, list[dict]] = defaultdict(list)
    for line in (args.run_dir / "trials.jsonl").open(encoding="utf-8"):
        row = json.loads(line)
        row.update(after_block(args.run_dir / row["artifacts"] / "agent.stdout"))
        arms[row["arm"]].append(row)

    print(
        "| Arm | Trials | Pass rate | Cost/trial | Turns | Blocked | Blocked and passed "
        "| Ran tests after | Edited code or tests after | Edited only scratch after |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|")
    for arm, rows in arms.items():
        costs = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
        blocked = [r for r in rows if r["blocked"]]
        print(
            f"| {arm} | {len(rows)} | {sum(r['passed'] for r in rows) / len(rows):.1%} "
            f"| ${statistics.mean(costs):.3f} ({len(costs)} with cost) "
            f"| {statistics.mean(r['turns'] or 0 for r in rows):.1f} | {len(blocked)} "
            f"| {sum(r['passed'] for r in blocked)} | {sum(r['tests'] for r in blocked)} "
            f"| {sum(r['edits'] for r in blocked)} "
            f"| {sum(r['scratch_edits'] and not r['edits'] for r in blocked)} |"
        )


if __name__ == "__main__":
    main()
