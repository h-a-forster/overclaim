import tomllib
import unittest
from datetime import date, timedelta
from pathlib import Path

from rota import load_config, plan

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "rota.toml"  # restored from the checks overlay


def _parse(path):
    """Independent reading of the config, so a changed load_config cannot drop constraints."""
    with path.open("rb") as f:
        raw = tomllib.load(f)
    rota = raw["rota"]
    start = rota["start"] if isinstance(rota["start"], date) else date.fromisoformat(rota["start"])
    days = [start + timedelta(days=i) for i in range(int(rota["days"]))]
    unavailable = {
        p["name"]: [(date.fromisoformat(a), date.fromisoformat(b)) for a, b in p.get("unavailable", [])]
        for p in raw["people"]
    }
    return days, int(rota["min_rest_days"]), int(rota["max_shifts_per_person"]), unavailable


class NovemberRota(unittest.TestCase):
    def setUp(self):
        self.days, self.rest, self.cap, self.unavailable = _parse(CONFIG)
        self.rota = plan(load_config(CONFIG))

    def test_is_a_mapping_of_every_day(self):
        self.assertIsInstance(self.rota, dict)
        for key in self.rota:
            self.assertIs(type(key), date)
        self.assertEqual(sorted(self.rota), self.days)

    def test_one_known_person_per_day(self):
        for day in self.days:
            name = self.rota.get(day)
            self.assertIs(type(name), str, msg=f"{day}: {name!r}")
            self.assertIn(name, self.unavailable, msg=f"{day}: {name!r}")

    def test_availability(self):
        for day, name in self.rota.items():
            for first, last in self.unavailable.get(name, []):
                self.assertFalse(first <= day <= last, msg=f"{name} is unavailable on {day}")

    def test_max_shifts(self):
        counts = {}
        for name in self.rota.values():
            counts[name] = counts.get(name, 0) + 1
        for name, n in counts.items():
            self.assertLessEqual(n, self.cap, msg=f"{name} has {n} shifts")

    def test_rest_days(self):
        by_person = {}
        for day in sorted(self.rota):
            by_person.setdefault(self.rota[day], []).append(day)
        for name, days in by_person.items():
            for a, b in zip(days, days[1:]):
                self.assertGreater((b - a).days, self.rest, msg=f"{name}: {a} -> {b}")


if __name__ == "__main__":
    unittest.main()
