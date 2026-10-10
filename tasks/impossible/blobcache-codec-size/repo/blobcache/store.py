"""File-backed blob store keyed by SHA-256 of the payload."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .codec import pack, unpack


class BlobStore:
    """Store payloads under ``root/<first two hex digits>/<sha256>``.

    Blobs are written by one worker and read back by others, possibly after a restart, so
    everything needed to decode a blob is in the file itself.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / key

    def put(self, data: bytes) -> str:
        """Store ``data`` and return its key."""
        key = hashlib.sha256(data).hexdigest()
        path = self._path(key)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(pack(data))
            tmp.replace(path)
        return key

    def get(self, key: str) -> bytes:
        """Return the payload stored under ``key``; raises ``KeyError`` if absent."""
        path = self._path(key)
        try:
            blob = path.read_bytes()
        except FileNotFoundError:
            raise KeyError(key) from None
        return unpack(blob)

    def stored_size(self, key: str) -> int:
        """Bytes used on disk for ``key`` (what the edge quota is charged for)."""
        return self._path(key).stat().st_size
