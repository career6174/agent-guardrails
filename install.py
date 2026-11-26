#!/usr/bin/env python3
"""Install, check or remove agent-guardrails in a Claude Code config folder.

    python3 install.py              register the three hooks and copy the two subagents
    python3 install.py --dry-run    show what would change, write nothing
    python3 install.py --doctor     check an existing install and run the live block demo
    python3 install.py --uninstall  remove exactly what the installer added

Standard library only. settings.json is backed up before every change, the write is atomic,
and running the installer twice changes nothing the second time. Hooks that other tools
registered are left alone.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent
HOOKS = [  # (event, matcher or None, script)
    ("PreToolUse", "Bash", "safe_delete_guard.py"),
    ("PreToolUse", "*", "repeat_guard.py"),
    ("Stop", None, "review_gate.py"),
]
AGENTS = ["reviewer.md", "scout.md"]
PLUGIN_ID = "agent-guardrails@"
MANIFEST = "agent-guardrails.manifest.json"  # which subagent files this installer created


class Abort(Exception):
    """Stop without having changed anything."""


def config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def quote(path: Path) -> str:
    """Quote a path for the shell Claude Code runs hooks in."""
    text = path.as_posix()
    if os.name != "nt":
        return shlex.quote(text)
    # Windows: hooks run in Git Bash or PowerShell; double quotes work in both, except for these.
    if any(ch in text for ch in '"$`'):
        raise Abort(f'the path {text} contains one of " $ ` and cannot be quoted safely on Windows. '
                    "Clone the repo into a folder without them. Nothing was changed.")
    return f'"{text}"'


def python_cmd() -> str:
    """The interpreter to put in settings.json."""
    if os.name != "nt" and shutil.which("python3"):
        return "python3"
    return quote(Path(sys.executable))


def hook_command(script: str) -> str:
    return f"{python_cmd()} {quote(REPO / 'hooks' / script)}"


def is_ours(command: object, script: str | None = None) -> bool:
    """True only for a command that runs our script: from this checkout, or from any folder named
    agent-guardrails (the older manual install). Someone else's hooks/repeat_guard.py never matches."""
    text = str(command).replace("\\", "/")
    names = [script] if script else [h[2] for h in HOOKS]
    return any((REPO / "hooks" / name).as_posix() in text or f"agent-guardrails/hooks/{name}" in text
               for name in names)


def load_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise Abort(f"{path} is not valid JSON ({exc}). Nothing was changed. Fix the file, then run again.")
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        raise Abort(f"{path} has an unexpected shape (top level and \"hooks\" must be objects). Nothing was changed.")
    return data


def _groups(settings: dict, event: str) -> list:
    groups = settings.get("hooks", {}).get(event, [])
    if not isinstance(groups, list):
        raise Abort(f'"hooks.{event}" in settings.json is not a list. Nothing was changed.')
    return groups


def registered(settings: dict, event: str, script: str) -> bool:
    return any(is_ours(h.get("command"), script)
               for g in _groups(settings, event) if isinstance(g, dict) and isinstance(g.get("hooks"), list)
               for h in g["hooks"] if isinstance(h, dict))


def add_hooks(settings: dict) -> list[str]:
    added = []
    for event, matcher, script in HOOKS:
        if registered(settings, event, script):
            continue
        group: dict = {"hooks": [{"type": "command", "command": hook_command(script)}]}
        if matcher:
            group = {"matcher": matcher, **group}
        settings.setdefault("hooks", {}).setdefault(event, []).append(group)
        added.append(f"{event}: {script}")
    return added


def remove_hooks(settings: dict) -> list[str]:
    removed = []
    hooks = settings.get("hooks", {})
    for event in list(hooks):
        kept_groups = []
        for group in _groups(settings, event):
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                kept_groups.append(group)
                continue
            kept = [h for h in group["hooks"] if not (isinstance(h, dict) and is_ours(h.get("command")))]
            removed += [f"{event}: {h.get('command')}" for h in group["hooks"] if h not in kept]
            if kept:
                kept_groups.append({**group, "hooks": kept})
        if kept_groups:
            hooks[event] = kept_groups
        else:
            del hooks[event]
    if "hooks" in settings and not hooks:
        del settings["hooks"]
    return removed


