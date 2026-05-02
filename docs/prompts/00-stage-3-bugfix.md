---

Status: ACTIVE
Type: implementation kickoff (plan + execute)
Authored: 2026-05-02

---

# Stage 3 bugfix + Discover-redesign — plan + implement

## Goal

Address a list of UI bugs and design-tension items the user surfaced after
plan 09 / Wave 3 shipped. **First** author an extensive plan as
`docs/plans/09a-stage-3-bugfix.md` per `AGENTS.md` § Workflow. Wait for user
approval. Then do your own extensive testing pass (manual browser + augment
existing pytest) to surface additional issues, fold them into the plan, and
implement after re-approval.

## Required reading (in order)

1. `AGENTS.md` § Workflow + § Tech Stack
2. `CLAUDE.md`
3. `ROADMAP.md` § Phase 1 (Wave 3 shipped 2026-05-02; Wave 4 unblocked but not started)
4. `docs/plans/POST_PHASE_1.md` § Immediate paper cuts (do NOT touch paper cut #3 — Playwright capture; that's its own track)  ← *renamed from `NEXT_STEPS.md` 2026-05-02*
5. `docs/plans/archive/09-stage-3-impl.md` (the plan that just shipped — ground truth on what exists)
6. `docs/design/SCREENS.md` (visual + functional contract — items 5, 7, 8 may require edits here)
7. `docs/design/DESIGN.md` (visual contract — colors, components)
8. `docs/design/INTERACTIONS.md` § F (keyboard + touch), § A (HTMX swap conventions)
9. `docs/design/COMPONENTS.md` § J (component-to-screen index — what's available)
10. `docs/design/DATA_MODEL.md` § C, § D (typed enums for application questions)

## User-reported issues

Triage each against the existing spec before fixing — some conflict with
SCREENS.md and need spec amendments first.

| #                            | Issue                                                                                 | Triage hint                                                                                                                                 |
| ---------------------------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| 1                            | No Lucide icons render anywhere (sidebar, resume, etc.)                               | base.js calls `lucide.createIcons()` — investigate CDN load, timing, CSP                                                                    |
| 2                            | Sidebar toggle works once then dies                                                   | Mobile drawer; check `data-sidebar-toggle` listener in base.js                                                                              |
| 3                            | Tinder-style swipe gestures don't work                                                | Not implemented — touch handlers missing entirely (only keyboard ships)                                                                     |
| 4                            | Application questions are freeform — should be typed dropdowns                        | DATA_MODEL.md already enums these. Swap `<input type="text">` → `<select>` mapped to enum values. Affects Profile                           |
| editor + sample_data display |
| 5                            | "Jobs" sidebar label vs "/discover" route — confusing                                 | SCREENS.md § Sidebar IA explicit; rename requires spec edit                                                                                 |
| 6                            | Discover action bar buttons too big                                                   | `swipe_action_btn.html` `flex-1` — probably needs `max-w-[120px]` per button at lg+                                                         |
| 7                            | Discover card too small to read JD inline                                             | Conflicts with SCREENS.md § 7 (560px swipe card by design). User wants larger card; may want hybrid: bigger card on desktop, swipe-stack on |
| mobile                       |
| 8                            | `/discover/:id` opens a separate full-page workspace; user expects in-place expansion | Conflicts with SCREENS.md § 8 (full page workspace by design). User may want slide-over or                                                  |
| in-place expand              |
| 9                            | Profile right-rail anchor nav doesn't scroll-spy or highlight on click                | `active_id` hardcoded to "experience"; no IntersectionObserver wired                                                                        |
| 10                           | Mobile broken on multiple pages                                                       | Vague — reproduce per-page, list each issue separately                                                                                      |

## Process

### Phase 1 — Plan authoring (do not implement yet)

1. Read everything in § Required reading.
2. Boot the dev server (`NAAVIK_DEBUG=1 uv run fastapi dev src/main.py` from
   `nix develop`) and reproduce each issue in a real browser. Confirm symptoms.
3. For items that conflict with SCREENS.md (5, 7, 8), surface the spec
   tension explicitly in the plan with **at least 2 design options each**
   plus the trade-offs. Do not assume the user wants the spec changed —
   they may want a different fix.
4. Do your own testing pass:
   - Click through every Phase 1 screen at desktop (1440×900) + mobile (375×812)
   - Test every interaction in INTERACTIONS.md § J per-screen recap
   - Run `uv run pytest tests/` and confirm all 225 still green
   - Look for: console errors, broken HTMX swaps, layout overflow, missing
     hover states, keyboard handlers that don't fire
   - Record every additional issue found
5. Author `docs/plans/09a-stage-3-bugfix.md` with:
   - Full required front-matter (`Status: PROPOSED`, `Type: bugfix + design`,
     `Authored`, `Last updated`, `Depends on`)
   - A Section per issue: Symptom · Reproduction · Root cause · Fix proposal
     (with options where applicable) · Spec impact · Test plan · Effort estimate
   - The new issues you discovered, same format
   - An ordered build sequence (simplest bugs first; spec-change items last)
   - An approval checklist at the bottom (one box per issue + one for the
     overall ordering)
   - Any deferred items go to a § Phase 1.x section (NOT into the active plan)
6. **STOP. Post the plan and wait for user approval.** Do not edit code.

### Phase 2 — Implement (after user approves the plan)

1. Implement issue-by-issue per the plan's build sequence.
2. After each fix:
   - Reproduce the original symptom in the browser; confirm it's gone
   - Run the targeted pytest cases + add new ones for the fix
   - Update SCREENS.md / DESIGN.md / INTERACTIONS.md if the fix touches a
     spec'd surface (per AGENTS.md § Workflow)
3. After all fixes:
   - Full `uv run pytest tests/` green
   - Full `ruff check .` + `ruff format --check .` clean
   - Manual smoke at desktop + mobile
   - Hand-back report (file list, test results, per-issue verification, any
     deviations from the plan)

## Forbidden patterns

- Don't gold-plate. If the user reported it, fix that. Don't refactor adjacent
  code unless it's blocking the fix.
- Don't change SCREENS.md without surfacing the change in the plan first.
- Don't skip the planning phase. The user explicitly wants plan → approve →
  implement, not implement → ask forgiveness.
- Don't touch plan 10 / Wave 4 territory (DB models, JWT auth, real LLM,
  Typst). Stay in plan-09 surface area.
- Don't break the 225 existing tests.

## Hand-back format

Plan-authoring phase: post the plan path + wait. Implementation phase:
file list, test results, per-issue verification (symptom gone? confirmed
in browser at both viewports?), and any deviations from the approved plan.
