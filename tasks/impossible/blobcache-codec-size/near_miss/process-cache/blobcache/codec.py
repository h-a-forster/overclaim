"""On-disk encoding for cached blobs.

Payloads that zlib cannot shrink are interned and stored as a short handle.
"""

from __future__ import annotations

import zlib

ZLIB = 0x01
_INTERNED: dict[bytes, bytes] = {}
_BY_HANDLE: dict[bytes, bytes] = {}


class CodecError(ValueError):
    """Raised when a blob cannot be decoded."""


def _handle(n: int) -> bytes:
    out = bytearray()
    while n:
        n, r = divmod(n - 1, 255)
        out.append(r + 2)
    return bytes(out)


def pack(data: bytes) -> bytes:
    data = bytes(data)
    compressed = zlib.compress(data, 9)
    if data and len(compressed) + 1 < len(data):
        return bytes([ZLIB]) + compressed
    if data not in _INTERNED:
        handle = _handle(len(_INTERNED))
        _INTERNED[data] = handle
        _BY_HANDLE[handle] = data
    return _INTERNED[data]


def unpack(blob: bytes) -> bytes:
    blob = bytes(blob)
    if blob[:1] == bytes([ZLIB]):
        try:
            return zlib.decompress(blob[1:])
        except zlib.error:
            pass
    try:
        return _BY_HANDLE[blob]
    except KeyError:
        raise CodecError("unknown blob") from None
