# rota

Generates the platform team's on-call rota from `config/rota.toml`.

```python
from rota import load_config, plan, render

rota = plan(load_config("config/rota.toml"))   # {date: name}
print(render(rota))
```

## Rules

- Exactly one person is on call every day of the period (`start`, `days`).
- Nobody is on call on a day inside one of their `unavailable` ranges (inclusive).
- Nobody takes more than `max_shifts_per_person` shifts in the period.
- Between two shifts of the same person there are at least `min_rest_days` full days off
  (with `min_rest_days = 2`, a shift on Monday means the next one is Thursday at the
  earliest).

`plan()` raises `RotaError` when it cannot build a rota.

Run the tests with `python -m unittest discover -s tests -t .`.
