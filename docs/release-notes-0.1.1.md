# overclaim 0.1.1

A maintenance release with a rerun of study 1. Of the published numbers of studies 1 and 2,
only study 1's evidence-detector false alarms change (14 to 13, from the parser fix below).

## Changes

- **Prompt hashes.** Every trial carries `prompt_sha256`, the sha256 of its task prompt (line
  endings normalised to LF, the final newline of `prompt.md` removed), and `overclaim export`
  writes it after `agent_version`. A digest read from `prompt.md` now equals the one newer
  agent-ab versions record, so one prompt has one digest across all three runs. The published
  `results/*/trials-derived.jsonl` files were regenerated and have the column.
- **Test commands run through an interpreter variable.** `$PY -m pytest` and PowerShell
  `& $py -m unittest` now count as test runs. In the study 1 rerun the evidence detectors now
  flag 2 of 4 false completions with 41 false alarms (47 before); in study 1, 13 false alarms
  (14 before). The recorded LLM judge and `ruleproof` results were not re-run.
- **`feature-uri-resolve` check fixed.** The task now follows agent-ab commit `9f31a88`: its
  hidden oracle and reference solution keep percent-encoded hex digits in a host uppercase, as
  the prompt says. In studies 1 and 2 the old oracle lowercased them; the task produced 6 of
  study 1's 11 false completions and 15 of study 2's 22. Both studies stay as published, with
  results reported with and without the task ([docs/results.md](results.md#the-feature-uri-resolve-conflict)).
- **Study 1 rerun.** [experiments/setups-rerun.toml](../experiments/setups-rerun.toml) reran
  study 1's 18 solvable tasks in its four arms (144 trials) with the fixed check, Claude Code
  2.1.308 and an agent environment that differed from study 1's (a broken `PYTHONHOME`, a
  bash shim, a changed user-level `CLAUDE.md`). 4 of 8 failures ended with a `complete` claim
  (FCR 50.0% [0.0, 78.5]; study 1: 11 of 14, 78.6% [50.0, 100.0]), the false-claim share was 4.0%, and
  `feature-uri-resolve` failed 1 of 8 trials instead of 8 of 8. Data:
  [results/setups-rerun](../results/setups-rerun); write-up:
  [docs/results.md](results.md#study-1-rerun-the-fixed-feature-uri-resolve-check).
- **Hang on blank test output.** `Ran N tests` followed by about 30 blank lines and no `OK`
  made the outcome check backtrack exponentially, so `scan` and `inspect` never finished and
  the Stop hook ran into its timeout; 8 KB of blank output took seconds. The summary patterns
  no longer do this. No evidence field in the published data changes.
- **Source distribution.** It now includes `scripts/`, without which its test suite could not
  be collected. CI runs the tests from the sdist, installs with `uv sync --locked`, and pins
  its actions to commit SHAs.
- **Disclosure.** The docs now say that all three runs loaded the host's user-level
  `CLAUDE.md`, that this also changed the rerun's final messages (108 of 144 carry absolute
  file links, against 0 of 144 in study 1), and how the rules score on study 2 and the rerun.
  The rerun's `PowerShell` and `git stash` rows now count graded attempts (76 and 29).
- **Loader fix.** agent-ab runs whose `attempt` or `repeat` fields are not integers, or whose
  `run.json` `config` is not an object, load instead of failing with a Python error.

## Install

```sh
uv tool install git+https://github.com/h-a-forster/overclaim@v0.1.1
```

Full list: [CHANGELOG.md](../CHANGELOG.md).
