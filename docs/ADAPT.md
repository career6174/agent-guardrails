# If you cannot install it whole

The one-command install is the fast path. This page is for everyone it does not fit: a different agent tool, settings you are not allowed to change, hooks of your own, or a wish to understand the idea before running someone else's code. Read section 1 for the thinking; then jump to your situation in section 2.

[繁體中文](ADAPT.zh-Hant.md)

## 1. The thinking, step by step

Everything in this repository came from one loop, repeated:

```
an agent caused real damage
        │
        ▼
Q1. Can a program detect this?  ── yes ──▶ put a small check where the agent acts (a hook)
        │ no
        ▼
Q2. Can a second agent detect it? ─ yes ─▶ a reviewer with a fresh context, shown the result, required to cite evidence
        │ no
        ▼
write it down as a rule, and promote it to Q1 or Q2 the second time it is ignored
```

Five ideas carry the whole design. If you take nothing else, take these.

**1. Enforce, do not advise**
- Before: "Please never delete permanently" sits in the prompt and is forgotten by step 40.
- After: A program inspects each command before it runs and refuses the dangerous ones.
- Everyday picture: A speed limit sign versus a speed limiter in the engine.

**2. Check at the point of action**
- Before: Mistakes are found by reading the transcript afterwards.
- After: Two checkpoints: just before a tool call, and at the moment the agent says "done".
- Everyday picture: Airport security stands at the gate, not at the destination.

**3. Maker and checker are different**
- Before: The agent that wrote the report also declares it correct.
- After: A second agent with no shared context opens the actual output and matches each claim to evidence.
- Everyday picture: The person who requests a payment cannot also approve it.

**4. Guards step aside when they break**
- Before: A buggy guard blocks forever and the session hangs.
- After: Any internal error lets the agent continue; a gate gives up after three blocks and says so.
- Everyday picture: A circuit breaker that trips can always be reset by hand.

**5. Count everything**
- Before: "It feels safer."
- After: Every block and every verdict is a log line, so "does it help?" is a query.
- Everyday picture: A shop that counts its returns knows which product is faulty.

Why hooks and not a longer prompt: a prompt is read once and competes with everything else in a long task. A hook is outside the model. It runs the same way on the first call and the five-hundredth.

Why a second agent and not a self-check: an agent asked to check its own conclusion tends to confirm it. In the first review of this repository the tests were green, and the reviewer still found six ways around the delete guard.

## 2. Find your situation

