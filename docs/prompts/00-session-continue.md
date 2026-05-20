---
Status: ACTIVE
Type: session-handoff
Authored: 2026-05-19
Last updated: 2026-05-19 (post run `2026-05-19T15-42-42_833f4a`)
---

# Session-continue handoff — what next session needs to know

> **For Claude Code new session.** Read this before anything else (it complements `naavik-cold-start` skill). Captures state + active directives from the prior session that won't auto-load from canonical docs.

## State at handoff

**Date:** 2026-05-19 end-of-session.

**Most recent commits on `main`:**
- `ca61814` — `chore(agents): revert architect + engineer frontmatter to claude-opus-4-7[1m] default`
- `e4bc137` — `chore(manager): dynamic model selection at dispatch — close 0.7.0.23a as resolved-by-design`
- `afb0acb` — `docs(roadmap): mark 0.7.0.21c done + file GH issue #131`
- `70ddba7` — `docs(archive): plan 40 + plan 41 archived via naavik-ops plan archive (dogfood)`
- `473d9b6` — PR #127 omnibus squash (plans 40 + 41 PR-A + 0.7.0.21 follow-ups + ROADMAP slim + budget recalibration + cadence rule + 2-LOW reviewer-finding closure)

**Active milestone:** 0.2.0 — 13 of 15 shipped. Remaining:
- `0.2.0.04` (PC.6b onboarding bypass) — small, ~300K dispatch estimate. Independent. Ready to ship anytime.
- `0.2.0.14` (n8n migration) — moved to `## Backlog (unprioritized)` in ROADMAP. Closed-by-deferral; only purpose is historical-data import, which user can decide later if needed.

**Open follow-ups (filed this session, ROADMAP-tracked, none blocking 0.2.0):**

| Issue | Task | Priority | Notes |
|---|---|---|---|
| #103 | 0.2.0.07a slug-validate URL components in 6 scrapers | MEDIUM | Gates multi-tenant cloud flip |
| #104 | 0.2.0.07b expand lint guard for urllib siblings | LOW | |
| #107 | 0.2.0.08a `JobExtraction.tags` Literal constraint | LOW | |
| #110 | 0.2.0.10a `/api/v1/scheduler/*` endpoints | LOW | |
| #111 | 0.2.0.10b `SQLAlchemyJobStore` pickle alternative | LOW | |
| #113 | 0.2.0.11a doc graduation for plan 36 (JOB_UI.md + SCREENS.md + COMPONENTS.md) | MEDIUM | |
| #114 | 0.2.0.11b CSRF + IDOR on `/api/v1/discover/save/skip` | MEDIUM | |
| #115 | 0.2.0.11c `JobRead` projection on `GET /api/v1/jobs/{id}` | LOW | |
| #117 | 0.2.0.12a symmetric Telegram parse_mode fix on wave-6 path | LOW | |
| #129 | 0.7.0.23b `MODEL_PICK` trace event | LOW | |
| #130 | 0.7.0.23c `tests/test_workflow_invariants/` lint suite | MEDIUM | |

**Batching opportunity:** the LOW-priority cluster (104, 107, 110, 111, 115, 117, 129) is 7 small items — fits the new § Batching small tasks rule (5-10 items per housekeeping plan). Manager should consider a `docs/plans/<NN>-housekeeping-batch-2026-05-XX.md` for these when picked up.

## New operating directives that landed this session

Read these in `manager.md` (re-load is mandatory; section anchors below):

