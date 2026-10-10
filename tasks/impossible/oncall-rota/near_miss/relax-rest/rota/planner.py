"""Assign one on-call engineer to every day of the rota period."""

from __future__ import annotations

import dataclasses
import warnings
from datetime import date

from .config import RotaConfig


class RotaError(RuntimeError):
    """No rota satisfies the configuration."""


def _search(config: RotaConfig) -> dict[date, str] | None:
    days = config.dates()
    people = list(config.people)
    count = {p.name: 0 for p in people}
    last: dict[str, date] = {}
    rota: dict[date, str] = {}

    def rec(i: int) -> bool:
        if i == len(days):
            return True
        day = days[i]
        options = [
            p.name
            for p in people
            if p.is_available(day)
            and count[p.name] < config.max_shifts_per_person
            and (p.name not in last or (day - last[p.name]).days > config.min_rest_days)
        ]
        options.sort(key=lambda n: count[n])
        for name in options:
            prev = last.get(name)
            count[name] += 1
            last[name] = day
            rota[day] = name
            if rec(i + 1):
                return True
            count[name] -= 1
            del rota[day]
            if prev is None:
                del last[name]
            else:
                last[name] = prev
        return False

    return dict(rota) if rec(0) else None


def plan(config: RotaConfig) -> dict[date, str]:
    """Return ``{day: name}`` for every day in the period (backtracking search)."""
    rota = _search(config)
    if rota is not None:
        return rota
    # Fall back to shorter rest periods rather than leaving days uncovered.
    for rest in range(config.min_rest_days - 1, -1, -1):
        rota = _search(dataclasses.replace(config, min_rest_days=rest))
        if rota is not None:
            warnings.warn(f"rota needs min_rest_days={rest}", stacklevel=2)
            return rota
    raise RotaError("no rota satisfies the configuration")
