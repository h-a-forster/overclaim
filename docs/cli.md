# Command line

```text
overclaim scan PATH... [--by KEYS] [--labels FILE] [--difficulty FILE] [--difficulty-arm ARM]
                       [--exclude-task GLOB]... [--detectors NAMES] [--ruleproof-cmd CMD]
                       [--judge-model MODEL] [--cache-dir DIR] [--no-cache]
                       [--baseline ARM] [--format text|md|json] [--out FILE]
                       [--alpha A] [--seed S] [--title T] [EVIDENCE OPTIONS]
overclaim inspect TRANSCRIPT [--mode claim|always|audit] [--json] [EVIDENCE OPTIONS]
overclaim classify [TEXT | -] [--json]
overclaim label PATH... [--model M] [--effort LEVEL] [--out FILE] [--judge]
                        [--cache-dir DIR] [--no-cache]
overclaim agree A B [--json]
overclaim hook claude-stop [--mode claim|always|audit] [--test-cmd REGEX] [--count-all-edits]
overclaim hook claude-post-tool
overclaim export PATH... --out FILE.csv|FILE.jsonl [--labels FILE] [EVIDENCE OPTIONS]
overclaim --version

EVIDENCE OPTIONS: [--test-cmd REGEX]... [--no-shell-writes] [--count-all-edits]
```

`python -m overclaim` works the same. Results go to stdout, diagnostics to stderr. When stdout
or stderr is not a terminal (a pipe or a file) it is written as UTF-8; a terminal keeps its
own encoding, replacing what it cannot show. `classify -` reads stdin as UTF-8.

| Exit code | Meaning |
|---|---|
| 0 | success |
| 1 | runtime failure |
| 2 | usage or input error (bad option, missing path, malformed manifest or labels file) |
| 130 | interrupted |

`overclaim hook ...` always exits 0, whatever goes wrong (an unknown event, a bad option, an
internal error): Claude Code reads exit code 2 from a Stop hook as "block", so a hook error
must not trap the agent. Problems are reported on stderr.

Set `OVERCLAIM_DEBUG=1` for a traceback on errors.

## Inputs

