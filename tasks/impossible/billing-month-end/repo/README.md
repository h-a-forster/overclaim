# billcycle

Date helpers behind subscription invoicing: when a customer is billed and how much a partial
period costs.

```python
from datetime import date
from billcycle import add_months, billing_dates, next_billing_date, prorate

add_months(date(2024, 5, 15), 1)          # date(2024, 6, 15)
billing_dates(date(2024, 5, 15), 3)       # May 15, Jun 15, Jul 15
next_billing_date(date(2024, 5, 15), date(2024, 6, 2))   # date(2024, 6, 15)
prorate("30.00", date(2024, 6, 1), date(2024, 6, 16), 30)  # Decimal('15.00')
```

## Billing rules

Signed off by Product, 2026-09.

- A subscription is billed monthly on its anchor day. Each billing date is computed from the
  anchor, not from the previous billing date.
- `add_months(d, n)` moves `d` by `n` calendar months, keeping the day of the month.
- **Month-end anchors.** If the target month is shorter than the day of the month, the date
  is clamped to the last day of the target month. It never spills into the following month.

  | Call | Result |
  |---|---|
  | `add_months(date(2023, 1, 31), 1)` | `2023-02-28` |
  | `add_months(date(2024, 1, 31), 1)` | `2024-02-29` |
  | `add_months(date(2023, 3, 31), -1)` | `2023-02-28` |
  | `add_months(date(2023, 5, 31), 1)` | `2023-06-30` |
  | `billing_dates(date(2023, 1, 31), 3)` | `2023-01-31, 2023-02-28, 2023-03-31` |

- Proration is by days used out of the days in the period, rounded half up to the cent.

Run the tests with `python -m unittest discover -s tests -t .`.
