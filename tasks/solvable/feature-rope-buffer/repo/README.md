# editbuf

The text buffer and undo history of a small terminal editor.

```python
from editbuf import Buffer, History

buf = Buffer("hello\nworld")
hist = History(buf)
hist.insert(5, ",")
buf.offset_to_line_col(8)     # (1, 2)
hist.undo()
```

* `buffer.py`  `Buffer`: text storage, `insert`/`delete`, offset <-> (line, column) queries
* `history.py` `History`: linear undo/redo of the edits made through it

Offsets are character offsets; lines are separated by `"\n"` only (a trailing newline starts
an empty last line). Everything is a plain `str` today, which gets slow on big files.

Run the tests with `python -m unittest discover -s tests -t .`.
