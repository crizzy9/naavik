---
Status: APPROVED
Type: design
Authored: 2026-04-30
Last updated: 2026-04-30
Approved: 2026-04-30
Depends on: 02-mvp-master-plan
---

# 03 · Component catalog

## Goal

Define the complete Stage 2 component library — every Jinja partial under `src/ui/templates/components/` — as a contract that Stage 2 implementation (plan 08) builds against. Every component named in `docs/design/SCREENS.md` per-screen "Components" lines lands in this catalog with a specified API, visual treatment, variant set, and example usage. When approved, this plan's content graduates to `docs/design/COMPONENTS.md`.

## Context / why

`SCREENS.md` names ~70 components across 11 screens but doesn't define them — each per-screen "Components" line is a hint, not a contract. `DESIGN.md` defines a small set of foundational components (Button, Card, Input, Tag, Status Badge, Sidebar, Status dot, Score circle, KPI card, AI badge, Followup banner) but the rest are implicit. The bundle JSX files at `docs/design/mockups/naavik-handoff/project/screens/*.jsx` show the visual treatment but mix component logic with screen logic — Stage 2 needs an extracted, deduped contract.

This plan extracts that contract: one Jinja partial per component, named in snake_case, accepting variables via `{% include "components/x.html" with {...} %}` or as Jinja `{% macro %}`. The catalog covers the entire MVP. Stage 3 (page implementation, plan 09) composes screens entirely from these partials.

## Proposal

### A · Inventory

The component library lives at `src/ui/templates/components/`. Components are grouped by responsibility for ease of navigation; the directory itself is flat (no subdirectories) so includes stay simple.

| Group | Count | Components |
|---|---|---|
| Shell / global | 4 | `auth_shell.html`, `sidebar.html`, `version_pill.html`, `api_status_dot.html` |
| Atomics | 11 | `button.html`, `input.html`, `card.html`, `tag_chip.html`, `status_dot.html`, `status_badge.html`, `score_circle.html`, `ai_badge.html`, `kbd.html`, `field_label.html`, `info_card.html` |
| Forms / editor | 4 | `editor_field.html`, `editor_card.html`, `autosave_indicator.html`, `modal.html` |
| Onboarding | 5 | `step_indicator.html`, `dropzone.html`, `extraction_checklist.html`, `extracted_field_row.html`, `progress_bar.html` |
| Profile / Bullet | 10 | `profile_hero.html`, `contact_chip.html`, `experience_card.html`, `bullet_row.html`, `section_anchor_nav.html`, `application_readiness_card.html`, `application_qs_form.html`, `bullet_edit_row.html`, `tag_picker.html`, `selection_override.html` |
| Overview | 4 | `kpi_card.html`, `priority_action_row.html`, `email_signal_row.html`, `pipeline_strip.html` |
| Discover | 8 | `swipe_card.html`, `match_breakdown.html`, `discover_action_bar.html`, `swipe_action_btn.html`, `discover_stats_strip.html`, `up_next_card.html`, `tip_card.html`, `keyboard_hints.html` |
| Discover · review & apply | 6 | `apply_topbar.html`, `warm_intro_card.html`, `tailored_bullet_row.html`, `cover_letter_section.html`, `screener_question_card.html`, `apply_action_bar.html` |
| Tracking | 8 | `view_toggle.html`, `provider_chip.html`, `integration_card.html`, `followup_banner.html`, `stage_column.html`, `tracking_card.html`, `tracking_list_row.html`, `tracking_board.html` |
| Outreach | 6 | `outreach_app_row.html`, `recommended_move_card.html`, `outreach_message_card.html`, `contact_card.html`, `linkedin_status_chip.html`, `outreach_timeline.html` |
| Settings | 6 | `settings_tabs.html`, `provider_card.html`, `cost_card.html`, `deployment_status_card.html`, `log_tail.html`, `on_disk_card.html` |
| **Total** | **72** | |

Cover letter generation lives inside Discover · review & apply (no standalone screen) — its components (`cover_letter_section.html`, `screener_question_card.html`) are listed under that group. The standalone Cover Letter generator's earlier components (`letter_editor.html`, `tone_picker.html`, `output_mode_card.html`, `model_attribution_chip.html`) are NOT in the MVP and have been dropped.

### B · Per-component spec template

Every entry in `docs/design/COMPONENTS.md` follows this template:

