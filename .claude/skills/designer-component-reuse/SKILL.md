---
description: Check `docs/design/COMPONENTS.md` (85-partial catalog) before designing a "new" component. The catalog is closed by default — extend via macro args, never invent. Use before any mockup that introduces a new visual unit, before implementing a partial in `src/ui/templates/components/`, when reviewing a UI diff for unnecessary new components. Triggers on phrases like "new component", "create a component", "i need a card for", "i need a button for", "should i invent", "component for", "85-partial", "components.md", "reuse component", "existing partial".
---

# designer-component-reuse

The component catalog at `docs/design/COMPONENTS.md` enumerates **85 partials across 12 groups** — every reusable UI unit Naavik composes from. The catalog is closed by default. New components require a documented extension to `COMPONENTS.md`; reinventing one is the most expensive design anti-pattern (drift accumulates, props drift, visual inconsistency follows). This skill is the lookup + the "did this already ship?" check.

## When to invoke

- Designer about to mock a screen that needs a new visual unit (card variant, banner, modal, input type).
- Engineer about to create a new `src/ui/templates/components/<name>.html`.
- Reviewer evaluating a UI PR for unnecessary new components.
- User asks "is there a component for X?" / "do we have a card that does Y?".

## What this skill does

1. **Identify the visual need.** What is this thing — a button, a card, a row, a banner, a chip, a modal, a skeleton? Use the catalog's 12-group taxonomy as a starting lens:

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

2. **Grep the catalog.**
   ```bash
   Grep "<noun>" docs/design/COMPONENTS.md
   ```
   Common nouns to try: `card`, `banner`, `chip`, `row`, `modal`, `input`, `badge`, `picker`, `column`.

3. **Read the component's spec.** Each entry follows the template at `docs/design/COMPONENTS.md § B`:
   - Purpose (one-line)
   - Used by (cross-ref to SCREENS.md sections)
   - API table (variable / type / required / default / description)
   - Visual spec (Tailwind classes anchored to DESIGN.md tokens)
   - Lucide icons used
   - Variants / states (`default`, `hover`, `disabled`, `loading`, plus context-specific)
   - Example invocation
   - Mockup reference (bundle JSX path)

4. **Decide:**

   **Option A — Reuse exactly.** Use the existing partial via `{% include "components/<name>.html" with {...} %}` or the macro pattern (for atomics like `tag_chip`, `score_circle`, `status_dot`, `kbd`, `meta_item`, `chip`, `log_line`). Done.

   **Option B — Extend via macro args.** The component already exists; you need a new variant. Add the variant to the partial via an additional macro arg + a Jinja conditional. Update `COMPONENTS.md` § the component's "Variants / states" row. This is the canonical path for "I need a card that's slightly different" — almost always the right answer.

   **Option C — Genuinely new component.** Only if the visual unit is not expressible as a variant of an existing partial. Process:
   1. Propose extension to `docs/design/COMPONENTS.md` (new row + spec table).
   2. Document under the right group (Atomics if reusable across screens, screen-specific group if not).
   3. Add the partial at `src/ui/templates/components/<name>.html`.
   4. Cross-ref the new entry from any SCREENS.md section that uses it.

   **Option D — Macro vs include?** Use the catalog's rule at `COMPONENTS.md § C`:
   - Macro: called many times in the same template, few args (≤4), no nested HTMX hooks.
   - Include: larger composite, structured data input (job dict, contact dict), has own `hx-*` attributes.

## Macros — already shipped

Quick reference for the macros that live in `src/ui/templates/components/_macros.html`:

```jinja
{% from "components/_macros.html" import tag_chip, score_circle, status_dot, kbd, meta_item, chip, log_line %}
```

- `tag_chip(name, selected=False)` — 9-tag vocabulary chip
- `score_circle(score, size='default')` — 0–100 ring (sizes: compact / default / hero)
- `status_dot(status)` — pipeline dot (color by status)
- `kbd(key)` — keyboard hint chip
- `meta_item(label, value)` — caption + value pair
- `chip(label, intent='neutral')` — generic chip with tint variants
- `log_line(line)` — mono log entry row

## Cross-cutting decisions to honor (from COMPONENTS.md § D)

1. **Tokens** — Tailwind classes that map to DESIGN.md tokens. No arbitrary hex.
2. **Icons** — Lucide only, stroke 1.5.
3. **Naming** — `snake_case.html` matching the spec name in SCREENS.md.
4. **No JS** in component files. Wire from `base.html` or page templates.
5. **Accessibility baseline** — `focus:ring-2 focus:ring-indigo-500/40` on every interactive element. `aria-label` on icon-only buttons. Native `<dialog>` for modals.
6. **Variants follow DESIGN.md naming** — `selected` / `unselected`, `default` / `hover` / `disabled` / `loading`, `info` / `success` / `warning` / `danger`.

## Canonical references

- `docs/design/COMPONENTS.md` — the canonical 85-partial catalog (graduated from plan 03).
- `DESIGN.md` (root) — visual contract the components consume.
- `docs/design/SCREENS.md` — which screens use which components.
- `docs/design/WORKFLOW.md` § Read order — COMPONENTS.md is step 4 in the UI read-order.
- `.claude/agents/designer.md` § "Component reuse (mandatory)".

## When NOT to invoke

- The component already loaded in your context this turn.
- Pure backend work, no template changes.
- Compaction events.

## Forbidden during invocation

- Do NOT add a new file at `src/ui/templates/components/<name>.html` without a corresponding `COMPONENTS.md` entry. The catalog is the contract; orphans rot.
- Do NOT fork a component to "tweak it slightly". Extend via macro args + document the variant. Forking is the most common drift source.
- Do NOT skip the catalog check because "this is obvious". The catalog has 85 entries; many things are already there.
- Do NOT add a font / icon set / styling library to satisfy a "new" component need. The stack is closed.
