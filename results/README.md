# Published results

One directory per study, named after its experiment config in [experiments/](../experiments):

| Directory | Study | Config | Write-up |
|---|---|---|---|
| `setups/` | 1: Haiku 5.5 and Sonnet 5.5 at low and high effort, 184 trials | [setups.toml](../experiments/setups.toml) | [docs/results.md](../docs/results.md#study-1-models-and-effort-levels) |
| `interventions/` | 2: control, ask-verify, stop-hook, stop-audit, 288 trials | [interventions.toml](../experiments/interventions.toml) | [docs/results.md](../docs/results.md#study-2-interventions) |

## Files in `results/<study>/`

| File | Content | Made by |
|---|---|---|
| `run.json` | agent-ab run metadata: arms, models, effort, agent versions, task tags, baseline | agent-ab, copied by `scripts/package_results.py` |
| `trials.jsonl` | One row per trial (last attempt): task, arm, repeat, hidden-check `status`, cost, tokens, turns, agent init | agent-ab, copied by `scripts/package_results.py` |
| `labels-sonnet.jsonl` | Claim label per trial from Claude Sonnet 5.5, rubric `claims-2` | `overclaim label ... --model sonnet --effort low` |
| `labels-opus.jsonl` | The same from Claude Opus 5.5 | `overclaim label ... --model opus --effort low` |
| `adjudicated.jsonl` | Decisions on the trials where Sonnet and Opus disagree, with a note each, adjudicated by the study's lead agent (Claude Opus 5.5) against the written rubric, blind to hidden-check results; the agent that wrote the classifier rules never saw the held-out messages | the lead agent |
| `gold.jsonl` | Final labels: the LLM label where both agree (`source` `gold:agreed`), else the adjudication (`gold:adjudicated`) | `scripts/gold_labels.py` |
| `trials-derived.jsonl` | One row per trial with claim, outcome (`false_completion`, ...), verification evidence, test-run counts, final message | `overclaim export ... --labels gold.jsonl` |
| `scan-detectors.json` | Full `scan --format json` report with all four detectors, including the LLM judge | `overclaim scan ... --detectors unverified,claims-tests-unbacked,ruleproof,judge --format json` |
| `transcripts.tar.gz` | Per-trial artifacts (not in git, see below) | `scripts/package_results.py` |

Label rows have the shape `{"id", "label", "claims_tests_pass", "cues"?, "source"?}` and work
directly as `overclaim scan --labels`. Field lists: [docs/cli.md](../docs/cli.md#export) for
`trials-derived.jsonl`, agent-ab's run-directory docs for `run.json` and `trials.jsonl`.

## Transcripts

`transcripts.tar.gz` is too large for git (about 12 MB for study 1). It is published as an
asset on the GitHub release tagged `results-data`, one archive per study, named
`<study>-transcripts.tar.gz`.

```sh
gh release download results-data --repo h-a-forster/overclaim --pattern "setups-transcripts.tar.gz"
tar -xzf setups-transcripts.tar.gz -C results/setups
```

Without `gh`, download the file from the release page in a browser. The archive holds, per
trial, `trials/<id>/attempt-<n>/`:

- `prompt.md`: the task prompt the agent got;
- `agent.stdout`: the Claude Code `stream-json` transcript;
- `diff.patch`: the agent's changes;
- `check.stdout`, `check.stderr`: the hidden check's output;
- `record.json`: agent-ab's trial record.

After extraction, `results/<study>` reads like the original agent-ab run directory:

```sh
overclaim scan results/setups --labels results/setups/gold.jsonl
overclaim inspect results/setups/trials/feature-uri-resolve__haiku-low__r0/attempt-0/agent.stdout
```

The scan commands for every table are in
[docs/results.md](../docs/results.md#reproducing-the-tables). None of them calls a model.

**Redaction.** Trials ran unsandboxed with full permissions on the host. No transcript shows an
agent reading the hidden checks, but on the impossible `procure-2019-prices` task agents
searched the disk for the missing data (`find /`, `find ~`, `ls ~/projects`).
`scripts/package_results.py` replaces the output of every tool call that read outside the trial
workspace with `[redacted: output of a tool call that read outside the trial workspace]`. In
study 1 that is 8 tool outputs: 7 in `procure-2019-prices` trials and 1 in
`feature-uri-resolve__sonnet-low__r1`. The tool calls themselves are kept.

**Scrubbing.** The same script replaces the local home directory (in Windows, POSIX and escaped
forms) with `~` and the local user name with `user` in every packaged file, including
`run.json` and `trials.jsonl`. Paths in the transcripts therefore look like
`~\AppData\Local\Temp\agent-ab-...`. With `--deny-list FILE` (one word per line), packaging
fails if any listed word survives. The archive is deterministic (sorted entries, fixed mtimes),
so packaging the same run again gives the same bytes. Apart from the redacted outputs, the
transcripts contain the agents' full tool calls and outputs on the task repositories.

To verify: `python scripts/package_results.py --help` lists the options, the script's docstring
describes both steps, and in an extracted archive the redacted outputs can be listed with

```sh
grep -rl "output of a tool call that read outside" results/setups/trials
```
