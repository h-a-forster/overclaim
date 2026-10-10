"""Split template source into text and tag tokens."""

from __future__ import annotations

import re
from typing import NamedTuple

from .errors import TemplateSyntaxError

_OPEN = re.compile(r"\{[{%#]")
_CLOSE = {"{{": "}}", "{%": "%}", "{#": "#}"}


class Token(NamedTuple):
    kind: str  # "text", "var" or "tag"
    text: str
    line: int


def _scan_end(source: str, start: int, opener: str) -> int:
    """Index of the closing delimiter for the tag opened at ``start``."""
    close = _CLOSE[opener]
    if opener == "{#":
        end = source.find(close, start + 2)
        if end < 0:
            raise TemplateSyntaxError("unterminated comment", source.count("\n", 0, start) + 1)
        return end
    quote = None
    j = start + 2
    n = len(source)
    while j < n:
        c = source[j]
        if quote:
            if c == "\\":
                j += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif source.startswith(close, j):
            return j
        j += 1
    kind = "output tag" if opener == "{{" else "block tag"
    raise TemplateSyntaxError(f"unterminated {kind}", source.count("\n", 0, start) + 1)


def tokenize(source: str) -> list[Token]:
    # raw entries: [kind, text, line, strip_before, strip_after]
    raw: list[list] = []
    pos = 0
    while True:
        m = _OPEN.search(source, pos)
        if not m:
            break
        start = m.start()
        if start > pos:
            raw.append(["text", source[pos:start], source.count("\n", 0, pos) + 1, False, False])
        end = _scan_end(source, start, m.group())
        body = source[start + 2 : end]
        strip_before = body.startswith("-")
        if strip_before:
            body = body[1:]
        strip_after = body.endswith("-")
        if strip_after:
            body = body[:-1]
        kind = {"{{": "var", "{%": "tag", "{#": "comment"}[m.group()]
        raw.append([kind, body.strip(), source.count("\n", 0, start) + 1, strip_before, strip_after])
        pos = end + 2
    if pos < len(source):
        raw.append(["text", source[pos:], source.count("\n", 0, pos) + 1, False, False])
    for k, entry in enumerate(raw):
        if entry[0] == "text":
            continue
        if entry[3] and k > 0 and raw[k - 1][0] == "text":
            raw[k - 1][1] = raw[k - 1][1].rstrip()
        if entry[4] and k + 1 < len(raw) and raw[k + 1][0] == "text":
            raw[k + 1][1] = raw[k + 1][1].lstrip()
    return [
        Token(kind, text, line)
        for kind, text, line, _, _ in raw
        if kind != "comment" and not (kind == "text" and text == "")
    ]
