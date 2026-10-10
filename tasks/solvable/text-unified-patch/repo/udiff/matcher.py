"""Apply hunks to a list of lines."""

from __future__ import annotations

from .errors import PatchError
from .models import Hunk


def apply_hunks(lines: list[str], hunks: list[Hunk], file: str | None = None) -> list[str]:
    """Return ``lines`` with ``hunks`` applied. Every hunk must match at its stated position."""
    out: list[str] = []
    pos = 0
    for number, hunk in enumerate(hunks, start=1):
        start = hunk.old_start - 1 if hunk.old_len > 0 else hunk.old_start
        block = hunk.old_block()
        if start < pos or lines[start : start + len(block)] != block:
            raise PatchError("hunk does not apply", file=file, hunk=number)
        out.extend(lines[pos:start])
        out.extend(hunk.new_block())
        pos = start + len(block)
    out.extend(lines[pos:])
    return out
