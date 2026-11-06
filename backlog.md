# Backlog

## In progress

## Waiting on me

- Branch `polish-2026-10-30` merged into `main` through a pull request with CI green, by merge commit or fast-forward (CI has never run on this branch, including the SHA-pinned actions and the sdist test step).
- `results/setups-rerun/transcripts.tar.gz` uploaded as `setups-rerun-transcripts.tar.gz` to the `results-data` release with `SHA256SUMS` updated, and `results/README.md` no longer saying it is not uploaded and listing it in the download commands.
- v0.1.1 tagged after the merge, with a GitHub release from `docs/release-notes-0.1.1.md`; `CHANGELOG.md` and `CITATION.cff` say 2026-10-30, so update them if it is tagged later, and bring the later notes from the release notes (blank-output hang, sdist, CI, prompt digest) into the changelog.
- Decision on the 6 commits on `polish-2026-10-30` and 10 on `main` that carry a Claude `Co-Authored-By` trailer: reword the polish commits before merging, or leave them.
- Remote branch `upgrades-2026-10-23` deleted (merged as #1).

## Decided

## Proposed

- A clean rerun of study 1's solvable tasks under agent-ab trial isolation (about $34 for agents plus $12 for labels and judge), so the rerun's FCR is not confounded with the host's instructions.
- Evidence that reads a revert check as a passing suite plus an intended failure, so `failed` and detector false alarms are not inflated by agents who prove their tests fail on the old code.
- Rule classifier retuned on messages with revert-check narration and unverified lists, scored on a new held-out split, so the Stop hook does not miss most `complete` claims in that style (rerun: 36 of 101 read as `complete`).
- A Codex study, subtler impossible tasks and a sandboxed run, for the questions the studies could not answer.
