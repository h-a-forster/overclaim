# AGENTS.md

Guide for coding agents (and humans) working on overclaim. User-facing docs are in `README.md`
and `docs/`; the study design and its deviations are in `docs/method.md`.

## What this is

A stdlib-only Python package that measures how often a coding agent's final message claims
success that an independent hidden check does not confirm, plus a Claude Code Stop hook, the
task suites, two published studies and a rerun of study 1 (`results/`, written up in
`docs/results.md`).

## Conventions

- uv + hatchling, `src/` layout, Python >= 3.11, no runtime dependencies. `ruff check` and
  `ruff format` (line length 100); `tasks/` is excluded because task repos contain deliberate
  defects.
- Tests run offline and fast: no real agents, no model calls (`overclaim.llm` takes an
  injectable runner). Files only under `tmp_path`; use `pathlib`; do not assume `sh`.
- The hooks always exit 0 and block at most once per stop; a hook error must never trap the
  agent.
- The rule classifier (`claims.py`) and the rubric (`docs/claims.md`, `RUBRIC_VERSION` in
  `llm.py`) change published numbers. Add corpus messages before changing rules and never move
  a held-out message into `tune` (see `CONTRIBUTING.md`).
- Every number in `README.md` and `docs/results.md` must trace to `results/<study>/` files or a
  scan command in `docs/results.md#reproducing-the-tables`. Change the numbers only with the
  data. `scripts/summarize_results.py` rebuilds `results/summary.json` from the committed files
  (CI diffs it), and `tests/test_docs.py` checks every README and CITATION number against it;
  a new number needs a key there and a claim, or a fixed entry whose source the README states
  (counts read only from the transcript archive). `docs/results.md` is not checked yet.
- Published data goes through `scripts/package_results.py` (redaction, home-path and user-name
  scrubbing, `--deny-list`). Transcript archives are release assets, not git files.
- Studies call models and run agents unsandboxed with full permissions: use a container or a
  disposable VM, keep each run resumable (agent-ab resumes a run directory; `overclaim label`
  caches calls), and log progress.
- Scratch files go in `tmp/`; run directories in `runs/` (both gitignored). No `.bak` copies;
  use git.
- The repository is public: change it through pull requests with CI. No personal names, emails,
  local user paths or machine details in committed files, commit messages or logs. No
  attribution trailers on commits or pull requests.
- Do not hand-edit `CHANGELOG.md`; change notes go in `docs/release-notes-<version>.md`.
- Open work lives in `backlog.md`, one outcome per line; delete finished items.
- Published `trials-derived.jsonl` files must stay byte-identical to `overclaim export . --labels
  gold.jsonl` run inside `results/<study>/` on the extracted archive.

## Layout

| Path | Role |
|---|---|
| `src/overclaim/transcript.py`, `sources.py` | transcript readers; agent-ab runs and JSONL manifests |
| `src/overclaim/evidence.py`, `claims.py` | test runs and edits from a transcript; rule classifier |
| `src/overclaim/metrics.py`, `stats.py`, `detectors.py`, `report.py` | outcomes, intervals, comparisons, detectors, reports |
| `src/overclaim/llm.py` | LLM labeller and judge through the `claude` CLI, with a cache |
| `src/overclaim/hook.py`, `cli.py` | Stop and PostToolUse hooks; command line |
| `tasks/solvable`, `tasks/impossible` | 18 agent-ab tasks; 5 impossible tasks with near misses |
| `experiments/` | agent-ab configs and hook overlays for each study |
| `results/` | published labels, trials and derived rows per study |
| `scripts/` | hook build, gold labels, packaging, hook activity, impossible-task validation |

## How to test

```sh
uv sync --locked --group dev
uv run pytest
uv run ruff check .
uv run ruff format --check src tests scripts
uv run python scripts/validate_impossible.py
```

CI runs these on Linux, macOS and Windows (Python 3.11-3.13), smoke-tests a built wheel and runs
the tests from the sdist. Solvable tasks are validated with `agent-ab validate <config> --tasks`
(not in CI). `uv sync` removes anything not locked, including an agent-ab installed by hand.

## Status

Updated: 2026-11-06 (v0.1.1 prepared on `polish-2026-10-30`, untagged; v0.1.0 and the
`results-data` release are published). Open work is in `backlog.md`.

- v0.1.0: package, hook, task suites, study 1 (184 trials) and study 2 (288 trials) with gold
  labels, packaged transcripts and write-ups.
- v0.1.1: see `docs/release-notes-0.1.1.md`. The study 1 rerun (144 trials, $33.67) is in
  `results/setups-rerun`; its archive is local until it is uploaded. Repackage it with
  `scripts/package_results.py runs/setups-rerun results/setups-rerun --deny-list FILE`, which
  reproduces the same bytes.
