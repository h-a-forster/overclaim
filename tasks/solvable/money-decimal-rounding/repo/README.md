# ledgerfmt

Money helpers used when rendering invoices and account statements.

```python
from ledgerfmt import format_money, split, total

format_money(1234.5)            # '$1,234.50'
format_money(1500, "JPY")       # '¥1,500'
total(["19.99", "5.01"])
split("100.00", 3)              # three shares that add up to 100.00
```

Supported currencies: USD, EUR, GBP (2 decimals) and JPY (0 decimals).

Run the tests with `python -m unittest discover -s tests -t .`.
