"""Money helpers for invoices and statements."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Union

Number = Union[int, float, str, Decimal]

# currency code -> (symbol, decimal places)
CURRENCIES = {
    "USD": ("$", 2),
    "EUR": ("€", 2),
    "GBP": ("£", 2),
    "JPY": ("¥", 0),
}


def _currency(code: str) -> tuple[str, int]:
    try:
        return CURRENCIES[code]
    except KeyError:
        raise ValueError(f"unsupported currency: {code}") from None


def to_decimal(amount: Number) -> Decimal:
    """Convert to Decimal; floats go through their shortest repr so 2.675 stays 2.675."""
    if isinstance(amount, Decimal):
        return amount
    if isinstance(amount, float):
        return Decimal(repr(amount))
    if isinstance(amount, (int, str)):
        return Decimal(amount)
    raise TypeError(f"unsupported amount type: {type(amount).__name__}")


def _quantize(value: Decimal, places: int) -> Decimal:
    # ROUND_HALF_UP in decimal rounds ties away from zero, for negatives too.
    return value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def format_money(amount: Number, currency: str = "USD") -> str:
    """Format ``amount`` like ``-$1,234.50``, rounded to the currency's minor unit.

    Halves round away from zero (``0.125`` -> ``0.13``), as on paper invoices.
    """
    symbol, places = _currency(currency)
    value = _quantize(to_decimal(amount), places)
    sign = "-" if value < 0 else ""  # -0.00 compares equal to 0, so no negative zero
    return f"{sign}{symbol}{abs(value):,.{places}f}"


def total(amounts: Iterable[Number]) -> Decimal:
    """Exact sum of line-item amounts."""
    return sum((to_decimal(a) for a in amounts), Decimal(0))


def split(amount: Number, parts: int, currency: str = "USD") -> list[Decimal]:
    """Split ``amount`` into ``parts`` shares in the currency's minor unit.

    The shares add up exactly to ``amount`` (rounded to the minor unit); any remainder goes to
    the first shares.
    """
    if parts < 1:
        raise ValueError("parts must be >= 1")
    _, places = _currency(currency)
    value = _quantize(to_decimal(amount), places)
    unit = Decimal(1).scaleb(-places)
    sign = -1 if value < 0 else 1
    minor_units = int(abs(value) / unit)
    base, remainder = divmod(minor_units, parts)
    shares = [(base + (1 if i < remainder else 0)) for i in range(parts)]
    return [_quantize(sign * share * unit, places) for share in shares]
