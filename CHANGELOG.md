# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-11

### Added

- `overclaim scan`: false-completion rate, false-claim share, honest-failure rate and pass rate
  by arm, model, effort, difficulty, task or tag, with task-clustered intervals; paired arm
  comparisons; detector precision and recall.
- `overclaim inspect`, `classify`, `label`, `agree` and `export`. `label` rows record
  `rubric_version`, `model` and `effort` (and `judge_version` for judge rows).
- `overclaim hook claude-stop`: a Claude Code Stop hook that sends an agent back once when it
  claims completion without a passing test run after its last edit (`--mode claim`), whatever
  the message says (`--mode always`), or for a requirement-by-requirement check of every
  report (`--mode audit`). `overclaim hook claude-post-tool` logs commands and edits for it
  when no session transcript is kept.
- Transcript readers for Claude Code (`stream-json` and session files), Codex (`exec --json`)
  and a generic JSONL format; agent-ab run directories and JSONL manifests as inputs. A
  `stream-json` transcript with several `result` events has all of their texts, joined, as its
  final message (`meta["result_count"]` counts them).
- Rule-based claim classifier with a labelled corpus and real-message fixtures; optional LLM
  labeller and judge through the `claude` CLI, with a cache.
- Task suites: 18 solvable tasks from agent-ab and 5 impossible tasks with near-miss checks.
- `scripts/package_results.py`: packages a run for publication, redacts the output of tool
  calls that read outside the trial workspace, scrubs home paths and the user name, and fails
  on surviving words from `--deny-list FILE`.
- Study 1 (setups): Haiku 5.5 and Sonnet 5.5 at low and high effort, 23 tasks, 184 trials.
  FCR on solvable tasks 11/14; no success claims on impossible tasks (0/40).
- Study 2 (interventions): `control`, `ask-verify`, `stop-hook` and `stop-audit` on Haiku 5.5,
  18 tasks, 288 trials. No intervention changed false-completion incidence detectably (FCR
  5/6, 6/9, 5/9, 6/7).
