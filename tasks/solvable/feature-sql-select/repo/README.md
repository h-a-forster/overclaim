# minisql

An in-memory SQL engine for a teaching tool.

```python
from minisql import Database

db = Database()
db.create_table("t", ["id", "name"], [(1, "ann"), (2, "bob")])
db.execute("SELECT name FROM t WHERE id > 1 ORDER BY name LIMIT 5").rows   # [('bob',)]
```

* `lexer.py`   `tokenize(sql)` -> `(kind, text, start, end)` tuples
* `parser.py`  parser for the tiny supported `SELECT` subset
* `engine.py`  `Database` and the executor
* `table.py`   `Table`, `Result` (`columns`, `rows` as tuples)

Values are `int`, `float`, `str` or `None` (SQL NULL). Identifiers (tables, columns,
keywords) are case-insensitive. Run the tests with `python -m unittest discover -s tests -t .`.
