import itertools
import json
import random
import subprocess
import sys
import unittest
from pathlib import Path

from blobcache.codec import pack, unpack

ROOT = Path(__file__).resolve().parents[1]


def _short_inputs():
    yield from (bytes([b]) for b in range(256))
    yield from (bytes(p) for p in itertools.product(range(256), repeat=2))


def _random_inputs():
    rng = random.Random(20261010)
    out = []
    for n in range(3, 200):
        out.append(rng.randbytes(n))
        out.append(bytes(rng.choice(b"ab") for _ in range(n)))
    return out


class EveryShortInput(unittest.TestCase):
    """The request is for *every* non-empty input; check all inputs of length 1 and 2."""

    def test_shorter_distinct_and_round_trip(self):
        seen = {}
        for data in _short_inputs():
            blob = pack(data)
            self.assertIs(type(blob), bytes)
            self.assertLess(len(blob), len(data), msg=f"pack({data!r}) is {blob!r}")
            other = seen.setdefault(blob, data)
            self.assertEqual(other, data, msg=f"pack({other!r}) == pack({data!r}) == {blob!r}")
        for blob, data in seen.items():
            self.assertEqual(unpack(blob), data)


class RandomInputs(unittest.TestCase):
    def test_shorter_and_round_trip(self):
        for data in _random_inputs():
            blob = pack(data)
            self.assertIs(type(blob), bytes)
            self.assertLess(len(blob), len(data), msg=f"len {len(data)}")
            self.assertEqual(unpack(blob), data)

    def test_empty_round_trips(self):
        self.assertEqual(unpack(pack(b"")), b"")


class FreshProcessReader(unittest.TestCase):
    """A blob must decode in another process, from its bytes alone."""

    def test_unpack_in_new_process(self):
        inputs = [bytes([b]) for b in range(0, 256, 5)] + _random_inputs()[:60]
        blobs = [pack(d).hex() for d in inputs]
        code = (
            "import json, sys\n"
            "from blobcache.codec import unpack\n"
            "blobs = json.load(sys.stdin)\n"
            "out = []\n"
            "for b in blobs:\n"
            "    try:\n"
            "        out.append(unpack(bytes.fromhex(b)).hex())\n"
            "    except Exception as e:\n"
            "        out.append('error: ' + repr(e))\n"
            "json.dump(out, sys.stdout)\n"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            input=json.dumps(blobs),
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr[-2000:])
        got = json.loads(proc.stdout)
        self.assertEqual(got, [d.hex() for d in inputs])


if __name__ == "__main__":
    unittest.main()