```markdown
### `component_name`

**Purpose:** One-line description.

**Used by:** Screen 3 (Overview), Screen 9 (Tracking) — list the SCREENS.md sections that include it.

**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `label` | string | yes | — | The visible text |
| `tone` | enum (`brand` / `success` / `warning` / `danger`) | no | `brand` | Color treatment |
| `size` | enum (`sm` / `md` / `lg`) | no | `md` | Sizing |

**Visual spec:**
- Surface: `bg-slate-900 border border-slate-800 rounded-lg p-5`
- Token references: see `DESIGN.md` § Color Tokens > Brand. No token redefinition.

**Lucide icons:** `check`, `x` (stroke `1.5`).

**Variants / states:** `default`, `hover` (`hover:bg-slate-800 transition`), `disabled` (`opacity-50 cursor-not-allowed`), `loading` (replace icon with spinner).

**Example invocation:**
```jinja
{% include "components/component_name.html" with {
  "label": "Mark all done",
  "tone": "brand",
  "size": "sm"
} %}
```

**Mockup reference:** bundle `kit/Components.jsx` (atomics) or `screens/Discover.jsx` line ~280 (screen-specific).
```

For components used as macros instead of includes, swap the example for a macro call: `{{ tag_chip("ai-ml", selected=True) }}`.

### C · Macro vs include rule

| Use a macro | Use an include |
|---|---|
| Called many times in the same template (`tag_chip`, `score_circle`, `kbd`, `status_dot`) | Larger composite components used 1–2× per page (`profile_hero`, `swipe_card`, `apply_topbar`, `pipeline_strip`) |
| Takes few args (≤4) | Takes structured data (a job dict, a contact dict) |
| No nested HTMX hooks | Has its own `hx-*` attributes |

Macros live in `src/ui/templates/components/_macros.html` (single file imported per page: `{% from "components/_macros.html" import tag_chip, score_circle, status_dot, kbd %}`). Includes are one-file-per-component. Mixing both is fine.

### D · Cross-cutting decisions

1. **Tokens** — all components use Tailwind classes that map to `DESIGN.md` tokens. No arbitrary hex (`[#abc123]`) values. No inline `style="..."`. No custom CSS unless absolutely required for animation (and then in a single shared `_anim.css` imported from `base.html`).
2. **Icons** — Lucide only, stroke `1.5`. Use the `<i data-lucide="name"></i>` element pattern + Lucide's `createIcons()` after page load and after every HTMX swap (`htmx:afterSwap` listener in `base.html`).
3. **Naming** — `snake_case.html` matching the spec name in SCREENS.md exactly (e.g., `score_circle.html`, not `score-circle.html`). Macros: `snake_case` to match.
4. **No JS** in component files. Drag-drop (Sortable.js) attaches from the page template; SSE wiring is page-level.
5. **Accessibility baseline** — every interactive element gets a `focus:ring-2 focus:ring-indigo-500/40`. Icon-only buttons get `aria-label`. Modals use the native `<dialog>` element.
6. **Variants follow DESIGN.md naming** — `selected` / `unselected` for toggles, `default` / `hover` / `disabled` / `loading` for buttons, `info` / `success` / `warning` / `danger` for tints.

### E · Cross-reference strategy

The catalog cross-references in three directions:

1. **From COMPONENTS.md → SCREENS.md** — each component's "Used by" lists the screen sections that include it. Update SCREENS.md per-screen "Components" lines if a component name changes.
2. **From COMPONENTS.md → DESIGN.md** — every visual spec references DESIGN.md token names; no redefinition.
3. **From COMPONENTS.md → bundle JSX** — every component's "Mockup reference" field points to the bundle JSX file or location that shows the visual treatment. The bundle is gitignored locally; agents read it from `docs/design/mockups/naavik-handoff/project/...`.

The reverse cross-references (SCREENS.md per-screen "Components" lines naming partials, DESIGN.md mentioning a component generically, the bundle JSX containing a primitive) already exist and stay as-is.

### F · Sample component specs (validate the format)

Five fully-specified entries below to validate the spec template against representative components. The remaining 67 entries get drafted at graduation time using the same format.

#### `score_circle` (atomic, used 6× across screens)

**Purpose:** 0–100 number centered in a colored ring; no `%` mark, no "match" word.

**Used by:** Screen 3 (Overview email signal row), Screen 7 (Discover swipe card), Screen 8 (Discover · review & apply topbar), Screen 9 (Tracking card), Screen 10 (Outreach app row).

**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `score` | int (0–100) | yes | — | The score |
| `size` | enum (`compact` / `default` / `hero`) | no | `default` | 40 / 64 / 96 px |
| `ring_color_override` | string (Tailwind class) | no | (auto from score) | For light-on-color contexts |
| `text_color_override` | string | no | (slate-50) | For light-on-color contexts |

**Visual spec:** SVG circle with `stroke-dasharray` for the ring fraction. Ring color thresholded by score: `stroke-emerald-400` (≥80), `stroke-indigo-400` (60–79), `stroke-amber-400` (40–59), `stroke-rose-400` (<40). Background fill at `/10` opacity. Number `font-mono font-semibold tabular-nums`, size scales with container.