1. **§ Parallel reviewer invariant — non-negotiable.** PR_REVIEW_GATE reviewer dispatches MUST land in single assistant tool-use response with TWO `Agent` tool calls. (Codified PR #99.)
2. **§ Requirement-slot feedback** (post-0.7.0.24). Every new user directive (not status query, not gate response) gets `Slotted: <task-id> — <title> — <plan> — <PR>. Status: ...` as FIRST line of manager response.
3. **§ Doc-sizing matrix** (post-0.7.0.25). 3 tiers — Small (≤30 LOC mechanical, no plan, manager-direct) / Medium (30-200 LOC, short plan, architect short-brief) / Large (>200 LOC, full plan + PLAN_GATE + parallel reviewers).
4. **§ Batching small tasks** (post-0.7.0.25). 5-10 small items batched into one housekeeping plan; no option matrices, no PLAN_GATE pause for batched mechanical work.
5. **§ Dynamic resource allocation.** Manager handles small CONTRACT_CHANGE (≤100 LOC, ≤3 files) directly as staff-engineer. Dispatch architect/engineer when scope exceeds OR when design decisions / specialized cognition needed.
6. **§ Dynamic model selection at dispatch — no twin files.** 3 tiers: `sonnet` (tiny <20K), `opus` (small-med 20-60K, frontmatter `[1m]` dropped via override), no override (default `[1m]` for ≥60K). Codified post-0.7.0.23a closure.
7. **§ Dynamic reviewer selection.** Default both reviewers; hacker-only for security-only small fixes; architect-only for doc-only contract changes; **NO "skip both reviewers" lane**.
8. **§ Bookkeeping fold-in rule** (post-0.7.0.23). When related PR open, fold bookkeeping into PR branch (no `--amend`). Direct-push to main only when no related PR.
9. **§ Anti-patterns** — added "Round borderline scope UP (dispatch engineer), not DOWN (manager-direct)".

## Key memory decisions (auto-loaded via `.claude/naavik-ops memory list decisions`)

- `manager-as-staff-engineer-activation` (2026-05-19) — plan 41 PR-A activated immediately, not deferred.
- `budget-max-plan-baseline` (2026-05-19) — daily ceiling 30M, Max plan reality.
- `requirement-slot-feedback-cadence` (2026-05-19) — first-line ack mandatory.
- `dynamic-model-selection-via-task-override` (2026-05-19, supersedes `plan-41-model-threshold`) — no twin files; Task `model` enum override.

## Budget state

`.claude/budget.json`:
- `daily_token_ceiling`: 30_000_000 (Max plan baseline)
- Per-agent caps: architect 8M / engineer 10M / hacker 5M / manager 5M / devops 3M / designer 3M
- `plan`: "max" (user is on Anthropic Max plan; 34% weekly usage at last check)

`.claude/budget-ledger.json`:
- `total_today` ≈ 13M (approximate; reconciliation imperfect)
- Per-agent spend over per-agent caps (as expected for 10-PR session)
- Next session resets to fresh daily ceiling

## What to NOT redo

- ROADMAP_OVERVIEW.md is DELETED. Its content lives in `ROADMAP.md § Index + § Phase status + § Active conventions`. Don't recreate.
- The "Earlier line:" header chain in ROADMAP is gone. We evolve as we go; don't reintroduce.
- Twin agent files (`architect-1m.md` + `engineer-1m.md`) are NOT going to ship. Manager dispatches dynamically via Task `model` override.
- Plan 41 D.3 (twin files) is CLOSED as resolved-by-design. D.5 (MODEL_PICK trace) + D.7 (lint suite) remain open as `0.7.0.23b/c`.

## Next-recommended-actions (in order of best-value)

1. **`0.2.0.04`** (PC.6b onboarding bypass) — ~300K dispatch, closes the last open 0.2.0 row. Independent.
2. **Housekeeping batch plan** — 5-10 LOW follow-ups bundled per the new batching rule. Cleanest signal of the new doc-sizing tier in action.
3. **`0.2.0.11a`** (doc graduation for plan 36: JOB_UI.md + SCREENS.md + COMPONENTS.md) — MEDIUM; closes a gap from PR #112.
4. **`0.2.0.07a`** (slug-validate URL composition) — MEDIUM; gates multi-tenant cloud.

## Trace + run state

- This session's run-id: `2026-05-19T15-42-42_833f4a`
- Manifest: `traces/2026-05-19T15-42-42_833f4a/MANIFEST.json` (will be finalized at session close)
- Run-log entry already appended to `traces/runs.log`
- Engineer-deviations.log has 15+ entries (most already promoted to archived plans via dogfood `naavik-ops plan archive`)

## Reading order for fresh session

1. `Skill: naavik-cold-start` (mandatory first action).
2. This file (`docs/prompts/00-session-continue.md`).
3. `ROADMAP.md § Index` for current-state-at-a-glance.
4. `.claude/agents/manager.md` (re-read in full — many new sections this session).
5. Recent `docs/plans/archive/` entries (40 + 41 are the key new ones).

## Session-handoff invariant

This file is the canonical handoff. Update it ONLY at end-of-session. Mid-session edits = unreliable. If you (new session) need state at any point, re-load this file.