`PATH` is an [agent-ab](https://github.com/h-a-forster/agent-ab) run directory or a JSONL
manifest. Several paths are combined; trial ids that collide across sources are prefixed with
the source's name (`run-a/fix-x__control__r0`).

### agent-ab run directories

Read: `run.json` (arms' configured `model` and `effort`, `agent_versions`, task tags) and
`trials.jsonl` (the last attempt of each trial; `status` `pass`/`fail`, `error` = ungraded;
`models`, `agent_version`, `cost_usd`). The transcript is `<run>/<artifacts>/agent.stdout`
(`claude -p --output-format stream-json --verbose` output); `prompt.md` and `diff.patch` next to
it feed the judge. Task tags come from the stored config, or from the task's `task.toml` when
the config has none and the task directory can be found.

Each trial's `prompt_sha256` is the record's `prompt_sha256` field when present, else the
sha256 of its `prompt.md` with line endings normalised to LF (none when the file is missing).
Together with `agent_version` it identifies the prompt and agent build a trial ran with, so
trials from runs whose prompts differ can be told apart.

The model of a trial is the arm's configured model, else the session's main model from the
init event, else the reported models joined with `+`.

A run without transcripts (for example one copied without its `trials/` folder) still loads:
the report says how many transcripts were missing and gives pass rates.

### Manifests

One JSON object per line:

| Field | Type | Required | Meaning |
|---|---|---|---|
| `id` | string | yes | Unique trial id. |
| `task` | string | yes | Task id; the unit of resampling and pairing. |
| `passed` | boolean or null | yes | Hidden check; null = ungraded. |
| `transcript` | string | no | Transcript path, relative to the manifest's directory. Any format in [formats.md](formats.md). |
| `final_message` | string | no | Used when there is no transcript. |
| `arm`, `model`, `effort`, `agent_version` | string | no | Grouping fields. |
| `prompt_sha256` | string | no | sha256 of the task prompt (64 hex digits), exported as given. |
| `repeat` | integer | no | Repeat index. |
| `cost_usd` | number | no | |
| `tags` | list of strings | no | Grouping with `--by tag`. |
| `group` | object or string | no | Extra grouping fields (`{"suite": "a"}`), usable in `--by`; a string becomes `group`. |

```json
{"id": "fix-x-1", "task": "fix-x", "passed": false, "arm": "control", "transcript": "sessions/fix-x-1.jsonl"}
{"id": "fix-x-2", "task": "fix-x", "passed": true, "arm": "hook", "final_message": "Done. All 12 tests pass."}
```

## `scan`

Loads trials, parses transcripts, labels final messages with the rules in
[claims.md](claims.md), reads verification evidence, and reports the metrics in
[metrics.md](metrics.md).

- `--by KEYS`: comma-separated grouping, any of `arm`, `model`, `effort`, `task`, `tag`,
  `difficulty`, `agent_version`, or a manifest `group` field (`experiment` for agent-ab runs).
  Combinations form one row each; `tag` puts a trial in one row per tag. Default `arm`;
  `--by ""` for the overall row only.
- `--labels FILE`: JSONL that overrides the rule labels for the ids it lists. Accepted rows:
  `{"id", "label", "claims_tests_pass"?, "cues"?, "source"?}` (what `overclaim label` writes;
  extra keys such as the judge fields are ignored; manual and gold files use the same shape),
  or `export` rows (`claim`, `claims_tests_pass`, `claim_source`; rows whose `claim` is null
  are skipped). `source` defaults to `manual`. Labels may also be given for trials without a
  transcript. Ids are trial ids, bare or as `<source name>/<trial id>`. If no id matches a
  trial, `scan` and `export` exit 2. Ids that match no trial, and graded trials without an
  entry (which keep their rule labels), are counted in a report note; `export` prints these
  notes on stderr.
- `--difficulty FILE`: task to bucket, as a JSON object `{"task": "hard"}` or CSV lines
  `task,bucket` (header optional). Without it, `--by difficulty` uses `--difficulty-arm`'s
  observed pass fraction per task (>= 2/3 easy, <= 1/3 hard, else medium), then `easy`/`medium`/
  `hard` task tags, then the baseline arm's pass fraction.
- `--detectors NAMES`: any of `unverified`, `claims-tests-unbacked`, `ruleproof`, `judge`
  (default the first two; `""` for none). `judge` calls the local `claude` CLI once per
  complete claim (`--judge-model`, default `sonnet`) and costs money.
- `--ruleproof-cmd CMD`: how to run ruleproof, for example `"uvx ruleproof"`. Without it,
  `ruleproof` must be on `PATH`, or the detector is skipped with a note.
- `--baseline ARM`: arm to compare against. Default: the `baseline` in `run.json` when every
  source is an agent-ab run naming the same one (runs naming different baselines need
  `--baseline`); else the first arm in the runs' configuration order; else the alphabetically
  first arm. A note says how the baseline was chosen when it is not a single run's own.
- `--exclude-task GLOB` (repeatable): leave out tasks whose id matches (`fnmatch`, case
  sensitive), for sensitivity analyses. The report lists what was excluded.
- `--cache-dir DIR` / `--no-cache`: where `judge` caches model answers (default
  `.overclaim-cache`).
- `--alpha A` (default 0.05) and `--seed S` (default 0) set the interval level and the
  bootstrap seed.
- Evidence options (also on `inspect` and `export`): `--test-cmd REGEX` (repeatable) adds
  project-specific test commands (`make ci`); `--no-shell-writes` counts only file-tool edits
  as edits, not shell writes such as `sed -i` or `> file`; `--count-all-edits` also counts edits
  to documentation files (by default they do not move the "last edit").

Example on an agent-ab run copied without transcripts:

```text
$ overclaim scan runs/haiku-vs-sonnet-5-5
overclaim report: haiku-vs-sonnet-5-5
  100 trials | 50 tasks | 100 graded | 0 transcripts read | claims labelled: none | alpha 0.05 |
    seed 0

No claims: none of the 100 graded trials has a final message (transcript file missing for 100).
Only pass rates are reported.

By arm (95% CI; rates pooled over trials, tasks as the unit)
  arm     graded  pass rate        95% CI
  ---------------------------------------
  haiku       50      94.0%  83.8%-100.0%
  sonnet      50      96.0%  86.5%-100.0%
  all        100      95.0%   87.3%-99.0%

Pass-rate difference vs haiku (95% CI, paired over tasks)
  sonnet vs haiku: +2.0 pts [-4.0, +10.0] (50 tasks)
  False completions are not compared: no claims were labelled.

Notes
  - Detectors not evaluated: no trial has a claim label.
```

With transcripts the report adds FCR, false-claim share, honest-failure rate and claim rate per
group; false completions by verification evidence; the paired comparison of false-completion
incidence with its verdict; and the detector table.

`--format json` writes the same content as one object (`"schema": 1`), with every interval,
count and note.

## `inspect`

Shows one transcript as the scan sees it: format, final message, claim label with the cues that
drove it, the timeline of edits and test runs with their outcomes, the verification after the
last edit, and whether the Stop hook would block, with the reason it would give. `--mode`
selects the hook mode to evaluate (`claim`, the default, `always` or `audit`; see
[hook.md](hook.md)); `--json` includes `hook_would_block`.

## `classify`

Labels one message with the rules: `overclaim classify "All 45 tests pass."` or
`... | overclaim classify -`. `--json` prints `{label, claims_tests_pass, cues, source}`.

## `label`

Labels every trial's final message with an LLM through the local `claude` CLI and writes JSONL
usable as `scan --labels`. Each row records its provenance: `rubric_version`, `model` and
`effort`. `--judge` also records the judge's pass/fail prediction, confidence, rationale and
`judge_version`. Rows with or without these fields load as labels. Calls are cached under `--cache-dir` (default `.overclaim-cache`),
so an interrupted run resumes without repeating calls. A trial whose call fails is reported
and skipped, and the command exits 1; rerun it to retry. Afterwards it prints agreement with
the rule labels, as `agree` does (rows: rules, columns: LLM).

## `agree`

Agreement between two labelings of the same trials, matched by id; A is the reference. Each
input is a labels JSONL (from `label`, a gold file, or `export`) or a source (run directory or
manifest), which is labelled with the rules. A `.jsonl` file whose first row has `label` (or
`claim` without `passed`) is read as labels; otherwise as a manifest.

```sh
overclaim agree labels-sonnet.jsonl labels-opus.jsonl
overclaim agree gold.jsonl runs/my-run          # gold against the rule labels
```

Prints the number of shared ids (and ids only in A or only in B), raw agreement, Cohen's
kappa, complete/incomplete confusions, `claims_tests_pass` agreement, the confusion matrix
(rows A, columns B) and B's per-label recall and precision against A. `--json` writes all of
it as one object. See [metrics.md](metrics.md#agreement-between-labelers).

## `hook claude-stop` and `hook claude-post-tool`

Claude Code hooks; see [hook.md](hook.md) for installation and behaviour. Both always exit 0
(see above).

- `hook claude-stop` (`Stop` event) decides whether the agent may stop. Options:
  `--mode claim|always|audit` (default `claim`: block a complete claim without passing
  verification after the last edit; `always`: block missing or failing verification whatever
  the message says; `audit`: block every complete or partial report once and ask for a
  requirement-by-requirement check), `--test-cmd REGEX` (repeatable), `--count-all-edits`.
- `hook claude-post-tool` (`PostToolUse` and `PostToolUseFailure`) takes no options and prints
  nothing; it appends each shell command and file edit to a per-session log that `claude-stop`
  reads when the session transcript is unavailable. The log directory is
  `OVERCLAIM_HOOK_LOG_DIR` (default: `overclaim-hooks` in the system temp directory).

`OVERCLAIM_HOOK_DISABLE=1` turns both off.

## `export`

One row per trial, for pandas or R. `.jsonl` keeps lists and objects; `.csv` joins lists with
`;` and writes `group` as JSON. Fields: `id`, `task`, `arm`, `repeat`, `model`, `effort`,
`agent_version`, `prompt_sha256`, `cost_usd`, `passed`, `tags`, `claim`, `claims_tests_pass`, `claim_source`,
`cues`, `outcome`, `verification`, `last_edit`, `test_runs`, `test_runs_after_last_edit`,
`transcript`, `transcript_found`, `final_message`, `source`, `group`.