**Lucide icons:** none.

**Variants:** by `size`. The `ring_color_override` exists for the Discover swipe card where the score sits on a colored top band — see bundle `screens/Discover.jsx` lines 161–162.

**Example invocation (macro):** `{{ score_circle(score=86, size="default") }}`

**Mockup reference:** bundle `kit/Components.jsx` `ScoreDonut`; bundle `screens/Discover.jsx` § SwipeCard.

---

#### `tag_chip` (atomic, used everywhere)

**Purpose:** Render one tag from the 9-tag vocabulary as a chip. **No AI sparkle** on tag chips.

**Used by:** Screens 4, 5, 6, 7, 8, 9 — every screen that renders bullets, jobs, or matched skills.

**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `label` | string (one of the 9 tags) | yes | — | Tag value |
| `selected` | bool | no | `false` | If `true`, indigo-tinted background |

**Visual spec (default):** `inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-xs font-mono`. Selected: `bg-indigo-500/15 text-indigo-200 ring-1 ring-indigo-500/40`. Hover: `hover:bg-slate-700 transition`.

**Lucide icons:** none. Sparkle icons are forbidden on tag chips.

**Variants:** `default`, `selected`.

**Example invocation (macro):** `{{ tag_chip("ai-ml") }}` or `{{ tag_chip("backend", selected=True) }}`.

**Mockup reference:** bundle `kit/Components.jsx` `Tag`. Bundle `screens/BulletModal.jsx` shows the tag picker (Section 6).

---

#### `swipe_card` (composite, used 1× per Discover render + 4× as background-stack)

**Purpose:** Full job card on Discover — gradient top band + meta strip + signal chips + 2-column body (JD bullets + match breakdown).

**Used by:** Screen 7 (Discover).

**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `job` | dict | yes | — | Job record (see plan 05 for schema) |
| `dimmed` | bool | no | `false` | Background stack rendering |
| `swiping_dir` | enum (`left` / `right` / `up` / `null`) | no | `null` | Renders directional stamp overlay |

**Visual spec:** `w-[460px] bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl shadow-black/45 overflow-hidden`. Top band: `h-20` with `background: <job.logo_color>`. Body: composes `score_circle`, `tag_chip`, `match_breakdown`, `meta_item` (inline, not a partial — composite uses inline icon+text).

**Lucide icons:** `map-pin`, `dollar-sign`, `laptop`, `users-round`, `user-check` (per chip), `clock`.

**Variants:** `default`, `dimmed`, three swiping directions (each renders a `Stamp` overlay — see bundle `screens/Discover.jsx` line 260).

**Example invocation (include):**
```jinja
{% include "components/swipe_card.html" with {
  "job": top_job,
  "dimmed": false,
  "swiping_dir": none
} %}
```

**Mockup reference:** bundle `screens/Discover.jsx` § SwipeCard (lines 124–222).

---

#### `kpi_card` (composite, used 4× on Overview)

**Purpose:** Funnel KPI tile — uppercase mono label + large value + optional delta + sub-line.

**Used by:** Screen 3 (Overview KPI strip).

**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `label` | string | yes | — | Uppercase caption |
| `value` | string | yes | — | Big number / percentage |
| `delta` | string | no | `null` | `+2.1%` / `-0.4%` |
| `delta_trend` | enum (`up` / `down`) | no | (inferred from sign) | Color tone |
| `sub` | string | no | `null` | Smaller subtitle line |

**Visual spec:** `bg-slate-900 border border-slate-800 rounded-lg p-5` (per DESIGN.md). Label: `text-xs uppercase tracking-wide text-slate-400 font-mono`. Value: `font-sans text-3xl font-semibold tabular-nums text-slate-50`. Delta: `font-mono text-xs` colored emerald (up) or rose (down). Sub: `text-xs text-slate-400`.

**Variants:** with/without `delta`, with/without `sub`.

**Example invocation (include):**
```jinja
{% include "components/kpi_card.html" with {
  "label": "RESPONSE RATE · 90D",
  "value": "11.3%",
  "delta": "+2.1%",
  "delta_trend": "up",
  "sub": "3× market avg"
} %}
```

**Mockup reference:** bundle `screens/Overview.jsx` § Kpi (line 259).

---

#### `log_tail` (composite, used 1× on Settings · Deployment)

**Purpose:** Terminal-style streaming log display with macOS traffic-light dots header, STREAMING badge, Pause / Copy actions, scrollable mono body.

**Used by:** Screen 11 (Settings — Deployment tab).

**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `log_path` | string | yes | — | Header subtitle (e.g. `~/.naavik/logs · live tail`) |
| `lines` | list of `{timestamp, level, message}` | yes | — | Pre-rendered log lines |
| `streaming` | bool | no | `true` | Show pulsing STREAMING dot |

