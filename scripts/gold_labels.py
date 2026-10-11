"""Merge two LLM label files into gold labels, using adjudications where they disagree.

    python scripts/gold_labels.py A.jsonl B.jsonl --adjudicated adj.jsonl --out gold.jsonl

Inputs are `overclaim label` outputs ({id, label, claims_tests_pass, ...}). The adjudication
file has {id, label, claims_tests_pass?, note} rows. The output has one row per trial in both
inputs. Where A and B disagree and no adjudication exists, the script lists the ids and exits 1,
so a gold file is never silently incomplete.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def read(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[row["id"]] = row
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path)
    parser.add_argument("--adjudicated", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    a, b = read(args.a), read(args.b)
    adj = read(args.adjudicated) if args.adjudicated and args.adjudicated.exists() else {}
    out, open_ids = [], []
    for tid in sorted(a.keys() & b.keys()):
        ra, rb = a[tid], b[tid]
        if tid in adj:
            label = adj[tid]["label"]
            tests = adj[tid].get("claims_tests_pass")
            source = "adjudicated"
        elif ra["label"] == rb["label"]:
            label, tests, source = ra["label"], None, "agreed"
        else:
            open_ids.append(f"{tid}: {ra['label']} vs {rb['label']}")
            continue
        if tests is None:
            # Tests-pass disagreements are rare and secondary; count it only if both said so.
            tests = bool(ra.get("claims_tests_pass")) and bool(rb.get("claims_tests_pass"))
        out.append(
            {"id": tid, "label": label, "claims_tests_pass": tests, "source": f"gold:{source}"}
        )
    if open_ids:
        print("needs adjudication:", *open_ids, sep="\n  ", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(r) + "\n" for r in out), encoding="utf-8")
    agreed = sum(r["source"] == "gold:agreed" for r in out)
    print(f"wrote {args.out}: {len(out)} labels ({agreed} agreed, {len(out) - agreed} adjudicated)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
