# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.1] - 2026-10-30

### Added

- Trials carry `prompt_sha256`: the sha256 of the task prompt (agent-ab `prompt.md`, line
  endings normalised to LF, or a recorded `prompt_sha256` field; a manifest's `prompt_sha256`
  field). `overclaim export` writes it after `agent_version`. The published
  `results/*/trials-derived.jsonl` files were regenerated with 0.1.1 and have this column.
- `experiments/setups-rerun.toml`: study 1's 18 solvable tasks and four arms (144 trials),
  rerun with the fixed `feature-uri-resolve` check. Data in `results/setups-rerun/` (labels,
  adjudications, gold labels, derived rows, detector report), write-up in `docs/results.md`
  and deviation 6 in `docs/method.md`: FCR 4/8 (50.0% [0.0, 78.5]) against study 1's 11/14,
  false-claim share 4.0%; the agent environment differed from study 1's.

### Changed

- `tasks/solvable/feature-uri-resolve` follows agent-ab commit `9f31a88`: the hidden oracle and
  the reference solution keep percent-encoded hex digits in a host uppercase, as the prompt
  says, and the hidden check has a test case for it. Studies 1 and 2 used the earlier check
  (tag `v0.1.0`); their published results are unchanged and the docs describe both.

### Fixed

- `is_test_command` recognises an interpreter held in a variable and run with `-m`
  (`$PY -m pytest`, PowerShell `& $py -m unittest`). The study 1 rerun used this form in 33
  transcripts; its evidence detectors now report 2 of 4 false completions with 41 false alarms
  (47 before), and study 1's 13 false alarms (14 before). Derived rows, detector reports and
  the rerun's archive were regenerated; the recorded LLM judge and `ruleproof` results were
  not re-run.
- agent-ab runs whose `attempt` or `repeat` fields are not integers, or whose `run.json`
  `config` is not an object, load instead of failing with a Python error.

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
- `scripts/package_results.py`: packages a run for publication. It keeps shell outputs only
  for test commands, redacts the output of other shell commands and of tool calls that read
  outside the trial workspace, scrubs home paths and the user name, and fails on surviving
  words from `--deny-list FILE`. Redaction changes no evidence field.
- Study 1 (setups): Haiku 5.5 and Sonnet 5.5 at low and high effort, 23 tasks, 184 trials.
  FCR on solvable tasks 11/14; no success claims on impossible tasks (0/40).
- Study 2 (interventions): `control`, `ask-verify`, `stop-hook` and `stop-audit` on Haiku 5.5,
  18 tasks, 288 trials. No intervention changed false-completion incidence detectably (FCR
  5/6, 6/9, 5/9, 6/7).
- `scripts/hook_activity.py`: counts Stop hook blocks and what agents did after them.
