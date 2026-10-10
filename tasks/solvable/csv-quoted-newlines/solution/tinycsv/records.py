"""Header-aware helpers on top of :mod:`tinycsv.reader`."""

from __future__ import annotations

from .reader import CSVError, parse_with_lines


def parse_records(text: str, delimiter: str = ",") -> list[dict[str, str]]:
    """Parse CSV with a header row into a list of dicts keyed by column name.

    A data row with a different number of fields than the header is an error.
    """
    rows = parse_with_lines(text, delimiter)
    if not rows:
        return []
    (header_line, header), *data = rows
    if len(set(header)) != len(header):
        raise CSVError("duplicate column name in header", header_line)
    records = []
    for line, row in data:
        if len(row) != len(header):
            raise CSVError(f"expected {len(header)} fields, got {len(row)}", line)
        records.append(dict(zip(header, row)))
    return records
