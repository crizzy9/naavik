---
description: Run the 11-item plan quality-bar self-check before handing any plan back. Confirms frontmatter completeness, file-by-file detail, risk table presence, no ROADMAP duplication, no CLI/vault extension, and proper cross-refs to canonical design docs. Use at the end of every architect plan-authoring dispatch, before any "plan ready for review" hand-back. Triggers on phrases like "plan quality bar", "self-review the plan", "before I hand back", "ready to send to manager", "plan checklist", "is this plan ready".
---

# architect-plan-quality-bar

Architect's plans are the contract every downstream agent reads in full. A plan that's missing a risk row or buries an open question creates rework that costs more tokens than authoring the plan correctly the first time. This skill is the self-review checklist — run before every hand-back, no exceptions.

## When to invoke

- Architect just finished drafting a plan + thinks it's ready for manager review.
- Architect revised a plan after user feedback and is about to re-submit.
- Pre-archive sanity check on an executed plan (verify it shipped against a complete contract).

## What this skill does

Walk the 11-item checklist below. Tick each `[ ]` or fix the gap before handing back. Plans that fail any item are not ready.

```
[ ] Frontmatter complete:
    - Status: DRAFT (until user APPROVES)
    - Type: design | execution
    - Authored: YYYY-MM-DD
    - Last updated: YYYY-MM-DD (bump on every revision)
    - Depends on: <plan refs or "none">
    - GitHub: <#N> (added after `scripts/gh-project.sh create-issue` runs)

[ ] Goal + Why fit in ~10 lines total
    - A non-context-loaded human can approve from just these two sections.
    - "Why" links to the ROADMAP row that motivates the work.

[ ] Proposal is file-by-file
    - Engineer can read the plan and write the diff without re-researching.
    - For each file touched: full path, what changes, why, code snippet if non-obvious.
    - Per-section headers (## D.1, ## D.2, ...) make the build-sequence step indices precise.

[ ] At least one Risk row per non-trivial change
    - Risk + mitigation table per `architect.md` § Plan contract.
    - Columns: Risk | Likelihood | Impact | Mitigation.
    - Risks include known issues (e.g. SubagentStart unreliability via GitHub issue #27755 in plan 16).

[ ] Build sequence listed if multi-step
    - Numbered, ordered for reads-before-edits.
    - Each step names which file(s) it touches.

[ ] Open questions section is empty OR each box BLOCKS approval
    - "I'm confident" → leave the section empty.
    - Otherwise: each `[ ]` is a question the user must answer before engineer starts.
    - Never bury a question in the plan body — they go here.

[ ] Approval checklist
    - One `[ ]` per design decision the user must sign off on.
    - Not a duplicate of ROADMAP tracking (§ Single-doc-tracking forbids that).
    - Each box names the locked decision concretely (e.g. "Skill naming: <agent>-<verb> + naavik-<verb>").

[ ] No tracking-table duplication of ROADMAP
    - Plan-internal scope tables are fine + encouraged (describe HOW).
    - But the `[ ] / [~] / [x]` ledger of "is task X done?" lives only in ROADMAP.
    - § Single-doc-tracking is the canonical rule.

[ ] Does NOT extend the CLI or vault
    - No new `naavik` subcommands (Phase 2 task 2.11 sunset).
    - No new `src/services/vault.py` scopes or AES-GCM machinery (Phase 2 task 2.12 sunset).
    - New operator capability ships as Settings UI surface OR `.env.example` slot.
    - If reaching for one of these, invoke `architect-sunset-guard` first.

[ ] References the relevant canonical design docs as needed
    - `docs/ARCHITECTURE.md` for layer responsibilities.
    - `DESIGN.md` for UI tokens (if UI work).
    - `docs/design/SCREENS.md` for screen specs.
    - `docs/design/INTERACTIONS.md` for HTMX patterns.
    - `docs/RUNBOOK.md` for known failure modes the plan must avoid re-introducing.

[ ] Cites file paths with line numbers where possible
    - `src/config.py:42` style — engineer should be able to jump directly.
    - For modules with no existing relevant code, name the module ("new in src/services/").
```

## Worked example — applied to plan 16 (this plan)

| Item | Status | Notes |
|---|---|---|
| Frontmatter | ✅ | Status DRAFT, Type execution, Authored + Last updated 2026-05-16, Depends on none, GitHub #48 |
| Goal + Why ≤ 10 lines | ✅ | One paragraph each |
| File-by-file | ✅ | § D.1–D.10 specify every file |
| Risk rows | ✅ | 8 rows in § Risk + mitigation |
| Build sequence | ✅ | § H ships 11 numbered steps |
| Open questions empty? | ✅ | All 6 resolved in § C with option matrices |
| Approval checklist | ✅ | 11 items per § Approval checklist |
| No ROADMAP duplication | ✅ | Plan references ROADMAP rows but doesn't mirror the ledger |
| No CLI/vault extension | ✅ | Plan ships skills, hooks, agent prompt edits — no `naavik` subcommand, no vault scope |
| Cross-refs to canonical docs | ✅ | AGENTS.md, AGENT_OPS.md, RUNBOOK.md, CLAUDE.md, design system cited inline |
| File paths with line numbers | ⚠ | Mostly OK; some references like `.claude/agents/manager.md:4` are precise; a few `src/...` references could be tighter post-Phase-2 |

That row-by-row pattern is what the skill produces on demand. Surface any ⚠ or ❌ rows in the hand-back so the user sees the gaps you knowingly accepted.

## Canonical references

- `.claude/agents/architect.md` § "Plan quality bar (self-review before handing back)".
- `.claude/agents/architect.md` § "Plan contract (AGENTS.md § Workflow step 2)".
- `AGENTS.md` § Workflow steps 2 + 4 + 7.
- `AGENTS.md` § Single-doc-tracking principle.
- `AGENTS.md` § Key Conventions § CLI (sunset rules).
- `docs/plans/README.md` — plan-file conventions.

## When NOT to invoke

- Mid-research (you don't have a plan yet to review).
- For one-paragraph clarifications or trivial doc edits that aren't plans.
- Compaction events.

## Forbidden during invocation

- Do NOT hand back a plan with `Open questions` non-empty. Those BLOCK approval; the user expects them resolved or surfaced for decision.
- Do NOT skip the CLI/vault check. Plans that slip vault extensions past this filter get rejected at manager review (AGENTS.md § "If an architect plan slips a vault extension past this filter, reject the plan and ask the architect to redesign").
- Do NOT tick a box you didn't actually verify. The checklist is for honest self-review, not theater.
