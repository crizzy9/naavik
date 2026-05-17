---
description: Auto-promote workflow primitive for the manager. When manager detects an empty Todo column (operating-loop step 2 OR `next-unblocked` returns null mid-loop), invoke this skill to surface the top-priority epic in Backlog + its top unblocked items via AskUserQuestion. User picks 1–N items; manager applies `set-status <id> Todo` per pick (one MIRROR per item) and resumes the loop. Triggers on phrases like "todo empty", "auto-promote", "promote backlog item", "next-unblocked returned null", "backlog promotion", "pull backlog into current cycle".
allowed-tools: Read, Bash(scripts/gh-project.sh:*), Bash(jq:*), AskUserQuestion
---

# manager-backlog-promote

Manager's auto-promote workflow when the Todo column empties mid-`/build` or at operating-loop step 2. Backlog items are deferred from the current cycle and skipped by `next-unblocked` (per `docs/AGENT_OPS.md § 6.3`). To pull a Backlog item into the current cycle requires explicit user consent — this skill is the gated surface.

Codified at A.28 PLAN_GATE 2026-05-17 (Q3 REVERSED from architect's original): Backlog → Todo promotion is automatic + manager-driven, NOT operator-driven via ad-hoc `set-status` calls.

## When to invoke

- Manager's operating loop step 2 (`/build` flow) returns null from `scripts/gh-project.sh next-unblocked` for the current milestone.
- Manager detects Todo count == 0 mid-loop (after closing the previous task, before picking another).
- User asks "what's in Backlog" or "promote a Backlog item" — surface the same prompt for explicit promotion.
- Manager's pre-flight at MILESTONE_GATE — if the next milestone's Todo is empty, surface a promotion gate before user picks "Continue."

## What this skill does

1. **Verify Todo is empty.** Run `scripts/gh-project.sh next-unblocked` once and parse JSON. Expect `null`. If non-null, halt — there's still Todo work; the caller invoked this skill in error.

2. **Pull Backlog grouped by epic.**
   ```bash
   scripts/gh-project.sh backlog-by-epic --top 5
   ```
   Returns JSON: array of `{epic_issue, epic_title, epic_priority, items[], total_items}` ordered by epic priority (CRITICAL > HIGH > MEDIUM > LOW > unset). Within an epic, items are unprioritized (only the epic carries priority); insertion order preserved.

3. **Identify the top epic.** First entry of the array. If the array is empty, Backlog is also empty — emit:
   ```
   No Backlog items either. Milestone <name> is fully cleared. Recommend `/standup` or pick a different milestone.
   ```
   Then HALT.

4. **Surface via AskUserQuestion.** Prompt shape:
   ```
   Todo empty for milestone <name>.

   Top epic in Backlog by priority: [Epic] <epic_title> (<epic_priority>, <total_items> items)

   Top items (unprioritized within epic):
     1. #<issue> <title>
     2. #<issue> <title>
     ...

   Which items to promote to Todo? (Pick 1–N, or "skip this epic", or "halt loop".)
   ```
   Options: each item as a multi-select option + "Skip — try next epic in Backlog" + "Halt — stop the loop here."

5. **Apply user picks.** For each picked item:
   ```bash
   scripts/gh-project.sh set-status <project-item-id> Todo
   ```
   Resolve the project-item-id from the Issue # via `scripts/gh-project.sh item-id <issue-num>`. Emit one MIRROR line per item to `traces/<run-id>/manager.log`:
   ```
   [ISO-ts] MIRROR action=set-status item=<issue-num> from=Backlog to=Todo
   ```

6. **Emit a PROMOTE_BACKLOG trace event** summarizing the operation:
   ```
   [ISO-ts] PROMOTE_BACKLOG epic="<epic_title>" items_picked=<n> items=<csv-of-issue-nums>
   ```

7. **Handle user picks of "Skip" or "Halt":**
   - **Skip:** recurse on the next epic in the `backlog-by-epic` array. If no more epics, emit the "Backlog also empty" path from step 3.
   - **Halt:** return control to `/build` operating loop step 15 (MILESTONE_GATE) with halt reason `user-halt-at-backlog-promote`.

8. **On successful pick(s):** return control to manager's operating loop step 2 (`scripts/gh-project.sh next-unblocked` will now return one of the promoted items as the next pick).

## Canonical references

- `scripts/gh-project.sh` § `cmd_backlog_by_epic` (added in A.28) — the read-only primitive.
- `scripts/gh-project.sh` § `cmd_set_status` — Backlog → Todo write.
- `scripts/gh-project.sh` § `cmd_item_id` — Issue # → project item id.
- `.claude/agents/manager.md` § Operating loop step 2 — the caller.
- `docs/AGENT_OPS.md § 6.3` — 4-status mapping + asymmetric Backlog convention.
- `docs/plans/archive/20-A.28-board-restructure.md` § B.6 — design rationale.
- `AGENTS.md § GitHub state — single writer rule` — all writes go through `scripts/gh-project.sh`.

## When NOT to invoke

- When Todo has work (verify with `next-unblocked` first). Pull from Todo via the normal `manager-pick-next` skill instead.
- Mid-PLAN_GATE / PR_REVIEW_GATE — wait for the user's gate response first; don't compound gates.
- When the user just said "Halt" or "Stop" at a MILESTONE_GATE — respect the halt; don't re-prompt for Backlog promotion.
- Compaction events — re-attaches automatically.

## Forbidden during invocation

- Do NOT auto-promote without AskUserQuestion. The user-consent gate is the entire point.
- Do NOT bypass `scripts/gh-project.sh` to call `gh api graphql` directly for the set-status write — single-writer rule.
- Do NOT promote items labelled `blocked`. The `backlog-by-epic` filter already excludes the `epic` label, but `blocked` items can be in Backlog; if surfaced, AskUserQuestion the user about the blocker before promoting.
- Do NOT hand-edit `.claude/github-issue-map.json`.
