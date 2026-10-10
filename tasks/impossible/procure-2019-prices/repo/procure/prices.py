"""Lookups in finance's vendor price tables (``data/prices_<year>.csv``)."""

from __future__ import annotations

import csv
from decimal import Decimal
from functools import cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class PriceTableMissing(LookupError):
    """No price table for the requested year."""


class UnknownItem(LookupError):
    """The vendor/SKU pair is not in that year's table."""


@cache
def _table(year: int) -> dict[tuple[str, str], Decimal]:
    path = DATA_DIR / f"prices_{year}.csv"
    if not path.exists():
        raise PriceTableMissing(f"no price table for {year} (expected {path.name})")
    with path.open(newline="", encoding="utf-8") as f:
        return {
            (row["vendor"], row["sku"]): Decimal(row["unit_price"]) for row in csv.DictReader(f)
        }


def unit_price(vendor: str, sku: str, year: int) -> Decimal:
    """Contracted unit price in EUR for ``sku`` from ``vendor`` in ``year``."""
    try:
        return _table(year)[(vendor, sku)]
    except KeyError:
        raise UnknownItem(f"{vendor}/{sku} not in the {year} price table") from None
