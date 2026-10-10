"""Proration of a monthly price for partial periods."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal


def prorate(monthly_price: Decimal | str, start: date, end: date, period_days: int) -> Decimal:
    """Charge for ``start`` (inclusive) to ``end`` (exclusive) out of a ``period_days`` period."""
    if end < start:
        raise ValueError("end before start")
    if period_days <= 0:
        raise ValueError("period_days must be positive")
    used = (end - start).days
    amount = Decimal(monthly_price) * used / period_days
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
