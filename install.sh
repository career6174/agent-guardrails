#!/usr/bin/env bash
# One-command installer for agent-guardrails.
#   curl -fsSL https://raw.githubusercontent.com/career6174/agent-guardrails/main/install.sh | bash
# Pass options after "bash -s --", e.g.  ... | bash -s -- --dry-run
# It downloads the repo next to your Claude Code config, then runs install.py (which backs up
# settings.json before touching it). Undo with:  python3 <install dir>/install.py --uninstall
set -euo pipefail

REPO_URL="${AGENT_GUARDRAILS_REPO:-https://github.com/career6174/agent-guardrails}"
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
DEST="${AGENT_GUARDRAILS_HOME:-$CONFIG_DIR/agent-guardrails}"

say() { printf '%s\n' "$*"; }
die() { say "agent-guardrails: $*" >&2; exit 1; }

command -v git >/dev/null 2>&1 || die "git is required. Install git, then run this again."
PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
[ -n "$PY" ] || die "Python 3.10 or newer is required."

if [ -d "$DEST/.git" ]; then
  say "Updating $DEST"
  git -C "$DEST" pull --ff-only --quiet || die "could not update $DEST (local changes?). Fix or move it, then retry."
elif [ -e "$DEST" ]; then
  die "$DEST exists and is not a git checkout. Move it away, or set AGENT_GUARDRAILS_HOME to another folder."
else
  say "Downloading to $DEST"
  mkdir -p "$(dirname "$DEST")"
  git clone --depth 1 --quiet "$REPO_URL" "$DEST"
fi

exec "$PY" "$DEST/install.py" "$@"
