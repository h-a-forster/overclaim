# dec

Decimal numbers for an invoicing tool.

```python
from dec import Dec

total = Dec("19.99") * 3 + Dec("0.50")      # exact
str(total)                                   # '60.47'
Dec("1.50") == Dec("1.5")                    # True (but prints differently)
Dec("2.345").round_places(2)                 # Dec('2.35'), ties away from zero
```

* `number.py` `Dec(sign, coefficient, exponent)`: parsing, `str` (scientific notation when the
  exponent is positive or the number is tiny), exact `+ - *`, numeric comparison, `as_tuple`,
  `adjusted`

Arithmetic on `Dec` operators is exact. Only `Dec` and `int` mix in expressions.

Run the tests with `python -m unittest discover -s tests -t .`.
