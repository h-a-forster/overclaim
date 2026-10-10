# Experiments

Experiment configs for [agent-ab](https://github.com/h-a-forster/agent-ab). Each `.toml` file
is one study; agent-ab runs every task in every arm and keeps each trial's transcript, which
`overclaim scan` reads. Task paths in the configs are relative to this directory.

| File | Study | Tasks | Arms | Trials | Results |
|---|---|---|---|---|---|
| [setups.toml](setups.toml) | 1: models and effort levels | 18 solvable + 5 impossible | `haiku-low`, `haiku-high`, `sonnet-low`, `sonnet-high` | 23 x 4 x 2 = 184 | [docs/results.md](../docs/results.md#study-1-models-and-effort-levels) |
| [interventions.toml](interventions.toml) | 2: interventions | 18 solvable | `control`, `ask-verify`, `stop-hook`, `stop-audit` | 18 x 4 x 4 = 288 | [docs/results.md](../docs/results.md#study-2-interventions) |

Both use Claude Code (`claude-code` adapter) with `bypassPermissions`, `--setting-sources
project`, at most 100 turns, $2 and 30 minutes per trial. The design and its deviations are in
[docs/method.md](../docs/method.md).

## Arms

`setups.toml`: Claude Haiku 5.5 and Sonnet 5.5, each at effort `low` and `high`. The baseline is
`haiku-low`.

`interventions.toml`: Claude Haiku 5.5 at the CLI's default effort. The baseline is `control`.

- `control`: the task prompt only.
- `ask-verify`: the prompt plus a suffix (`prompt_suffix`) asking the agent to run the tests
  after its last change and to say what it verified and what is unfinished, failing or
  unverified.
- `stop-hook`: overlay [arms/stop-hook](arms/stop-hook). Its `.claude/settings.json` runs the
  overclaim Stop hook with `--mode claim`: a completion claim without a passing test run after
  the last edit is sent back once.
- `stop-audit`: overlay [arms/stop-audit](arms/stop-audit). The same hook with `--mode audit`:
  every completion claim is sent back once for a requirement-by-requirement check.

agent-ab copies an arm's overlay directory into each trial workspace. Both overlays also
register the `PostToolUse` and `PostToolUseFailure` logger, so the Stop hook has evidence
without a session transcript. The hooks run `python .claude/hooks/overclaim.pyz`, a zipapp
built from `src/` that is not in git. It needs Python 3.11+ on `PATH` and nothing else. See
[docs/hook.md](../docs/hook.md) for the hook's behaviour.

## Running

The agents run unattended with full permissions. Use a container or a disposable VM.

Study 1:

```sh
agent-ab validate experiments/setups.toml
agent-ab run experiments/setups.toml --out runs/setups
overclaim scan runs/setups --by arm,difficulty --difficulty tasks/difficulty.json
```

`agent-ab validate --tasks` fails on the impossible tasks by design. Validate those with
`scripts/validate_impossible.py`, and the solvable ones with `--only` on `tasks/solvable`.

Study 2 (build the hook first, so both hook arms contain the current `overclaim.pyz`):

```sh
python scripts/build_hook.py
agent-ab run experiments/interventions.toml --out runs/interventions
overclaim scan runs/interventions --baseline control --difficulty tasks/difficulty.json
```

Rebuild the hook after any change under `src/overclaim/`. The zipapp is deterministic, so the
same source gives the same file. Published data and how it was packaged:
[results/README.md](../results/README.md).
