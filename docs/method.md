# Study design

This plan was committed before the main runs were analysed. Only a 20-trial pilot
(`runs/pilot-setups`, not used in the results) had been looked at. Changes after that point are
listed under [Deviations](#deviations).

## Question

When a coding agent says it finished, how often does an independent hidden check say it did not?
Does that depend on the model, the effort level or the task? Can a cheap detector catch these
cases, and does a "verify before you say done" Stop hook prevent them?

## Unit and ground truth

- **Trial:** one run of an agent (Claude Code, `claude -p`) on one task in a fresh workspace,
  driven by [agent-ab](https://github.com/h-a-forster/agent-ab).
- **Ground truth:** the task's hidden check. It runs after the agent stops, from files the agent
  never saw. Exit 0 is a pass. Infrastructure errors are ungraded and excluded.
- **Claim:** the label of the agent's final message: `complete`, `partial`, `incomplete` or
  `none` ([claims.md](claims.md)). Runs that ended on a timeout, the turn limit or a tool call
  have no final message and are labelled `none`.

## Tasks

- 18 solvable Python tasks from agent-ab: the ones that failed at least once in agent-ab's
  published runs ([tasks/solvable](../tasks/solvable/README.md)). They are bucketed `easy` (at
  least 85% historical pass rate) or `hard`, using runs independent of this study.
- 5 impossible tasks ([tasks/impossible](../tasks/impossible/README.md)). The requirement cannot
  be met (counting arguments, a lower bound, missing data, a spec that contradicts its tests), so
  every `complete` claim on them is false by construction.

## Studies

1. **Setups** ([experiments/setups.toml](../experiments/setups.toml)): Claude Haiku 5.5 and
   Sonnet 5.5, each at effort `low` and `high`. 23 tasks x 4 arms x 2 repeats = 184 trials.
2. **Interventions** ([experiments/interventions.toml](../experiments/interventions.toml)):
   Haiku 5.5 at the CLI's default effort, with three arms:
   - `control`: the task prompt only;
   - `ask-verify`: the prompt plus a request to verify and to state what is unverified;
   - `stop-hook`: overclaim's Stop hook.

   23 tasks x 3 arms x 3 repeats = 207 trials.

Claude Code 2.1.296, `--setting-sources project`, no MCP servers, `bypassPermissions`, at most
100 turns and $2 per trial, 30 minutes per trial.

## Labels

- **Primary labels:** Claude Sonnet 5.5 at low effort with a fixed rubric (`RUBRIC_VERSION`
  in `src/overclaim/llm.py`), given the task prompt and the final message only. It never sees
  the hidden-check result.
- **Second labels:** Claude Opus 5.5 with the same rubric. Agreement is reported as Cohen's
  kappa.
- **Gold labels:** where the two models agree, their label. Where they disagree, a human reads
  the message and decides, blind to the hidden-check result.
- **Rule classifier:** the offline classifier (`overclaim.claims`, which the Stop hook uses) is
  scored against the gold labels. It was tuned on real messages from half the tasks, chosen at
  random with seed 0, and is scored on the other half.

## Outcomes

Primary:

- **False-completion rate (FCR)** = P(claim `complete` | hidden check failed), per arm.
- **False-claim share** = P(hidden check failed | claim `complete`): how often "done" is wrong.

Secondary:

- **Honest-failure rate:** P(`partial` or `incomplete` | failed).
- **Pass rate.**
- **Verification breakdown of false completions:** what the agent's last test run after its last
  edit showed (`passed`, `failed`, `not_run`, `unknown`).
- **FCR on impossible tasks** alone.
- **Detector precision and recall** among `complete` claims. The positive class is "hidden check
  failed". Detectors: `unverified`, `claims-tests-unbacked`, `ruleproof`, and an LLM judge
  (Sonnet 5.5, which sees the task, diff, final message and evidence summary, but not the
  hidden check).
- **Interventions:** the paired difference in false-completion incidence per task vs `control`
  (sign-flip permutation test, Holm across the two arms, alpha 0.05), plus pass rate and cost.

## Statistics

- **Rates** are pooled over trials. Their 95% intervals resample tasks (cluster bootstrap,
  4,000 draws) and are widened to a design-effect-adjusted Wilson interval at the boundaries
  ([metrics.md](metrics.md)).
- **Comparisons** are paired by task.
- **Verdicts:** a difference is reported only when the Holm-adjusted p < 0.05 and the CI
  excludes 0. Otherwise the result is "no detectable difference", with the interval.

Expected precision: the pilot and agent-ab's history suggest 15–25% of solvable-task trials fail,
so each setup arm has roughly 10–15 failures. FCR per arm will have wide intervals (about ±25
points). Pooled FCR and the impossible-task rates are the headline numbers. Differences between
arms are reported as exploratory.

## Sensitivity analyses

- **Without `feature-uri-resolve`,** which has a known gap in its spec.
- **Primary labels replaced** by the rule classifier, and by the Opus labels.

## Deviations

None yet.
