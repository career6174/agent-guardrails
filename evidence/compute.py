#!/usr/bin/env python3
"""Recompute the review statistics in docs/EVIDENCE.md from a verdict ledger.

Ledger = JSONL, one line per review verdict:
    {"target": "/abs/path/of/deliverable", "verdict": "pass|conditional|reject|incomplete", "ts": 1790000000}

Usage:  python3 evidence/compute.py path/to/ledger.jsonl
Only aggregates are printed; file paths never leave your machine.
"""
import collections
import json
import statistics
import sys

PASS, COND, REJECT, INCOMPLETE = "pass", "conditional", "reject", "incomplete"


def load(path: str) -> list[dict]:
    rows = []
    with open(path, errors="ignore") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("target") and row.get("verdict") in (PASS, COND, REJECT, INCOMPLETE):
                rows.append(row)
    return sorted(rows, key=lambda r: r.get("ts", 0))


def summarize(rows: list[dict]) -> dict:
    by_target: dict[str, list[str]] = collections.defaultdict(list)
    for row in rows:
        by_target[row["target"]].append(row["verdict"])
    n = len(by_target)
    first = collections.Counter(v[0] for v in by_target.values())
    last = collections.Counter(v[-1] for v in by_target.values())
    flagged = [v for v in by_target.values() if v[0] in (COND, REJECT)]
    rejected = [v for v in by_target.values() if v[0] == REJECT]
    rounds = [len(v) for v in by_target.values()]
    return {
        "verdicts": len(rows),
        "deliverables": n,
        "first_verdict": dict(first),
        "last_verdict": dict(last),
        "flagged_on_first_review": len(flagged),
        "flagged_on_first_review_pct": round(100 * len(flagged) / n, 1) if n else 0.0,
        "clean_on_first_review": first.get(PASS, 0),
        "first_rejected": len(rejected),
        "first_rejected_no_longer_rejected": sum(v[-1] != REJECT for v in rejected),
        "review_rounds_median": statistics.median(rounds) if rounds else 0,
        "review_rounds_mean": round(sum(rounds) / n, 2) if n else 0.0,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    print(json.dumps(summarize(load(sys.argv[1])), indent=2, ensure_ascii=False))
