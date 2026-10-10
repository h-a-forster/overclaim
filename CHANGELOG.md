# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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
