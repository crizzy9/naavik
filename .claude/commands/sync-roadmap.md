---
description: Diff ROADMAP.md task state vs GitHub Project board. With --apply, pushes ROADMAP -> Project (ROADMAP wins per AGENTS.md § Single-doc-tracking).
argument-hint: [--apply]
---

Sync ROADMAP.md → GitHub Project board. Per AGENTS.md § Single-doc-tracking and `docs/AGENT_OPS.md` § 6.5.

**Pre-flight:** confirm `.claude/github-project.json` exists; if not, route to `/bootstrap`.

**Step 1 — Dry-run diff:**

```
scripts/gh-project.sh sync
```

This prints every row where ROADMAP and the Project disagree on Status or Priority. Categorize the diffs:
- **Status drifts** (Project says Todo but ROADMAP says `[~]`, etc.).
- **Priority drifts** (Project says HIGH but ROADMAP says CRITICAL, etc.).
- **Missing on board** (ROADMAP has a row with no matching `[<id>]` issue — needs `/plan` or bootstrap).

**Step 2 — Confirm with user** via AskUserQuestion if drifts > 0:
- Apply all (push ROADMAP wins).
- Apply Status drifts only.
- Apply Priority drifts only.
- Cancel (investigate manually).

If args contained `--apply`, skip step 2 and go straight to step 3.

**Step 3 — Apply:**

```
scripts/gh-project.sh sync --apply
```

**Step 4 — Wrap-up:** print the diff count + applied count + the canonical reminder ("ROADMAP is the single source of truth — if you wanted Project state to win, edit ROADMAP first, then sync").

**Note on direction:** sync is intentionally one-way. There is no `--reverse` flag and no automated "pull from Project." If the Project has fresh state that ROADMAP doesn't reflect, manual reconciliation is required: read both, decide which is correct, update ROADMAP, run `/sync-roadmap --apply`.

**Note on Backlog (post-A.28):** the board has 4 Status options — Todo / In Progress / Done / Backlog. Backlog is a board-only deferred state with no ROADMAP-checkbox equivalent. `/sync-roadmap --apply` preserves Backlog: ROADMAP `[ ]` maps to Todo OR Backlog (distinguished only by the Project Status column), so a Backlog item is NOT flagged as drift against ROADMAP `[ ]`. To promote a Backlog item into the current cycle, run `scripts/gh-project.sh set-status <item-id> Todo` explicitly — `/sync-roadmap` never auto-promotes. See `docs/AGENT_OPS.md § 6.3` for the asymmetric mapping.
