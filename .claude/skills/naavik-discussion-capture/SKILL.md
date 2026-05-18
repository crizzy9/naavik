---
description: Scan the current run's `manager.log` for deferred items (SIDE_TASK, BLOCKED, OPEN_QUESTION, ROADMAP_EDIT row=<new>) and surface them via AskUserQuestion before closing a PR_REVIEW_GATE or MILESTONE_GATE. Each candidate is dispositioned (file as ROADMAP row / file as memory discussion / skip / merge with existing). Use whenever manager is about to close a gate. Triggers on phrases like "gate approved", "about to merge", "milestone done", "wrapping up", "before we close", "anything we deferred", "discussion capture", "what did we talk about".
allowed-tools: Read, Grep, Bash(grep:*), Bash(scripts/agent-memory.sh:*), Bash(scripts/gh-project.sh:*), AskUserQuestion
---

# naavik-discussion-capture

Manager invokes at PR_REVIEW_GATE (operating loop step 10) + MILESTONE_GATE (step 15). Deterministic answer to "we discuss things … we must add them to roadmap if not addressed immediately" — yes, every gate.

Surface-then-ask. System surfaces what it noticed; user decides per item. Locked per plan 19 § C.3 Q2.

## When to invoke

- Manager operating loop step 10 — PR_REVIEW_GATE before merge.
- Manager operating loop step 15 — MILESTONE_GATE before milestone summary print.
- User asks "anything deferred", "before we close", "did we miss anything".
- End of long `/discuss` thread surfacing side topics.

## Steps

### 1 — Scan current run's manager.log

```bash
RUN_ID=<current run-id>
grep -hE "^\[.*\] (SIDE_TASK|BLOCKED|OPEN_QUESTION|ROADMAP_EDIT row=<new>) " \
  traces/$RUN_ID/manager.log
```

Event shapes:

| Event | Meaning | Disposition surface |
|---|---|---|
| `SIDE_TASK` | Manager noticed side topic during run (e.g. "JWT denylist on rotation" during PC.6 review) | Candidate for ROADMAP row + memory discussion |
| `BLOCKED action=... reason=...` | Step blocked by sandbox / external dep / scope cap | Candidate for memory discussion (track recurrence) |
| `OPEN_QUESTION` | Architect surfaced question plan didn't resolve | Candidate for ROADMAP row (if user wants follow-up) |
| `ROADMAP_EDIT row=<new>` | Manager already filed row; confirmation entry | Already disposed; surface for accuracy verification |

### 2 — Cap at 5 candidates (hard limit)

If > 5 candidates surface, rank:

1. `SIDE_TASK` > `OPEN_QUESTION` > `BLOCKED` > `ROADMAP_EDIT` (already-filed).
2. Most recent first.

Show top 5; rest in "see more" expandable note pointing at log line.

### 3 — Surface via AskUserQuestion

One question per gate, one row per candidate. Each row offers:

- **File as ROADMAP row** — manager runs `scripts/gh-project.sh create-issue <task-id> "<title>" --priority MEDIUM --effort S` AND records discussion via `scripts/agent-memory.sh record-discussion ... --filed-as #<N>`.
- **File as memory discussion only** — no ROADMAP row; manager runs `scripts/agent-memory.sh record-discussion <topic> manager.log --priority LOW` (operator wanted rationale, not work).
- **Skip** — explicit skip; manager records `scripts/agent-memory.sh record-discussion <topic> manager.log --priority LOW --filed-as skipped` so future runs see it was considered + rejected.
- **Merge with existing row #N** — operator names existing ROADMAP/Issue # candidate belongs to.

### 4 — Apply dispositions

Per user response, manager invokes matching writer (single-writer rule):

- ROADMAP row: edit `ROADMAP.md` (BOOKKEEPING — direct push post-merge) + `scripts/gh-project.sh create-issue ...` for Project mirror.
- Memory discussion: `scripts/agent-memory.sh record-discussion ...`.
- Merge: append `merged_into: #<N>` via `record-discussion --filed-as #<N>`.

### 5 — Append run-level event

```
[ISO-timestamp] DISCUSSION_CAPTURE candidates=<N> filed=<M> skipped=<K> merged=<L>
```

## Argument shape (when invoked programmatically)

```
Skill: naavik-discussion-capture
Args:
  gate: pr_review | milestone
  run_id: <YYYY-MM-DDTHH-MM-SS_<6hex>>
```

## Canonical references

- `docs/design/AGENT_MEMORY.md § 4` — discussion-capture gate procedure.
- `docs/AGENT_OPS.md § 7.2` — event shapes for manager.log.
- `.claude/agents/manager.md` § Operating loop step 10 + step 15.
- `scripts/agent-memory.sh record-discussion` — write path.
- `scripts/gh-project.sh create-issue` — ROADMAP-mirror write path.
- `AGENTS.md § GitHub state — single writer rule` + § Single-doc-tracking.

## When NOT to invoke

- Current run has zero `SIDE_TASK` / `BLOCKED` / `OPEN_QUESTION` events. Skip cleanly.
- Outside `/build` run (ad-hoc Q&A turn). Gate context doesn't exist.
- Compaction events.

## Forbidden during invocation

- Do NOT auto-file ROADMAP rows without user consent (plan 19 § C.3 — surface-then-ask).
- Do NOT bypass `scripts/gh-project.sh` for Project mirror. Breaks persistent issue-map cache.
- Do NOT skip "Skip" option in AskUserQuestion — operator must dismiss noise without ceremony.
- Do NOT cap below 5 without recording truncation. Future `/learn` needs full denominator.
- Do NOT surface ROADMAP_EDIT events as "new" candidates — already filed by definition. Surface for accuracy verification only.
