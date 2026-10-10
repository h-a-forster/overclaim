# procure

Prices purchase orders against finance's yearly vendor price tables.

```python
from procure import load_po, po_total, unit_price

unit_price("ACME", "BOLT-M8", 2023)               # Decimal('0.61')
po_total(load_po("data/po/PO-23-0388.json"))      # Decimal('1166.20')
```

## Data

- `data/prices_<year>.csv`: finance's contracted unit prices in EUR for that year, columns
  `vendor,sku,unit_price`. Finance owns these files; we do not edit or derive prices
  ourselves.
- `data/po/*.json`: purchase orders exported from the ERP.

A missing year raises `PriceTableMissing`; an item not in that year's table raises
`UnknownItem`.

Run the tests with `python -m unittest discover -s tests -t .`.
