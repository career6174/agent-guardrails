# Evidence: does it actually help?

Short answer: on one real deployment, **an independent reviewer flagged at least one issue in 72% of the deliverables an agent was ready to hand over, and rejected 22% outright**. A flag is a finding, not a confirmed defect. Below is where that number comes from, how to recompute it, and what it does *not* prove.

## Where the data comes from

- One person's always-on assistant setup (several agent sessions a day on a cloud VM: coding, reports, scheduled jobs).
- Every review verdict is appended to a ledger by a hook, so nobody has to remember to log anything.
- Window: **2026-10-24 to 2026-11-22 (30 days)**, 136 sessions. Snapshot taken 2026-11-22; `summary.json` is static.
- These numbers come from the original, larger private deployment. The three hooks in this repo are a clean-room port of its core and have not produced these numbers themselves.
- Counted: verdicts from the main reviewer whose target is a file (1,675 rows, 713 files). Not counted: 1,234 rows keyed by reviewer run instead of by file (one per run, including interrupted runs), 124 rows on workflow targets, and verdicts from two other review agents. With every target of the main reviewer included, 873 of 1,566 targets (55.7%) were flagged on first review.
- Only aggregates are published here. The raw ledger contains private file paths and stays private.

## Review gate

| Metric | Value |
|---|---|
| Review verdicts recorded | 1,675 |
| Distinct deliverables reviewed | 713 |
| Flagged on first review (conditional or rejected) | **512 (71.8%)** |
| of which rejected outright | 158 (22.2%) |
| Passed clean on first review | 21 (2.9%) |
| First review did not finish (reviewer ran out of turn or was interrupted) | 180 (25.2%) |
| Rejected deliverables that later moved off "rejected" | 73 of 158 (46%) |
| Review rounds per deliverable | median 2, mean 2.35 |

These 713 deliverables were ones the authoring agent considered ready to hand over. Without the gate they would have been delivered with no independent check.

## Stop gates (same deployment, hook logs)

| Gate | Since | What the log shows |
|---|---|---|
| "No delivery without review" stop gate | 2026-11-05 | blocked a final answer **357** times (blocks, not distinct answers: one session can be blocked more than once) |
| "A promise needs a tracked follow-up" gate | 2026-11-15 | of 86 final answers containing "I'll do X once Y", **55** had no tracked follow-up and were sent back |

## A worked example: this repository

The hooks here went through the same loop before release.

| Review round | What the independent reviewer found | Tests after the fix |
|---|---|---|
| 1 | The delete guard missed six spellings (absolute path, `xargs`, `find -delete`, `bash -c`, subshell, newline) and wrongly blocked `git stash pop` | 9 → 35 |
| 2 | `sudo -u`, `bash -lc`, `eval`, `git push origin +main`, `git branch -D` got through; a commit message containing "reset --hard" was wrongly blocked | 35 → 50 |
| 3 | Re-running the same test command after each edit would trip the repeat guard; the review gate could be silently exhausted for a file | 50 → 52 |
| 4 | Pass | 52 |
| 5 (final approver, a different model run) | Shell keywords hid the delete (`for … do`, `if … then`, `{ }`, `timeout`, `xargs -n 1`); the delete guard could crash on `tool_input: null`; a claim in the playbook was broader than the code | 53 → 62 |

The first version had passing tests and a green CI run. It was still wrong in ways its author did not see.

## Recompute it yourself

Keep a ledger of your own reviews (one JSON line per verdict), then:

```bash
python3 evidence/compute.py path/to/ledger.jsonl
```

The published numbers are the output of that script on the filtered ledger, with the original labels mapped to pass / conditional / reject / incomplete: see [`evidence/summary.json`](../evidence/summary.json).

## What this does not prove

- **No control group.** There is no "same work without the gate" arm, so this is not a measured reduction in defects. It is a count of findings that would otherwise have shipped unreviewed.
- **The reviewer is also a model.** A flag is a finding, not a confirmed defect. Nobody labelled the 512 flags as true or false positives. The worked example above is the part that was checked by hand.
- **One user, one month.** Different work and different models will give different rates.
- **Many items never reached a clean pass.** The last recorded verdict was "pass" for only 67 of 713. Conditional verdicts usually mean "fine to use, note the caveats", but the ledger does not record what the user did next.

The roadmap item that would close most of these gaps: a labelled set of real agent transcripts, measuring catch rate and false-block rate per hook.
