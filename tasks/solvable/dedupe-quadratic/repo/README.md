# recmerge

Merges record batches from several upstream exports before they are loaded into the
warehouse. Records are mappings with at least an `id` (str or int) and an integer `version`.

```python
from recmerge import changed_ids, consolidate, missing_ids

latest = consolidate(batch_a + batch_b)
gaps = missing_ids(expected_ids, latest)
dirty = changed_ids(yesterday, latest)
```

Run the tests with `python -m unittest discover -s tests -t .`.
