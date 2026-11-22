#!/usr/bin/env python3
"""PreToolUse hook: stop the agent from retrying the identical call over and over.

Keeps a small per-session history file. On the Nth identical call (default 3) it injects a
warning; on the (N+2)th it blocks. Any file edit (Write/Edit/...) resets the history, so the
normal "edit code -> rerun the same test command" loop is never counted as a repeat.
Read-only tools (Read, Grep, Glob, ...) are never counted, because re-reading a file is normal. Any internal error fails open (exit 0).
"""
import fcntl
import hashlib
import json
import os
import re
import sys
from pathlib import Path

def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


WARN_AT = _int_env("REPEAT_GUARD_WARN", 3)
BLOCK_AT = _int_env("REPEAT_GUARD_BLOCK", 5)
WINDOW = 20
RESETS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
IGNORE = set(os.environ.get("REPEAT_GUARD_IGNORE", "Read,Grep,Glob,LS,TodoWrite").split(","))
STATE_DIR = Path(os.environ.get("REPEAT_GUARD_DIR", Path.home() / ".cache" / "agent-guardrails"))


def fingerprint(event: dict) -> str:
    raw = json.dumps([event.get("tool_name"), event.get("tool_input")], sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def record(session: str, fp: str | None) -> int:
    """Append fp to the session history under a file lock; return its count in the window."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session)[:64] or "default"
    with open(STATE_DIR / f"repeat-{safe}.json", "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.seek(0)
        try:
            history = json.loads(fh.read() or "[]")
        except json.JSONDecodeError:
            history = []
        history = [] if fp is None else (history + [fp])[-WINDOW:]
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps(history))
    return history.count(fp) if fp else 0


def main() -> int:
    try:
        event = json.load(sys.stdin)
        if event.get("tool_name") in IGNORE:
            return 0
        reset = event.get("tool_name") in RESETS
        count = record(str(event.get("session_id", "default")), None if reset else fingerprint(event))
    except Exception:  # noqa: BLE001 - a guard must never crash the agent
        return 0
    if count >= BLOCK_AT:
        print(f"Blocked: identical call #{count} in the last {WINDOW}. Change parameters, "
              "switch tool, or report the obstacle.", file=sys.stderr)
        return 2
    if count >= WARN_AT:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": f"Repeat #{count}: if the last attempt failed, do not retry verbatim."}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
