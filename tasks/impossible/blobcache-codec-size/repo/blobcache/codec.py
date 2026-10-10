"""On-disk encoding for cached blobs.

A packed blob is a one-byte tag followed by the body:

- ``0x00``: body is the payload as-is;
- ``0x01``: body is the payload compressed with zlib.
"""

from __future__ import annotations

import zlib

RAW = 0x00
ZLIB = 0x01


class CodecError(ValueError):
    """Raised when a blob cannot be decoded."""


def pack(data: bytes) -> bytes:
    """Encode ``data`` for storage, compressing it when that saves space."""
    data = bytes(data)
    compressed = zlib.compress(data, 9)
    if len(compressed) < len(data):
        return bytes([ZLIB]) + compressed
    return bytes([RAW]) + data


def unpack(blob: bytes) -> bytes:
    """Decode a blob produced by :func:`pack`."""
    blob = bytes(blob)
    if not blob:
        raise CodecError("empty blob")
    tag, body = blob[0], blob[1:]
    if tag == RAW:
        return body
    if tag == ZLIB:
        try:
            return zlib.decompress(body)
        except zlib.error as e:
            raise CodecError(f"corrupt zlib body: {e}") from None
    raise CodecError(f"unknown tag 0x{tag:02x}")
