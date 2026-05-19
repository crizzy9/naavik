---
description: Auto-promote workflow primitive for the manager. When manager detects an empty Todo column (operating-loop step 2 OR `next-unblocked` returns null mid-loop), invoke this skill to surface the top-priority epic in Backlog + its top unblocked items via AskUserQuestion. User picks 1–N items; manager applies `set-status <id> Todo` per pick (one MIRROR per item) and resumes the loop. Triggers on phrases like "todo empty", "auto-promote", "promote backlog item", "next-unblocked returned null", "backlog promotion", "pull backlog into current cycle".
allowed-tools: Read, Bash(.claude/naavik-ops:*), Bash(jq:*), AskUserQuestion
---

# manager-backlog-promote

Auto-promote when Todo column empties mid-`/build` or at operating-loop step 2. Backlog items are deferred + skipped by `next-unblocked` (per `docs/AGENT_OPS.md § 6.3`). Pulling a Backlog item into current cycle requires explicit user consent — this is the gated surface.

Codified A.28 PLAN_GATE 2026-05-17 (Q3 REVERSED): Backlog → Todo promotion is automatic + manager-driven, NOT operator-driven via ad-hoc `set-status` calls.

## When to invoke

- Manager operating loop step 2 (`/build`) → `.claude/naavik-ops gh next-unblocked` returns null for current milestone.
- Manager detects Todo count == 0 mid-loop (post-close, pre-next-pick).
- User asks "what's in Backlog" / "promote a Backlog item" — same prompt surfaced for explicit promotion.
- Manager pre-flight at MILESTONE_GATE — next milestone's Todo empty → surface promotion gate before "Continue."

## Steps

1. **Verify Todo empty.** Run `.claude/naavik-ops gh next-unblocked`. Expect `null`. Non-null → halt; caller invoked in error.

2. **Pull Backlog by epic.**
   ```bash
   .claude/naavik-ops gh backlog-by-epic --top 5
   ```
   Returns JSON: array of `{epic_issue, epic_title, epic_priority, items[], total_items}` ordered by epic priority (CRITICAL > HIGH > MEDIUM > LOW > unset). Within epic, items unprioritized (only epic carries priority); insertion order preserved.

3. **Top epic.** First array entry. Array empty → Backlog empty:
   ```
   No Backlog items either. Milestone <name> fully cleared. Recommend `/standup` or pick different milestone.
   ```
   HALT.

4. **Surface via AskUserQuestion.** Shape:
   ```
   Todo empty for milestone <name>.

   Top epic in Backlog by priority: [Epic] <epic_title> (<epic_priority>, <total_items> items)

   Top items (unprioritized within epic):
     1. #<issue> <title>
     2. #<issue> <title>
     ...

   Which items to promote to Todo? (Pick 1–N, or "skip this epic", or "halt loop".)
   ```
   Options: each item multi-select + "Skip — try next epic" + "Halt — stop loop here."

5. **Apply picks.** Per picked item:
   ```bash
   .claude/naavik-ops gh set-status <project-item-id> Todo
   ```
   Resolve project-item-id from Issue # via `.claude/naavik-ops gh item-id <issue-num>`. One MIRROR line per item to `traces/<run-id>/manager.log`:
   ```
   [ISO-ts] MIRROR action=set-status item=<issue-num> from=Backlog to=Todo
   ```

6. **PROMOTE_BACKLOG trace event** summarizing operation:
   ```
   [ISO-ts] PROMOTE_BACKLOG epic="<epic_title>" items_picked=<n> items=<csv-of-issue-nums>
   ```

7. **Skip / Halt:**
   - **Skip** → recurse on next epic in `backlog-by-epic` array. No more epics → "Backlog also empty" path from step 3.
   - **Halt** → return control to `/build` step 15 (MILESTONE_GATE) w/ halt reason `user-halt-at-backlog-promote`.

8. **Successful pick(s)** → return control to manager operating loop step 2 (`next-unblocked` will now return one of promoted items).

## Canonical references

- `.claude/naavik_ops/gh.py` § `cmd_backlog_by_epic` (added A.28; ported to native Python in 0.1.1) — read-only primitive.
- `.claude/naavik_ops/gh.py` § `cmd_set_status` — Backlog → Todo write.
- `.claude/naavik_ops/gh.py` § `cmd_item_id` — Issue # → project item id.
- `.claude/agents/manager.md` § Operating loop step 2 — caller.
- `docs/AGENT_OPS.md § 6.3` — 4-status mapping + asymmetric Backlog convention.
- `docs/plans/archive/20-A.28-board-restructure.md` § B.6 — design rationale.
- `AGENTS.md § GitHub state — single writer rule` — all writes via `.claude/naavik-ops gh`.

## When NOT to invoke

- Todo has work (verify with `next-unblocked`). Use `manager-pick-next` instead.
- Mid-PLAN_GATE / PR_REVIEW_GATE — wait for user gate response; don't compound gates.
- User just said "Halt"/"Stop" at MILESTONE_GATE — respect halt; don't re-prompt.
- Compaction events.

## Forbidden during invocation

- Do NOT auto-promote without AskUserQuestion. User-consent gate is the point.
- Do NOT bypass `.claude/naavik_ops/gh.py` to call `gh api graphql` for set-status — single-writer rule.
- Do NOT promote `blocked`-labelled items. `backlog-by-epic` filter excludes `epic` label, but `blocked` items can be in Backlog; if surfaced, AskUserQuestion before promoting.
- Do NOT hand-edit `.claude/github-issue-map.json`.