| Your situation | Do this | What you get |
|---|---|---|
| Claude Code on macOS, Linux or WSL | The one command at the top of the [README](../README.md) | Everything |
| Claude Code on Windows | `git clone` then `python install.py` ([INSTALL.md](../INSTALL.md#other-routes)) | Everything |
| You may not edit user settings (company laptop) | `CLAUDE_CONFIG_DIR=./.claude python3 install.py` inside one project | Everything, in that project only |
| Your settings are centrally managed and hooks are locked | Ask the administrator to add the three entries from [INSTALL.md](../INSTALL.md#manual-install); meanwhile use section 3 | Rules and reviewer now, hooks when approved |
| You already have your own hooks | Run the installer: it appends and never rewrites your entries. If one of ours overlaps with yours, install the others by hand | The guards you choose |
| You want one guard only | Copy one file from `hooks/`, add one settings entry | That guard |
| Another agent tool with hooks | Section 4 | The same checks, wired to your tool |
| An agent with no hook system (chat window, hosted assistant) | Section 3 | The rules and the review step, without enforcement |
| You want to design your own guards | Section 5 | The method |

## 3. No hooks available: the text-only version

Without hooks nothing is enforced, so expect the rules to be skipped sometimes. It is still much better than nothing, because the review step catches what the rules miss.

1. Put the contents of [`templates/CLAUDE.md`](../templates/CLAUDE.md) in whatever your tool reads at the start of each session (a system prompt, a project instruction file, a pinned note). Fill in the parts in angle brackets.
2. Before you accept any deliverable, open a **new** conversation, paste the body of [`agents/reviewer.md`](../agents/reviewer.md), then paste the deliverable. Do not paste the author's summary. A new conversation is what makes the reviewer independent.
3. Before you ask for anything to be built, do the same with [`agents/scout.md`](../agents/scout.md) and the description of what you want.
4. Keep a tally for two weeks: how many deliverables the reviewer flagged, and how many flags were real. That number tells you whether enforcement is worth setting up.

What you lose compared with the hooks: the delete and retry guards (there is nothing to stop a command), and the guarantee that review happens (you have to remember it).

## 4. Porting to another agent tool

Most tools that can run commands have some way to run a program before a tool call or at the end of a turn. The names differ; the shape is the same. What each piece needs from the host:

| Piece | Reads | Says "block" by | Portable part |
|---|---|---|---|
| `safe_delete_guard.py` | The shell command about to run | Exit code 2, reason on stderr | `check(command)`: a pure function, returns a reason or `None`. No Claude-specific code |
| `repeat_guard.py` | Tool name, tool input, a session id | Exit code 2; a JSON warning before that | `fingerprint()` and `record()`: hash the call, count it in a 20-call window |
| `review_gate.py` | The session transcript as JSON lines | A JSON object `{"decision": "block", "reason": ...}` on stdout | `needs_review(lines)`: which deliverables were written after the last review |
| `agents/reviewer.md`, `agents/scout.md` | Nothing | Not applicable | Plain Markdown prompts; the front matter is the only Claude-specific part |
| `templates/CLAUDE.md`, `docs/PLAYBOOK.md` | Nothing | Not applicable | Plain text; rename to whatever your tool loads (`AGENTS.md`, a rules file) |

The input the three hooks expect on stdin is JSON with these fields: `tool_name`, `tool_input` (for shell calls, `tool_input.command`), `session_id`, and for the review gate `transcript_path`. If your tool sends different field names, a ten-line wrapper that renames them is the whole port.

The fastest way to do the port is to let your own agent do it. Paste this:

```
Read https://github.com/career6174/agent-guardrails : docs/ADAPT.md, the three files in hooks/, and tests/test_hooks.py.
Then look up how hooks (or the closest equivalent) work in <name of my tool>.
Port the three guards so they run in my tool. Keep the check logic unchanged; write only a thin adapter for the input and output format.
Port the tests too and run them. Show me each file before you install it, and tell me plainly which guard could not be ported and why.
```

Only Claude Code has been tested here. For any other tool, treat the table above as a map, and trust the ported tests, not this page.

## 5. Build your own guard in five steps

This is the recipe every guard in this repository went through.

1. **Start from an incident, not an idea.** Write one sentence: what the agent did, and what it cost. No incident, no guard. (Ours: one `git stash` swept away 6,033 uncommitted files.)
2. **Write the smallest check that would have stopped it.** One file, standard library, a pure function that takes the action and returns a reason or nothing. Keep it small enough to read in one sitting.
3. **Make it fail open, and test that.** Feed it garbage input, a missing file, a corrupt state file. In every case the agent must be allowed to continue.
4. **Have a different agent attack it.** Give a reviewer the code and ask for inputs that get past it. Every bypass becomes a test. The delete guard here went from 9 tests to 62 this way, over five rounds.
5. **Log and review after two weeks.** Count blocks. A guard that never fires may be unnecessary; a guard that fires on normal work is wrong and gets fixed or removed.

A rule that cannot be checked by a program or by a second agent is a wish. Keep it in the instruction file if you like, and do not rely on it.

## 6. What this will not do for you

- It is a seatbelt against accidents. It is not a security boundary: a deliberately disguised command gets through.
- The reviewer is also a model. A flag is a finding to look at, not a proven defect.
- The numbers in the README come from one person's deployment over one month. Measure your own before quoting them.
