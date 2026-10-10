"""Tickets compare by urgency, which only the scoring service can judge."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class Scorer(Protocol):
    def more_urgent(self, a: str, b: str) -> bool:
        """True if ticket ``a`` should be handled before ticket ``b``."""


@dataclass(eq=False)
class Ticket:
    """A support ticket. ``a < b`` means ``a`` is more urgent than ``b``.

    There is no numeric urgency score: the scoring service only answers pairwise questions,
    and each answer is a network round trip (~40 ms).
    """

    id: str
    subject: str
    scorer: Scorer = field(repr=False)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Ticket):
            return NotImplemented
        return self.scorer.more_urgent(self.id, other.id)
