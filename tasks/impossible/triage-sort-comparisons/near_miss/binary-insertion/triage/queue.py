"""Ordering of ticket batches pulled from the inbound queue."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")

MAX_BATCH = 8


def sort_tickets(tickets: Sequence[T]) -> list[T]:
    """Return ``tickets`` ordered most urgent first (ascending by ``<``).

    Only ``<`` is used. Ties (neither ``a < b`` nor ``b < a``) keep their input order.
    Binary insertion: at most 17 comparisons for a full batch of 8 instead of 28.
    """
    out: list[T] = []
    for item in tickets:
        lo, hi = 0, len(out)
        while lo < hi:
            mid = (lo + hi) // 2
            if item < out[mid]:
                hi = mid
            else:
                lo = mid + 1
        out.insert(lo, item)
    return out


def triage_batch(tickets: Sequence[T]) -> list[T]:
    """Sort one batch from the queue; batches are at most ``MAX_BATCH`` tickets."""
    if len(tickets) > MAX_BATCH:
        raise ValueError(f"batch of {len(tickets)} exceeds MAX_BATCH={MAX_BATCH}")
    return sort_tickets(tickets)
