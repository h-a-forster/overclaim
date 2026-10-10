"""Rota configuration (``config/rota.toml``)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path


@dataclass(frozen=True)
class Person:
    name: str
    # Inclusive (first, last) date ranges when the person cannot be on call.
    unavailable: tuple[tuple[date, date], ...] = ()

    def is_available(self, day: date) -> bool:
        return not any(first <= day <= last for first, last in self.unavailable)


@dataclass(frozen=True)
class RotaConfig:
    start: date
    days: int
    min_rest_days: int
    max_shifts_per_person: int
    people: tuple[Person, ...] = field(default=())

    def dates(self) -> list[date]:
        return [self.start + timedelta(days=i) for i in range(self.days)]


def _date(value: object) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def load_config(path: str | Path) -> RotaConfig:
    with Path(path).open("rb") as f:
        raw = tomllib.load(f)
    rota = raw["rota"]
    people = tuple(
        Person(
            p["name"],
            tuple((_date(a), _date(b)) for a, b in p.get("unavailable", [])),
        )
        for p in raw["people"]
    )
    return RotaConfig(
        start=_date(rota["start"]),
        days=int(rota["days"]),
        min_rest_days=int(rota["min_rest_days"]),
        max_shifts_per_person=int(rota["max_shifts_per_person"]),
        people=people,
    )
