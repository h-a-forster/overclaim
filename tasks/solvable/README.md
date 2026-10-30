# Solvable tasks

18 Python tasks copied unchanged from [agent-ab](https://github.com/h-a-forster/agent-ab)
(`examples/tasks`, commit `9f31a88`, MIT). Studies 1 and 2 used commit `7d3069e`, which
differs only in `feature-uri-resolve` (see below). Each has a prompt, a starting repo, visible
tests and a hidden check the agent never sees. Format: [agent-ab docs/tasks.md](https://github.com/h-a-forster/agent-ab/blob/main/docs/tasks.md).

They are the 18 of agent-ab's 50 tasks that failed at least once in agent-ab's published runs
(570 graded trials, mostly Claude Haiku 5.5 and Sonnet 5.5). The other 32 passed every time, so
they cannot produce a false completion.

`tasks/difficulty.json` buckets them by that historical pass rate, which comes from runs
independent of this study:

| Bucket | Historical pass rate | Tasks |
|---|---|---|
| `hard` | below 85% | bughunt-textadv, config-validation-errors, csv-quoted-newlines, data-interval-sets, feature-sql-select, feature-uri-resolve, money-decimal-rounding, semver-precedence, text-template-engine |
| `easy` | 85% or more | api-config-layers, bughunt-ratelimit, dedupe-quadratic, dst-daily-schedule, feature-decimal-context, feature-minire, feature-rope-buffer, feature-toml-config, text-unified-patch |

`feature-uri-resolve` failed all 9 historical trials. In the version studies 1 and 2 used, its
hidden oracle contradicted the prompt on one point: the prompt keeps percent-encoded hex digits
in a host uppercase, the oracle lowercased them, so an agent that followed the prompt failed.
agent-ab commit `9f31a88` makes the oracle and the reference solution follow the prompt and
adds a hidden test case for it; this directory has that version. The published results are
reported with and without the task; see [docs/results.md](../../docs/results.md#the-feature-uri-resolve-conflict).
