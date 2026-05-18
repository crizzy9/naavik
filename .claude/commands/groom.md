---
description: Manager grooms the GitHub Project board — splits oversized epics, reorders priorities to match ROADMAP.md, closes stale items, surfaces newly emerged work.
argument-hint: <optional milestone name>
---

Milestone: $ARGUMENTS (default: current open milestone)

1. **Spawn `manager` via Task.** Manager:
   - Reads `ROADMAP.md` + identifies current phase + open task ledger.
   - Queries GitHub Project via `.claude/naavik-ops gh milestone-status [name]`.
   - **Diffs two states.** ROADMAP is authoritative (AGENTS.md § Single-doc-tracking). Projects drifts → Project board needs fix — never other direction.

2. **Manager proposes grooming plan**, output as structured report:
   - **Split list** — epics too large; proposed sub-issues w/ titles.
   - **Reorder list** — items whose priority on board doesn't match ROADMAP's priority signal (CRITICAL / HIGH / MEDIUM / LOW).
   - **Close list** — items closed in ROADMAP (`[x]`) but still open on board, OR items whose scope was absorbed elsewhere.
   - **New-items list** — items present in ROADMAP but missing from board.
   - **Drift notes** — any item where ROADMAP + board describe scope differently; flag for user attention.

3. **Ask user for approval on grooming plan** via AskUserQuestion (Approve all / Approve subset / Cancel + free-form notes). Manager does NOT mutate board until user replies.

4. **On approval**, manager executes mutations:
   - Splits via `gh issue create` + `.claude/naavik-ops gh add-item`.
   - Reorders via `gh api graphql` setting Priority field.
   - Closes via `gh issue close --reason completed` + `.claude/naavik-ops gh set-status <id> Done`.
   - Adds new items via `gh issue create` + `.claude/naavik-ops gh add-item`.

5. **Manager reports** final board state w/ one-paragraph summary + any drift items still open (user must resolve).

**Backlog awareness (post-A.28):** board has 4 Status options — Todo / In Progress / Done / Backlog. While grooming, also surface:
   - **Todo → Backlog candidates:** items in Todo for current milestone looking deferred (LOW priority, no plan, not on user's current Tier 1/Tier 2 list). Propose moving them to Backlog via `.claude/naavik-ops gh set-status <id> Backlog`.
   - **Backlog → Todo candidates:** items in Backlog whose parent epic is highest-priority Backlog epic AND user explicitly named in current scope. Defer actual move to `manager-backlog-promote` skill — `/groom` flags candidates but user-consent gate is promote skill's surface.
   - **Empty-epic Backlogs:** Project epics w/ zero open Backlog AND zero open Todo items — surface as candidates for closure.
