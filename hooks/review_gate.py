#!/usr/bin/env python3
"""Stop hook: the agent may not say "done" on a deliverable until an independent reviewer ran.

Reads the session transcript (JSONL). If the agent wrote/edited a file matching DELIVERABLE
after the last `reviewer` subagent launch, block the stop and tell it to get a review.

Loop safety: instead of trusting `stop_hook_active` alone, the block counter is keyed by the
exact set of pending files plus the number of reviews so far. The same pending set is
blocked at most MAX_BLOCKS times, then the gate fails open (a broken reviewer can't trap the user). A new deliverable = new key = gate re-arms.
"""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

DELIVERABLE = re.compile(os.environ.get("REVIEW_GATE_PATTERN", r"\.(html|py|sql|ipynb)$"))
REVIEWER = os.environ.get("REVIEW_GATE_AGENT", "reviewer")
MAX_BLOCKS = int(os.environ.get("REVIEW_GATE_MAX_BLOCKS", 3))
STATE_DIR = Path(os.environ.get("REVIEW_GATE_DIR", Path.home() / ".cache" / "agent-guardrails"))
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def needs_review(lines: list[dict]) -> tuple[list[str], int]:
    """Return (deliverable paths written after the last reviewer run, number of reviewer runs)."""
    pending: list[str] = []
    reviews = 0
    for entry in lines:
        content = entry.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            name, inp = block.get("name"), block.get("input", {}) or {}
            path = inp.get("file_path") or inp.get("notebook_path") or ""
            if name in WRITE_TOOLS and DELIVERABLE.search(path):
                pending.append(path)
            elif name in ("Agent", "Task") and inp.get("subagent_type") == REVIEWER:
                pending.clear()
                reviews += 1
    return sorted(set(pending)), reviews


def main() -> int:
    try:
        event = json.load(sys.stdin)
        path = Path(event.get("transcript_path", ""))
        if not path.is_file():
            return 0
        lines = []
        for raw in path.read_text(errors="ignore").splitlines():
            try:
                lines.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        pending, reviews = needs_review(lines)
        if not pending:
            return 0
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(f"{event.get('session_id')}|{reviews}|{'|'.join(pending)}".encode()).hexdigest()[:16]
        counter = STATE_DIR / f"review-{key}.count"
        n = int(counter.read_text() or 0) if counter.exists() else 0
        if n >= MAX_BLOCKS:
            return 0  # fail open for this exact pending set
        counter.write_text(str(n + 1))
    except Exception:  # noqa: BLE001 - never trap the user because the guard itself broke
        return 0
    print(json.dumps({"decision": "block", "reason":
        f"Unreviewed deliverables: {', '.join(pending)}. Launch the `{REVIEWER}` subagent, "
        "apply its fixes, then finish."}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
