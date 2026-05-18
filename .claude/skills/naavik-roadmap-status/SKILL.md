---
description: Load the current phase status + active work + recently shipped from `docs/ROADMAP_OVERVIEW.md` (one-page executive digest) and dive into `ROADMAP.md § <phase>` for the per-task ledger. Use whenever any agent needs phase state, when the user asks "where are we", "what's the status of <phase>", "what's done", or before picking up scope. Shared cross-agent skill. Triggers on phrases like "roadmap status", "what phase", "where are we", "what's done", "what's shipped", "current phase", "next phase", "phase a", "phase 2", "what's open", "what's blocked".
---

# naavik-roadmap-status

`ROADMAP.md` = authoritative 800-line ledger. `docs/ROADMAP_OVERVIEW.md` = one-page executive digest. Cross-agent lookup — every role needs phase state. Read overview first; drill ROADMAP only when scope work requires.

## When to invoke

- Start of any dispatch where phase context matters (architect scope, manager standup, engineer cold-start).
- User: "where are we" / "what's done" / "what's open" / "status of phase X".
- Pre-dispatch sanity: "is this scope still queued for current phase?".
- Before opening plan touching specific phase deliverable.

## Steps

### 1 — Read executive digest

```
Read docs/ROADMAP_OVERVIEW.md
```

130 lines, full. Sections:

| § | Content |
|---|---|
| 1 | Where we are (one sentence) |
| 2 | Phase status table (7 phases: 0/1/2/3/4/5/6 + A — goal, plan, status) |
| 3 | Active work (next 5 by priority) |
| 4 | Recently shipped (last 5 plans) |
| 5 | Plan-to-phase mapping |

Answers 95% of status questions in ~3k tokens.

### 2 — Drill `ROADMAP.md` for per-task detail

For `[ ] / [~] / [x]` ledger of specific phase:

```bash
Grep "^### Phase " ROADMAP.md
```

Then `Read ROADMAP.md` with offset around matching line. Per phase:

- Phase header (`### Phase N: <name>`)
- `**Status:**`
- `**Plan:**` (links)
- `**Goal:**`
- Task table (columns: `# | Task | Status | Priority | Estimate | Notes`)

### 3 — Cross-reference live Project board (optional)

For live mirror state (Project Status column, assignments):

```bash
.claude/naavik-ops gh milestone-status "<phase-name>"
```

Read-only. Mods via `.claude/naavik-ops gh` (subprocess-wraps `scripts/gh-project.sh` during A.29) per single-writer rule (`AGENTS.md § GitHub state — single writer rule`).

### 4 — Read issue-map for Issue numbers

For Issue # of specific task ID:

```bash
jq -r --arg t "<task-id>" '.issues[$t]' .claude/github-issue-map.json
```

Example: `jq -r '.issues["PC.5"]' .claude/github-issue-map.json` → `7`.

## Current phase snapshot (as of 2026-05-16)

(Snapshot — always trust live docs over this card.)

- **Phase 1** ✅ Complete (2026-05-03): 11 MVP screens + backend substrate.
- **Phase A** 🟢 Active (2026-05-16): A.1–A.7 done; A.8 (first end-to-end `/build`) open; A.11 = plan 16.
- **Phase 2** 🟡 Queued: scrapers + vault/CLI sunset. Pre-Phase-2 paper cuts (PC.5, PC.6) still open.
- **Phase 3** ⚪ Future: scoring + matching.
- **Phase 4** ⚪ Future: tracking + auto-apply polish.
- **Phase 5** ⚪ Future: email + outreach.
- **Phase 6** ⚪ Future: observability, light mode, LaTeX.

## Sunset-track tasks (single-doc-tracking)

Work to DELETE, not extend:

- **Phase 2 task 2.11** — CLI sunset. Delete `src/cli/`.
- **Phase 2 task 2.12** — Vault deprecation. Delete `src/services/vault.py` + AES-GCM + `~/.naavik/secrets.enc` + `~/.naavik/key.bin`. Sequence BEFORE 2.11.

Proposals to extend either rejected at architect/manager/hacker review. See `architect-sunset-guard` + `naavik-vault-sunset-guard` skills.

## Canonical references

- `docs/ROADMAP_OVERVIEW.md` — executive digest.
- `ROADMAP.md` — 800-line authoritative ledger.
- `AGENTS.md` § Roadmap Maintenance Rules.
- `AGENTS.md` § Single-doc-tracking principle.
- `.claude/naavik-ops gh milestone-status` — live Project mirror.
- `.claude/github-issue-map.json` — `{task_id → issue#}` cache.

## When NOT to invoke

- Already loaded ROADMAP_OVERVIEW or ROADMAP this turn.
- Only need task ID for known scope (use grep + issue-map directly).
- Compaction events.

## Forbidden during invocation

- Do NOT edit `ROADMAP.md` to match stale Project board — ROADMAP wins always (`AGENTS.md § Identity invariant` for manager).
- Do NOT create plan-internal tracking tables duplicating ROADMAP's `[ ] / [~] / [x]` ledger. § Single-doc-tracking forbids.
- Do NOT trust this skill's snapshot over live `ROADMAP.md` — snapshot drifts; file is authoritative.
- Do NOT bypass `.claude/naavik-ops gh` for board state lookups.
