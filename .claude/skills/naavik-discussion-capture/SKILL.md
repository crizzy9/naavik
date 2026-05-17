---
description: Scan the current run's `manager.log` for deferred items (SIDE_TASK, BLOCKED, OPEN_QUESTION, ROADMAP_EDIT row=<new>) and surface them via AskUserQuestion before closing a PR_REVIEW_GATE or MILESTONE_GATE. Each candidate is dispositioned (file as ROADMAP row / file as memory discussion / skip / merge with existing). Use whenever manager is about to close a gate. Triggers on phrases like "gate approved", "about to merge", "milestone done", "wrapping up", "before we close", "anything we deferred", "discussion capture", "what did we talk about".
allowed-tools: Read, Grep, Bash(grep:*), Bash(scripts/agent-memory.sh:*), Bash(scripts/gh-project.sh:*), AskUserQuestion
---

# naavik-discussion-capture

Manager invokes at PR_REVIEW_GATE (operating loop step 10) and MILESTONE_GATE (step 15). This is the deterministic answer to the user's question "we discuss things … we must add them to the roadmap if it's not being addressed immediately. are we doing that?" — yes, every gate.

Surface-then-ask. The system surfaces what it noticed; user decides per item. Locked decision per plan 19 § C.3 Q2.

## When to invoke

- Manager's operating loop step 10 — PR_REVIEW_GATE before merge.
- Manager's operating loop step 15 — MILESTONE_GATE before printing the milestone summary.
- User asks "anything deferred", "before we close", "did we miss anything".
- End of a long `/discuss` thread where the conversation surfaced side topics.

## What this skill does

### Step 1 — Scan the current run's manager.log

```bash
RUN_ID=<current run-id>
grep -hE "^\[.*\] (SIDE_TASK|BLOCKED|OPEN_QUESTION|ROADMAP_EDIT row=<new>) " \
  traces/$RUN_ID/manager.log
```

Event shapes:

| Event | Meaning | Disposition surface |
|---|---|---|
| `SIDE_TASK ` | Manager noticed a side topic during the run (e.g. "JWT denylist on rotation" surfaced during PC.6 review) | Candidate for ROADMAP row + memory discussion |
| `BLOCKED action=... reason=...` | Step blocked by sandbox / external dep / scope cap | Candidate for memory discussion (track the recurrence) |
| `OPEN_QUESTION ` | Architect surfaced a question the plan didn't resolve | Candidate for ROADMAP row (if user wants follow-up) |
| `ROADMAP_EDIT row=<new>` | Manager already filed a row; this is a confirmation entry | Already disposed; surface for accuracy verification |

### Step 2 — Cap at 5 candidates (hard limit)

If more than 5 candidates surface, rank by significance:

1. `SIDE_TASK` > `OPEN_QUESTION` > `BLOCKED` > `ROADMAP_EDIT` (already-filed).
2. Most recent first.

Show top 5; remaining go in a "see more" expandable note pointing at the log line.

### Step 3 — Surface via AskUserQuestion

One question per gate, with one row per candidate. Each row offers:

- **File as ROADMAP row** — manager runs `scripts/gh-project.sh create-issue <task-id> "<title>" --priority MEDIUM --effort S` AND records the discussion via `scripts/agent-memory.sh record-discussion ... --filed-as #<N>`.
- **File as memory discussion only** — no ROADMAP row; manager runs `scripts/agent-memory.sh record-discussion <topic> manager.log --priority LOW` (the operator wanted to capture rationale but not work).
- **Skip** — explicit skip; manager records `scripts/agent-memory.sh record-discussion <topic> manager.log --priority LOW --filed-as skipped` so future runs see this was considered and rejected.
- **Merge with existing row #N** — operator names an existing ROADMAP/Issue # the candidate belongs to.

### Step 4 — Apply dispositions

For each user response, manager invokes the matching writer (single-writer rule applies):

- ROADMAP row: edit `ROADMAP.md` (BOOKKEEPING — direct push post-merge) + `scripts/gh-project.sh create-issue ...` for the Project mirror.
- Memory discussion: `scripts/agent-memory.sh record-discussion ...`.
- Merge: append a `merged_into: #<N>` field via `record-discussion --filed-as #<N>`.

### Step 5 — Append run-level event

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
- `scripts/agent-memory.sh record-discussion` — the write path.
- `scripts/gh-project.sh create-issue` — the ROADMAP-mirror write path.
- `AGENTS.md § GitHub state — single writer rule` + § Single-doc-tracking.

## When NOT to invoke

- The current run has zero `SIDE_TASK` / `BLOCKED` / `OPEN_QUESTION` events. Skip cleanly; manager continues.
- Outside a `/build` run (ad-hoc question-answer turn). The gate context doesn't exist.
- Compaction events.

## Forbidden during invocation

- Do NOT auto-file ROADMAP rows without user consent (per plan 19 § C.3 — surface-then-ask, not auto-file).
- Do NOT bypass `scripts/gh-project.sh` for the Project mirror write. The persistent issue-map cache breaks otherwise.
- Do NOT skip the "Skip" option from the AskUserQuestion — the operator must be able to dismiss noise without ceremony.
- Do NOT cap below 5 candidates without recording the truncation. Future `/learn` retrospectives need the full denominator.
- Do NOT surface ROADMAP_EDIT events as "new" candidates — they're already filed by definition. Surface for accuracy verification only.
