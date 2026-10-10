import unittest
from datetime import date
from pathlib import Path

from rota import Person, RotaConfig, load_config, plan, render

CONFIG = Path(__file__).resolve().parent.parent / "config" / "rota.toml"


def assert_valid(test, cfg, rota):
    test.assertEqual(sorted(rota), cfg.dates())
    people = {p.name: p for p in cfg.people}
    shifts = {}
    for day in cfg.dates():
        name = rota[day]
        test.assertIn(name, people)
        test.assertTrue(people[name].is_available(day), f"{name} unavailable on {day}")
        shifts.setdefault(name, []).append(day)
    for name, days in shifts.items():
        test.assertLessEqual(len(days), cfg.max_shifts_per_person, name)
        for a, b in zip(days, days[1:]):
            test.assertGreater((b - a).days, cfg.min_rest_days, f"{name}: {a} -> {b}")


class SmallTeamTests(unittest.TestCase):
    def test_spring_cover(self):
        cfg = RotaConfig(
            start=date(2026, 3, 2),
            days=10,
            min_rest_days=1,
            max_shifts_per_person=4,
            people=(
                Person("ana", ((date(2026, 3, 7), date(2026, 3, 7)),)),
                Person("ben", ((date(2026, 3, 6), date(2026, 3, 8)),)),
                Person("cy", ((date(2026, 3, 9), date(2026, 3, 10)),)),
            ),
        )
        assert_valid(self, cfg, plan(cfg))

    def test_two_people_alternate(self):
        cfg = RotaConfig(date(2026, 1, 5), 6, 1, 3, (Person("x"), Person("y")))
        rota = plan(cfg)
        assert_valid(self, cfg, rota)


class ShippedConfigTests(unittest.TestCase):
    def test_load_config(self):
        cfg = load_config(CONFIG)
        self.assertEqual(cfg.start, date(2026, 11, 2))
        self.assertEqual(cfg.days, 28)
        self.assertEqual([p.name for p in cfg.people], ["alice", "bo", "carol", "dana", "eli"])
        self.assertFalse(cfg.people[2].is_available(date(2026, 11, 10)))

    def test_november_rota_is_complete(self):
        cfg = load_config(CONFIG)
        rota = plan(cfg)
        self.assertEqual(len(rota), cfg.days)
        self.assertEqual(sorted(rota), cfg.dates())
        self.assertEqual(len(render(rota).splitlines()), cfg.days)


if __name__ == "__main__":
    unittest.main()
