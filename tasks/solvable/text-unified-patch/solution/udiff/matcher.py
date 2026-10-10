"""Apply hunks to a list of lines."""

from __future__ import annotations

from .errors import PatchError
from .models import Hunk


def _find(lines: list[str], block: list[str], expected: int, lo: int, hi: int) -> int | None:
    """Closest position in ``[lo, hi]`` to ``expected`` where ``block`` matches (earlier on ties)."""
    if hi < lo:
        return None
    reach = max(abs(expected - lo), abs(hi - expected))
    for d in range(reach + 1):
        for q in (expected - d, expected + d):
            if lo <= q <= hi and lines[q : q + len(block)] == block:
                return q
    return None


def apply_hunks(lines: list[str], hunks: list[Hunk], file: str | None = None) -> list[str]:
    """Return ``lines`` with ``hunks`` applied, searching around each hunk's stated position."""
    out: list[str] = []
    pos = 0
    drift = 0
    for number, hunk in enumerate(hunks, start=1):
        block = hunk.old_block()
        nominal = hunk.old_start - 1 if hunk.old_len > 0 else hunk.old_start
        found = _find(lines, block, nominal + drift, pos, len(lines) - len(block))
        if found is None:
            raise PatchError("hunk does not apply", file=file, hunk=number)
        out.extend(lines[pos:found])
        out.extend(hunk.new_block())
        pos = found + len(block)
        drift = found - nominal
    out.extend(lines[pos:])
    return out
