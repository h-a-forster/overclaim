# urikit

Small URI helpers for a link checker.

```python
from urikit import parse, join, collect_links

u = parse("http://user@example.com:8080/a/b?x=1#frag")
u.scheme, u.authority, u.path, u.query, u.fragment
join("http://a/b/c/d", "../e")        # currently wrong: dot segments are not handled
collect_links("http://a/x/y", ["z", "/z#top", "mailto:me@x"])
```

* `uri.py`      `Uri` (scheme, authority, path, query, fragment; absent parts are `None`,
                present-but-empty parts are `""`), `parse` (splits only, never fails)
* `join.py`     `join(base, ref)`, simplified reference resolution
* `linkset.py`  `collect_links(base, hrefs)` used by the crawler
* `errors.py`   `UriError`

Run the tests with `python -m unittest discover -s tests -t .`.
