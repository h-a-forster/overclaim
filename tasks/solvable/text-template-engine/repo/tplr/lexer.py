"""Split template source into text and tag tokens."""

from __future__ import annotations

import re
from typing import NamedTuple

_TOKEN = re.compile(r"(\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\})", re.S)


class Token(NamedTuple):
    kind: str  # "text", "var" or "tag"
    text: str
    line: int


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    line = 1
    for piece in _TOKEN.split(source):
        if piece == "":
            continue
        if piece.startswith("{{") and piece.endswith("}}"):
            tokens.append(Token("var", piece[2:-2].strip(), line))
        elif piece.startswith("{%") and piece.endswith("%}"):
            tokens.append(Token("tag", piece[2:-2].strip(), line))
        elif piece.startswith("{#") and piece.endswith("#}"):
            pass  # comment
        else:
            tokens.append(Token("text", piece, line))
        line += piece.count("\n")
    return tokens
