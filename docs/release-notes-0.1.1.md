# overclaim 0.1.1

A maintenance release with a rerun of study 1. No published number of studies 1 and 2
changes.

## Changes

- **Prompt hashes.** Every trial carries `prompt_sha256`, the sha256 of its task prompt (line
  endings normalised to LF), and `overclaim export` writes it after `agent_version`. The
  published `results/*/trials-derived.jsonl` files predate it and do not have the column.
- **`feature-uri-resolve` check fixed.** The task now follows agent-ab commit `9f31a88`: its
  hidden oracle and reference solution keep percent-encoded hex digits in a host uppercase, as
  the prompt says. In studies 1 and 2 the old oracle lowercased them; the task produced 6 of
  study 1's 11 false completions and 15 of study 2's 22. Both studies stay as published, with
  results reported with and without the task ([docs/results.md](results.md#the-feature-uri-resolve-conflict)).
- **Study 1 rerun.** [experiments/setups-rerun.toml](../experiments/setups-rerun.toml) reran
  study 1's 18 solvable tasks in its four arms (144 trials) with the fixed check, Claude Code
  2.1.308 and an agent environment that differed from study 1's (a broken `PYTHONHOME`, a
  changed user-level `CLAUDE.md`). 4 of 8 failures ended with a `complete` claim (FCR 50.0%
  [0.0, 78.5]; study 1: 11 of 14, 78.6% [50.0, 100.0]), the false-claim share was 4.0%, and
  `feature-uri-resolve` failed 1 of 8 trials instead of 8 of 8. Data:
  [results/setups-rerun](../results/setups-rerun); write-up:
  [docs/results.md](results.md#study-1-rerun-the-fixed-feature-uri-resolve-check).
- **Loader fix.** agent-ab runs whose `attempt` or `repeat` fields are not integers, or whose
  `run.json` `config` is not an object, load instead of failing with a Python error.

## Install

```sh
uv tool install git+https://github.com/h-a-forster/overclaim@v0.1.1
```

Full list: [CHANGELOG.md](../CHANGELOG.md).
