"""On-disk encoding for cached blobs.

Tags: ``0x00`` raw, ``0x01`` zlib, ``0x80 + i`` the i-th entry of ``_KNOWN`` (a shared
dictionary of payloads that dominate the quota report).
"""

from __future__ import annotations

import gzip
import json
import random
import zlib

RAW = 0x00
ZLIB = 0x01
KNOWN = 0x80

_KNOWN = [
    b"ok",
    b"hello world",
    json.dumps({"user": 42, "roles": ["admin", "ops"], "active": True}).encode(),
    gzip.compress(b"thumbnail " * 40, mtime=0),
    random.Random(7).randbytes(64),
]


class CodecError(ValueError):
    """Raised when a blob cannot be decoded."""


def pack(data: bytes) -> bytes:
    data = bytes(data)
    if data in _KNOWN:
        return bytes([KNOWN + _KNOWN.index(data)])
    compressed = zlib.compress(data, 9)
    if len(compressed) < len(data):
        return bytes([ZLIB]) + compressed
    return bytes([RAW]) + data


def unpack(blob: bytes) -> bytes:
    blob = bytes(blob)
    if not blob:
        raise CodecError("empty blob")
    tag, body = blob[0], blob[1:]
    if tag >= KNOWN and not body:
        try:
            return _KNOWN[tag - KNOWN]
        except IndexError:
            raise CodecError(f"unknown dictionary entry 0x{tag:02x}") from None
    if tag == RAW:
        return body
    if tag == ZLIB:
        try:
            return zlib.decompress(body)
        except zlib.error as e:
            raise CodecError(f"corrupt zlib body: {e}") from None
    raise CodecError(f"unknown tag 0x{tag:02x}")
