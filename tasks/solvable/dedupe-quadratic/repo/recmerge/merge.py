"""Merge record batches coming from several upstream exports."""

from __future__ import annotations

from typing import Any, Hashable, Iterable, Mapping, Sequence

Record = Mapping[str, Any]


def consolidate(records: Iterable[Record]) -> list[Record]:
    """Keep one record per ``"id"``: the one with the highest ``"version"``.

    On equal versions the record that comes later in the input wins. The result lists ids in
    the order in which each id first appeared, and contains the original record objects.
    """
    result: list[Record] = []
    for record in records:
        ids = [r["id"] for r in result]
        if record["id"] in ids:
            index = ids.index(record["id"])
            if record["version"] >= result[index]["version"]:
                result[index] = record
        else:
            result.append(record)
    return result


def missing_ids(expected: Sequence[Hashable], present: Iterable[Record]) -> list[Hashable]:
    """Ids from ``expected`` (in that order, duplicates kept) that no record in ``present`` has."""
    present_ids = [r["id"] for r in present]
    return [i for i in expected if i not in present_ids]


def changed_ids(old: Iterable[Record], new: Iterable[Record]) -> list[Hashable]:
    """Ids whose record in ``new`` differs from the one in ``old`` (or is new), in ``new`` order."""
    old_list = list(old)
    out = []
    for record in new:
        match = [r for r in old_list if r["id"] == record["id"]]
        if not match or match[-1] != record:
            if record["id"] not in out:
                out.append(record["id"])
    return out
