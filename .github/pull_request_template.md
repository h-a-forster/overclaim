## What and why

<!-- What this changes and why. Link the issue if there is one. -->

## Checklist

- [ ] `uv run pytest` passes
- [ ] `uv run ruff check .` passes
- [ ] Tests added or updated (offline, no real agents or model calls, Windows-safe)
- [ ] Documentation updated (`README.md`, `docs/`) if behaviour, labels or metrics changed
- [ ] Entry added under "Unreleased" in `CHANGELOG.md` for user-visible changes
- [ ] No new runtime dependencies
- [ ] Claim classifier changes: corpus accuracy reported for both splits
- [ ] New impossible tasks: `python scripts/validate_impossible.py` passes
