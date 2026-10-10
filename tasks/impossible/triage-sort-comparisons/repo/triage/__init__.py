"""Ticket triage: order incoming support tickets by urgency."""

from .queue import sort_tickets, triage_batch
from .ticket import Ticket

__all__ = ["Ticket", "sort_tickets", "triage_batch"]
