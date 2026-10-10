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
    index_of: dict[Hashable, int] = {}
    for record in records:
        key = record["id"]
        index = index_of.get(key)
        if index is None:
            index_of[key] = len(result)
            result.append(record)
        elif record["version"] >= result[index]["version"]:
            result[index] = record
    return result


def missing_ids(expected: Sequence[Hashable], present: Iterable[Record]) -> list[Hashable]:
    """Ids from ``expected`` (in that order, duplicates kept) that no record in ``present`` has."""
    present_ids = {r["id"] for r in present}
    return [i for i in expected if i not in present_ids]


def changed_ids(old: Iterable[Record], new: Iterable[Record]) -> list[Hashable]:
    """Ids whose record in ``new`` differs from the one in ``old`` (or is new), in ``new`` order."""
    last_old: dict[Hashable, Record] = {}
    for record in old:
        last_old[record["id"]] = record  # later records overwrite earlier ones
    out: list[Hashable] = []
    seen: set[Hashable] = set()
    for record in new:
        key = record["id"]
        if key in seen:
            continue
        if key not in last_old or last_old[key] != record:
            seen.add(key)
            out.append(key)
    return out
