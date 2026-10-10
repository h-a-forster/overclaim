"""Lookups in finance's vendor price tables (``data/prices_<year>.csv``)."""

from __future__ import annotations

import csv
import warnings
from decimal import Decimal
from functools import cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class PriceTableMissing(LookupError):
    """No price table for the requested year."""


class UnknownItem(LookupError):
    """The vendor/SKU pair is not in that year's table."""


def _available_years() -> list[int]:
    return sorted(int(p.stem.split("_")[1]) for p in DATA_DIR.glob("prices_*.csv"))


def _resolve_year(year: int) -> int:
    if (DATA_DIR / f"prices_{year}.csv").exists():
        return year
    years = _available_years()
    if not years or abs(min(years, key=lambda y: abs(y - year)) - year) > 2:
        raise PriceTableMissing(f"no price table for {year} (expected prices_{year}.csv)")
    nearest = min(years, key=lambda y: abs(y - year))
    warnings.warn(f"no price table for {year}; using {nearest}", stacklevel=3)
    return nearest


@cache
def _table(year: int) -> dict[tuple[str, str], Decimal]:
    path = DATA_DIR / f"prices_{_resolve_year(year)}.csv"
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
