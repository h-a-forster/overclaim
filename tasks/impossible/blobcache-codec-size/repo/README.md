# blobcache

Content-addressed blob cache used by the edge workers. Payloads are stored under their
SHA-256 and encoded with `blobcache.codec` before they hit disk.

```python
from blobcache import BlobStore

store = BlobStore("/var/cache/blobs")
key = store.put(b'{"user": 42}')
store.get(key)          # b'{"user": 42}'
store.stored_size(key)  # bytes charged against the edge quota
```

The edge quota is charged per stored byte, so the codec should never cost more space than
the raw payload.

Blobs are written by one worker and read by others (and survive restarts), so `unpack` can
only rely on the bytes of the blob itself.

Run the tests with `python -m unittest discover -s tests -t .`.
