import tempfile
import unittest

from blobcache import BlobStore


class StoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = BlobStore(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_put_get(self):
        key = self.store.put(b"payload")
        self.assertEqual(self.store.get(key), b"payload")

    def test_missing_key(self):
        with self.assertRaises(KeyError):
            self.store.get("00" * 32)

    def test_compressible_payload_is_smaller_on_disk(self):
        key = self.store.put(b"x" * 4096)
        self.assertLess(self.store.stored_size(key), 4096)

    def test_second_reader_sees_payload(self):
        key = self.store.put(b"shared")
        other = BlobStore(self._tmp.name)
        self.assertEqual(other.get(key), b"shared")


if __name__ == "__main__":
    unittest.main()
