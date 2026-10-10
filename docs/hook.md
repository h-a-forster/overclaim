# Claude Code hooks

`overclaim` ships two [Claude Code hooks](https://code.claude.com/docs/en/hooks) that work
together:

- `overclaim hook claude-stop`, for the `Stop` event, makes the decision;
- `overclaim hook claude-post-tool`, for `PostToolUse` and `PostToolUseFailure`, records the
  agent's shell commands and file edits as they happen, so the Stop hook has evidence even
  when there is no session transcript.

`overclaim hook claude-stop` is the hook for the `Stop` event. When the agent tries to end its turn while saying the task is done, and
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

Then add the hooks to `.claude/settings.json` (project) or `~/.claude/settings.json` (user):

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Bash|PowerShell|Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [
          {"type": "command", "command": "overclaim hook claude-post-tool", "timeout": 30}
        ]
      }
    ],
    "PostToolUseFailure": [
      {
        "matcher": "Bash|PowerShell|Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [
          {"type": "command", "command": "overclaim hook claude-post-tool", "timeout": 30}
        ]
      }
    ],
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

The post-tool entries are optional when Claude Code keeps session transcripts (the
default), and needed when it does not: `claude -p --no-session-persistence` (as agent-ab runs
it) and many CI setups write no transcript, so `transcript_path` points to a file that does
not exist.

`Stop` takes no matcher. To also cover subagents, add the same entry under
`SubagentStop`; the hook then reads the subagent's own transcript
(`agent_transcript_path`) and final message.

## What it does

1. Reads the hook input from stdin (as UTF-8, whatever the console code page). If
   `stop_hook_active` is `true` (the agent is already continuing because a Stop hook
   blocked), it exits at once: the hook blocks at most once per stop, so it cannot trap the
   agent in a loop.
2. Parses the session transcript at `transcript_path` (Claude Code session JSONL), or
   for `SubagentStop` the subagent's transcript at `agent_transcript_path`. When that file
   does not exist, it reads the post-tool log for the session instead (see
   [The post-tool log](#the-post-tool-log)). With neither, `claim` and `always` modes allow
   the stop with a note on stderr, and `audit` mode decides from the final message alone.
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

   Otherwise it prints nothing and the agent stops normally. This is the default `claim`
   mode; see [Options](#options) for `always` and `audit`.

An honest report ("done, but I could not run the integration tests") is labelled partial and
is never blocked in the default mode.

## Options

| Option | Effect |
|---|---|
| `--mode claim` | default: block only when the final message claims completion |
| `--mode always` | block on missing or failing verification whatever the message says |
| `--mode audit` | block every report of finished work (complete or partial) once, even after passing tests (see [Audit mode](#audit-mode)) |
| `--count-all-edits` | count edits to documentation files as edits too (see [Limits](#limits)) |
| `--test-cmd REGEX` | extra pattern for a test command, searched in each simple command; repeatable (`--test-cmd "\bcheck\.sh\b"`) |

`overclaim inspect TRANSCRIPT --mode MODE` shows whether the hook would block a recorded
session in a given mode.

### Audit mode

Passing tests show only that the agent's own checks pass. Most false completions come after
the agent's tests passed: the work did what it checked, not everything the task asked. In
audit mode, the hook blocks once whatever the evidence says, whenever the final message reports
finished work (labelled complete or partial), with:

> Before you finish, audit your work against the request. Re-read the task and list each
> requirement it states, including edge cases and error behaviour. For each one, point to a
> test or command you ran that shows it works; where none exists, write a quick check and
> run it. Fix anything that fails. Then report which requirements you verified and which you
> could not.

When verification is also missing or failing, the reason ends with a note saying so (for
example "Note: no test command ran after your last edit (src/parser.py)."). Messages that say
the work is not done (incomplete) or make no claim are never blocked. Partial reports are
audited too because the rule classifier confuses complete and partial far more often than
either with incomplete ([claims.md](claims.md)). As in every mode, `stop_hook_active` limits
this to one block per stop, so each audited stop costs one more agent turn.

Set `OVERCLAIM_HOOK_DISABLE=1` in the environment to turn the hook off without editing
settings.

## The post-tool log

`overclaim hook claude-post-tool` appends one line per call to
`<temp dir>/overclaim-hooks/<session_id>.jsonl` (the session id reduced to `A-Z a-z 0-9 _ -`;
`OVERCLAIM_HOOK_LOG_DIR` overrides the directory). It never writes into the project and never
prints to stdout. Lines are [generic-jsonl](formats.md#generic-jsonl) events:

```json
{"type": "edit", "path": "src/parser.py", "tool": "Edit"}
{"type": "command", "tool": "Bash", "command": "pytest -q", "exit_code": 1, "is_error": true, "output": "..."}
```

- Shell tools (`Bash`, `PowerShell`): `PostToolUse` means the command exited 0 (exit code 0,
  output from `tool_response.stdout` and `stderr`). `PostToolUseFailure` carries `error`,
  whose first line is `Exit code N` for a command that ran; the exit code is N, or unknown
  for failures without that line (timeouts, denials, `is_interrupt`). Backgrounded and
  interrupted commands have no exit code. Output is capped at 8 KB.
- File tools (`Edit`, `Write`, `MultiEdit`, `NotebookEdit`): one `edit` per successful call;
  failed calls changed nothing and are not logged.
- Other tools are ignored. Subagents share the session id, so their calls land in the same
  log.

The logs are small and are not deleted (a session can stop several times); clear the
directory when you like.

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

From the Claude Code hooks reference (<https://code.claude.com/docs/en/hooks>, checked
2026-10-10).

PostToolUse and PostToolUseFailure: both receive `tool_name`, `tool_input` and
`tool_use_id`. PostToolUse runs "after a tool call succeeds" and adds `tool_response`, which
for `Bash` is an object with `stdout`, `stderr`, `interrupted` and `isImage`.
PostToolUseFailure runs after a tool call fails and adds `error` (for a shell command that
ran, starting with `Exit code N`) and `is_interrupt`. Matchers on the tool name apply to both.
Neither can block, and the post-tool hook prints nothing.

Stop and SubagentStop:

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
