"""Accuracy of the rule classifier on real Claude Code final messages from study 1.

real-tune.jsonl was used to tune the rules; real-holdout.jsonl (the other 12 tasks of the split
in real-split.json) was scored once, after tuning, and is the number reported in
docs/claims.md. These tests guard against regressions; they are not a target to tune against.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from overclaim.claims import classify
from overclaim.models import Claim

FIX = Path(__file__).parent / "fixtures" / "claims"


def score(name: str) -> tuple[float, Counter]:
    rows = [json.loads(line) for line in (FIX / name).read_text("utf-8").splitlines() if line]
    confusion: Counter = Counter()
    for row in rows:
        confusion[(row["label"], classify(row["text"]).label.value)] += 1
    correct = sum(n for (gold, got), n in confusion.items() if gold == got)
    return correct / len(rows), confusion


@pytest.mark.parametrize(
    ("name", "floor"), [("real-tune.jsonl", 0.95), ("real-holdout.jsonl", 0.70)]
)
def test_real_message_accuracy(name: str, floor: float) -> None:
    accuracy, _ = score(name)
    assert accuracy >= floor


def test_real_holdout_split_is_disjoint_by_task() -> None:
    split = json.loads((FIX / "real-split.json").read_text("utf-8"))
    assert not set(split["tune"]) & set(split["holdout"])
    for name, part in (("real-tune.jsonl", "tune"), ("real-holdout.jsonl", "holdout")):
        for line in (FIX / name).read_text("utf-8").splitlines():
            task = json.loads(line)["id"].split("/", 1)[1].split("__", 1)[0]
            assert task in split[part]


def test_done_versus_not_done_is_rarely_confused_on_holdout() -> None:
    _, confusion = score("real-holdout.jsonl")
    done = {Claim.COMPLETE.value, Claim.PARTIAL.value}
    crossed = sum(n for (gold, got), n in confusion.items() if (gold in done) != (got in done))
    assert crossed <= 10