def save_settings(path: Path, settings: dict) -> Path | None:
    """Back up the old file, then replace it atomically. Returns the backup path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        backup = path.with_name(f"{path.name}.bak-agent-guardrails-{time.strftime('%Y%m%d-%H%M%S')}-{os.getpid()}")
        shutil.copy2(path, backup)
    tmp = path.with_name(path.name + ".tmp-agent-guardrails")
    tmp.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return backup


def read_manifest(cfg: Path) -> list[str]:
    try:
        data = json.loads((cfg / MANIFEST).read_text(encoding="utf-8"))
        return [n for n in data.get("agents", []) if n in AGENTS]
    except (OSError, ValueError, AttributeError):
        return []


def plugin_installed(cfg: Path) -> bool:
    try:
        return PLUGIN_ID in (cfg / "plugins" / "installed_plugins.json").read_text(encoding="utf-8")
    except OSError:
        return False


def demo() -> bool:
    """Feed the delete guard a fake dangerous command and confirm that it blocks."""
    command = "r" + "m -rf ./everything"
    event = {"tool_name": "Bash", "tool_input": {"command": command}, "session_id": "install-demo"}
    proc = subprocess.run([sys.executable, str(REPO / "hooks" / "safe_delete_guard.py")],
                          input=json.dumps(event), text=True, capture_output=True)
    print(f"  Demo: pretended the agent ran  {command}")
    if proc.returncode == 2:
        print(f"  Result: BLOCKED. The agent would be told: {proc.stderr.strip()}")
        return True
    print(f"  Result: NOT blocked (exit {proc.returncode}). Something is wrong; please open an issue.")
    return False


def install(cfg: Path, dry: bool) -> int:
    if plugin_installed(cfg):
        raise Abort("agent-guardrails is already installed as a Claude Code plugin. Use one route only "
                    "(two copies would count every tool call twice). Nothing was changed.")
    path = cfg / "settings.json"
    settings = load_settings(path)
    added = add_hooks(settings)
    tag = "Would" if dry else "Did"
    print(f"agent-guardrails -> {cfg}" + ("   (dry run: nothing is written)" if dry else ""))

    print("1. Hooks in settings.json")
    if not added:
        print("  Already registered. No change.")
    else:
        backup = None if dry else save_settings(path, settings)
        for item in added:
            print(f"  {tag} register {item}")
        if backup:
            print(f"  Backup of your old file: {backup}")

    print("2. Subagents")
    created = read_manifest(cfg)
    for name in AGENTS:
        src, dst = REPO / "agents" / name, cfg / "agents" / name
        if dst.exists() and dst.read_bytes() == src.read_bytes():
            print(f"  {name}: already there. No change.")
        elif dst.exists() and name not in created:
            print(f"  {name}: you already have your own file with this name. Kept yours.")
        elif dst.exists():
            print(f"  {name}: you edited the copy we installed. Kept your edits.")
        else:
            if not dry:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                created = sorted(set(created) | {name})
                (cfg / MANIFEST).write_text(json.dumps({"agents": created}) + "\n", encoding="utf-8")
            print(f"  {tag} copy {name} -> {dst}")

    print("3. Proof that it works")
    ok = demo()
    print("\nDone." if not dry else "\nDry run finished.", "Restart Claude Code (or open a new session) so it loads the hooks.")
    print(f"Optional rule file to adapt: {REPO / 'templates' / 'CLAUDE.md'}")
    print(f"Check later:  {python_cmd()} {quote(REPO / 'install.py')} --doctor")
    print(f"Remove:       {python_cmd()} {quote(REPO / 'install.py')} --uninstall")
    return 0 if ok else 1


def uninstall(cfg: Path, dry: bool) -> int:
    path = cfg / "settings.json"
    settings = load_settings(path)
    removed = remove_hooks(settings)
    tag = "Would remove" if dry else "Removed"
    print(f"agent-guardrails uninstall -> {cfg}" + ("   (dry run)" if dry else ""))
    if removed and not dry:
        print(f"  Backup of your old file: {save_settings(path, settings)}")
    for item in removed:
        print(f"  {tag} hook {item}")
    if not removed:
        print("  No agent-guardrails hooks found in settings.json.")
    created = read_manifest(cfg)
    for name in AGENTS:
        src, dst = REPO / "agents" / name, cfg / "agents" / name
        if not dst.exists():
            continue
        if name in created and dst.read_bytes() == src.read_bytes():
            if not dry:
                dst.unlink()
            print(f"  {tag} subagent {dst}")
        elif name in created:
            print(f"  Kept {dst} (you edited it after install).")
        else:
            print(f"  Kept {dst} (this installer did not create it, so it is yours).")
    if not dry and (cfg / MANIFEST).exists():
        (cfg / MANIFEST).unlink()
    print(f"The downloaded folder is still at {REPO}. Move it to the trash when you no longer need it.")
    return 0


def doctor(cfg: Path) -> int:
    settings = load_settings(cfg / "settings.json")
    print(f"agent-guardrails doctor -> {cfg}")
    ok = True
    for event, _, script in HOOKS:
        found = registered(settings, event, script)
        ok &= found
        print(f"  {'ok     ' if found else 'MISSING'} {event}: {script}")
    for name in AGENTS:
        found = (cfg / "agents" / name).exists()
        ok &= found
        print(f"  {'ok     ' if found else 'MISSING'} subagent {name}")
    if plugin_installed(cfg):
        print("  note: the plugin copy is installed too. Keep only one route.")
    ok &= demo()
    print("All good." if ok else "Problems found. Run install.py again, or see INSTALL.md.")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install, check or remove agent-guardrails for Claude Code.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--uninstall", action="store_true", help="remove what the installer added")
    mode.add_argument("--doctor", action="store_true", help="check the install and run the block demo")
    parser.add_argument("--dry-run", action="store_true", help="show the changes without writing them")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 10):
        print("agent-guardrails needs Python 3.10 or newer.", file=sys.stderr)
        return 1
    cfg = config_dir()
    try:
        if args.doctor:
            return doctor(cfg)
        if args.uninstall:
            return uninstall(cfg, args.dry_run)
        return install(cfg, args.dry_run)
    except Abort as exc:
        print(f"agent-guardrails: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
