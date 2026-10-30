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
  data.
- Published data goes through `scripts/package_results.py` (redaction, home-path and user-name
  scrubbing, `--deny-list`). Transcript archives are release assets, not git files.
- Studies call models and run agents unsandboxed with full permissions: use a container or a
  disposable VM, keep each run resumable (agent-ab resumes a run directory; `overclaim label`
  caches calls), and log progress.
- Scratch files go in `tmp/`; run directories in `runs/` (both gitignored). No `.bak` copies;
  use git.
- Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. The repository
  is public: change it through pull requests with CI. No personal names, emails, local user
  paths or machine details in committed files, commit messages or logs.

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
uv sync --group dev
uv run pytest
uv run ruff check .
uv run ruff format --check src tests scripts
uv run python scripts/validate_impossible.py
```

CI runs these on Linux, macOS and Windows (Python 3.11-3.13) and smoke-tests a built wheel.
Solvable tasks are validated with `agent-ab validate --tasks <config>` (not in CI).

## Status and next steps

Updated: 2026-10-30 (v0.1.1 prepared on a branch, untagged; v0.1.0 and the `results-data`
release are published).

Done:
- v0.1.0: package, hook, task suites, study 1 (184 trials) and study 2 (288 trials) with gold
  labels, packaged transcripts and write-ups.
- v0.1.1: `prompt_sha256` per trial; loader fix for non-integer `attempt`/`repeat`;
  `feature-uri-resolve` updated to agent-ab `9f31a88` (hidden check follows the prompt; the new
  check fails the old reference solution); `experiments/setups-rerun.toml`, run (144 trials,
  $33.67) and written up with gold labels, blind adjudication, judge and scan
  (`results/setups-rerun`, method deviation 6).

Open:
1. Upload `results/setups-rerun/transcripts.tar.gz` as `setups-rerun-transcripts.tar.gz` to
   the `results-data` release (package it again with `scripts/package_results.py runs/setups-rerun
   results/setups-rerun --deny-list FILE` if needed). Before the next run, start agent-ab with
   `PYTHONHOME` unset and no user-level `CLAUDE.md`; both leaked into the rerun's agents.
2. Tag v0.1.1 after the branch is merged.
3. The published `trials-derived.jsonl` files lack `prompt_sha256`; regenerate them with
   `overclaim export` at the next data release.
4. Open questions the studies could not answer: other agents (the Codex reader exists, but no
   Codex study was run), subtler impossible tasks, and a sandboxed rerun.
