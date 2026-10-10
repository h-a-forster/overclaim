"""Ordering of ticket batches pulled from the inbound queue."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")

MAX_BATCH = 8


def sort_tickets(tickets: Sequence[T]) -> list[T]:
    """Return ``tickets`` ordered most urgent first (ascending by ``<``).

    Only ``<`` is used. Ties (neither ``a < b`` nor ``b < a``) keep their input order.
    """
    items = list(tickets)
    out: list[T] = []
    while items:
        best = 0
        for i in range(1, len(items)):
            if items[i] < items[best]:
                best = i
        out.append(items.pop(best))
    return out


def triage_batch(tickets: Sequence[T]) -> list[T]:
    """Sort one batch from the queue; batches are at most ``MAX_BATCH`` tickets."""
    if len(tickets) > MAX_BATCH:
        raise ValueError(f"batch of {len(tickets)} exceeds MAX_BATCH={MAX_BATCH}")
    return sort_tickets(tickets)
