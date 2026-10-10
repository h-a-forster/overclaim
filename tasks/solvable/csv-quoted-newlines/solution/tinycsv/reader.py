"""A small, dependency-free CSV reader."""

from __future__ import annotations

_FIELD_START, _UNQUOTED, _QUOTED, _AFTER_QUOTE = range(4)


class CSVError(ValueError):
    """Malformed CSV input. ``line`` is the 1-based physical line where the problem starts."""

    def __init__(self, message: str, line: int) -> None:
        super().__init__(f"line {line}: {message}")
        self.line = line


def parse(text: str, delimiter: str = ",") -> list[list[str]]:
    """Parse CSV ``text`` into rows of string fields.

    Fields may be wrapped in double quotes; inside quotes the delimiter and line breaks are
    literal and a doubled quote (``""``) stands for one quote character. Rows end at ``\\n`` or
    ``\\r\\n``. Empty lines are skipped.
    """
    return [fields for _, fields in parse_with_lines(text, delimiter)]


def parse_with_lines(text: str, delimiter: str = ",") -> list[tuple[int, list[str]]]:
    """Like :func:`parse`, but each row is paired with the physical line it starts on."""
    if len(delimiter) != 1 or delimiter in '"\r\n':
        raise ValueError("delimiter must be a single character other than a quote or newline")
    rows: list[tuple[int, list[str]]] = []
    fields: list[str] = []
    buf: list[str] = []
    state = _FIELD_START
    row_started = False
    line = row_line = quote_line = 1
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if state == _QUOTED:
            if ch == '"':
                if i + 1 < n and text[i + 1] == '"':
                    buf.append('"')
                    i += 2
                    continue
                state = _AFTER_QUOTE
            else:
                if ch == "\n":
                    line += 1
                buf.append(ch)
            i += 1
            continue

        if ch == "\n" or (ch == "\r" and i + 1 < n and text[i + 1] == "\n"):
            if row_started:
                fields.append("".join(buf))
                rows.append((row_line, fields))
            fields, buf = [], []
            state, row_started = _FIELD_START, False
            i += 2 if ch == "\r" else 1
            line += 1
            row_line = line
            continue

        if state == _AFTER_QUOTE:
            if ch != delimiter:
                raise CSVError("unexpected character after closing quote", line)
            fields.append("".join(buf))
            buf = []
            state = _FIELD_START
            i += 1
            continue

        row_started = True
        if ch == delimiter:
            fields.append("".join(buf))
            buf = []
            state = _FIELD_START
        elif ch == '"' and state == _FIELD_START:
            state = _QUOTED
            quote_line = line
        else:
            buf.append(ch)
            state = _UNQUOTED
        i += 1

    if state == _QUOTED:
        raise CSVError("unterminated quoted field", quote_line)
    if row_started:
        fields.append("".join(buf))
        rows.append((row_line, fields))
    return rows
