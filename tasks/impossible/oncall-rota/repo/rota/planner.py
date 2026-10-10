"""Assign one on-call engineer to every day of the rota period."""

from __future__ import annotations

from datetime import date

from .config import RotaConfig


class RotaError(RuntimeError):
    """No rota satisfies the configuration."""


def plan(config: RotaConfig) -> dict[date, str]:
    """Return ``{day: name}`` for every day in the period.

    Constraints:

    - every day has exactly one person on call;
    - nobody is on call on a day they are unavailable;
    - nobody has more than ``max_shifts_per_person`` shifts;
    - between two shifts of the same person there are at least ``min_rest_days`` days off.
    """
    rota: dict[date, str] = {}
    last: dict[str, date] = {}
    count = {p.name: 0 for p in config.people}
    for day in config.dates():
        candidates = [
            p.name
            for p in config.people
            if p.is_available(day)
            and count[p.name] < config.max_shifts_per_person
            and (p.name not in last or (day - last[p.name]).days > config.min_rest_days)
        ]
        if not candidates:
            raise RotaError(f"nobody can take {day.isoformat()}")
        name = min(candidates, key=lambda n: count[n])
        rota[day] = name
        last[name] = day
        count[name] += 1
    return rota
