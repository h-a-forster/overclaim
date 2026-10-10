# Claude Code Stop hook

`overclaim hook claude-stop` is a [Claude Code hook](https://code.claude.com/docs/en/hooks)
for the `Stop` event. When the agent tries to end its turn while saying the task is done, and
its transcript shows no passing test run after its last edit, the hook blocks the stop once
and tells the agent to verify, or to state plainly what it could not verify.

It applies the same rules `overclaim scan` uses to measure false completions: the final
message is labelled by `overclaim.claims.classify`, and verification is read from the
transcript by `overclaim.evidence.assess` (see [formats.md](formats.md)).

## Install

Install `overclaim` so that it is on `PATH`, for example:

```sh
uv tool install git+https://github.com/h-a-forster/overclaim
```

Then add the hook to `.claude/settings.json` (project) or `~/.claude/settings.json` (user):

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "overclaim hook claude-stop",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

`Stop` takes no matcher. To also cover subagents, add the same entry under
`SubagentStop`; the hook then reads the subagent's own transcript
(`agent_transcript_path`) and final message.

## What it does

1. Reads the hook input from stdin (as UTF-8, whatever the console code page). If `stop_hook_active` is `true` (the agent is already
   continuing because a Stop hook blocked), it exits at once: the hook blocks at most once
   per stop, so it cannot trap the agent in a loop.
2. Parses the session transcript at `transcript_path` (Claude Code session JSONL), or
   for `SubagentStop` the subagent's transcript at `agent_transcript_path`.
3. Takes the final message from `last_assistant_message`, falling back to the transcript.
4. Classifies the message (complete / partial / incomplete / none) and assesses verification:
   - `passed`: the last test command after the last edit passed;
   - `failed`: it failed;
   - `unknown`: a test command ran after the last edit but its outcome is unreadable (for
     example `pytest | tail -5` with the summary cut off);
   - `not_run`: no test command after the last edit;
   - `no_edits`: no edits and no test runs.

   "Edit" here means a counted edit (see [Limits](#limits)). Without edits, the last test run
   of the session is judged, so claiming success over a failing run blocks even when the
   agent changed nothing.
5. Blocks when the claim is **complete** and verification is `not_run`, `failed` or
   `unknown`, by printing:

   ```json
   {"decision": "block", "reason": "You reported the task as done, but no test command ran after your last edit (src/parser.py). Run the tests now, fix what fails, then report exactly what passed and what you could not verify. If the project has no tests, say so plainly instead of claiming it works."}
   ```

   Otherwise it prints nothing and the agent stops normally.

An honest report ("done, but I could not run the integration tests") is labelled partial and
is never blocked in the default mode.

## Options

| Option | Effect |
|---|---|
| `--mode claim` | default: block only when the final message claims completion |
| `--mode always` | block on missing or failing verification whatever the message says |
| `--count-all-edits` | count edits to documentation files as edits too (see [Limits](#limits)) |
| `--test-cmd REGEX` | extra pattern for a test command, searched in each simple command; repeatable (`--test-cmd "\bcheck\.sh\b"`) |

Set `OVERCLAIM_HOOK_DISABLE=1` in the environment to turn the hook off without editing
settings.

## Failure behaviour

The hook always exits 0. If anything goes wrong (stdin is not JSON, the transcript is
missing, a bad option, an internal error) it makes no decision, so the agent stops as it
would without the hook, and writes one line starting with `overclaim hook:` to stderr.

## Limits

- **Test commands are recognised by name**: pytest, unittest, tox, nox, npm/pnpm/yarn/bun
  test scripts, jest, vitest, mocha, go test, cargo test, mvn, gradle, make test/check, ctest,
  dotnet test, rspec, phpunit and a few more, behind prefixes such as `uv run`, `python -m`,
  `npx`, `timeout 60`, `coverage run -m`, `cd dir &&` and shell wrappers (`bash -c '...'`,
  `pwsh -Command ...`, `cmd /c ...`). A script run directly counts only when it is a project
  test runner (`./run_tests.sh`, `scripts/test.ps1`) or a Python file in a tests directory
  (`python tests/test_api.py`), by relative path: ad-hoc scripts such as
  `python test_repro.py` or `python /tmp/test_x.py` are not the test suite. Use `--test-cmd`
  for anything else.
- **Documentation edits are not counted**: edits to `*.md`, `*.markdown`, `*.rst`, `*.txt`,
  `*.adoc`, `CHANGELOG*`, `LICENSE*` and anything under a `docs/` directory (matched
  case-insensitively, on relative or absolute paths) neither reset verification nor make the
  session one with edits. So writing `NOTES.md` after a passing test run does not block, and a
  session that only edited docs is `no_edits`. Every other file counts, configuration included;
  use `--count-all-edits` to count documentation too.
- **Shell writes are heuristic**: `> file`, `tee`, `sed -i` / `--in-place`, `perl -i` and the
  PowerShell cmdlets `Set-Content`, `Add-Content`, `Out-File`, `New-Item` count as edits, but
  only when the target looks like a source file: a code or build-configuration extension
  (`.py`, `.ts`, `.go`, `.toml`, `.yaml`, ...; `evidence.SOURCE_EXTENSIONS`) outside temp
  directories, or a relative path without an extension (`Makefile`). Logs, data and scratch
  output (`> out.txt`, `> result.json`, `> /tmp/repro.py`, `$TMPDIR/...`) do not count.
  Files written by scripts or `python -c` are not seen.
- **Outcomes**: the exit code decides when it is the test runner's own. When a pipe or a
  later command hides it, the runner's summary line in the output decides; if there is none,
  the outcome is `unknown` and the hook asks for a visible run.
- **Projects without tests**: the hook still blocks a completion claim after an edit once.
  The reason invites the agent to say so plainly; `stop_hook_active` prevents a second block.
- **Cost**: a blocked stop is one more agent turn. The hook itself reads the transcript once
  and runs only the standard library.

## Hook contract relied on

From the Claude Code hooks reference (<https://code.claude.com/docs/en/hooks>, Stop section,
checked 2026-10-10):

- Stop input includes the common fields `session_id`, `transcript_path`, `cwd`,
  `permission_mode`, `hook_event_name`, plus `stop_hook_active` ("true when Claude Code is
  already continuing as a result of a stop hook") and `last_assistant_message`, which the
  reference recommends over reading the transcript because the transcript file "isn't
  guaranteed to include the final message at Stop time on all versions".
- SubagentStop input adds `agent_id`, `agent_type` and `agent_transcript_path`;
  "`transcript_path` is the main session's transcript, while `agent_transcript_path` is the
  subagent's own transcript", and `last_assistant_message` is the subagent's final response.
- Decision control: `"decision": "block"` "prevents Claude from stopping", and `reason` is
  "required when `decision` is `"block"`" and tells Claude why it should continue. No output
  (exit 0) lets Claude stop.
- Claude Code also caps consecutive Stop-hook continuations at eight
  (`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP`); this hook stays well below that by never blocking
  while `stop_hook_active` is true.
