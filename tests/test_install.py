import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(cfg, *args):
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(cfg)}
    return subprocess.run([sys.executable, str(ROOT / "install.py"), *args], text=True,
                          capture_output=True, env=env)


def settings(cfg):
    return json.loads((cfg / "settings.json").read_text(encoding="utf-8"))


def commands(cfg):
    return [h["command"] for groups in settings(cfg).get("hooks", {}).values()
            for g in groups for h in g["hooks"]]


def backups(cfg):
    return sorted(cfg.glob("settings.json.bak-agent-guardrails-*"))


def state(cfg):
    """Everything in the config folder except our manifest and backups."""
    return sorted(p.name for p in cfg.iterdir()
                  if p.name != "agent-guardrails.manifest.json" and ".bak-agent-guardrails-" not in p.name)


def test_fresh_install_registers_everything_and_shows_a_block(tmp_path):
    p = run(tmp_path)
    assert p.returncode == 0, p.stderr
    assert "BLOCKED" in p.stdout
    s = settings(tmp_path)
    assert [g["matcher"] for g in s["hooks"]["PreToolUse"]] == ["Bash", "*"]
    assert "matcher" not in s["hooks"]["Stop"][0]
    assert len(commands(tmp_path)) == 3
    assert (tmp_path / "agents" / "reviewer.md").exists() and (tmp_path / "agents" / "scout.md").exists()
    assert backups(tmp_path) == []  # nothing existed, so nothing to back up


def test_registered_commands_actually_run(tmp_path):
    run(tmp_path)
    event = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}, "session_id": "t"})
    for cmd in commands(tmp_path):
        p = subprocess.run(cmd, shell=True, input=event, text=True, capture_output=True,
                           env={**os.environ, "REPEAT_GUARD_DIR": str(tmp_path / "state")})
        assert p.returncode == 0, (cmd, p.stderr)


def test_second_run_changes_nothing(tmp_path):
    run(tmp_path)
    before = (tmp_path / "settings.json").read_bytes()
    p = run(tmp_path)
    assert p.returncode == 0 and "Already registered" in p.stdout
    assert (tmp_path / "settings.json").read_bytes() == before
    assert backups(tmp_path) == []


def test_keeps_existing_settings_and_other_hooks(tmp_path):
    original = {"model": "x", "permissions": {"allow": ["Bash(ls:*)"]},
                "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-check"}]}],
                          "SessionStart": [{"hooks": [{"type": "command", "command": "hello"}]}]}}
    (tmp_path / "settings.json").write_text(json.dumps(original), encoding="utf-8")
    assert run(tmp_path).returncode == 0
    s = settings(tmp_path)
    assert s["model"] == "x" and s["permissions"] == original["permissions"]
    assert s["hooks"]["SessionStart"] == original["hooks"]["SessionStart"]
    assert s["hooks"]["PreToolUse"][0] == original["hooks"]["PreToolUse"][0]
    assert len(commands(tmp_path)) == 5
    assert len(backups(tmp_path)) == 1
    assert json.loads(backups(tmp_path)[0].read_text(encoding="utf-8")) == original


def test_uninstall_restores_the_original(tmp_path):
    original = {"model": "x", "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "my-own-check"}]}]}}
    (tmp_path / "settings.json").write_text(json.dumps(original), encoding="utf-8")
    run(tmp_path)
    p = run(tmp_path, "--uninstall")
    assert p.returncode == 0, p.stderr
    assert settings(tmp_path) == original
    assert not (tmp_path / "agents" / "reviewer.md").exists()


def test_uninstall_after_fresh_install_leaves_no_hooks_key(tmp_path):
    run(tmp_path)
    run(tmp_path, "--uninstall")
    assert settings(tmp_path) == {}


def test_invalid_json_aborts_and_touches_nothing(tmp_path):
    (tmp_path / "settings.json").write_text("{ not json", encoding="utf-8")
    p = run(tmp_path)
    assert p.returncode == 1 and "Nothing was changed" in p.stderr
    assert (tmp_path / "settings.json").read_text(encoding="utf-8") == "{ not json"
    assert not (tmp_path / "agents").exists()


def test_unexpected_shape_aborts(tmp_path):
    for bad in ('[]', '{"hooks": []}', '{"hooks": {"Stop": {}}}'):
        (tmp_path / "settings.json").write_text(bad, encoding="utf-8")
        p = run(tmp_path)
        assert p.returncode == 1, bad
        assert (tmp_path / "settings.json").read_text(encoding="utf-8") == bad


def test_dry_run_writes_nothing(tmp_path):
    p = run(tmp_path, "--dry-run")
    assert p.returncode == 0 and "Would register" in p.stdout
    assert list(tmp_path.iterdir()) == []


def test_keeps_a_users_own_reviewer(tmp_path):
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "reviewer.md").write_text("mine", encoding="utf-8")
    p = run(tmp_path)
    assert "Kept yours" in p.stdout
    run(tmp_path, "--uninstall")
    assert (tmp_path / "agents" / "reviewer.md").read_text(encoding="utf-8") == "mine"
    assert not (tmp_path / "agents" / "scout.md").exists()


