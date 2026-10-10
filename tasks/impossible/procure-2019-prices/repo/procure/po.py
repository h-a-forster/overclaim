"""Purchase orders and their totals."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from .prices import unit_price


@dataclass(frozen=True)
class Line:
    vendor: str
    sku: str
    qty: int


@dataclass(frozen=True)
class PurchaseOrder:
    number: str
    year: int
    lines: tuple[Line, ...]


def load_po(path: str | Path) -> PurchaseOrder:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    lines = tuple(Line(ln["vendor"], ln["sku"], int(ln["qty"])) for ln in raw["lines"])
    return PurchaseOrder(raw["number"], int(raw["year"]), lines)


def po_total(po: PurchaseOrder) -> Decimal:
    """Sum of ``qty * unit price`` over the lines, rounded half up to the cent."""
    total = sum(
        (ln.qty * unit_price(ln.vendor, ln.sku, po.year) for ln in po.lines), Decimal("0")
    )
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
