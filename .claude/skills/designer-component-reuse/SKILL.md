---
description: Check `docs/design/COMPONENTS.md` (85-partial catalog) before designing a "new" component. The catalog is closed by default — extend via macro args, never invent. Use before any mockup that introduces a new visual unit, before implementing a partial in `src/ui/templates/components/`, when reviewing a UI diff for unnecessary new components. Triggers on phrases like "new component", "create a component", "i need a card for", "i need a button for", "should i invent", "component for", "85-partial", "components.md", "reuse component", "existing partial".
---

# designer-component-reuse

Catalog at `docs/design/COMPONENTS.md` enumerates **85 partials across 12 groups** — every reusable UI unit. Catalog is closed by default. New components require documented `COMPONENTS.md` extension; reinventing is most expensive anti-pattern (drift accumulates, props drift, visual inconsistency follows). Lookup + "did this already ship?" check.

## When to invoke

- Designer about to mock screen needing new visual unit (card variant, banner, modal, input type).
- Engineer about to create new `src/ui/templates/components/<name>.html`.
- Reviewer evaluating UI PR for unnecessary new components.
- User asks "is there a component for X?" / "do we have a card that does Y?".

## Steps

1. **Identify visual need.** Button, card, row, banner, chip, modal, skeleton? Use 12-group taxonomy:

   | Group | Count | Examples |
   |---|---|---|
   | Shell / global | 5 | `auth_shell`, `sidebar`, `version_pill`, `api_status_dot`, `deployment_badge` |
   | Atomics | 15 | `button`, `input`, `card`, `tag_chip`, `status_dot`, `score_circle`, `ai_badge`, `kbd`, `info_card`, `spinner`, `toast`, `empty_state`, `avatar` |
   | Forms / editor | 5 | `editor_field`, `editor_card`, `autosave_indicator`, `modal`, `confirm_modal` |
   | Onboarding | 5 | `step_indicator`, `dropzone`, `extraction_checklist`, `extracted_field_row`, `progress_bar` |
   | Profile / Bullet | 11 | `profile_hero`, `experience_card`, `bullet_row`, `bullet_edit_row`, `tag_picker`, `selection_override`, `bullet_textarea`, etc. |
   | Overview | 4 | `kpi_card`, `priority_action_row`, `email_signal_row`, `pipeline_strip` |
   | Discover | 8 | `swipe_card`, `match_breakdown`, `discover_action_bar`, `up_next_card`, `tip_card`, `keyboard_hints` |
   | Discover · review & apply | 6 | `apply_topbar`, `warm_intro_card`, `tailored_bullet_row`, `cover_letter_section`, `screener_question_card`, `apply_action_bar` |
   | Tracking | 8 | `view_toggle`, `provider_chip`, `integration_card`, `followup_banner`, `stage_column`, `tracking_card`, `tracking_list_row`, `tracking_board` |
   | Outreach | 6 | `outreach_app_row`, `recommended_move_card`, `outreach_message_card`, `contact_card`, `linkedin_status_chip`, `outreach_timeline` |
   | Settings | 7 | `settings_tabs`, `provider_card`, `cost_card`, `deployment_status_card`, `log_tail`, `on_disk_card`, `connection_status_card` |
   | Skeletons | 5 | `swipe_card_skeleton`, `tracking_card_skeleton`, etc. |

2. **Grep catalog.**
   ```bash
   Grep "<noun>" docs/design/COMPONENTS.md
   ```
   Common nouns: `card`, `banner`, `chip`, `row`, `modal`, `input`, `badge`, `picker`, `column`.

3. **Read component spec.** Each entry follows template at `docs/design/COMPONENTS.md § B`:
   - Purpose (one-line)
   - Used by (cross-ref to SCREENS.md sections)
   - API table (variable / type / required / default / description)
   - Visual spec (Tailwind classes anchored to DESIGN.md tokens)
   - Lucide icons used
   - Variants / states (`default`, `hover`, `disabled`, `loading`, plus context-specific)
   - Example invocation
   - Mockup reference (bundle JSX path)

4. **Decide:**

   **Option A — Reuse exactly.** Use existing partial via `{% include "components/<name>.html" with {...} %}` or macro pattern (atomics like `tag_chip`, `score_circle`, `status_dot`, `kbd`, `meta_item`, `chip`, `log_line`). Done.

   **Option B — Extend via macro args.** Component exists; new variant needed. Add variant via additional macro arg + Jinja conditional. Update `COMPONENTS.md` § component's "Variants / states" row. Canonical path for "I need a card that's slightly different" — almost always right answer.

   **Option C — Genuinely new component.** Only if visual unit not expressible as variant of existing partial. Process:
   1. Propose extension to `docs/design/COMPONENTS.md` (new row + spec table).
   2. Document under right group (Atomics if reusable across screens, screen-specific group if not).
   3. Add partial at `src/ui/templates/components/<name>.html`.
   4. Cross-ref new entry from any SCREENS.md section using it.

   **Option D — Macro vs include?** Use catalog rule at `COMPONENTS.md § C`:
   - Macro: called many times in same template, few args (≤4), no nested HTMX hooks.
   - Include: larger composite, structured data input (job dict, contact dict), has own `hx-*` attributes.

## Macros — already shipped

Quick reference for macros in `src/ui/templates/components/_macros.html`:

```jinja
{% from "components/_macros.html" import tag_chip, score_circle, status_dot, kbd, meta_item, chip, log_line %}
```

- `tag_chip(name, selected=False)` — 9-tag vocabulary chip
- `score_circle(score, size='default')` — 0–100 ring (sizes: compact / default / hero)
- `status_dot(status)` — pipeline dot (color by status)
- `kbd(key)` — keyboard hint chip
- `meta_item(label, value)` — caption + value pair
- `chip(label, intent='neutral')` — generic chip w/ tint variants
- `log_line(line)` — mono log entry row

## Cross-cutting decisions (from COMPONENTS.md § D)

1. **Tokens** — Tailwind classes mapping to DESIGN.md tokens. No arbitrary hex.
2. **Icons** — Lucide only, stroke 1.5.
3. **Naming** — `snake_case.html` matching spec name in SCREENS.md.
4. **No JS** in component files. Wire from `base.html` or page templates.
5. **Accessibility baseline** — `focus:ring-2 focus:ring-indigo-500/40` on every interactive element. `aria-label` on icon-only buttons. Native `<dialog>` for modals.
6. **Variants follow DESIGN.md naming** — `selected` / `unselected`, `default` / `hover` / `disabled` / `loading`, `info` / `success` / `warning` / `danger`.

## Canonical references

- `docs/design/COMPONENTS.md` — canonical 85-partial catalog (graduated from plan 03).
- `DESIGN.md` (root) — visual contract components consume.
- `docs/design/SCREENS.md` — which screens use which components.
- `docs/design/WORKFLOW.md` § Read order — COMPONENTS.md is step 4 in UI read-order.
- `.claude/agents/designer.md` § "Component reuse (mandatory)".

## When NOT to invoke

- Component already loaded in your context this turn.
- Pure backend work, no template changes.
- Compaction events.

## Forbidden during invocation

- Do NOT add new file at `src/ui/templates/components/<name>.html` without corresponding `COMPONENTS.md` entry. Catalog is contract; orphans rot.
- Do NOT fork component to "tweak it slightly". Extend via macro args + document variant. Forking is most common drift source.
- Do NOT skip catalog check because "this is obvious". Catalog has 85 entries; many things already there.
- Do NOT add font / icon set / styling library to satisfy "new" component need. Stack is closed.
