# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Claude Code `stream-json` transcripts with several `result` events: the final message is now
  every non-empty `result` text joined by a blank line, not only the last one
  (`meta["result_count"]` counts them). 8 study 1 trials had been labelled on a short trailing
  note.
- `overclaim hook claude-stop --help` and `claude-post-tool --help` print usage and exit 0.
- `overclaim agree` on a run without transcripts says so and exits 2.

### Changed

- `overclaim label` rows record `rubric_version`, `model` and `effort` (and `judge_version` for
  judge rows).
- Study 1 results regenerated after relabelling those 8 messages: 19 adjudications (was 16),
  98 complete claims (was 96), false-claim share 11.2% [2.1, 28.8] (was 11.5%). FCR on
  solvable tasks is unchanged at 11/14. See deviation 4 in `docs/method.md`.
- `scripts/package_results.py` redacts the output of tool calls that read outside the trial
  workspace (8 in study 1) and accepts `--deny-list FILE` to fail on surviving private words.
- Real-message classifier fixtures use the joined final messages; real-holdout accuracy is
  0.76 (was 0.73) with the classifier unchanged.

## [0.1.0] - 2026-10-10

### Added

- `overclaim scan`: false-completion rate, false-claim share, honest-failure rate and pass rate
  by arm, model, effort, difficulty, task or tag, with task-clustered intervals; paired arm
  comparisons; detector precision and recall.
- `overclaim inspect`, `classify`, `label`, `agree` and `export`.
- `overclaim hook claude-stop`: a Claude Code Stop hook that sends an agent back once when it
  claims completion without a passing test run after its last edit.
- Transcript readers for Claude Code (`stream-json` and session files), Codex (`exec --json`)
  and a generic JSONL format; agent-ab run directories and JSONL manifests as inputs.
- Rule-based claim classifier with a labelled corpus; optional LLM labeller and judge through
  the `claude` CLI, with a cache.
- Task suites: 18 solvable tasks from agent-ab and 5 impossible tasks with near-miss checks.
- Two experiments (setups, interventions) and their results.
