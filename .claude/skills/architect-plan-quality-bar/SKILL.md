---
description: Run the 11-item plan quality-bar self-check before handing any plan back. Confirms frontmatter completeness, file-by-file detail, risk table presence, no ROADMAP duplication, no CLI/vault extension, and proper cross-refs to canonical design docs. Use at the end of every architect plan-authoring dispatch, before any "plan ready for review" hand-back. Triggers on phrases like "plan quality bar", "self-review the plan", "before I hand back", "ready to send to manager", "plan checklist", "is this plan ready".
---

# architect-plan-quality-bar

Plans = contract every downstream agent reads in full. Plan missing risk row or burying open question creates rework costing more than authoring correctly first time. Self-review checklist — run before every hand-back, no exceptions.

## When to invoke

- Architect finished drafting plan + thinks ready for manager review.
- Architect revised plan after user feedback + about to re-submit.
- Pre-archive sanity on executed plan (verify shipped against complete contract).

## Checklist (11 items)

Walk each. Tick `[ ]` or fix gap before handing back. Plans failing any item are not ready.

```
[ ] Frontmatter complete:
    - Status: DRAFT (until user APPROVES)
    - Type: design | execution
    - Authored: YYYY-MM-DD
    - Last updated: YYYY-MM-DD (bump on every revision)
    - Depends on: <plan refs or "none">
    - GitHub: <#N> (added after `.claude/naavik-ops gh create-issue` runs)

[ ] Goal + Why fit in ~10 lines total
    - Non-context-loaded human can approve from just these two.
    - "Why" links to ROADMAP row motivating the work.

[ ] Proposal is file-by-file
    - Engineer can read + write diff without re-researching.
    - Per file: full path, what changes, why, code snippet if non-obvious.
    - Per-section headers (## D.1, ## D.2, ...) make build-sequence step indices precise.

[ ] At least one Risk row per non-trivial change
    - Risk + mitigation table per `architect.md` § Plan contract.
    - Columns: Risk | Likelihood | Impact | Mitigation.
    - Risks include known issues (e.g. SubagentStart unreliability via GitHub issue #27755 in plan 16).

[ ] Build sequence listed if multi-step
    - Numbered, ordered for reads-before-edits.
    - Each step names which file(s) it touches.

[ ] Open questions empty OR each box BLOCKS approval
    - "I'm confident" → leave section empty.
    - Otherwise: each `[ ]` is question user must answer before engineer starts.
    - Never bury question in plan body — goes here.

[ ] Approval checklist
    - One `[ ]` per design decision user must sign off on.
    - Not duplicate of ROADMAP tracking (§ Single-doc-tracking forbids).
    - Each box names locked decision concretely (e.g. "Skill naming: <agent>-<verb> + naavik-<verb>").

[ ] No tracking-table duplication of ROADMAP
    - Plan-internal scope tables fine + encouraged (describe HOW).
    - But `[ ] / [~] / [x]` ledger of "is task X done?" lives only in ROADMAP.
    - § Single-doc-tracking is canonical rule.

[ ] Does NOT extend CLI or vault
    - No new `naavik` subcommands (Phase 2 task 2.11 sunset).
    - No new `src/services/vault.py` scopes or AES-GCM machinery (Phase 2 task 2.12 sunset).
    - New operator capability ships as Settings UI surface OR `.env.example` slot.
    - Reaching for one of these → invoke `architect-sunset-guard` first.

[ ] References relevant canonical design docs
    - `docs/ARCHITECTURE.md` for layer responsibilities.
    - `DESIGN.md` for UI tokens (UI work).
    - `docs/design/SCREENS.md` for screen specs.
    - `docs/design/INTERACTIONS.md` for HTMX patterns.
    - `docs/RUNBOOK.md` for known failure modes plan must avoid re-introducing.

[ ] Cites file paths w/ line numbers where possible
    - `src/config.py:42` style — engineer should jump directly.
    - For modules w/ no existing relevant code, name module ("new in src/services/").
```

## Worked example — applied to plan 16

| Item | Status | Notes |
|---|---|---|
| Frontmatter | PASS | Status DRAFT, Type execution, Authored + Last updated 2026-05-16, Depends on none, GitHub #48 |
| Goal + Why ≤ 10 lines | PASS | One paragraph each |
| File-by-file | PASS | § D.1–D.10 specify every file |
| Risk rows | PASS | 8 rows in § Risk + mitigation |
| Build sequence | PASS | § H ships 11 numbered steps |
| Open questions empty? | PASS | All 6 resolved in § C with option matrices |
| Approval checklist | PASS | 11 items per § Approval checklist |
| No ROADMAP duplication | PASS | Plan references ROADMAP rows but doesn't mirror ledger |
| No CLI/vault extension | PASS | Plan ships skills, hooks, agent prompt edits — no `naavik` subcommand, no vault scope |
| Cross-refs to canonical docs | PASS | AGENTS.md, AGENT_OPS.md, RUNBOOK.md, CLAUDE.md, design system cited inline |
| File paths w/ line numbers | WARN | Mostly OK; some refs like `.claude/agents/manager.md:4` are precise; few `src/...` refs could be tighter post-Phase-2 |

Row-by-row pattern = what skill produces on demand. Surface any WARN or FAIL rows in hand-back so user sees gaps you knowingly accepted.

## Canonical references

- `.claude/agents/architect.md` § "Plan quality bar (self-review before handing back)".
- `.claude/agents/architect.md` § "Plan contract (AGENTS.md § Workflow step 2)".
- `AGENTS.md` § Workflow steps 2 + 4 + 7.
- `AGENTS.md` § Single-doc-tracking principle.
- `AGENTS.md` § Key Conventions § CLI (sunset rules).
- `docs/plans/README.md` — plan-file conventions.

## When NOT to invoke

- Mid-research (no plan yet to review).
- One-paragraph clarifications or trivial doc edits that aren't plans.
- Compaction events.

## Forbidden during invocation

- Do NOT hand back plan w/ `Open questions` non-empty. Those BLOCK approval; user expects them resolved or surfaced for decision.
- Do NOT skip CLI/vault check. Plans slipping vault extensions past this filter get rejected at manager review (AGENTS.md § "If architect plan slips vault extension past this filter, reject the plan and ask architect to redesign").
- Do NOT tick box you didn't actually verify. Checklist is for honest self-review, not theater.
