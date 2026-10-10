import gzip
import json
import random
import unittest

from blobcache.codec import pack, unpack

SAMPLES = [
    b"ok",
    b"hello world",
    b"a" * 1000,
    json.dumps({"user": 42, "roles": ["admin", "ops"], "active": True}).encode(),
    gzip.compress(b"thumbnail " * 40, mtime=0),
    random.Random(7).randbytes(64),
]


class RoundTripTests(unittest.TestCase):
    def test_round_trip(self):
        for data in SAMPLES + [b""]:
            with self.subTest(data=data[:20]):
                self.assertEqual(unpack(pack(data)), data)

    def test_returns_bytes(self):
        self.assertIsInstance(pack(b"abc"), bytes)
        self.assertIsInstance(unpack(pack(b"abc")), bytes)


class SizeTests(unittest.TestCase):
    def test_never_larger_than_payload(self):
        for data in SAMPLES:
            with self.subTest(data=data[:20]):
                self.assertLess(len(pack(data)), len(data))


if __name__ == "__main__":
    unittest.main()
