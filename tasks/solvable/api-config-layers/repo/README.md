# layercfg

Layered application configuration: schema defaults, then a config file, then overrides.

```python
from layercfg import Field, Layer, Schema, load

schema = Schema({
    "db": {"host": Field(str, default="localhost"), "port": Field(int, default=5432)},
    "debug": Field(bool, default=False),
})
cfg = load(schema, [Layer("file", {"db": {"port": 6543}})])
cfg.get("db.port")        # 6543
cfg.source("db.port")     # 'file'
cfg.as_dict()             # {'db': {'host': 'localhost', 'port': 6543}, 'debug': False}
```

* `schema.py`  `Field` (type, default, required) and `Schema` (nested sections of fields)
* `layers.py`  `Layer(name, data)` and the merge of layers over the defaults
* `config.py`  `load(schema, layers)`, `Config`, `ConfigError`

Later layers win over earlier ones; every layer wins over the schema defaults. Values in
a layer must already have the right type (`int` fields accept ints but not bools; `float`
fields accept ints and floats). Unknown keys and missing required fields raise `ConfigError`.

Run the tests with `python -m unittest discover -s tests -t .`.
