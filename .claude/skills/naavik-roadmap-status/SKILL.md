---
description: Load the current phase status + active work + recently shipped from `docs/ROADMAP_OVERVIEW.md` (one-page executive digest) and dive into `ROADMAP.md § <phase>` for the per-task ledger. Use whenever any agent needs phase state, when the user asks "where are we", "what's the status of <phase>", "what's done", or before picking up scope. Shared cross-agent skill. Triggers on phrases like "roadmap status", "what phase", "where are we", "what's done", "what's shipped", "current phase", "next phase", "phase a", "phase 2", "what's open", "what's blocked".
---

# naavik-roadmap-status

`ROADMAP.md` is the authoritative 800-line ledger. `docs/ROADMAP_OVERVIEW.md` is the one-page executive digest agents load when they only need state, not detail. This skill is the cross-agent lookup — manager / architect / engineer / designer / hacker / devops all need to know phase state at some point. Read the overview first; drill into the full ROADMAP only when scope work requires.

## When to invoke

- Start of any dispatch where phase context matters (architect picking scope, manager standup, engineer cold-start).
- User asks "where are we" / "what's done" / "what's open" / "status of phase X".
- Pre-dispatch sanity check — "is this scope still queued for the current phase?".
- Before opening a plan that touches a specific phase's deliverable.

## What this skill does

### Step 1 — Read the executive digest

```
Read docs/ROADMAP_OVERVIEW.md
```

130 lines, full. Sections:

| Section | Content |
|---|---|
| § 1 | Where we are (one sentence) |
| § 2 | Phase status table (all 7 phases — 0/1/2/3/4/5/6 + A — with goal, plan, status) |
| § 3 | Active work (next 5 items, highest priority first) |
| § 4 | Recently shipped (last 5 plans) |
| § 5 | Plan-to-phase mapping |

This answers 95% of "what's the status" questions in ~3k tokens.

### Step 2 — Drill into ROADMAP.md for per-task detail

If you need per-task granularity (the `[ ] / [~] / [x]` ledger for a specific phase):

```bash
Grep "^### Phase " ROADMAP.md   # find phase headers
```

Then `Read ROADMAP.md` with offset around the matching line. Per phase you'll find:

- Phase header (`### Phase N: <name>`)
- `**Status:**` (current state)
- `**Plan:**` (link to the implementing plan(s))
- `**Goal:**` (what end-state defines "complete")
- Task table (the `[ ]` / `[~]` / `[x]` ledger — column shape: `# | Task | Status | Priority | Estimate | Notes`)

### Step 3 — Cross-reference the GitHub Project board (optional)

If you need to see the live mirror state (Project Status column, current assignments):

```bash
scripts/gh-project.sh milestone-status "<phase-name>"
```

This is read-only. Modifications go through `scripts/gh-project.sh` subcommands per the single-writer rule (`AGENTS.md § GitHub state — single writer rule`).

### Step 4 — Read the persistent issue-map for issue numbers

If you need the Issue # for a specific task ID:

```bash
jq -r --arg t "<task-id>" '.issues[$t]' .claude/github-issue-map.json
```

Example: `jq -r '.issues["PC.5"]' .claude/github-issue-map.json` → `7`.

## Current phase state (as of 2026-05-16)

(This is a snapshot; always trust the live docs over this card.)

- **Phase 1** ✅ Complete (2026-05-03): 11 MVP screens + backend substrate.
- **Phase A** 🟢 Active (2026-05-16): A.1–A.7 done; A.8 (first end-to-end `/build`) open; A.11 = plan 16 (this dispatch).
- **Phase 2** 🟡 Queued: scrapers + vault/CLI sunset. Pre-Phase-2 paper cuts (PC.5, PC.6) still open.
- **Phase 3** ⚪ Future: scoring + matching.
- **Phase 4** ⚪ Future: tracking + auto-apply polish.
- **Phase 5** ⚪ Future: email + outreach.
- **Phase 6** ⚪ Future: optimization + polish (observability, light mode, LaTeX).

## Sunset-track tasks (single-doc-tracking)

These show up in ROADMAP as work to DELETE, not extend:

- **Phase 2 task 2.11** — CLI sunset. Delete `src/cli/`.
- **Phase 2 task 2.12** — Vault deprecation. Delete `src/services/vault.py` + AES-GCM machinery + `~/.naavik/secrets.enc` + `~/.naavik/key.bin`. Sequence BEFORE 2.11.

Any work that proposes to extend either is rejected at architect/manager/hacker review. See `architect-sunset-guard` + `naavik-vault-sunset-guard` skills.

## Canonical references

- `docs/ROADMAP_OVERVIEW.md` — the one-page executive digest.
- `ROADMAP.md` — the full 800-line ledger (authoritative).
- `AGENTS.md` § Roadmap Maintenance Rules.
- `AGENTS.md` § Single-doc-tracking principle.
- `scripts/gh-project.sh milestone-status` — live Project mirror state.
- `.claude/github-issue-map.json` — persistent `{task_id → issue#}` cache.

## When NOT to invoke

- You already loaded ROADMAP_OVERVIEW or ROADMAP in this turn.
- You only need the task ID for a known scope (use grep + the issue-map directly).
- Compaction events.

## Forbidden during invocation

- Do NOT edit `ROADMAP.md` to match a stale Project board — ROADMAP wins always (codified in `AGENTS.md § Identity invariant` for manager).
- Do NOT create plan-internal tracking tables that duplicate ROADMAP's `[ ] / [~] / [x]` ledger. § Single-doc-tracking forbids this.
- Do NOT trust the snapshot in this skill body over the live `ROADMAP.md` — the snapshot drifts; the file is authoritative.
- Do NOT bypass `scripts/gh-project.sh` for board state lookups. The persistent map cache + the script subcommands are the canonical access path.