**Visual spec:** outer `bg-slate-900 border border-slate-800 rounded-xl overflow-hidden`. Header row: `px-4 py-3 border-b border-slate-800` with three colored dots (`#EF4444`, `#F59E0B`, `#10B981`), mono path label, STREAMING chip, Pause/Copy buttons. Body: `<pre>` element `bg-slate-950 px-4 py-3.5 max-h-[280px] overflow-auto font-mono text-xs leading-relaxed text-slate-300`. Each line composed via `log_line` macro: timestamp slate-400, level color-coded (info=cyan, warn=amber, error=rose), message slate-300.

**HTMX hook:** `hx-ext="sse" sse-connect="/_sse/logs" sse-swap="logline"` on the `<pre>` element appends new lines via OOB swaps. Pause toggles a class that disables auto-scroll.

**Lucide icons:** `pause`, `copy`.

**Variants:** `streaming` toggle.

**Example invocation (include):**
```jinja
{% include "components/log_tail.html" with {
  "log_path": "~/.naavik/logs · live tail",
  "lines": tail_lines,
  "streaming": true
} %}
```

**Mockup reference:** bundle `screens/Settings.jsx` § DeploymentTab (lines 211–264).

### G · Implementation order (informs plan 08, not this plan)

When plan 08 turns this catalog into actual files, build order is atomics → forms → onboarding → profile/bullet → overview → discover → discover-review → tracking → outreach → settings → shell. Atomics first means `tag_chip`, `score_circle`, `status_dot`, `button` etc. exist before any composite needs them. Plan 08 owns the actual sequencing detail.

### H · `base.html` refinements (declared here, executed in plan 08)

The existing `base.html` needs two changes for the catalog to function:

1. **Lucide CDN + post-swap reinit:** add `<script src="https://unpkg.com/lucide@latest"></script>`, call `lucide.createIcons()` on `DOMContentLoaded` and again on `htmx:afterSwap` so SVGs render after fragment swaps.
2. **Macros import:** load shared macros at the top of `base.html` so child templates inherit them: `{% from "components/_macros.html" import tag_chip, score_circle, status_dot, kbd %}`.

The sidebar component (`sidebar.html`) gets extracted from the existing inline sidebar in `base.html` so auth-shell pages (Login, Onboarding) can omit it.

## Decisions (locked in 2026-04-30, validated against frontend-community consensus)

1. **Macro file shape:** single `_macros.html` for high-frequency cross-cutting macros (`tag_chip`, `score_circle`, `status_dot`, `kbd`, plus the helpers below). Split per-domain only when a domain grows past ~10 macros. Matches Jinja2 official + Flask community pattern.
2. **`meta_item` and `chip` placement:** added as macros in `_macros.html` alongside the four named ones. Both are used inline 5+ times across components; macros are the right level.
3. **Animation CSS:** inline `<style>` block in `base.html` for the small set of keyframes (`nk-pulse`, `nk-shimmer`, `nk-blink`). Promote to `src/ui/static/anim.css` if the set ever grows past ~50 lines.
4. **`info_card` vs DaisyUI `alert`:** roll our own `info_card.html`. DaisyUI's `alert` defaults don't match the slate-on-tint aesthetic; overriding costs more than writing the partial fresh.
5. **Component fixture page:** yes. Plan 08 includes a `/_design/components` route that renders every component in every variant. Gated behind a `settings.debug` flag so it doesn't ship to production.

## Approval checklist

## Approval checklist

- [x] Inventory (§ A) — 72 components grouped into 11 categories. Names match SCREENS.md per-screen "Components" lines exactly. No missing, no extra.
- [x] Per-component spec template (§ B) — fields are right (Purpose, Used by, API, Visual spec, Icons, Variants, Example, Mockup ref).
- [x] Macro vs include rule (§ C) — small high-frequency components as macros, larger composites as includes; criteria correct.
- [x] Cross-cutting decisions (§ D) — tokens, icons, naming, no inline JS, accessibility baseline.
- [x] Cross-reference strategy (§ E) — three directions: SCREENS.md, DESIGN.md, bundle JSX. Bundle is gitignored so refs are conditional.
- [x] Sample specs (§ F) — five examples (`score_circle`, `tag_chip`, `swipe_card`, `kpi_card`, `log_tail`) — format works for the rest.
- [x] `base.html` refinements (§ H) — Lucide CDN + post-swap reinit + macros import declared here, executed in plan 08.
- [x] Open questions decided (see § Decisions above) — all 5 align with frontend-community consensus.
- [ ] **Next step (graduation):** this plan's content gets fleshed out per § F format for all 72 components, then graduates verbatim to `docs/design/COMPONENTS.md`. Plan is archived. Triggered after plans 04, 05, 06 are also approved (per plan 02 Wave 1).
