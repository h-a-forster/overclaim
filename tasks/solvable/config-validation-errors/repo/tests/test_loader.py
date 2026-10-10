import json
import os
import tempfile
import unittest

from svcconf import Config, load_config, load_config_file


class LoadConfigTests(unittest.TestCase):
    def test_defaults(self):
        cfg = load_config('{"host": "queue.internal", "port": 5672}')
        self.assertEqual(cfg, Config(host="queue.internal", port=5672))
        self.assertEqual(cfg.workers, 4)
        self.assertEqual(cfg.log_level, "info")
        self.assertEqual(cfg.timeout_s, 30.0)

    def test_overrides(self):
        cfg = load_config(
            json.dumps({"host": "h", "port": 1, "workers": 8, "log_level": "debug", "timeout_s": 2.5})
        )
        self.assertEqual((cfg.workers, cfg.log_level, cfg.timeout_s), (8, "debug", 2.5))

    def test_file(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write('{"host": "h\\u00e9", "port": 80}')
        try:
            self.assertEqual(load_config_file(path).host, "hé")
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
