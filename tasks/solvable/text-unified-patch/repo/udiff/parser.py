"""Parse unified diff text."""

from __future__ import annotations

import re

from .errors import PatchError
from .models import FilePatch, Hunk

_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _path(raw: str) -> str:
    return raw.split("\t", 1)[0].rstrip()


def parse_patch(text: str) -> list[FilePatch]:
    """Parse ``text`` into one :class:`FilePatch` per ``---``/``+++`` pair."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    patches: list[FilePatch] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- ") and i + 1 < len(lines) and lines[i + 1].startswith("+++ "):
            patches.append(FilePatch(_path(line[4:]), _path(lines[i + 1][4:])))
            i += 2
            continue
        m = _HEADER.match(line)
        if m:
            if not patches:
                raise PatchError("hunk before any file header", line=i + 1)
            old_len = 1 if m.group(2) is None else int(m.group(2))
            new_len = 1 if m.group(4) is None else int(m.group(4))
            hunk = Hunk(int(m.group(1)), old_len, int(m.group(3)), new_len)
            i += 1
            while (old_len > 0 or new_len > 0) and i < len(lines):
                body = lines[i]
                tag, rest = body[:1], body[1:]
                if tag == " ":
                    old_len, new_len = old_len - 1, new_len - 1
                elif tag == "-":
                    old_len -= 1
                elif tag == "+":
                    new_len -= 1
                else:
                    raise PatchError("unexpected line in hunk", line=i + 1)
                hunk.lines.append((tag, rest))
                i += 1
            patches[-1].hunks.append(hunk)
            continue
        i += 1  # junk between files (diff --git, index ..., etc.)
    return patches
