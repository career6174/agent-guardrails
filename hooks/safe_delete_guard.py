#!/usr/bin/env python3
"""PreToolUse hook: block destructive deletes, point the agent to a recoverable trash command.

Claude Code sends the tool call as JSON on stdin. Exit code 2 = block, stderr is shown to the model.

The command is split into segments (on ; && || | newlines, $( and backticks), wrapper words
such as sudo / env / xargs / command are skipped, and the *program* of each segment is checked.
So `echo rm` or `npm rm` pass, while `/bin/rm x`, `xargs rm`, `bash -c "rm x"` are blocked.
"""
import json
import os
import re
import shlex
import sys

DELETERS = {"rm", "rmdir", "shred", "unlink"}
WRAPPERS = {"sudo", "env", "command", "xargs", "nohup", "time", "nice", "exec", "builtin", "doas", "timeout",
            "then", "do", "else", "elif", "{", "!"}
SHELLS = {"bash", "sh", "zsh", "dash"}
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SPLIT = re.compile(r"\|\||&&|[;|&\n`]|\$\(|\(|\)")

# wrapper -> flags of that wrapper that take a separate value
WRAPPER_ARG_FLAGS = {"sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-T"},
                     "env": {"-u", "-C", "-S"}, "nice": {"-n"}, "doas": {"-u", "-C"},
                     "xargs": {"-n", "-P", "-L", "-s", "-E", "-d", "-I"}, "timeout": {"-s", "-k"}}
DURATION = re.compile(r"^\d+(\.\d+)?[smhd]?$")
SHELL_C = re.compile(r"^-[A-Za-z]*c[A-Za-z]*$")


def _program(tokens: list[str]) -> tuple[str, list[str]]:
    """Skip wrappers (and their flags/values) and VAR=value prefixes; return (basename, args)."""
    wrapper, i = None, 0
    while i < len(tokens):
        tok = tokens[i]
        base = os.path.basename(tok)
        if ASSIGN.match(tok):
            i += 1
        elif wrapper and tok.startswith("-"):
            i += 2 if tok in WRAPPER_ARG_FLAGS.get(wrapper, ()) else 1
        elif wrapper == "timeout" and DURATION.match(tok):
            i += 1
        elif base in WRAPPERS:
            wrapper, i = base, i + 1
        else:
            return base, tokens[i + 1:]
    return "", []


def _git_reason(args: list[str]) -> str | None:
    """Judge by git subcommand + its own flags only, so commit messages never trigger a block."""
    while args and args[0].startswith("-"):  # global options like -C dir
        args = args[2:] if args[0] in ("-C", "-c") else args[1:]
    if not args:
        return None
    sub, rest = args[0], args[1:]
    flags = {a for a in rest if a.startswith("-")}
    if "--dry-run" in flags or (sub in ("clean", "push") and
                                any(not a.startswith("--") and "n" in a for a in flags)):
        return None
    if sub == "reset" and "--hard" in flags:
        return "git reset --hard"
    if sub == "clean" and any(a.startswith("-") and not a.startswith("--") and "f" in a for a in rest) | ("--force" in flags):
        return "git clean -f"
    if sub == "stash" and rest[:1] in (["drop"], ["clear"]):
        return "git stash drop/clear"
    if sub == "checkout" and "--" in rest:
        return "git checkout -- <path> (discards edits)"
    if sub == "checkout" and rest == ["."]:
        return "git checkout ."
    if sub == "restore" and not flags & {"--staged", "-S"}:
        return "git restore"
    if sub == "push" and (flags & {"-f", "--force"} or any(a.startswith("+") for a in rest)):
        return "git push --force"
    if sub == "branch" and "-D" in flags:
        return "git branch -D"
    if sub == "reflog" and rest[:1] == ["expire"]:
        return "git reflog expire"
    if sub == "gc" and any(a.startswith("--prune") for a in rest):
        return "git gc --prune"
    return None


def _segment_reason(segment: str, depth: int = 0) -> str | None:
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError:
        tokens = segment.split()
    prog, args = _program(tokens)
    if not prog:
        return None
    if prog in DELETERS:
        return f"permanent delete ({prog})"
    if prog == "find" and ("-delete" in args or any(os.path.basename(a) in DELETERS for a in args)):
        return "find -delete / -exec rm"
    if depth < 3 and prog == "eval":
        return check(" ".join(args), depth + 1)
    if depth < 3 and prog in SHELLS:
        for j, a in enumerate(args):
            if SHELL_C.match(a) and j + 1 < len(args):
                return check(args[j + 1], depth + 1)
    if prog == "git":
        reason = _git_reason(args)
        return f"{reason} discards work" if reason else None
    return None


def check(command: str, depth: int = 0) -> str | None:
    """Return a block reason, or None if the command is allowed."""
    for segment in SPLIT.split(command):
        if segment.strip():
            reason = _segment_reason(segment, depth)
            if reason:
                return reason
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
        if event.get("tool_name") != "Bash":
            return 0
        reason = check(str((event.get("tool_input") or {}).get("command", "")))
    except Exception:  # noqa: BLE001 - fail open on anything unexpected; never brick the agent
        return 0
    if reason:
        print(f"Blocked: {reason}. Use `trash-put <path>` (recoverable) or `mv <path> ./_attic/`; "
              "for git, commit or copy first, then ask the user.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
