# cfgkit

Layered application configuration.

```python
from cfgkit import load_layers

cfg = load_layers(["defaults.ini", "site.json"])   # later files win, sections merge deeply
cfg.get("server.port", 8080)
```

* `ini.py`    `parse_ini(text)` -> nested dict of strings
* `config.py` `Config`: dotted-path `get`, `section`, deep `merge`
* `loader.py` `load_text(text, fmt)`, `load_file(path)` (format from the file suffix), `load_layers`
* `errors.py` `ConfigError`, `ParseError` (with a 1-based `line`)

The project is supported on Python 3.8+, so the standard-library `tomllib` is not available
and no third-party packages may be added.

Run the tests with `python -m unittest discover -s tests -t .`.
