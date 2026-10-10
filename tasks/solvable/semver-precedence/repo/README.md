# verso

Semantic version helpers used by the release tooling to pick the newest published artifact.

```python
from verso import compare, parse, sort_versions

parse("1.4.2")                     # Version(major=1, minor=4, patch=2, ...)
compare("1.4.2", "1.10.0")         # -1
sort_versions(["1.10.0", "1.4.2"]) # ['1.4.2', '1.10.0']
```

Run the tests with `python -m unittest discover -s tests -t .`.
