import unittest

from layercfg import ConfigError, Field, Layer, Schema, load

SCHEMA = Schema({
    "db": {"host": Field(str, default="localhost"), "port": Field(int, default=5432)},
    "debug": Field(bool, default=False),
    "ratio": Field(float, default=0.5),
    "name": Field(str, required=True),
})


class Load(unittest.TestCase):
    def test_defaults_and_override(self):
        cfg = load(SCHEMA, [Layer("file", {"name": "x", "db": {"port": 1}}), Layer("late", {"db": {"port": 2}})])
        self.assertEqual(cfg.get("db.port"), 2)
        self.assertEqual(cfg.source("db.port"), "late")
        self.assertEqual(cfg.source("db.host"), "defaults")
        self.assertEqual(cfg["name"], "x")

    def test_as_dict(self):
        cfg = load(SCHEMA, [Layer("f", {"name": "n"})])
        self.assertEqual(cfg.as_dict()["db"], {"host": "localhost", "port": 5432})

    def test_type_errors(self):
        for data in ({"debug": 1}, {"db": {"port": True}}, {"db": {"port": "5"}}, {"zzz": 1}, {"db": 3}):
            with self.assertRaises(ConfigError):
                load(SCHEMA, [Layer("f", dict(data, name="n"))])

    def test_float_accepts_int(self):
        self.assertEqual(load(SCHEMA, [Layer("f", {"name": "n", "ratio": 2})]).get("ratio"), 2.0)

    def test_required(self):
        with self.assertRaises(ConfigError):
            load(SCHEMA, [])


if __name__ == "__main__":
    unittest.main()
