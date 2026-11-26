"""CI helper: run each hook command exactly as written in settings.json, through bash."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

settings = json.loads((Path(os.environ["CLAUDE_CONFIG_DIR"]) / "settings.json").read_text(encoding="utf-8"))
commands = [h["command"] for groups in settings["hooks"].values() for g in groups for h in g["hooks"]]
event = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git reset --hard"}, "session_id": "ci"})
bash = shutil.which("bash") or "bash"  # PATH order, so Git Bash wins inside a Git Bash step on Windows
print("bash:", bash)
codes = []
for command in commands:
    proc = subprocess.run([bash, "-c", command], input=event, text=True, capture_output=True)
    print(proc.returncode, command, proc.stderr.strip())
    codes.append(proc.returncode)
sys.exit(0 if codes == [2, 0, 0] else 1)
