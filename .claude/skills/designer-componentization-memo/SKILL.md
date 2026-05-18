---
description: Generate the canonical handoff memo to engineer for a new screen — what components compose it (from the 85-catalog), what variants if any are new, what HTMX patterns wire it up, what data accessor it reads, where the build target lives. Use after producing a mockup, before handing off to engineer, when reviewing a screen-handoff PR for completeness. Triggers on phrases like "componentization memo", "handoff to engineer", "screen handoff", "mockup ready", "what components for", "build target", "engineer notes", "design handoff".
---

# designer-componentization-memo

Every mockup ships w/ one-page memo so engineer doesn't re-derive component composition from visual artifact. Memo names: components used (from catalog), new variants introduced (if any — propose `COMPONENTS.md` edit), HTMX patterns referenced, mockup paths, build target file path, route handler, data accessor. Contract between designer + engineer.

## When to invoke

- Designer produced mockup at `docs/design/mockups/{n}-{slug}-{desktop|mobile}.png`, handing off to engineer.
- Designer just composed new screen using `frontend-design` or `huashu-design` skill output.
- Reviewing screen-handoff PR — verify memo is complete + accurate.

## Memo shape

Render in exact shape (matches `.claude/agents/designer.md § Componentization notes`):

```
Screen: <screen name>

Composition:
  - <component-name> (qty) — purpose / variant args
  - <component-name> (qty) — purpose / variant args
  - ...

New variants introduced: <or "none">
  - <variant-name> on <component> — rationale, propose docs/design/COMPONENTS.md edit

HTMX patterns used: <autosave | modal | SSE | drag-drop | optimistic-rollback | keyboard-shortcuts>
  - Pattern → spec reference: docs/design/INTERACTIONS.md § <ref>

Mockup files:
  docs/design/mockups/{n}-{slug}-desktop.png
  docs/design/mockups/{n}-{slug}-mobile.png

Build target: src/ui/templates/pages/<slug>.html
Route handler: src/ui/routes/<area>.py:get_<slug>
Accessor:
  - memory mode: src/db/sample_data.py:<accessor>
  - db mode: src/services/<service>.py:<method>
```

## Section guidance

**Composition.** List every partial used, count, variant args. Order outermost to innermost (shell → page-level → row-level → atomic). Example for Tracking:
```
- sidebar (1) — nav variant=tracking
- view_toggle (1) — modes=[board, list], default=board
- followup_banner (1) — when_followups_pending=True
- tracking_board (1) — columns=[APPLIED, RECRUITER_SCREEN, ONSITE_LOOP, OFFER]
  - stage_column (4) — per status column
    - tracking_card (n) — per application
- tracking_card_skeleton (5) — used during loading state
- empty_state (1) — shown when no applications yet
```

**New variants introduced.** Couldn't satisfy design w/ existing variants → document addition:
```
- variant=urgent on followup_banner — adds rose-tinted border for >7-day stalled threads
  Rationale: existing amber tint is for "needs followup"; urgent is stronger signal
  Propose: COMPONENTS.md § Tracking row for followup_banner — add `urgent` to Variants column
```

**HTMX patterns.** Reference `docs/design/INTERACTIONS.md` by section. Common:
- `autosave` — inline field saves w/ 500ms debounce + `autosave_indicator`
- `modal` — `<dialog>` element w/ `hx-target="#modal-content"` + fade entry
- `SSE` — server-sent events for live updates (Tracking refreshes, scoring progress)
- `drag-drop` — Sortable.js + HTMX swap on drop (Tracking board reordering)
- `optimistic-rollback` — apply locally + revert on HTMX error
- `keyboard-shortcuts` — `keys.js` bindings, `kbd` macros in UI

**Mockup files.** Both desktop + mobile PNGs. Engineer compares to these during Manual QA Gate.

**Build target / Route handler / Accessor.** Tells engineer exactly where to write code. Accessor has two lines (memory mode + db mode) because Phase 1's NAAVIK_PERSISTENCE env var supports both.

## Worked example — Tracking screen

```
Screen: Tracking (`/tracking`)

Composition:
  - sidebar (1) — nav variant=tracking, badge=12 (open followups count)
  - view_toggle (1) — modes=[board, list], default=board
  - followup_banner (1) — when_followups_pending=True (shows top 4 stalled threads)
  - tracking_board (1) — columns=[APPLIED, RECRUITER_SCREEN, ONSITE_LOOP, OFFER]
    - stage_column (4) — one per status
      - tracking_card (n) — per application
  - tracking_card_skeleton (5) — loading state per stage_column
  - empty_state (1) — when no applications across all stages
  - log_tail (0, not on this screen)

New variants introduced: none

HTMX patterns used:
  - drag-drop — INTERACTIONS.md § Tracking board reordering (Sortable.js + hx-post on drop)
  - SSE — INTERACTIONS.md § Live status updates (auto-apply submit, recruiter email parse)
  - modal — INTERACTIONS.md § Application detail modal (click card → open modal)

Mockup files:
  docs/design/mockups/08-tracking-desktop.png
  docs/design/mockups/08-tracking-mobile.png

Build target: src/ui/templates/pages/tracking.html
Route handler: src/ui/routes/tracking.py:get_tracking_board
Accessor:
  - memory mode: src/db/sample_data.py:list_applications_for_user
  - db mode: src/services/application_service.py:list_applications_for_user
```

## Implementation handoff checklist (mental, for designer)

Before sending memo:

```
[ ] Mockup exists at docs/design/mockups/{n}-{slug}-{desktop|mobile}.png
[ ] All components from COMPONENTS.md (no inventions, or new variants documented)
[ ] HTMX patterns cross-referenced to INTERACTIONS.md sections
[ ] Accessibility checklist (docs/design/WORKFLOW.md § Accessibility) passes
[ ] Voice fits "developer tool, not SaaS" (no upsell, no flowery copy)
[ ] Mobile layout works at 375 × 812 (not just narrow-desktop)
[ ] Empty state defined (never blank tables)
[ ] Loading skeleton chosen (use existing *_skeleton component)
[ ] Build target + route handler + accessor explicitly named
```

## Canonical references

- `.claude/agents/designer.md` § "Componentization notes (handoff to engineer)" — canonical template.
- `.claude/agents/designer.md` § "Implementation handoff checklist".
- `docs/design/COMPONENTS.md` — catalog composition pulls from.
- `docs/design/SCREENS.md` — per-screen functional contract.
- `docs/design/INTERACTIONS.md` — HTMX patterns memo references.
- `docs/design/WORKFLOW.md` § Read order + § Accessibility checklist.

## When NOT to invoke

- Polish pass on existing screen (memo purpose is new-screen handoff; for polish, use critique skill).
- Pure component-extension change (no screen-level composition shift).
- Compaction events.

## Forbidden during invocation

- Do NOT skip "New variants introduced" section. Introduced none → explicitly say "none". Silence reads as "I didn't check catalog".
- Do NOT omit mobile path. Mobile layout is half the work; engineer needs both.
- Do NOT name non-existent partial in Composition list. If "new", lives in "New variants" section w/ proposed COMPONENTS.md edit.
- Do NOT skip accessor field. Engineer needs both memory + db paths because Phase 1's persistence mode is env-driven.
