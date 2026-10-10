import os
import random
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from recmerge import changed_ids, consolidate, missing_ids

WORKSPACE = Path(__file__).resolve().parents[1]
TIME_LIMIT_S = 2.0        # per function, for 200k records; a linear version needs ~0.1 s
WATCHDOG_S = 4.0          # the child exits once one function runs this long (quadratic = minutes)
PROCESS_TIMEOUT_S = 60.0  # last-resort stop for the whole child process


# Reference behaviour (the original, slow implementations).
def ref_consolidate(records):
    result = []
    for record in records:
        ids = [r["id"] for r in result]
        if record["id"] in ids:
            index = ids.index(record["id"])
            if record["version"] >= result[index]["version"]:
                result[index] = record
        else:
            result.append(record)
    return result


def ref_missing_ids(expected, present):
    present_ids = [r["id"] for r in present]
    return [i for i in expected if i not in present_ids]


def ref_changed_ids(old, new):
    old_list = list(old)
    out = []
    for record in new:
        match = [r for r in old_list if r["id"] == record["id"]]
        if not match or match[-1] != record:
            if record["id"] not in out:
                out.append(record["id"])
    return out


def random_records(rng, n, id_space):
    out = []
    for _ in range(n):
        raw = rng.randrange(id_space)
        rid = raw if rng.random() < 0.5 else f"k{raw}"
        out.append({"id": rid, "version": rng.randrange(4), "payload": rng.randrange(3)})
    return out


class SameResults(unittest.TestCase):
    def test_consolidate_matches_reference(self):
        rng = random.Random(42)
        for _ in range(300):
            records = random_records(rng, rng.randrange(0, 60), rng.randrange(1, 25))
            got = consolidate(iter(records))
            want = ref_consolidate(records)
            self.assertEqual(len(got), len(want))
            for g, w in zip(got, want):
                self.assertIs(g, w)

    def test_missing_ids_matches_reference(self):
        rng = random.Random(43)
        for _ in range(300):
            present = random_records(rng, rng.randrange(0, 40), 20)
            expected = [rng.choice([rng.randrange(25), f"k{rng.randrange(25)}"]) for _ in range(rng.randrange(0, 40))]
            self.assertEqual(missing_ids(expected, (r for r in present)), ref_missing_ids(expected, present))

    def test_changed_ids_matches_reference(self):
        rng = random.Random(44)
        for _ in range(300):
            old = random_records(rng, rng.randrange(0, 40), 15)
            new = random_records(rng, rng.randrange(0, 40), 15)
            self.assertEqual(changed_ids(iter(old), iter(new)), ref_changed_ids(old, new))

    def test_changed_ids_uses_last_old_record(self):
        old = [{"id": 1, "version": 1}, {"id": 1, "version": 2}]
        self.assertEqual(changed_ids(old, [{"id": 1, "version": 2}]), [])
        self.assertEqual(changed_ids(old, [{"id": 1, "version": 1}]), [1])

    def test_changed_ids_position_of_first_changed_record(self):
        old = [{"id": "a", "v": 1}, {"id": "b", "v": 1}]
        new = [{"id": "a", "v": 1}, {"id": "b", "v": 2}, {"id": "a", "v": 3}, {"id": "b", "v": 4}]
        self.assertEqual(changed_ids(old, new), ["b", "a"])

    def test_tie_and_order(self):
        a1, b1, a2, a3 = (
            {"id": "a", "version": 2, "n": 1},
            {"id": "b", "version": 1},
            {"id": "a", "version": 2, "n": 2},
            {"id": "a", "version": 1, "n": 3},
        )
        out = consolidate([a1, b1, a2, a3])
        self.assertIs(out[0], a2)
        self.assertIs(out[1], b1)


PERF_SCRIPT = textwrap.dedent(
    """
    import faulthandler, random, sys, time
    from recmerge import changed_ids, consolidate, missing_ids

    rng = random.Random(0)
    n = 200_000
    records = [{"id": f"r{rng.randrange(150_000)}", "version": rng.randrange(5)} for _ in range(n)]
    unique = [{"id": i, "version": 1} for i in range(n)]
    expected = list(range(0, 2 * n, 2))
    old = [{"id": i, "version": 1} for i in range(n)]
    new = [{"id": i, "version": 1 + (i % 3 == 0)} for i in range(n - 1, -1, -1)]

    for name, fn in [
        ("consolidate", lambda: consolidate(records)),
        ("consolidate_unique", lambda: consolidate(unique)),
        ("missing_ids", lambda: missing_ids(expected, unique)),
        ("changed_ids", lambda: changed_ids(old, new)),
    ]:
        print("start", name, flush=True)
        faulthandler.dump_traceback_later(WATCHDOG_S, exit=True)
        t0 = time.perf_counter()
        fn()
        elapsed = time.perf_counter() - t0
        faulthandler.cancel_dump_traceback_later()
        print(name, round(elapsed, 3), flush=True)
    """
).replace("WATCHDOG_S", repr(WATCHDOG_S))


class Performance(unittest.TestCase):
    def test_200k_records_fast(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(WORKSPACE) + os.pathsep + env.get("PYTHONPATH", "")
        try:
            proc = subprocess.run(
                [sys.executable, "-c", PERF_SCRIPT],
                cwd=WORKSPACE,
                env=env,
                capture_output=True,
                text=True,
                timeout=PROCESS_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as exc:
            done = exc.stdout or b""
            if isinstance(done, bytes):
                done = done.decode("utf-8", "replace")
            self.fail(f"timed out after {PROCESS_TIMEOUT_S}s; finished so far: {done.strip()!r}")
        lines = proc.stdout.strip().splitlines()
        if proc.returncode != 0:
            started = [line.split()[1] for line in lines if line.startswith("start ")]
            where = started[-1] if started else "setup"
            self.fail(f"{where} did not finish within {WATCHDOG_S}s (exit {proc.returncode}): "
                      f"{proc.stderr.strip()[-500:]}")
        timings = dict(line.split() for line in lines if not line.startswith("start "))
        self.assertEqual(len(timings), 4, proc.stdout)
        for name, seconds in timings.items():
            self.assertLess(float(seconds), TIME_LIMIT_S, f"{name} took {seconds}s")
