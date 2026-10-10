import unittest
from decimal import Decimal
from pathlib import Path

from procure import PriceTableMissing, UnknownItem, load_po, po_total, unit_price

PO_DIR = Path(__file__).resolve().parent.parent / "data" / "po"


class UnitPriceTests(unittest.TestCase):
    def test_lookups(self):
        self.assertEqual(unit_price("ACME", "BOLT-M8", 2021), Decimal("0.52"))
        self.assertEqual(unit_price("NORDSTAHL", "PLATE-3MM", 2022), Decimal("131.20"))
        self.assertEqual(unit_price("KLEBTEC", "SEALANT-300", 2023), Decimal("9.70"))

    def test_unknown_item(self):
        with self.assertRaises(UnknownItem):
            unit_price("KLEBTEC", "SEALANT-300", 2021)

    def test_missing_year(self):
        with self.assertRaises(PriceTableMissing):
            unit_price("ACME", "BOLT-M8", 2015)


class PurchaseOrderTests(unittest.TestCase):
    def test_2021_order(self):
        self.assertEqual(po_total(load_po(PO_DIR / "PO-21-0107.json")), Decimal("302.80"))

    def test_2023_order(self):
        self.assertEqual(po_total(load_po(PO_DIR / "PO-23-0388.json")), Decimal("1166.20"))


class Audit2019Tests(unittest.TestCase):
    """Sample from the 2019 audit request: the auditors' figure for PO-19-0412."""

    def test_po_19_0412(self):
        self.assertEqual(po_total(load_po(PO_DIR / "PO-19-0412.json")), Decimal("1372.20"))


if __name__ == "__main__":
    unittest.main()
