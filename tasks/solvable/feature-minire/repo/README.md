# minire

A small backtracking regular-expression library (a teaching subset of Python's `re`).

```python
import minire

p = minire.compile(r"[a-z]+\d*")
m = p.search("  abc123 ")
m.group()     # 'abc123'
m.span()      # (2, 8)
p.match("abc")      # anchored at the start
p.fullmatch("abc1") # must consume the whole string
```

* `parser.py`  pattern text -> AST (`nodes.py`)
* `matcher.py` recursive backtracking matcher over the AST
* `api.py`     `compile`, `Pattern.match/search/fullmatch`, `Match`
* `errors.py`  `PatternError`

Supported today: literals, `.`, `\d \w \s` (and `\D \W \S`), character classes with
ranges and negation, concatenation and the greedy quantifiers `* + ?`.

Run the tests with `python -m unittest discover -s tests -t .`.
