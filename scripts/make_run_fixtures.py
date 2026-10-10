"""Regenerate tests/fixtures/runs (agent-ab style run directory and a manifest)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "runs"
RUN = ROOT / "ab-mini"


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8", newline="\n")


def stream(final, test_output=None, test_failed=False):
    lines = [
        {"type": "system", "subtype": "init", "model": "claude-haiku-5-5",
         "claude_code_version": "2.1.296", "session_id": "fixture"},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "tu1", "name": "Edit",
             "input": {"file_path": "src/app.py", "old_string": "a", "new_string": "b"}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "tu1",
             "content": "The file src/app.py has been updated successfully."}]}},
    ]
    if test_output is not None:
        lines += [
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": "tu2", "name": "Bash",
                 "input": {"command": "python -m pytest -q"}}]}},
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu2", "content": test_output,
                 "is_error": test_failed}]}},
        ]
    lines += [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": final}]}},
        {"type": "result", "subtype": "success", "is_error": False, "result": final,
         "num_turns": 3, "total_cost_usd": 0.01},
    ]
    return "".join(json.dumps(x) + "\n" for x in lines)


PASS_OUT = "...\n3 passed in 0.12s"
FAIL_OUT = "Exit code 1\n..F.F\n2 failed, 3 passed in 0.31s"

trials = [
    # (task, arm, attempt, status, transcript)
    ("t-easy", "control", 0, "pass", stream("Done. All tests pass.", PASS_OUT)),
    ("t-easy", "hook", 0, "pass", stream("Done. All tests pass.", PASS_OUT)),
    ("t-hard", "control", 0, "error", None),
    ("t-hard", "control", 1, "fail", stream(
        "I've implemented the feature. Everything is complete and working.")),
    ("t-hard", "hook", 0, "fail", stream(
        "I implemented the parser, but 2 tests still fail; I could not fix them.",
        FAIL_OUT, True)),
    ("t-notag", "control", 0, "fail", None),  # transcript file missing
    ("t-notag", "hook", 0, "error", None),  # ungraded, no artifacts
]

rows = []
for task, arm, attempt, status, transcript in trials:
    tid = f"{task}__{arm}__r0"
    art = f"trials/{tid}/attempt-{attempt}"
    has_art = not (task == "t-notag" and arm == "hook")
    if transcript is not None:
        p = RUN / art / "agent.stdout"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(transcript, encoding="utf-8", newline="\n")
        (RUN / art / "prompt.md").write_text(f"Fix {task}.\n", encoding="utf-8", newline="\n")
        (RUN / art / "diff.patch").write_text("--- a/src/app.py\n+++ b/src/app.py\n",
                                             encoding="utf-8", newline="\n")
    rows.append({
        "trial_id": tid, "task": task, "arm": arm, "repeat": 0, "attempt": attempt,
        "status": status, "passed": {"pass": True, "fail": False}.get(status),
        "cost_usd": None if status == "error" else 0.02,
        "models": ["claude-haiku-5-5"], "agent_version": "2.1.296",
        "artifacts": art if has_art else None, "schema": 1,
    })
(RUN / "trials.jsonl").write_text(
    "".join(json.dumps(r) + "\n" for r in rows) + '{"trial_id": "trunc', encoding="utf-8",
    newline="\n",
)
dump(RUN / "run.json", {
    "schema": 1, "tool": "agent-ab", "version": "0.1.0", "experiment": "ab-mini",
    "baseline": "control", "planned_trials": 6, "agent_versions": {"control": "2.1.296"},
    "config": {
        "config": "experiment.toml",
        "arms": [
            {"name": "control", "agent": {"adapter": "claude-code", "model": "claude-haiku-5-5",
                                          "effort": None}},
            {"name": "hook", "agent": {"adapter": "claude-code", "model": None, "effort": "low"}},
        ],
        "tasks": [
            {"id": "t-easy", "path": "tasks/t-easy", "tags": ["easy"]},
            {"id": "t-hard", "path": "tasks/t-hard", "tags": ["hard", "parser"]},
            {"id": "t-notag", "path": "tasks/t-notag"},
        ],
    },
})
(RUN / "tasks" / "t-notag").mkdir(parents=True, exist_ok=True)
(RUN / "tasks" / "t-notag" / "task.toml").write_text(
    'prompt = "x"\ntags = ["medium", "from-toml"]\n', encoding="utf-8", newline="\n")

manifest = [
    {"id": "m1", "task": "a", "passed": False, "arm": "x", "final_message": "All done!",
     "tags": ["easy"], "group": {"suite": "s1"}},
    {"id": "m2", "task": "a", "passed": True, "arm": "x", "final_message": "All done!",
     "model": "m", "effort": "high"},
    {"id": "m3", "task": "b", "passed": None, "arm": "y", "final_message": "Blocked."},
    {"id": "m4", "task": "b", "passed": False, "arm": "y",
     "transcript": "ab-mini/trials/t-hard__control__r0/attempt-1/agent.stdout", "group": "g2"},
]
(ROOT / "manifest.jsonl").write_text(
    "".join(json.dumps(m) + "\n" for m in manifest), encoding="utf-8", newline="\n")
print("wrote", ROOT)
