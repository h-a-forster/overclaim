# Solvable tasks

18 Python tasks copied unchanged from [agent-ab](https://github.com/h-a-forster/agent-ab)
(`examples/tasks`, commit `7d3069e`, MIT). Each has a prompt, a starting repo, visible tests and
a hidden check the agent never sees. Format: [agent-ab docs/tasks.md](https://github.com/h-a-forster/agent-ab/blob/main/docs/tasks.md).

They are the 18 of agent-ab's 50 tasks that failed at least once in agent-ab's published runs
(570 graded trials, mostly Claude Haiku 5.5 and Sonnet 5.5). The other 32 passed every time, so
they cannot produce a false completion.

`tasks/difficulty.json` buckets them by that historical pass rate, which comes from runs
independent of this study:

| Bucket | Historical pass rate | Tasks |
|---|---|---|
| `hard` | below 85% | bughunt-textadv, config-validation-errors, csv-quoted-newlines, data-interval-sets, feature-sql-select, feature-uri-resolve, money-decimal-rounding, semver-precedence, text-template-engine |
| `easy` | 85% or more | api-config-layers, bughunt-ratelimit, dedupe-quadratic, dst-daily-schedule, feature-decimal-context, feature-minire, feature-rope-buffer, feature-toml-config, text-unified-patch |

`feature-uri-resolve` failed all 9 historical trials. Its hidden oracle contradicts the prompt
on one point: the prompt keeps percent-encoded hex digits in a host uppercase, the oracle
lowercases them. An agent that follows the prompt fails. Results are reported with and without
it; see [docs/results.md](../../docs/results.md#the-feature-uri-resolve-conflict).
