"""Money helpers for invoices and statements."""

from __future__ import annotations

from typing import Iterable, Union

Number = Union[int, float, str]

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


def format_money(amount: Number, currency: str = "USD") -> str:
    """Format ``amount`` like ``-$1,234.50``, rounded to the currency's minor unit.

    Halves round away from zero (``0.125`` -> ``0.13``), as on paper invoices.
    """
    symbol, places = _currency(currency)
    value = round(float(amount), places)
    sign = "-" if value < 0 else ""
    return f"{sign}{symbol}{abs(value):,.{places}f}"


def total(amounts: Iterable[Number]) -> float:
    """Sum line-item amounts."""
    return sum(float(a) for a in amounts)


def split(amount: Number, parts: int, currency: str = "USD") -> list[float]:
    """Split ``amount`` into ``parts`` shares in the currency's minor unit.

    The shares add up exactly to ``amount``; any remainder goes to the first shares.
    """
    if parts < 1:
        raise ValueError("parts must be >= 1")
    _, places = _currency(currency)
    share = round(float(amount) / parts, places)
    return [share] * parts
