"""A small, dependency-free CSV reader."""

from __future__ import annotations


class CSVError(ValueError):
    """Malformed CSV input. ``line`` is the 1-based physical line where the problem starts."""

    def __init__(self, message: str, line: int) -> None:
        super().__init__(f"line {line}: {message}")
        self.line = line


def parse(text: str, delimiter: str = ",") -> list[list[str]]:
    """Parse CSV ``text`` into rows of string fields.

    Fields may be wrapped in double quotes; inside quotes the delimiter is literal and a doubled
    quote (``""``) stands for one quote character. Empty lines are skipped.
    """
    if len(delimiter) != 1 or delimiter in '"\r\n':
        raise ValueError("delimiter must be a single character other than a quote or newline")
    rows = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line == "":
            continue
        rows.append(_split_line(line, delimiter, lineno))
    return rows


def _split_line(line: str, delimiter: str, lineno: int) -> list[str]:
    fields: list[str] = []
    buf: list[str] = []
    in_quotes = False
    i = 0
    while i < len(line):
        ch = line[i]
        if in_quotes:
            if ch == '"':
                if i + 1 < len(line) and line[i + 1] == '"':
                    buf.append('"')
                    i += 1
                else:
                    in_quotes = False
            else:
                buf.append(ch)
        elif ch == '"' and not buf:
            in_quotes = True
        elif ch == delimiter:
            fields.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    if in_quotes:
        raise CSVError("unterminated quoted field", lineno)
    fields.append("".join(buf))
    return fields
