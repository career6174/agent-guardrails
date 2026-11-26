# Playbook: the working rules behind the hooks

The hooks are the enforcement. These are the rules behind them, collected over months of running agents every day. A rule only earns a place here if it can be checked by a program or by a second agent; "be careful" does not count.

Every rule has the same shape: **the rule, why it exists, and how it is enforced.** Three of them ship as hooks in this repository (rules 1, 4, 5). The rest are enforced in the original deployment by hooks that are not ported yet; here they come as instruction-file text and subagent templates.

## 1. "Done" needs evidence someone else has opened

- **Rule.** Nothing is reported as finished until a reviewer that did not write it has opened the actual output: the file, the diff, the test log, the rendered page. Summaries, exit code 0 and "it should work" are not evidence.
- **Why.** Agents report success from their own summary. In the first review of this very repository, the tests were green and the delete guard still missed six common spellings.
- **Enforced by.** `hooks/review_gate.py` blocks the final answer until the reviewer subagent has run after the last edit. `agents/reviewer.md` forces a "claim → evidence → result" table.

## 2. The author does not grade their own work

- **Rule.** Review is done by a separate agent with a fresh context, given the artefact and not the author's conclusion. Agreement between two agents that share a context is not independent evidence.
- **Why.** An agent handed its own hypothesis tends to hand it back confirmed.
- **Enforced by.** The review gate only clears when the named reviewer subagent has been launched after the last edit. The reviewer template starts with "you did not write this and you do not trust its summary".

## 3. "Zero", "empty" and "nothing changed" are red flags

- **Rule.** A result of zero, empty, or identical-to-last-time is confirmed with a second independent source before it is reported as fact.
- **Why.** Silence often means the pipeline broke. A keyword pre-filter once silently dropped 353 of 499 records before anything looked at them; a parse error can read exactly like "no new mail today".
- **Enforced by.** Reviewer checklist item 3. In your own automation: make success an observable remote state (the remote commit equals the local commit), never an exit code.

## 4. Destructive actions must be recoverable

- **Rule.** Delete means "move to trash". History-rewriting git commands need a human. If something cannot be undone, the agent asks first, once, with a recommendation.
- **Why.** One `git stash` in a shared working tree swept away 6,033 uncommitted files that other sessions were using.
- **Enforced by.** `hooks/safe_delete_guard.py`.

## 5. Two failures, then change the approach

- **Rule.** The same call with the same arguments may fail twice. The third attempt must differ: change parameters, switch tool, simplify, or record the obstacle and move on.
- **Why.** Agents will retry a call that was never going to work until the budget is gone, and the real error scrolls out of view.
- **Enforced by.** `hooks/repeat_guard.py` (warn on the 3rd identical call, block on the 5th, reset on any edit).

## 6. Look for prior art before building

- **Rule.** Before writing a new service, workflow or any script that will run for a long time, search what already exists: your own past notes and working examples first, then mature open-source tools. Build only when there is a stated, checkable reason the existing option does not fit.
- **Why.** Agents happily rebuild from scratch what already exists two folders away, or what a mature open-source tool does better.
- **Enforced by.** A read-only "scout" subagent (`agents/scout.md`) whose only job is to answer "has someone already solved this?" and return a compressed verdict.

## 7. Changing A must not break B

- **Rule.** Before editing an existing file, list who consumes it and how each consumer will be verified. Make the smallest change. After the change, run the checks for the change *and* its consumers, then stop.
- **Why.** Shared files have consumers the author never opened. The fix for one job is the outage for another.
- **Enforced by.** The reviewer runs one realistic failure scenario per change (empty input, rerun, timezone, upstream format change). Shared files and scheduled jobs always get a full review.

## 8. Protect the one thing that must not go down

- **Rule.** Name your crown-jewel service explicitly. Any action that *might* affect it is not taken; it is reported instead. If an agent sees it unhealthy during any task, it alerts the human immediately and carries on. This rule outranks every other instruction, including "finish the task".
- **Why.** An agent once noticed the production service returning 503, wrote it down as a to-do and kept working. The service stayed down two more hours.
- **Enforced by.** A short deny-list at the top of the instruction file (`templates/CLAUDE.md`), plus a PreToolUse hook on the specific commands (deployment-specific, not in this repo).

## 9. Memory is layered, and every card is a bet

- **Rule.** Do not dump everything into one always-loaded file. Keep a short index, scenario cards that route to fact cards, and raw logs that are only searched on demand. Write a memory only for things learned the hard way; for anything that can be looked up, store where to look. Mark each card `verified` or `guess`.
- **Why.** One always-loaded memory file grows until half of it is stale, and a note left by an earlier session saying "this is normal" is an assumption, not a fact.
- **Enforced by.** Layout in `templates/memory/README.md`; an index line cap; cards unread for three weeks move to cold storage.

## 10. Big tool output goes to disk, not into the conversation

- **Rule.** Crawls, long logs and batch results are written to a file. The conversation keeps a one-line pointer with IDs that can be grepped later. A summary must never be the only copy.
- **Why.** When a long session compacts its context, a paraphrase becomes the only record of the raw results, and nobody can check it.
- **Enforced by.** Convention in the instruction file; the reviewer rejects claims whose evidence path does not exist.

## 11. A promise needs a ledger line

- **Rule.** "I'll do X once Y happens" is only allowed if a dated, checkable line is written to the task file: what, the condition, a review-by date, and what happens at that date.
- **Why.** "I'll check the first run on Thursday" is easy to say in a session that will not exist on Thursday.
- **Enforced by.** A stop hook that spots conditional promises in the final answer and sends it back if no ledger line was written (in its first eight days, 55 of 86 such answers were sent back).

## 12. Say whether it is finished, first

- **Rule.** Every final answer opens with one of three states: finished (and where the result is), not finished (what is pending and whether to wait), or blocked on a question. Then: done, not done or unverified with the reason, decisions needed.
- **Why.** A person running six sessions at once needs to see in one line which of them are waiting.
- **Enforced by.** A stop hook that checks the first line.

## 13. Spend the human's attention like money

- **Rule.** Anything the agent can find out itself, it does not ask. Reversible choices are made and reported with how to undo them. Only irreversible, paid or out-of-scope decisions go to the human, once, with a recommendation.
- **Why.** Human attention is the scarcest resource in the loop. A question whose answer is in the repository spends it for nothing.
- **Enforced by.** Instruction-file rule; a background observer agent that reads each step and flags questions the agent could have answered itself.

## 14. Guards fail open and say so

- **Rule.** A guard that crashes must let the agent continue. A gate that keeps blocking must give up after a fixed number of tries and tell the human. Guards are seatbelts against accidents, never the only line of defence.
- **Why.** A headless agent that opens an interactive prompt nobody can see hangs forever, and a gate that never gives up is the same thing.
- **Enforced by.** In the hooks here, malformed input, odd environment values and corrupt state never block (tested), and the review gate gives up after three blocks on the same pending set (tested).

---

## How the pieces fit

```
instruction file (rules, in priority order)
        │
        ├── PreToolUse hooks ── stop the dangerous or wasteful call before it runs
        ├── subagents ───────── scout (before building), reviewer (before delivering)
        ├── Stop hooks ──────── refuse "done" without review / ledger line / status line
        └── ledgers ─────────── every verdict and every block is logged, so the system can be measured
```

Start with rules 1, 4 and 5: they are the three hooks in this repository. Add the others as instruction-file text first, and turn one into a hook the second time it gets ignored.
