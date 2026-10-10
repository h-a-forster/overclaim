# Contributing

Bug reports, wrong claim labels, new transcript formats, tasks and documentation fixes are
welcome.

## Setup

You need [uv](https://docs.astral.sh/uv/) and git. From a clone:

```sh
uv sync --group dev
uv run overclaim --version
```

## Tests and lint

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check src tests scripts
uv run python scripts/validate_impossible.py
```

CI runs these on Linux, macOS and Windows with Python 3.11-3.13 and smoke-tests a built wheel.

Tests must run offline and fast: no real agents and no model calls. `overclaim.llm` takes an
injectable runner; use a fake. Write files only under pytest's `tmp_path`, use `pathlib`, and
do not assume `sh`.

## Claim labels

The rule classifier (`src/overclaim/claims.py`) decides what counts as a claim of success, so
changes to it change published numbers.

- Add the message to `tests/fixtures/claims/corpus.jsonl` with its gold label before changing
  rules. Use split `tune` for messages you tune on.
- Report accuracy on every split in the pull request, including the real-message splits.
- Never move a held-out message into `tune` after seeing the classifier's output on it.
- The rubric lives in [docs/claims.md](docs/claims.md). If a change needs a new rule there, bump
  `RUBRIC_VERSION` in `src/overclaim/llm.py` too.

## Transcripts

Fixtures under `tests/fixtures/transcripts/` come from real sessions. Scrub paths, user names,
emails and anything private before committing one. Keep fixtures small.

## Tasks

- Solvable tasks follow [agent-ab's task format](https://github.com/h-a-forster/agent-ab/blob/main/docs/tasks.md)
  and must pass `agent-ab validate <config> --tasks`.
- Impossible tasks have no `solution/`. Each one needs an argument in
  `tasks/impossible/README.md` and at least one `near_miss/` that
  `scripts/validate_impossible.py` confirms fails.

## Changes

- Add an entry under "Unreleased" in [CHANGELOG.md](CHANGELOG.md) for user-visible changes.
- No runtime dependencies.

Security issues: see [SECURITY.md](SECURITY.md). Do not open a public issue.
