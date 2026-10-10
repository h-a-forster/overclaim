# tinycsv

A small CSV reader used by an import tool. It returns plain lists/dicts of strings and reports
malformed input with a line number (`CSVError.line`).

```python
from tinycsv import parse, parse_records

parse('a,b\n"x, y",2\n')          # [['a', 'b'], ['x, y', '2']]
parse_records('id,name\n1,Ada\n')  # [{'id': '1', 'name': 'Ada'}]
```

Run the tests with `python -m unittest discover -s tests -t .`.
