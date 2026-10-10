"""Ordering of ticket batches pulled from the inbound queue."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")

MAX_BATCH = 8


def sort_tickets(tickets: Sequence[T]) -> list[T]:
    """Return ``tickets`` ordered most urgent first (ascending by ``<``).

    Only ``<`` is used. Ties (neither ``a < b`` nor ``b < a``) keep their input order.
    Batches usually arrive already ordered (or reversed), so check for a single run first:
    that costs ``len - 1`` comparisons. Otherwise fall back to a stable merge sort.
    """
    items = list(tickets)
    if len(items) < 2:
        return items
    ascending = not (items[1] < items[0])
    for i in range(1, len(items) - 1):
        if ascending:
            if items[i + 1] < items[i]:
                break
        elif not (items[i + 1] < items[i]):
            break
    else:
        return items if ascending else items[::-1]
    return _merge_sort(items)


def _merge_sort(items: list[T]) -> list[T]:
    if len(items) < 2:
        return items
    mid = len(items) // 2
    left, right = _merge_sort(items[:mid]), _merge_sort(items[mid:])
    out: list[T] = []
    i = j = 0
    while i < len(left) and j < len(right):
        if right[j] < left[i]:
            out.append(right[j])
            j += 1
        else:
            out.append(left[i])
            i += 1
    return out + left[i:] + right[j:]


def triage_batch(tickets: Sequence[T]) -> list[T]:
    """Sort one batch from the queue; batches are at most ``MAX_BATCH`` tickets."""
    if len(tickets) > MAX_BATCH:
        raise ValueError(f"batch of {len(tickets)} exceeds MAX_BATCH={MAX_BATCH}")
    return sort_tickets(tickets)
