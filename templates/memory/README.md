# Layered memory layout (template)

One always-loaded file does not scale: it grows stale and expensive. Use four layers and load downwards only as needed.

| Layer | File | Loaded | Holds |
|---|---|---|---|
| L3 | instruction file | every session | rules only |
| L2 | `scenario_<topic>.md` | when the task matches | a routing table: card name and when to read it |
| L1 | `<type>_<slug>.md` | when the scenario card points to it | one fact, one lesson, or one preference |
| L0 | `refs/` raw logs | only by grep | original text, never summarised away |

```
memory/
  MEMORY.md                  index of scenario cards, one line each, capped length
  scenario_deploys.md        "read [[lesson_stash_incident]] before touching git state"
  lesson_stash_incident.md   one card, one thing
  refs/signals.md            raw material, searched on demand
```

Card format:

```markdown
---
name: lesson-stash-incident
description: one line used to decide relevance
metadata:
  type: user | feedback | project | reference
  basis: verified | guess
  checked: 2026-01-31
---
The fact. **Why:** what happened. **How to apply:** what to do next time.
```

Rules that keep it healthy:
- Every card is a bet that it will be needed and still true. Do not store what can be looked up; store where to look.
- Update an existing card before creating a new one.
- New cards are linked from one scenario card, never from the index.
- Cards nobody has read for three weeks move to a cold folder and come back when read.