def test_manual_install_from_older_readme_is_not_duplicated(tmp_path):
    old = {"hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 ~/.claude/agent-guardrails/hooks/safe_delete_guard.py"}]},
        {"matcher": "*", "hooks": [{"type": "command", "command": "python3 ~/.claude/agent-guardrails/hooks/repeat_guard.py"}]}],
        "Stop": [{"hooks": [{"type": "command", "command": "python3 ~/.claude/agent-guardrails/hooks/review_gate.py"}]}]}}
    (tmp_path / "settings.json").write_text(json.dumps(old), encoding="utf-8")
    p = run(tmp_path)
    assert "Already registered" in p.stdout
    assert settings(tmp_path) == old


def test_doctor_reports_missing_then_ok(tmp_path):
    p = run(tmp_path, "--doctor")
    assert p.returncode == 1 and "MISSING" in p.stdout
    run(tmp_path)
    p = run(tmp_path, "--doctor")
    assert p.returncode == 0 and "All good" in p.stdout


def test_refuses_when_plugin_copy_is_installed(tmp_path):
    (tmp_path / "plugins").mkdir()
    (tmp_path / "plugins" / "installed_plugins.json").write_text('{"plugins": {"agent-guardrails@agent-guardrails": []}}', encoding="utf-8")
    p = run(tmp_path)
    assert p.returncode == 1 and "one route only" in p.stderr
    assert not (tmp_path / "settings.json").exists()


def test_install_sh_end_to_end_from_a_local_clone(tmp_path):
    if os.name == "nt":
        return
    cfg = tmp_path / "cfg"
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(cfg), "AGENT_GUARDRAILS_REPO": str(ROOT)}
    if subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True).returncode != 0:
        return  # not a git checkout (e.g. a source tarball)
    if subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", "HEAD:install.py"], capture_output=True).returncode != 0:
        return  # installer not committed yet
    p = subprocess.run(["bash", str(ROOT / "install.sh")], text=True, capture_output=True, env=env)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "BLOCKED" in p.stdout
    assert (cfg / "agent-guardrails" / "install.py").exists()
    assert all(str(cfg / "agent-guardrails").replace(os.sep, "/") in c for c in commands(cfg))
    p = subprocess.run(["bash", str(ROOT / "install.sh")], text=True, capture_output=True, env=env)
    assert p.returncode == 0 and "Already registered" in p.stdout


def test_someone_elses_hook_with_the_same_file_name_is_left_alone(tmp_path):
    theirs = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
        {"type": "command", "command": "python3 /opt/other-tool/hooks/repeat_guard.py"}]}]}}
    (tmp_path / "settings.json").write_text(json.dumps(theirs), encoding="utf-8")
    assert run(tmp_path).returncode == 0
    assert len(commands(tmp_path)) == 4  # theirs + our three: ours was not skipped
    assert run(tmp_path, "--uninstall").returncode == 0
    assert settings(tmp_path) == theirs


def test_identical_reviewer_that_was_already_there_survives_uninstall(tmp_path):
    (tmp_path / "agents").mkdir()
    (tmp_path / "agents" / "reviewer.md").write_bytes((ROOT / "agents" / "reviewer.md").read_bytes())
    run(tmp_path)
    p = run(tmp_path, "--uninstall")
    assert "did not create it" in p.stdout
    assert (tmp_path / "agents" / "reviewer.md").exists()
    assert not (tmp_path / "agents" / "scout.md").exists()
    assert not (tmp_path / "agent-guardrails.manifest.json").exists()


def test_group_with_null_hooks_does_not_crash(tmp_path):
    odd = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": None}]}}
    (tmp_path / "settings.json").write_text(json.dumps(odd), encoding="utf-8")
    p = run(tmp_path)
    assert p.returncode == 0, p.stderr
    assert "Traceback" not in p.stderr
    run(tmp_path, "--uninstall")
    assert settings(tmp_path) == odd


def test_install_from_a_path_with_spaces_and_non_ascii(tmp_path):
    import shutil
    repo = tmp_path / "my tools 工具" / "agent-guardrails"
    shutil.copytree(ROOT, repo, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache"))
    cfg = tmp_path / "cfg dir"
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(cfg), "PYTHONUTF8": "1", "REPEAT_GUARD_DIR": str(tmp_path / "state")}
    p = subprocess.run([sys.executable, str(repo / "install.py")], capture_output=True, env=env)
    assert p.returncode == 0, p.stderr
    blocked = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git reset --hard"}, "session_id": "t"})
    cmds = commands(cfg)
    assert len(cmds) == 3
    results = [subprocess.run(c, shell=True, input=blocked, text=True, capture_output=True, env=env).returncode for c in cmds]
    assert results[0] == 2 and results[1:] == [0, 0], results  # the delete guard really ran from that path
