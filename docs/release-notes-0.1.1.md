# overclaim 0.1.1

A maintenance release. No published number changes.

## Changes

- **Prompt hashes.** Every trial carries `prompt_sha256`, the sha256 of its task prompt (line
  endings normalised to LF), and `overclaim export` writes it after `agent_version`. The
  published `results/*/trials-derived.jsonl` files predate it and do not have the column.
- **`feature-uri-resolve` check fixed.** The task now follows agent-ab commit `9f31a88`: its
  hidden oracle and reference solution keep percent-encoded hex digits in a host uppercase, as
  the prompt says. In studies 1 and 2 the old oracle lowercased them; the task produced 6 of
  study 1's 11 false completions and 15 of study 2's 22. Both studies stay as published, with
  results reported with and without the task ([docs/results.md](results.md#the-feature-uri-resolve-conflict)).
- **Rerun config.** [experiments/setups-rerun.toml](../experiments/setups-rerun.toml) reruns
  study 1's 18 solvable tasks in its four arms (144 trials) with the fixed check.
- **Loader fix.** agent-ab runs whose `attempt` or `repeat` fields are not integers, or whose
  `run.json` `config` is not an object, load instead of failing with a Python error.

## Install

```sh
uv tool install git+https://github.com/h-a-forster/overclaim@v0.1.1
```

Full list: [CHANGELOG.md](../CHANGELOG.md).
