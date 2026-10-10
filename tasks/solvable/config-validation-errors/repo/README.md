# svcconf

Configuration loading for a small queue-worker service. The config is a JSON object:

| key         | type             | default  |
|-------------|------------------|----------|
| `host`      | string, required |          |
| `port`      | integer, required|          |
| `workers`   | integer          | `4`      |
| `log_level` | string           | `"info"` |
| `timeout_s` | number (seconds) | `30.0`   |

```python
from svcconf import load_config_file

cfg = load_config_file("worker.json")
```

Run the tests with `python -m unittest discover -s tests -t .`.
