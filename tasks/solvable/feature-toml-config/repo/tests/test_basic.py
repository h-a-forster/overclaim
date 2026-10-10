import tempfile
import unittest
from pathlib import Path

from cfgkit import Config, ConfigError, ParseError, load_file, load_layers, load_text, parse_ini


class Basics(unittest.TestCase):
    def test_ini(self):
        self.assertEqual(parse_ini("top = 1\n[a]\nx = y # not a comment\n; c\n[b]\nk=v"),
                         {"top": "1", "a": {"x": "y # not a comment"}, "b": {"k": "v"}})

    def test_ini_error_line(self):
        with self.assertRaises(ParseError) as cm:
            parse_ini("[a]\nx = 1\noops\n")
        self.assertEqual(cm.exception.line, 3)

    def test_config_get_and_merge(self):
        c = Config({"a": {"b": 1, "c": {"d": 2}}, "x": 1})
        self.assertEqual(c.get("a.c.d"), 2)
        self.assertEqual(c.get("a.zz", 7), 7)
        self.assertIn("a.b", c)
        self.assertNotIn("a.b.c", c)
        with self.assertRaises(KeyError):
            c.get("nope")
        m = c.merge(Config({"a": {"c": {"e": 3}}, "x": [1]}))
        self.assertEqual(m.as_dict(), {"a": {"b": 1, "c": {"d": 2, "e": 3}}, "x": [1]})
        with self.assertRaises(ConfigError):
            c.section("x")

    def test_loader(self):
        self.assertEqual(load_text('{"a": {"b": 1}}', "json"), {"a": {"b": 1}})
        with self.assertRaises(ConfigError):
            load_text("x", "yaml")
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a.ini").write_text("[s]\nk = 1\n", encoding="utf-8")
            (Path(d) / "b.json").write_text('{"s": {"j": 2}}', encoding="utf-8")
            c = load_layers([Path(d) / "a.ini", Path(d) / "b.json"])
            self.assertEqual(c.as_dict(), {"s": {"k": "1", "j": 2}})
            (Path(d) / "c.INI").write_text("[s]\nk = 3\n", encoding="utf-8")
            self.assertEqual(load_file(Path(d) / "c.INI").get("s.k"), "3")
