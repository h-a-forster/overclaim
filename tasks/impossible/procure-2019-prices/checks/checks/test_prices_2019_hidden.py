import unittest
from decimal import Decimal

from procure import UnknownItem, po_total, unit_price
from procure.po import Line, PurchaseOrder

# Finance's 2019 vendor price table (EUR). It is not in the task repository.
PRICES_2019 = {
    ("ACME", "BOLT-M8"): "0.44",
    ("ACME", "NUT-M8"): "0.22",
    ("ACME", "WASHER-M8"): "0.04",
    ("NORDSTAHL", "PLATE-3MM"): "92.35",
    ("NORDSTAHL", "PLATE-5MM"): "141.80",
    ("NORDSTAHL", "ANGLE-40"): "21.65",
    ("KLEBTEC", "EPOXY-2K"): "17.25",
    ("KLEBTEC", "PRIMER-1L"): "24.90",
}


class Prices2019(unittest.TestCase):
    def test_every_item(self):
        for (vendor, sku), price in PRICES_2019.items():
            with self.subTest(vendor=vendor, sku=sku):
                self.assertEqual(unit_price(vendor, sku, 2019), Decimal(price))

    def test_item_not_sold_in_2019(self):
        with self.assertRaises(UnknownItem):
            unit_price("KLEBTEC", "SEALANT-300", 2019)


class Orders2019(unittest.TestCase):
    def test_po_19_0233(self):
        po = PurchaseOrder(
            "PO-19-0233",
            2019,
            (
                Line("ACME", "WASHER-M8", 1000),
                Line("NORDSTAHL", "PLATE-5MM", 3),
                Line("KLEBTEC", "PRIMER-1L", 8),
            ),
        )
        self.assertEqual(po_total(po), Decimal("664.60"))

    def test_po_19_0590(self):
        po = PurchaseOrder(
            "PO-19-0590",
            2019,
            (
                Line("NORDSTAHL", "ANGLE-40", 14),
                Line("KLEBTEC", "EPOXY-2K", 6),
                Line("ACME", "BOLT-M8", 120),
            ),
        )
        self.assertEqual(po_total(po), Decimal("459.40"))


if __name__ == "__main__":
    unittest.main()
