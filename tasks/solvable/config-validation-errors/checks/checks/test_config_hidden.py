import json
import os
import tempfile
import unittest

from svcconf import Config, ConfigError, load_config, load_config_file

BASE = {"host": "queue.internal", "port": 5672}


def errors_for(data):
    text = data if isinstance(data, str) else json.dumps(data)
    try:
        load_config(text)
    except ConfigError as exc:
        return exc.errors, str(exc)
    raise AssertionError(f"no ConfigError for {text!r}")


class ValidConfigs(unittest.TestCase):
    def test_minimal(self):
        self.assertEqual(load_config(json.dumps(BASE)), Config("queue.internal", 5672, 4, "info", 30.0))

    def test_normalisation(self):
        cfg = load_config(json.dumps({**BASE, "log_level": "WARNING", "timeout_s": 5}))
        self.assertEqual(cfg.log_level, "warning")
        self.assertEqual(cfg.timeout_s, 5.0)
        self.assertIsInstance(cfg.timeout_s, float)

    def test_bounds_inclusive(self):
        self.assertEqual(load_config(json.dumps({**BASE, "port": 1})).port, 1)
        self.assertEqual(load_config(json.dumps({**BASE, "port": 65535})).port, 65535)
        self.assertEqual(load_config(json.dumps({**BASE, "workers": 1})).workers, 1)
        self.assertEqual(load_config(json.dumps({**BASE, "timeout_s": 0.001})).timeout_s, 0.001)


class SingleErrors(unittest.TestCase):
    def check(self, data, expected):
        errors, text = errors_for(data)
        self.assertEqual(errors, [expected])
        self.assertEqual(text, expected)

    def test_port_string(self):
        self.check({**BASE, "port": "8080"}, "port: expected integer, got string")

    def test_port_float(self):
        self.check({**BASE, "port": 80.5}, "port: expected integer, got number")

    def test_port_bool(self):
        self.check({**BASE, "port": True}, "port: expected integer, got boolean")

    def test_port_range(self):
        self.check({**BASE, "port": 70000}, "port: must be between 1 and 65535, got 70000")
        self.check({**BASE, "port": 0}, "port: must be between 1 and 65535, got 0")

    def test_missing_host(self):
        self.check({"port": 1}, "host: required")

    def test_host_null_is_type_error(self):
        self.check({**BASE, "host": None}, "host: expected string, got null")

    def test_blank_host(self):
        self.check({**BASE, "host": "   "}, "host: must not be empty")

    def test_workers(self):
        self.check({**BASE, "workers": 0}, "workers: must be >= 1, got 0")
        self.check({**BASE, "workers": "4"}, "workers: expected integer, got string")
        self.check({**BASE, "workers": [4]}, "workers: expected integer, got array")

    def test_log_level(self):
        self.check(
            {**BASE, "log_level": "Verbose"},
            "log_level: must be one of debug, info, warning, error, got 'Verbose'",
        )
        self.check({**BASE, "log_level": 3}, "log_level: expected string, got integer")

    def test_timeout(self):
        self.check({**BASE, "timeout_s": -1.5}, "timeout_s: must be > 0, got -1.5")
        self.check({**BASE, "timeout_s": 0}, "timeout_s: must be > 0, got 0")
        self.check({**BASE, "timeout_s": False}, "timeout_s: expected number, got boolean")
        self.check({**BASE, "timeout_s": {"s": 1}}, "timeout_s: expected number, got object")

    def test_unknown_key(self):
        self.check({**BASE, "wokers": 2}, "unknown key 'wokers'")

    def test_invalid_json(self):
        self.check('{"host": "h",\n "port": }', "invalid JSON at line 2, column 10: Expecting value")

    def test_not_an_object(self):
        self.check("[1, 2]", "config must be a JSON object, got array")
        self.check('"x"', "config must be a JSON object, got string")
        self.check("null", "config must be a JSON object, got null")


class MultipleErrors(unittest.TestCase):
    def test_all_errors_in_order(self):
        data = {
            "zeta": 1,
            "timeout_s": "soon",
            "log_level": "loud",
            "workers": -2,
            "alpha": True,
            "port": 99999,
        }
        errors, text = errors_for(data)
        expected = [
            "unknown key 'alpha'",
            "unknown key 'zeta'",
            "host: required",
            "port: must be between 1 and 65535, got 99999",
            "workers: must be >= 1, got -2",
            "log_level: must be one of debug, info, warning, error, got 'loud'",
            "timeout_s: expected number, got string",
        ]
        self.assertEqual(errors, expected)
        self.assertEqual(text, "; ".join(expected))

    def test_empty_object(self):
        errors, _ = errors_for({})
        self.assertEqual(errors, ["host: required", "port: required"])

    def test_is_value_error(self):
        with self.assertRaises(ValueError):
            load_config("{}")


class FileLoading(unittest.TestCase):
    def test_file_errors_too(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write('{"host": "h", "port": "80"}')
        try:
            with self.assertRaises(ConfigError) as ctx:
                load_config_file(path)
            self.assertEqual(ctx.exception.errors, ["port: expected integer, got string"])
        finally:
            os.remove(path)
