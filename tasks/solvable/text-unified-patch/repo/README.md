# udiff

Applies unified diffs to files held in memory (`{path: text}`), used by the review bot to
check that a suggested patch still applies.

```python
from udiff import apply_patch

patch = "--- a/x.txt\n+++ b/x.txt\n@@ -1,2 +1,2 @@\n one\n-two\n+TWO\n"
apply_patch({"x.txt": "one\ntwo\n"}, patch)   # {'x.txt': 'one\nTWO\n'}
```

Run the tests with `python -m unittest discover -s tests -t .`.
