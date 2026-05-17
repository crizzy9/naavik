---
description: Manager grooms the GitHub Project board — splits oversized epics, reorders priorities to match ROADMAP.md, closes stale items, surfaces newly emerged work.
argument-hint: <optional milestone name>
---

Milestone: $ARGUMENTS (default: current open milestone)

1. **Spawn `manager` via Task.** Manager:
   - Reads `ROADMAP.md` and identifies the current phase + open task ledger.
   - Queries the GitHub Project via `scripts/gh-project.sh milestone-status [name]`.
   - **Diffs the two states.** ROADMAP is authoritative (AGENTS.md § Single-doc-tracking). If Projects drifts, the Project board needs the fix — never the other direction.

2. **Manager proposes a grooming plan**, output as a structured report:
   - **Split list** — epics that are too large; proposed sub-issues with titles.
   - **Reorder list** — items whose priority on the board doesn't match ROADMAP's priority signal (CRITICAL / HIGH / MEDIUM / LOW).
   - **Close list** — items closed in ROADMAP (`[x]`) but still open on the board, OR items whose scope was absorbed elsewhere.
   - **New-items list** — items present in ROADMAP but missing from the board.
   - **Drift notes** — any item where ROADMAP and the board describe scope differently; flag for user attention.

3. **Ask the user for approval on the grooming plan** via AskUserQuestion (Approve all / Approve subset / Cancel + free-form notes). Manager does NOT mutate the board until the user replies.

4. **On approval**, manager executes the mutations:
   - Splits via `gh issue create` + `scripts/gh-project.sh add-item`.
   - Reorders via `gh api graphql` setting the Priority field.
   - Closes via `gh issue close --reason completed` + `scripts/gh-project.sh set-status <id> Done`.
   - Adds new items via `gh issue create` + `scripts/gh-project.sh add-item`.

5. **Manager reports** the final board state with a one-paragraph summary + any drift items still open (user must resolve).
