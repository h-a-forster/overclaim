# Transcript formats

`overclaim` reads an agent's transcript to find its final message, the shell commands it ran
(with exit codes and output) and the files it edited. `overclaim.transcript.load(path)` sniffs
the format from the first records; pass `format=` to skip sniffing.

| Format | Produced by | Sniffed from |
|---|---|---|
| [`claude-stream-json`](#claude-stream-json) | `claude -p --output-format stream-json --verbose` (agent-ab's `agent.stdout`) | `session_id`, `parent_tool_use_id` or a `result` record |
| [`claude-session`](#claude-session) | Claude Code session files, `~/.claude/projects/<project>/<session>.jsonl` (also the Stop hook's `transcript_path`) | `sessionId` or `parentUuid` |
| [`codex-jsonl`](#codex-jsonl) | `codex exec --json` | `thread.*`, `turn.*`, `item.*` records |
| [`generic-jsonl`](#generic-jsonl) | anything else, converted by you | `message`, `command`, `edit`, `tool`, `meta` records |

All formats are JSON Lines. Parsing is lenient: blank lines, lines that are not JSON objects
(log noise mixed into stdout), records of unknown types and malformed records are skipped. A
file with no recognisable record raises `TranscriptError`. Command output is capped at 8 KB,
keeping the first quarter and the last three quarters, since test runners print their summary
last. Windows line endings in output are normalised to `\n`.

## What is extracted

- **Messages**: assistant text, in order. The **final message** is what the claim classifier
  reads. It is `None` when the run did not end with a message: the agent was cut off (max
  turns, budget, timeout, crash) or its last action was a tool call. The last text is kept
  in `meta["last_text"]` for inspection, and `meta["stop_reason"]` says how the run ended:

  | `stop_reason` | Meaning | Final message |
  |---|---|---|
  | `success` | stream-json `result` with subtype `success` | result text, else last text |
  | `end_turn` | session file ending with assistant text | last text |
  | `error_max_turns`, `error_max_budget_usd`, `error_during_execution`, ... | stream-json `result` subtype | `None` |
  | `error` | `result` with `is_error: true` but subtype `success`; Codex `turn.failed` | `None` |
  | `no_result` | stream-json without a `result` record; Codex turn never completed | `None` |
  | `tool_use_after_text` | a tool call followed the last assistant text | `None` |

  Generic transcripts have no `stop_reason`.
- **Commands**: shell commands with `exit_code` (only when the transcript makes it knowable,
  otherwise `None`), the tool result's `is_error` flag, and output.
- **Edits**: file changes made through file tools. A file-tool call whose result is an error
  ("String to replace not found", a denied write) changed nothing and is not an edit; it still
  appears in `events`. Shell commands that write files (`> file`, `tee`, `sed -i`, ...) are
  not edits here; `overclaim.evidence.assess` adds them when `shell_writes=True` (default).
  `Transcript.edits` lists every file change, documentation included. `assess` then leaves
  out edits matching `ignore_edits` (default `evidence.DOC_GLOBS`: `*.md`, `*.markdown`,
  `*.rst`, `*.txt`, `*.adoc`, `CHANGELOG*`, `LICENSE*`, `docs/**`, matched
  case-insensitively on the posix form of relative or absolute paths). They do not reset
  verification, `Evidence.last_edit` is the last counted edit, and a session with only such
  edits is judged on its test runs alone. Pass `ignore_edits=()` to count everything.
  Shell writes count only for source-like targets; see [hook.md](hook.md#limits).
- **Events**: everything above plus other tool calls, in transcript order. `index` fields of
  messages, commands and edits are positions in `events`, so "after the last edit" is a
  comparison of indices.

## claude-stream-json

Records: `system` (subtype `init` carries `model`, `claude_code_version`, `session_id`, `cwd`),
`assistant` and `user` messages with `message.content` blocks, and a final `result`
(`result`, `is_error`, `subtype`, `num_turns`, `total_cost_usd`). Other `system` subtypes
(`thinking_tokens`, `task_summary`, `post_turn_summary`, ...) are ignored.

- **Final message**: `result.result` when it is a non-empty string and the run succeeded,
  else the text of the last assistant message (all its text blocks, joined), unless a tool
  call came after it. A non-success `result` or a missing one gives `None` (see above).
- **Several `result` records**: a background-task notification (`system` /
  `task_notification`) can wake the agent after its report, and it then ends a second time,
  often with a short note ("That background find was stopped..."). The final message is then
  every non-empty `result` text, in order, joined by a blank line, so the report is never
  replaced by the note. `stop_reason` comes from the last `result`; `meta["result_count"]`
  counts them. Session files have no `result` records, so this does not apply to them.
- **Commands**: `tool_use` blocks named `Bash` or `PowerShell` (`input.command`), paired with
  the `tool_result` block of the same `tool_use_id`.
- **Edits**: `Edit`, `Write`, `MultiEdit` (`input.file_path`) and `NotebookEdit`
  (`input.notebook_path`).
- **Subagents**: records with a non-null `parent_tool_use_id` keep their commands and edits,
  but their text is recorded as a `message` event named `subagent` and never becomes the
  final message.
- **Meta**: `session_id`, `cwd`, `model`, `agent_version`, `is_error`, `subtype`,
  `num_turns`, `cost_usd` (all from the last `result`), `result_count`, `stop_reason`,
  `last_text`.

### Exit codes

Checked against real sessions of Claude Code 2.1.287 on Windows (Bash and PowerShell tools),
stored in `tests/fixtures/transcripts/`:

| Command ended | `tool_result` | `toolUseResult` (session) / `tool_use_result` (stream) |
|---|---|---|
| exit 0 | `is_error: false`, content is the output | object: `stdout`, `stderr`, `interrupted`, ... |
| exit N != 0 | `is_error: true`, content starts with `Exit code N` and a newline | string `Error: Exit code N` and the output |
| timed out, denied, failed to start | `is_error: true`, no `Exit code` line | varies |

So `exit_code` is N when the `Exit code N` line is present, 0 when `is_error` is `false` (or
absent with a `stdout` object, as in older files), and `None` otherwise: errors without the
line, commands run with `run_in_background`, and interrupted commands.

A pipeline's exit code is that of its last program: `pytest | tail -n 5` with failing tests
was recorded as exit 0, `is_error: false`, output ending in `FAILED (failures=1)`.
`overclaim.evidence` reads the outcome of such commands from their output. The same holds
for PowerShell: `python -m unittest 2>&1` there wraps stderr lines in `NativeCommandError`
records, but the exit code is still the test runner's.

Other tools (`Read`, `Grep`, `Task`, MCP tools, ...) become `tool` events with a one-line
summary of their input. Their results have no `is_error` field when they succeed.

## claude-session

The session file Claude Code writes as it works. The same `message` blocks as stream-json,
one record per content block (a message with text and a tool call is two records with the
same `message.id`), plus many other record types (`attachment`, `file-history-snapshot`,
`queue-operation`, `last-prompt`, `cost-state`, `summary`, ...) that are ignored. Text is
de-duplicated per message id and tool calls per `tool_use` id, since blocks can be repeated.

- **Final message**: the text of the last main-chain assistant message, unless a tool call
  came after it. Records with `isSidechain: true` (subagents) are handled as in stream-json,
  except in a subagent's own transcript (`<session>/subagents/agent-<id>.jsonl`), where every
  record is a sidechain record and is read as the main chain. Messages from the model
  `<synthetic>` (inserted by Claude Code for API errors and interrupts) are ignored.
- **Meta**: `session_id`, `cwd`, `agent_version` (from `version`), `model` (from the first
  assistant message).
- There is no `result` record and no cost.

## codex-jsonl

`codex exec --json` output. Only `item.completed` events are read (best effort; the format
changes between Codex versions):

| `item.type` | Becomes |
|---|---|
| `agent_message` (`assistant_message` in older versions) | message; the last one is the final message |
| `command_execution` (`command`, `exit_code`, `aggregated_output`, `status`) | command |
| `file_change` (`changes: [{path, kind}]`, `status`) | one edit per path, unless `status` is `failed` |
| `reasoning` | ignored |
| anything else (`mcp_tool_call`, `web_search`, ...) | tool event |

Commands are recorded as Codex ran them, usually wrapped: `bash -lc 'pytest -q'` or
`powershell.exe -Command "pytest -q"`. The wrapper is removed so that the inner script is what
gets matched. `thread.started` gives `session_id`. `turn.completed` gives `stop_reason`
`success`; `turn.failed` or `error` gives `error`, and a started turn that never completed
gives `no_result` (final message `None` in both cases). Output without turn events is not
judged.

## generic-jsonl

For other agents, write one JSON object per line:

```json
{"type": "meta", "model": "my-model", "agent_version": "1.2.0"}
{"type": "message", "text": "I'll fix the parser."}
{"type": "edit", "path": "src/parser.py", "tool": "write_file"}
{"type": "command", "command": "pytest -q", "exit_code": 1, "output": "1 failed in 0.20s"}
{"type": "tool", "name": "web_search", "input": {"query": "..."}}
{"type": "message", "text": "Fixed the parser; all tests pass."}
```

| Record | Fields |
|---|---|
| `message` | `text`; optional `role` (records whose `role` is not `assistant` are skipped) |
| `command` | `command`; optional `exit_code` (integer), `output`, `is_error` (boolean), `tool` |
| `edit` | `path`; optional `tool` |
| `tool` | `name`; optional `input` |
| `meta` | any fields, copied into `Transcript.meta` |

The final message is the last `message`. Omit `exit_code` when you do not know it; do not
write 0 for "unknown".
