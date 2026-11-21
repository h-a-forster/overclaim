"""Check that the numbers in a prose document are copied from a generated summary.

A claim is a fragment of a document with `{key}` placeholders. Rendered with the summary's
formatted values it must appear in the document; whitespace and line breaks do not matter.
Every number in the document must then sit inside a placeholder of a matched claim, or inside a
literal listed as fixed: a version, a design constant, or a number that cannot be regenerated
from committed data, which the document must say next to it. Fenced code blocks and link
targets are not checked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from string import Formatter

FENCE = re.compile(r"^(```|~~~).*?^\1[^\n]*$", re.DOTALL | re.MULTILINE)
LINK_TARGET = re.compile(r"\]\([^)]*\)")
TOKEN = re.compile(r"[^\s()\[\]{};:/|*`\"'<>=]+")
NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
UNIT = re.compile(r"[$~+\-]?\d[\d,.]*(?:-\d[\d,.]*)*(?:%|pp|k|x)?[.,]?")
SKIP = re.compile(r"\d{4}-\d{2}-\d{2}[.,]?|v?\d+\.\d+\.\d+[.,]?|#\d+[.,]?")
ROW = re.compile(r"\s*\|")
ITEM = re.compile(r"\s*(?:[-*+]|\d+\.)\s")


def blocks(text: str) -> list[tuple[str, bool]]:
    """Paragraphs, list items and table rows as (text, is a table row).

    Fenced code and link targets are dropped and whitespace is collapsed.
    """
    out: list[tuple[str, bool]] = []
    lines: list[str] = []

    def flush(row: bool = False) -> None:
        words = " ".join(lines).split()
        if words:
            out.append((" ".join(words), row))
        lines.clear()

    for line in LINK_TARGET.sub("]", FENCE.sub("\n\n", text)).splitlines():
        row = bool(ROW.match(line))
        if row or ITEM.match(line) or not line.strip():
            flush()
        lines.append(line)
        if row:
            flush(row=True)
    flush()
    return out


def normalise(text: str) -> str:
    """Drop fenced code and link targets, and collapse whitespace."""
    return " ".join(block for block, _ in blocks(text))


def render(template: str, values: dict[str, str]) -> tuple[str, list[tuple[int, int]]]:
    """Fill `{key}` placeholders; return the text and the spans the values occupy."""
    parts: list[str] = []
    spans: list[tuple[int, int]] = []
    length = 0
    for literal, name, _spec, _conv in Formatter().parse(" ".join(template.split())):
        parts.append(literal)
        length += len(literal)
        if name is None:
            continue
        if name not in values:
            raise KeyError(f"no generated value {name!r} (claim {template!r})")
        value = values[name]
        parts.append(value)
        spans.append((length, length + len(value)))
        length += len(value)
    return "".join(parts), spans


def numbers(text: str) -> list[tuple[int, int, str]]:
    """Numbers in normalised text, skipping identifiers such as model names and dates."""
    found = []
    for token in TOKEN.finditer(text):
        word = token.group()
        if not any(c.isdigit() for c in word) or SKIP.fullmatch(word):
            continue
        if re.search(r"[A-Za-z]", word) and not UNIT.fullmatch(word):
            continue
        for match in NUMBER.finditer(word):
            start = token.start() + match.start()
            found.append((start, start + len(match.group()), match.group()))
    return found


@dataclass
class Result:
    missing_claims: list[str] = field(default_factory=list)
    missing_fixed: list[str] = field(default_factory=list)
    unchecked: list[str] = field(default_factory=list)


def check(
    text: str,
    claims: list[str],
    fixed: list[str],
    values: dict[str, str],
    exempt: str | None = None,
) -> Result:
    """Every claim and fixed literal must appear, and every number must be covered by one.

    With `exempt`, a paragraph, list item or table row that contains that marker text may hold
    other numbers, and so may the table that a marked paragraph ending in a colon introduces.
    Claims are still checked there.
    """
    parts = blocks(text)
    body = " ".join(block for block, _ in parts)
    covered = bytearray(len(body))
    result = Result()

    def mark(start: int, end: int) -> None:
        covered[start:end] = b"\x01" * (end - start)

    start, introduced = 0, False
    for block, row in parts:
        introduced = introduced and row
        marked = exempt is not None and exempt in block
        if marked or introduced:
            mark(start, start + len(block))
        introduced = introduced or (marked and block.endswith(":"))
        start += len(block) + 1

    for claim in claims:
        rendered, spans = render(claim, values)
        hits = [m.start() for m in re.finditer(re.escape(rendered), body)]
        if not hits:
            result.missing_claims.append(rendered)
        for hit in hits:
            for start, end in spans:
                mark(hit + start, hit + end)
    for literal in fixed:
        literal = " ".join(literal.split())
        hits = [m.start() for m in re.finditer(re.escape(literal), body)]
        if not hits:
            result.missing_fixed.append(literal)
        for hit in hits:
            mark(hit, hit + len(literal))
    for start, end, number in numbers(body):
        if not all(covered[start:end]):
            context = body[max(0, start - 40) : end + 20]
            result.unchecked.append(f"{number!r} in ...{context}...")
    return result
