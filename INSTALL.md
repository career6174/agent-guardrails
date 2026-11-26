# Installing agent-guardrails

This page is written for two readers: a person, and an AI agent that a person asked to do the install. Both can follow it top to bottom.

## The short version

```bash
curl -fsSL https://raw.githubusercontent.com/career6174/agent-guardrails/main/install.sh | bash
```

Then restart Claude Code. To preview first, add `-s -- --dry-run` after `bash`: the repo folder is still downloaded, and your settings and subagents are left untouched.

## What gets changed

| What | Where | How to undo |
|---|---|---|
| This repo | `~/.claude/agent-guardrails/` | Move the folder to the trash |
| Three hook entries | `~/.claude/settings.json` (a timestamped backup is written beside it first) | `install.py --uninstall`, or restore the backup |
| Two subagents | `~/.claude/agents/reviewer.md`, `scout.md` (skipped if you already have files with those names) | `install.py --uninstall` removes only the files it created, and only if you have not edited them |
| A small list of what was created | `~/.claude/agent-guardrails.manifest.json` | Removed by `--uninstall` |
| Small state files while it runs | `~/.cache/agent-guardrails/` | Clear any time |

Nothing else is touched: no packages are installed, no instruction file is written, no network call is made after the download. If `CLAUDE_CONFIG_DIR` is set, that folder is used instead of `~/.claude`.

## Check that it works

```bash
python3 ~/.claude/agent-guardrails/install.py --doctor
```

Expected: five lines starting with `ok`, then `Result: BLOCKED`, then `All good.` A hook that is registered wrongly fails quietly, so this command is the way to know. The demo feeds a pretend delete command to the guard; nothing real is deleted.

In a new Claude Code session you can also ask the agent to permanently delete a scratch file. It should report that the command was blocked and switch to a recoverable delete.

## Update and remove

```bash
curl -fsSL https://raw.githubusercontent.com/career6174/agent-guardrails/main/install.sh | bash                      # update: same command again
python3 ~/.claude/agent-guardrails/install.py --uninstall     # remove
```

## Other routes

**Windows, Command Prompt (cmd):**

```
git clone https://github.com/career6174/agent-guardrails "%USERPROFILE%\.claude\agent-guardrails"
python "%USERPROFILE%\.claude\agent-guardrails\install.py"
```

**Windows, PowerShell:**

```powershell
git clone https://github.com/career6174/agent-guardrails "$env:USERPROFILE\.claude\agent-guardrails"
python "$env:USERPROFILE\.claude\agent-guardrails\install.py"
```

In Git Bash the one-command install above works as it is. On Windows the registered hook commands were verified running under Git Bash, which is what Claude Code uses when it is installed. On Windows the repeat guard has no file lock, so when several tool calls run at the same moment a repeat can occasionally go uncounted; the other two guards are unaffected.

**One project only** (nothing in your user settings): run from the project root.

```bash
git clone https://github.com/career6174/agent-guardrails .claude/agent-guardrails
CLAUDE_CONFIG_DIR=./.claude python3 .claude/agent-guardrails/install.py
```

This writes `./.claude/settings.json` and `./.claude/agents/`, which Claude Code reads as project settings. The hook paths are absolute, so this suits a personal checkout, not a file you commit for teammates.

**Claude Code plugin:**

```bash
claude plugin marketplace add career6174/agent-guardrails
claude plugin install agent-guardrails@agent-guardrails
```

The plugin route needs `python3` on your PATH. As a plugin the subagents are named `agent-guardrails:reviewer` and `agent-guardrails:scout`; the review gate accepts both the short and the prefixed name. Do not combine the plugin with the script install: every tool call would be counted twice. The script refuses to run if it sees the plugin. Run one installer at a time.

## Manual install

Use this when the installer stops (for example your `settings.json` is not valid JSON) or when you want only one guard. Clone the repo anywhere, then add the entries you want to the `hooks` object of your settings file, keeping whatever is already there:

```json
{
  "hooks": {
    "PreToolUse": [
      {"matcher": "Bash", "hooks": [{"type": "command", "command": "python3 ~/.claude/agent-guardrails/hooks/safe_delete_guard.py"}]},
      {"matcher": "*", "hooks": [{"type": "command", "command": "python3 ~/.claude/agent-guardrails/hooks/repeat_guard.py"}]}
    ],
    "Stop": [
      {"hooks": [{"type": "command", "command": "python3 ~/.claude/agent-guardrails/hooks/review_gate.py"}]}
    ]
  }
}
```

| You want | Add | Also needed |
|---|---|---|
| No permanent deletes, no history rewrites | the `safe_delete_guard.py` entry | nothing |
| No endless identical retries | the `repeat_guard.py` entry | nothing |
| No "done" without a review | the `review_gate.py` entry | `agents/reviewer.md` copied to `~/.claude/agents/` |

## Troubleshooting

| You see | Cause | Fix |
|---|---|---|
| `settings.json is not valid JSON ... Nothing was changed` | A stray comma or comment in your settings file | Fix the file (the message names the position), run again |
| `already installed as a Claude Code plugin` | Both routes at once | Keep one: remove the plugin, or skip the script |
| `could not update ... (local changes?)` | You edited files in the install folder | Move your edits elsewhere, or set `AGENT_GUARDRAILS_HOME` to a fresh folder |
| `cannot be quoted safely on Windows` | The install folder path contains `"`, `$` or a backtick | Clone into a folder without those characters |
| Hooks do not fire | Claude Code was not restarted, or a project-level setting disables hooks | Restart; run `--doctor`; check `/hooks` inside Claude Code |
| The review gate blocks too often | Its default file pattern does not suit your work | Set `REVIEW_GATE_PATTERN` (see README, Configure) |

## If you are an AI agent doing this install

1. Tell the user, in one or two sentences, what will change (the table above), before running anything.
2. Run the installer with `--dry-run` first and show the output.
3. Run the real install. Do not edit `settings.json` by hand unless the installer stopped and the user agrees to the manual route.
4. Run `--doctor` and paste its output. Report "installed" only if it ends with `All good.`
5. Tell the user to restart Claude Code, and give them the uninstall command.
6. If the machine cannot run the installer at all, do not improvise. Read [docs/ADAPT.md](docs/ADAPT.md) and follow the route that matches.
