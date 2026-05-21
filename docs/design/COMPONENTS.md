# Naavik Component Catalog

> **Last updated:** 2026-05-21 (plan 72 / `0.3.2.01` — registers 1 net-new Discover-group partial [`score_card.html`] as the Variant B linear-bento composite wrapping `score_circle` + `match_breakdown` + strengths/gaps/visa_note overlay. Also extends `tailored_bullet_row.html` API with an optional `rationale` arg for the Variant A inline-ledger bullet-selection preview (additive; backward compatible). Net total: 92 partials. Canonical contract: `docs/design/MOCKUP_HANDOFF-0.3.2.md` § Surface 1 + § Surface 2.)
> Earlier line: 2026-05-20 (plan 58 / `0.2.7.06` — registers 2 net-new Settings-group partials [`_rate_limit_editor.html` + `_keywords_editor.html`] for the Settings · Sources writable-popover editors. Net total: 91 partials. Canonical contract: `docs/design/SOURCES_UI.md` § H.)
> Earlier line: 2026-05-20 (plan 49 / `0.2.0.16` — registers 1 net-new Settings-group partial `_source_row.html` for the Settings · Sources sub-tab rewrite. Net total: 89 partials. Canonical contract: `docs/design/SOURCES_UI.md`.)
> Earlier line: 2026-05-20 (plan 36 / `0.2.0.11a` — registers 3 net-new Discover-group partials [`filter_toolbar.html`, `_filter_hidden_inputs.html`, `job_topbar.html`] + 1 new `filter_chip` macro. Net total: 88 partials + macro count grows by 1 in § I. Canonical Job-UI contract: `docs/design/JOB_UI.md`.)
> Earlier line: 2026-04-30
> **Status:** Canonical — graduated from `docs/plans/03-component-catalog.md` (archived).
> **Scope:** Every Jinja partial under `src/ui/templates/components/`. The contract Stage 2 implementation builds against; Stage 3 page templates compose entirely from these partials.
> **Companion docs:** `DESIGN.md` (visual contract — tokens, typography, motion), `docs/design/SCREENS.md` (per-screen functional spec), `docs/design/INTERACTIONS.md` (HTMX patterns), `docs/design/BACKEND.md` (route table consuming components), `docs/design/JOB_UI.md` (Job-UI surface contract — composes the filter toolbar + Job detail page).

---

## A · Inventory

The library lives at `src/ui/templates/components/`. Components grouped by responsibility for navigation; the directory itself is flat (no subdirectories) so includes stay simple. **Total: 92 components** across 12 groups.

| Group | Count | Components |
|---|---|---|
| Shell / global | 5 | `auth_shell.html`, `sidebar.html`, `version_pill.html`, `api_status_dot.html`, `deployment_badge.html` |
| Atomics | 15 | `button.html`, `input.html`, `card.html`, `tag_chip.html`, `status_dot.html`, `status_badge.html`, `score_circle.html`, `ai_badge.html`, `kbd.html`, `field_label.html`, `info_card.html`, `spinner.html`, `toast.html`, `empty_state.html`, `avatar.html` |
| Forms / editor | 5 | `editor_field.html`, `editor_card.html`, `autosave_indicator.html`, `modal.html`, `confirm_modal.html` |
| Onboarding | 5 | `step_indicator.html`, `dropzone.html`, `extraction_checklist.html`, `extracted_field_row.html`, `progress_bar.html` |
| Profile / Bullet | 11 | `profile_hero.html`, `contact_chip.html`, `experience_card.html`, `bullet_row.html`, `section_anchor_nav.html`, `application_readiness_card.html`, `application_qs_form.html`, `bullet_edit_row.html`, `tag_picker.html`, `selection_override.html`, `bullet_textarea.html` |
| Overview | 4 | `kpi_card.html`, `priority_action_row.html`, `email_signal_row.html`, `pipeline_strip.html` |
| Discover | 12 | `swipe_card.html`, `match_breakdown.html`, `discover_action_bar.html`, `swipe_action_btn.html`, `discover_stats_strip.html`, `up_next_card.html`, `tip_card.html`, `keyboard_hints.html`, `filter_toolbar.html` (plan 36), `_filter_hidden_inputs.html` (plan 36), `job_topbar.html` (plan 36), `score_card.html` (plan 72) |
| Discover · review & apply | 6 | `apply_topbar.html`, `warm_intro_card.html`, `tailored_bullet_row.html`, `cover_letter_section.html`, `screener_question_card.html`, `apply_action_bar.html` |
| Tracking | 8 | `view_toggle.html`, `provider_chip.html`, `integration_card.html`, `followup_banner.html`, `stage_column.html`, `tracking_card.html`, `tracking_list_row.html`, `tracking_board.html` |
| Outreach | 6 | `outreach_app_row.html`, `recommended_move_card.html`, `outreach_message_card.html`, `contact_card.html`, `linkedin_status_chip.html`, `outreach_timeline.html` |
| Settings | 10 | `settings_tabs.html`, `provider_card.html`, `cost_card.html`, `deployment_status_card.html`, `log_tail.html`, `on_disk_card.html`, `connection_status_card.html`, `_source_row.html` (plan 49), `_rate_limit_editor.html` (plan 58), `_keywords_editor.html` (plan 58) |
| Skeletons | 5 | `swipe_card_skeleton.html`, `tracking_card_skeleton.html`, `priority_action_row_skeleton.html`, `email_signal_row_skeleton.html`, `bullet_edit_row_skeleton.html` |
| **Total** | **92** | |

Cover letter generation lives inside Discover · review & apply (no standalone screen) — its components (`cover_letter_section.html`, `screener_question_card.html`) are listed under that group. The standalone Cover Letter generator's earlier components (`letter_editor.html`, `tone_picker.html`, `output_mode_card.html`, `model_attribution_chip.html`) are NOT in MVP and dropped.

Funnel / BarChart / LineChart components from the bundle's `Overview.jsx` are leftovers from when Analytics was on Overview — **not in MVP**, deferred to Phase 6.

---

## B · Per-component spec template

Every entry below follows this template:

```markdown
### `component_name`

**Purpose:** One-line description.
**Used by:** Screen 3 (Overview), Screen 9 (Tracking) — list the SCREENS.md sections that include it.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `label` | string | yes | — | The visible text |

**Visual spec:** classes anchored to DESIGN.md token names; no token redefinition.
**Lucide icons:** `check`, `x` (stroke `1.5`).
**Variants / states:** `default`, `hover`, `disabled`, `loading`.
**Example invocation:**
```jinja
{% include "components/component_name.html" with {...} %}
```
**Mockup reference:** bundle file + line.
```

For macros, the example uses macro-call syntax: `{{ tag_chip("ai-ml", selected=True) }}`.

---

## C · Macro vs include rule

| Use a macro | Use an include |
|---|---|
| Called many times in the same template (`tag_chip`, `score_circle`, `kbd`, `status_dot`, `meta_item`, `chip`, `log_line`) | Larger composite components used 1–2× per page (`profile_hero`, `swipe_card`, `apply_topbar`, `pipeline_strip`) |
| Takes few args (≤4) | Takes structured data (a job dict, a contact dict) |
| No nested HTMX hooks | Has its own `hx-*` attributes |

Macros live in `src/ui/templates/components/_macros.html` (single file imported per page: `{% from "components/_macros.html" import tag_chip, score_circle, status_dot, kbd, meta_item, chip, log_line %}`). Includes are one-file-per-component. Mixing both is fine.

---

## D · Cross-cutting decisions

1. **Tokens** — all components use Tailwind classes that map to DESIGN.md tokens. No arbitrary hex (`[#abc123]`) values. No inline `style="..."`. No custom CSS unless absolutely required for animation (and then in inline `<style>` in `base.html` per § F.2).
2. **Icons** — Lucide only, stroke `1.5`. Use `<i data-lucide="name"></i>` element pattern + `lucide.createIcons()` post-`htmx:afterSwap` listener in `base.html`.
3. **Naming** — `snake_case.html` matching the spec name in SCREENS.md exactly. Macros: `snake_case` to match.
4. **No JS** in component files. Drag-drop (Sortable.js), SSE wiring, key handlers — all attach from `base.html` or page templates per INTERACTIONS.md.
5. **Accessibility baseline** — every interactive element gets `focus:ring-2 focus:ring-indigo-500/40`. Icon-only buttons get `aria-label`. Modals use the native `<dialog>` element.
6. **Variants follow DESIGN.md naming** — `selected` / `unselected` for toggles, `default` / `hover` / `disabled` / `loading` for buttons, `info` / `success` / `warning` / `danger` for tints.
7. **Spec discrepancies resolved 2026-04-30:**
   - Tracking sidebar icon: **`inbox`** (per SCREENS.md), not `kanban-square` (bundle was wrong).
   - Sidebar width: **256px** desktop, **`w-16`** collapsed (per DESIGN.md), not 240px (bundle was wrong).
   - Charts on Overview: **none in MVP** (per SCREENS.md). Funnel / BarChart / LineChart deferred to Phase 6.

---

## E · Cross-reference strategy

The catalog cross-references in three directions:

1. **From COMPONENTS.md → SCREENS.md** — each component's "Used by" lists the screen sections that include it.
2. **From COMPONENTS.md → DESIGN.md** — every visual spec references DESIGN.md token names; no redefinition.
3. **From COMPONENTS.md → bundle JSX** — every component's "Mockup reference" field points to the bundle JSX file. The bundle is gitignored locally; agents read it from `docs/design/mockups/naavik-handoff/project/...`.

---

## F · `base.html` refinements

The existing `base.html` needs these changes for the catalog to function. All declared here, executed in plan 08 (Stage 2 implementation).

### F.1 Layout structure

```html
<!doctype html>
<html lang="en" data-theme="naavik">
<head>
  <link rel="stylesheet" href="/static/styles.css">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <meta name="csrf-token" content="{{ csrf_token }}">
</head>
<body
  hx-boost="true"
  hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'
  hx-ext="sse,response-targets"
  data-template="{{ active_template_path }}">

  {% block body %}
    <div class="flex min-h-screen">
      {% include "components/sidebar.html" %}
      <main class="flex-1">
        {% block main %}{% endblock %}
      </main>
    </div>
  {% endblock %}

  <!-- Persistent IDs for cross-cutting concerns (per INTERACTIONS.md § A.4) -->
  <div id="modal-region"></div>
  <div id="toast-region"></div>
  <div id="sidebar-badge-jobs" hx-swap-oob="true"></div>
  <div id="sidebar-badge-tracking" hx-swap-oob="true"></div>

  <script src="https://unpkg.com/lucide@latest"></script>
  <script src="https://unpkg.com/[email protected]/htmx.min.js"></script>
  <script src="https://unpkg.com/htmx.org/dist/ext/sse.js"></script>
  <script src="https://unpkg.com/htmx.org/dist/ext/response-targets.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/sortablejs@latest/Sortable.min.js"></script>
  <script src="/static/keys.js"></script>
  <script src="/static/base.js"></script>

  {% from "components/_macros.html" import tag_chip, score_circle, status_dot, kbd, meta_item, chip, log_line %}
</body>
</html>
```

Auth-shell pages (Login, Onboarding) override `{% block body %}` to render the centered card layout without sidebar.

### F.2 Required `base.js` scripts

A single `src/ui/static/base.js` attaches the cross-cutting handlers per INTERACTIONS.md § I.1:

| Handler | Purpose | Section |
|---|---|---|
| Lucide post-swap reinit | `lucide.createIcons()` after `htmx:afterSwap` | DESIGN.md § Iconography |
| Sortable.js auto-init | `[data-sortable="true"]` after `htmx:afterSettle` | INTERACTIONS.md § D |
| Modal-close listener | Close any open `<dialog>` on `closeModal` event | INTERACTIONS.md § E.2 |
| Toast auto-dismiss | Remove success/info toasts after 4s | INTERACTIONS.md § G |
| Optimistic rollback | Restore pre-action DOM on `htmx:responseError`/`htmx:sendError` | INTERACTIONS.md § H.4 |
| Upload progress | Update `<progress>` on `htmx:xhr:progress` | INTERACTIONS.md § B.5 |

Animation keyframes (`nk-pulse`, `nk-shimmer`, `nk-blink`) live as inline `<style>` in `base.html` for Phase 1; promote to `src/ui/static/anim.css` if the set grows past ~50 lines.

### F.3 Component fixture page

`/_design/components` (per BACKEND.md § B) renders every component in every variant. Gated behind `Settings.debug`. Useful for visual QA during plan 08 implementation.

---

## G · Implementation order (informs plan 08)

Build order optimized so each batch can be visually validated against the bundle JSX without dependency surprises:

1. **Shell** — `base.html` refinements + `auth_shell.html` + `sidebar.html`. Without these, no page renders.
2. **Atomics** — Button → Input → Card → Tag chip → Score circle → Status dot → Status badge → AI badge → Avatar → Kbd → Spinner → Toast → Empty state → Field label → Info card.
3. **Forms** — Editor field → Editor card → Modal → Confirm modal → Autosave indicator.
4. **Onboarding** — Step indicator → Dropzone → Extraction checklist → Extracted field row → Progress bar.
5. **Profile / Bullet** — Profile hero → Contact chip → Experience card → Bullet row → Bullet edit row → Bullet textarea → Tag picker → Selection override → Section anchor nav → Application readiness card → Application qs form.
6. **Overview** — KPI card → Priority action row → Email signal row → Pipeline strip.
7. **Discover** — Score circle (already from Atomics) → Match breakdown → Swipe action btn → Discover action bar → Discover stats strip → Up next card → Tip card → Keyboard hints → Swipe card.
8. **Discover · review & apply** — Apply topbar → Warm intro card → Tailored bullet row → Cover letter section → Screener question card → Apply action bar.
9. **Tracking** — View toggle → Provider chip → Integration card → Followup banner → Stage column → Tracking card → Tracking list row → Tracking board.
10. **Outreach** — Outreach app row → Recommended move card → Outreach message card → Contact card → LinkedIn status chip → Outreach timeline.
11. **Settings** — Settings tabs → Provider card → Cost card → Deployment status card → Log tail → On disk card → Connection status card.
12. **Skeletons** — Swipe card skeleton → Tracking card skeleton → Priority action row skeleton → Email signal row skeleton → Bullet edit row skeleton.

Each batch passes `uv run ruff check` and renders cleanly in `/_design/components` before the next batch starts. Atomics first means primitives exist before composites need them; Shell first means `base.html` structure is in place for any rendering at all.

---

## H · Component specifications

Specs grouped by the inventory in § A.

### H.1 Shell

#### `auth_shell.html`

**Purpose:** Centered-card layout for auth-only pages (Login, Onboarding). Replaces sidebar layout from `base.html`.
**Used by:** Screen 1 (Login), Screen 2 (Onboarding).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `caller` (block) | block | yes | — | Card content (Login form, Onboarding step) |
| `version_pill_props` | dict | no | `{version: "0.4.2", mode: "self-hosted"}` | Top-left version pill |
| `api_online` | bool | no | `true` | Top-right API status dot |

**Visual spec:** `min-h-screen bg-slate-950 relative` — full-bleed background. Faint compass-pattern motif via `background-image: url('/static/compass-pattern.svg')` at 5% opacity. Centered child `flex items-center justify-center min-h-screen`.
**Lucide icons:** none directly (consumed via children).
**Variants:** none.
**Example invocation:**
```jinja
{% extends "components/auth_shell.html" %}
{% block caller %}
  <div class="bg-slate-900 border border-slate-800 rounded-xl p-8 w-[440px]">
    <!-- Login form -->
  </div>
{% endblock %}
```
**Mockup reference:** bundle `screens/Login.jsx` lines 4–175; bundle `screens/Onboarding.jsx` lines 3–100.

#### `sidebar.html`

**Purpose:** Persistent left navigation. 256px desktop, drawer on mobile. Per DESIGN.md § Components > Sidebar.
**Used by:** Every authenticated screen (Overview, Profile, Profile editor, Discover, Discover · review & apply, Tracking, Outreach, Settings).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `active` | string | yes | — | Active item ID: `overview` / `profile` / `jobs` / `tracking` / `outreach` / `settings` |
| `user_name` | string | yes | — | Sidebar bottom user name |
| `user_initials` | string | yes | — | 2-char fallback for avatar |
| `deployment_mode` | enum (`self-hosted` / `cloud`) | yes | — | Drives bottom badge tone |
| `unswiped_count` | int | no | `0` | Discover badge (Jobs item) |
| `followup_count` | int | no | `0` | Tracking badge |

**Visual spec:** `w-64 bg-slate-900 border-r border-slate-800 flex flex-col p-4 gap-1 shrink-0`. Top: brand lockup (compass icon in indigo tile + "Naavik" wordmark, Inter 700 16px). Items: `flex items-center gap-2.5 px-2.5 py-2 rounded-lg`. Active: `bg-indigo-500 text-white`. Hover: `bg-slate-800 text-slate-50`. Default: `text-slate-300`. Right-side count badge: `font-mono text-[11px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400` (or white-on-indigo when active).
**Items (per SCREENS.md sidebar IA):**
1. `Overview` · `layout-dashboard` · `/`
2. `Profile` · `user-round` · `/profile`
3. `Jobs` · `briefcase` · `/discover` · count=`unswiped_count`
4. `Tracking` · `inbox` · `/tracking` · count=`followup_count` *(spec: SCREENS.md > bundle; bundle's `kanban-square` is wrong)*
5. `Outreach` · `send` · `/outreach`
6. `Settings` · `settings` · `/settings`

**Bottom block:** `mt-12 p-3 rounded-lg bg-slate-950 border border-slate-800 flex items-center gap-2.5`. Avatar (28px, gradient purple→indigo with initials) + name (`text-sm text-slate-50 font-medium truncate`) + `deployment_badge.html`. **No theme toggle** — single dark mode.
**Lucide icons:** `compass` (brand), per-item icons above, `chevron-up` (bottom block).
**Variants:** `desktop` (default `w-64`), `mobile` (drawer, slide-in from left, full-width).
**Example invocation:**
```jinja
{% include "components/sidebar.html" with {
  "active": "overview",
  "user_name": "Shyam Padia",
  "user_initials": "SP",
  "deployment_mode": "self-hosted",
  "unswiped_count": 47,
  "followup_count": 12
} %}
```
**Mockup reference:** bundle `kit/Sidebar.jsx`.

#### `version_pill.html`

**Purpose:** Top-left version + deployment-mode pill on auth shells.
**Used by:** Screen 1 (Login), Screen 2 (Onboarding).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `version` | string | yes | — | e.g. `0.4.2` |
| `mode` | enum (`self-hosted` / `cloud`) | yes | — | Tone |

**Visual spec:** `inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-slate-900 border border-slate-800 font-mono text-[11px] text-slate-400`. Format: `v{{ version }} · {{ mode }}`.
**Lucide icons:** none.
**Variants:** `self-hosted` (default), `cloud` (no color difference; tone is in the text).
**Example invocation:**
```jinja
{% include "components/version_pill.html" with {"version": "0.4.2", "mode": "self-hosted"} %}
```
**Mockup reference:** bundle `screens/Login.jsx` ~line 30.

#### `api_status_dot.html`

**Purpose:** Top-right "API ONLINE" status pill on auth shells.
**Used by:** Screen 1 (Login), Screen 2 (Onboarding).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `online` | bool | no | `true` | Drives color and label |

**Visual spec:** `inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-900 border border-slate-800`. Dot: `h-1.5 w-1.5 rounded-full bg-emerald-500` (online) or `bg-rose-500` (offline). Label: `font-mono text-[10px] uppercase tracking-wide text-slate-400`.
**Lucide icons:** none.
**Variants:** `online` (emerald), `offline` (rose).
**Example invocation:** `{% include "components/api_status_dot.html" with {"online": true} %}`
**Mockup reference:** bundle `screens/Login.jsx` ~line 35.

#### `deployment_badge.html`

**Purpose:** Sidebar-bottom + Settings-Deployment-tab badge showing self-hosted vs cloud.
**Used by:** Sidebar bottom block (every authenticated screen), Settings · Deployment tab status card.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `mode` | enum (`self-hosted` / `cloud`) | yes | — | Drives label + tint |

**Visual spec:** `inline-flex px-1.5 py-0.5 rounded font-mono text-[10px] uppercase tracking-wide`. `self-hosted`: `bg-emerald-500/15 text-emerald-300 ring-1 ring-emerald-500/30`. `cloud`: `bg-indigo-500/15 text-indigo-300 ring-1 ring-indigo-500/30`.
**Lucide icons:** none.
**Variants:** `self-hosted`, `cloud`.
**Example invocation:** `{{ deployment_badge(mode="self-hosted") }}` (used as macro since it's small + frequent).
**Mockup reference:** bundle `kit/Sidebar.jsx` line 69; bundle `screens/Settings.jsx` § DeploymentTab.

---

### H.2 Atomics

#### `button.html`

**Purpose:** Primary, Secondary, Ghost, Danger, Icon-only buttons.
**Used by:** Every screen.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `variant` | enum (`primary` / `secondary` / `ghost` / `danger` / `icon`) | no | `primary` | Tone |
| `label` | string | yes (unless icon-only) | — | Button text |
| `icon` | string (Lucide name) | no | — | Optional leading icon |
| `size` | enum (`sm` / `md` / `lg`) | no | `md` | Padding scale |
| `disabled` | bool | no | `false` | |
| `type` | string | no | `button` | HTML type (`button` / `submit` / `reset`) |
| `extra_attrs` | string | no | — | Extra attrs (e.g. `hx-post="..."` for HTMX-bound buttons) |

**Visual spec:** all share `font-medium rounded-lg transition focus:outline-none focus:ring-2 focus:ring-indigo-500/40`.
- `primary`: `bg-indigo-500 hover:bg-indigo-400 text-white px-4 py-2`
- `secondary`: `bg-slate-800 hover:bg-slate-700 text-slate-100 border border-slate-700 px-4 py-2`
- `ghost`: `hover:bg-slate-800 text-slate-300 hover:text-slate-50 px-4 py-2`
- `danger`: `bg-rose-500 hover:bg-rose-400 text-white px-4 py-2`
- `icon`: `p-2 rounded-lg hover:bg-slate-800 text-slate-300`

Sizes: `sm` = `px-3 py-1.5 text-sm`, `md` = `px-4 py-2 text-sm`, `lg` = `px-5 py-2.5 text-base`.

Loading state: when used inside `htmx:request` parent, swap content via `.htmx-show-loading` / `.htmx-hide-loading` per INTERACTIONS.md § A.5.

**Lucide icons:** any (per `icon` arg).
**Variants:** `primary` (default), `secondary`, `ghost`, `danger`, `icon`. Disabled: `opacity-50 cursor-not-allowed`.
**Example invocation:**
```jinja
{% include "components/button.html" with {
  "variant": "primary",
  "label": "Save bullet",
  "icon": "check",
  "extra_attrs": 'hx-post="/api/v1/bullets/42" hx-target="#bullet-row-42"'
} %}
```
**Mockup reference:** bundle `kit/Components.jsx:Button` lines 32–73.

#### `input.html`

**Purpose:** Text / email / password / textarea form input.
**Used by:** Login, Onboarding (rare), Profile editor, Bullet editor (textarea variant), Settings, Outreach.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | yes | — | HTML name attr |
| `type` | string | no | `text` | `text` / `email` / `password` / `number` / `textarea` |
| `value` | string | no | `""` | Initial value |
| `placeholder` | string | no | — | |
| `required` | bool | no | `false` | |
| `autocomplete` | string | no | — | HTML autocomplete hint |
| `extra_attrs` | string | no | — | HTMX attrs (`hx-put="..." hx-trigger="blur changed delay:500ms"`) |
| `aria_label` | string | no | — | Falls back to `name` |
| `error` | string | no | — | Inline error message; renders below input in rose |
| `mono` | bool | no | `false` | Use JetBrains Mono (for IDs / API keys) |

**Visual spec:** `w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 placeholder-slate-500 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition`. Mono: `font-mono`. Textarea: same + `min-h-[100px] resize-y`. Error state: `border-rose-500 focus:ring-rose-500/20` plus `<p class="mt-1 text-xs text-rose-300">{{ error }}</p>`.
**Lucide icons:** none.
**Variants:** `text` (default), `password` (with show/hide eye toggle button — uses `eye` / `eye-off` icons), `textarea`, `mono`, `error`.
**Example invocation:**
```jinja
{% include "components/input.html" with {
  "name": "full_name",
  "type": "text",
  "value": profile.full_name,
  "extra_attrs": 'hx-put="/api/v1/profile/full_name" hx-trigger="blur changed delay:500ms" hx-swap="none"'
} %}
```
**Mockup reference:** bundle `screens/Login.jsx` § inputStyle (line 189); bundle `screens/ProfileEdit.jsx` § Field.

#### `card.html`

**Purpose:** Generic surface with optional title/sub/footer. Most-reused composite primitive.
**Used by:** Every screen.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `title` | string | no | — | Card title |
| `sub` | string | no | — | Subtitle below title |
| `actions` | block | no | — | Top-right action area |
| `caller` (block) | block | yes | — | Body content |
| `padding` | enum (`compact` / `standard`) | no | `standard` | `p-5` vs `p-6` |
| `hover` | bool | no | `false` | Adds `hover:border-slate-700 transition` |

**Visual spec:** `bg-slate-900 border border-slate-800 rounded-lg`. Padding via `padding` (`p-5` compact, `p-6` standard). Hover: `hover:border-slate-700 transition`. Title row: `flex items-baseline justify-between mb-3` with title (`text-base font-medium text-slate-50`) on left and actions on right.
**Lucide icons:** none.
**Variants:** `compact`, `standard`, `hover`.
**Example invocation:**
```jinja
{% call card_with(title="Recent activity", sub="last 24h") %}
  <!-- body content -->
{% endcall %}
```
**Mockup reference:** bundle `screens/Overview.jsx:Card` line 272; widely reused.

#### `tag_chip.html`

**Purpose:** Render one tag from the 9-tag vocabulary as a chip. **No AI sparkle on tag chips.**
**Used by:** Screens 4, 5, 6, 7, 8, 9 — every screen rendering bullets, jobs, or matched skills.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `label` | string (one of 9 tags) | yes | — | Tag value |
| `selected` | bool | no | `false` | Indigo-tinted background |

**Visual spec (default):** `inline-flex items-center gap-1 px-2 py-0.5 rounded bg-slate-800 text-slate-300 text-xs font-mono`. Selected: `bg-indigo-500/15 text-indigo-200 ring-1 ring-indigo-500/40`. Hover: `hover:bg-slate-700 transition`.
**Lucide icons:** none. **Sparkle is forbidden on tag chips** — sparkle is for AI-generated content only.
**Variants:** `default`, `selected`.
**Example invocation:** `{{ tag_chip("ai-ml") }}` or `{{ tag_chip("backend", selected=True) }}`.
**Mockup reference:** bundle `kit/Components.jsx:Tag` line 75.

#### `status_dot.html`

**Purpose:** Colored dot for status pipeline + auxiliary indicators.
**Used by:** Sidebar (count badges), pipeline strip, Tracking card, status badge composite, Outreach state pill.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `status` | enum (`DRAFT` / `APPLIED` / `RECRUITER_SCREEN` / `ONSITE_LOOP` / `OFFER` / `CLOSED` / `info` / `warning` / `success` / `danger`) | yes | — | Drives color |

**Visual spec:** `inline-block h-2 w-2 rounded-full`. Color map per DESIGN.md § Status Pipeline: DRAFT=`bg-slate-500`, APPLIED=`bg-indigo-500`, RECRUITER_SCREEN=`bg-cyan-500`, ONSITE_LOOP=`bg-amber-500`, OFFER=`bg-emerald-500`, CLOSED=`bg-rose-500`. Aux: info=`bg-sky-500`, warning=`bg-amber-500`, success=`bg-emerald-500`, danger=`bg-rose-500`.
**Lucide icons:** none.
**Variants:** by status.
**Example invocation:** `{{ status_dot("APPLIED") }}`.
**Mockup reference:** bundle widely uses inline SVG dots.

#### `status_badge.html`

**Purpose:** Status dot + label (uppercase, mono).
**Used by:** Tracking card, Tracking list row, Application detail, Pipeline strip column header, Outreach state pill.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `status` | ApplicationStatus | yes | — | Drives dot color and label |
| `label_override` | string | no | — | Custom label (defaults to status name title-cased) |
| `pill` | bool | no | `true` | If false, render plain inline (no rounded-full) |

**Visual spec:** `inline-flex items-center gap-1.5`. Pill: `px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700`. Dot via `status_dot.html`. Label: `text-[11px] font-medium uppercase tracking-wide text-slate-300` (or matching status tone for highlighted variants).
**Lucide icons:** none.
**Variants:** `pill` (default), `inline` (no rounded-full pill).
**Example invocation:** `{% include "components/status_badge.html" with {"status": "ONSITE_LOOP"} %}`.
**Mockup reference:** bundle `kit/Components.jsx:StatusBadge` line 103.

#### `score_circle.html`

**Purpose:** 0–100 number centered in a colored ring. **No `%` mark, no "match" word.**
**Used by:** Screen 3 (email signal row), Screen 7 (swipe card), Screen 8 (apply topbar), Screen 9 (tracking card), Screen 10 (outreach app row).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `score` | int (0–100) | yes | — | The score. Pass `score * 100` if model gives 0.0–1.0 |
| `size` | enum (`compact` / `default` / `hero`) | no | `default` | 40 / 64 / 96 px |
| `ring_color_override` | string (Tailwind class) | no | (auto from score) | For light-on-color contexts (e.g. swipe card top band) |
| `text_color_override` | string | no | `text-slate-50` | |

**Visual spec:** SVG with two `<circle>` elements — track + arc. `stroke-dasharray` for ring fraction. Ring color thresholded:
- `≥ 80` — `stroke-emerald-400` (green)
- `60–79` — `stroke-indigo-400`
- `40–59` — `stroke-amber-400`
- `< 40` — `stroke-rose-400`

Background fill: same color at `/10` opacity. Number: `font-mono font-semibold tabular-nums`, font size scales (`text-sm` for 40, `text-xl` for 64, `text-3xl` for 96).
**Lucide icons:** none.
**Variants:** by `size` × score-threshold-color × override.
**Example invocation:** `{{ score_circle(score=86, size="default") }}`.
**Mockup reference:** bundle `kit/Components.jsx:ScoreDonut` line 201.

#### `ai_badge.html`

**Purpose:** Cyan-tinted badge labeling AI-generated content. **Reserved for content; never on tag chips, status badges, or metadata.**
**Used by:** Screen 2 (extraction confidence card), Screen 8 (cover letter "AI · enthusiastic" tab badge, model attribution), Screen 10 (outreach AI draft card).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `qualifier` | string | no | — | Optional tone qualifier ("enthusiastic", "claude-3.5-sonnet"); appended after `·` |
| `variant` | enum (`badge` / `draft`) | no | `badge` | `badge` is the inline chip; `draft` is the larger card-label form |

**Visual spec (badge):** `inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-cyan-400/10 text-cyan-300 text-[11px] font-mono uppercase tracking-wide`. Sparkle icon (`sparkles`, 12px, `text-cyan-400`). Label: `AI` (with optional `· {{ qualifier }}` lowercase mono after).
**Variant `draft`:** larger, card-label scale: `inline-flex gap-1.5 px-2 py-0.5 rounded text-xs uppercase tracking-wide`.
**Lucide icons:** `sparkles` (cyan-400, stroke 1.5).
**Variants:** `badge` (default inline), `draft` (larger). Tone qualifier optional.
**Example invocation:** `{% include "components/ai_badge.html" with {"qualifier": "enthusiastic"} %}` or `{% include "components/ai_badge.html" with {"qualifier": "claude-3.5-sonnet", "variant": "badge"} %}`.
**Mockup reference:** DESIGN.md § AI badge.

#### `kbd.html`

**Purpose:** Keyboard key cap (e.g. `←`, `⌘K`).
**Used by:** Screen 7 (keyboard hints), Screen 8 (cover letter shortcuts), modal save hints.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `key` | string | yes | — | Display character (`←`, `↵`, `⌘K`) |

**Visual spec:** `inline-flex items-center justify-center min-w-[24px] h-6 px-1.5 rounded bg-slate-800 border border-slate-700 text-[11px] font-mono text-slate-300`. Used as macro since called many times per page.
**Lucide icons:** none.
**Variants:** none.
**Example invocation:** `{{ kbd("←") }} skip · {{ kbd("→") }} auto-apply · {{ kbd("↵") }} review`
**Mockup reference:** bundle `screens/Discover.jsx:KeyboardHints` line 309.

#### `field_label.html`

**Purpose:** Caption-style label above a form field.
**Used by:** Profile editor, Login, Bullet editor, Settings forms.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `label` | string | yes | — | Caption text |
| `for_id` | string | no | — | HTML `for` attr |
| `hint` | string | no | — | Right-aligned secondary hint (e.g. "Tags · 3 selected") |

**Visual spec:** `flex items-baseline justify-between mb-1.5`. Label: `text-xs uppercase tracking-wide text-slate-400 font-medium`. Hint: `text-xs text-slate-500`.
**Lucide icons:** none.
**Variants:** with/without hint.
**Example invocation:** `{% include "components/field_label.html" with {"label": "Tags", "for_id": "tags", "hint": "3 selected"} %}`.
**Mockup reference:** bundle `screens/BulletModal.jsx`.

#### `info_card.html`

**Purpose:** Tinted info / warning / success / danger card with icon + body.
**Used by:** Screen 1 (SSO coming soon), Screen 2 (extraction "Parsed locally" hint), Screen 5 (US application questions explainer), Screen 8 (warm intro card uses similar tint pattern).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `tone` | enum (`info` / `success` / `warning` / `danger`) | no | `info` | Tint |
| `icon` | string (Lucide name) | yes | — | Leading icon |
| `title` | string | no | — | Optional title (bold) |
| `caller` (block) | block | yes | — | Body content |

**Visual spec:** `flex gap-3 p-4 rounded-lg`. Tone tints:
- `info`: `bg-indigo-500/10 border border-indigo-500/30 text-indigo-200`
- `success`: `bg-emerald-500/10 border border-emerald-500/30 text-emerald-200`
- `warning`: `bg-amber-500/10 border border-amber-500/30 text-amber-200`
- `danger`: `bg-rose-500/10 border border-rose-500/30 text-rose-200`

Icon: 20px, color matches tone.
**Lucide icons:** any (per `icon` arg). Common: `key` (info), `lock` (info), `info`, `check-circle-2` (success), `alert-triangle` (warning), `alert-circle` (danger).
**Variants:** by `tone`.
**Example invocation:**
```jinja
{% call info_card(tone="info", icon="key", title="SSO coming soon") %}
  Self-hosted instances will support OIDC providers like Authentik, Keycloak, and Okta.
{% endcall %}
```
**Mockup reference:** bundle `screens/Login.jsx` SSO card; DESIGN.md § Voice & Tone > Empty States (similar pattern).

#### `spinner.html`

**Purpose:** Inline loading spinner (in-button) or standalone.
**Used by:** Every form submit button (Login, Save bullet, Submit application), test-connection responses, anywhere `.htmx-show-loading` reveals it.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `size` | enum (`xs` / `sm` / `md`) | no | `sm` | 12 / 16 / 20 px |
| `color` | string (Tailwind class) | no | `text-current` | Defaults to inheriting parent text color |

**Visual spec:** `inline-flex items-center justify-center` with SVG spinning circle (`animate-spin` via Tailwind keyframe). 2px stroke. Sizes: `xs` = `h-3 w-3`, `sm` = `h-4 w-4`, `md` = `h-5 w-5`.
**Lucide icons:** `loader-2` (already spins via stroke pattern).
**Variants:** by size + color.
**Example invocation:** `{% include "components/spinner.html" with {"size": "sm"} %}`. Used inside button: `<span class="htmx-show-loading hidden">{% include "components/spinner.html" %}</span>`.
**Mockup reference:** common pattern, no specific bundle ref.

#### `toast.html`

**Purpose:** Notification toast for OOB swap into `#toast-region`.
**Used by:** Cross-cutting via INTERACTIONS.md § G; any state-changing endpoint.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `tone` | enum (`success` / `info` / `warning` / `danger`) | yes | — | Drives color and dismiss policy |
| `message` | string | yes | — | Body text |
| `dismissable` | bool | no | `true` | Show × button |

**Visual spec:** `flex items-start gap-2.5 px-3 py-2.5 rounded-lg shadow-lg max-w-md` plus the OOB-swap wrapper `<div hx-swap-oob="afterbegin:#toast-region">`. Tone classes:
- `success`: `bg-emerald-500/10 border border-emerald-500/30 text-emerald-200`
- `info`: `bg-sky-500/10 border border-sky-500/30 text-sky-200`
- `warning`: `bg-amber-500/10 border border-amber-500/30 text-amber-200`
- `danger`: `bg-rose-500/10 border border-rose-500/30 text-rose-200`

Auto-dismiss policy: `success` and `info` self-remove after 4s via `base.js`; `warning` and `danger` persist until user clicks ×.
**Lucide icons:** Per tone: `check-circle-2` (success), `info` (info), `alert-triangle` (warning), `alert-circle` (danger). Plus `x` for close.
**Variants:** by tone × dismissable.
**Example invocation:**
```jinja
<div hx-swap-oob="afterbegin:#toast-region">
  {% include "components/toast.html" with {"tone": "success", "message": "Bullet saved"} %}
</div>
```
**Mockup reference:** INTERACTIONS.md § G.

#### `empty_state.html`

**Purpose:** Empty-state placeholder per DESIGN.md § Voice & Tone — icon + line + CTA.
**Used by:** Discover (empty queue), Tracking (no applications), Outreach (no contacts), Profile sections (empty Education / Projects / Certifications).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `icon` | string (Lucide name) | yes | — | Centered icon |
| `line` | string | yes | — | One-line description |
| `cta_label` | string | no | — | Optional CTA button label |
| `cta_url` | string | no | — | Optional CTA target (HTMX or full nav) |
| `cta_method` | enum (`get` / `post`) | no | `get` | HTMX method for CTA |

**Visual spec:** `flex flex-col items-center text-center gap-3.5 px-6 py-12`. Icon tile: `h-12 w-12 rounded-xl bg-slate-800 flex items-center justify-center` with 24px Lucide icon `text-slate-500`. Line: `text-sm text-slate-300`. CTA: primary button (`button.html` variant=primary).
**Lucide icons:** any (per `icon`).
**Variants:** with/without CTA.
**Example invocation:**
```jinja
{% include "components/empty_state.html" with {
  "icon": "search",
  "line": "No new matches today. Naavik scans hourly — check back soon.",
  "cta_label": "Find jobs",
  "cta_url": "/discover"
} %}
```
**Mockup reference:** bundle `kit/Components.jsx:EmptyState` line 226; DESIGN.md § Voice & Tone > Empty States.

#### `avatar.html`

**Purpose:** User avatar (initials, gradient) or company-letter tile (single-letter, colored). High-reuse.
**Used by:** Sidebar bottom (user), Profile hero (large user), Email signal row (company), Tracking card (company), Swipe card top band (company), Outreach app row (company), Contact card (mixed user/company).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `kind` | enum (`user` / `company`) | yes | — | Drives default tone (user: purple→indigo gradient; company: per-company color) |
| `text` | string | yes | — | 1–2 chars (initials for user; first letter for company) |
| `size` | enum (`xs` / `sm` / `md` / `lg` / `xl`) | no | `md` | 24 / 28 / 36 / 48 / 64 px |
| `color_override` | string | no | — | Override default color (CSS class or hex via `style` attr) |
| `shape` | enum (`circle` / `square`) | no | `square` | `square` = `rounded-lg`; `circle` = `rounded-full` |

**Visual spec:** `flex items-center justify-center font-semibold text-white shrink-0`. User default: `bg-gradient-to-br from-purple-600 to-indigo-600`. Company default: per-company color (Stripe purple, Anthropic orange, Linear violet — passed via `color_override` or generated via hash of company name). Sizes set both width/height + font-size.
**Lucide icons:** none.
**Variants:** by `kind` × `size` × `shape`.
**Example invocation:**
```jinja
{# User avatar in sidebar bottom #}
{% include "components/avatar.html" with {"kind": "user", "text": "SP", "size": "sm", "shape": "circle"} %}

{# Company tile on Discover swipe card #}
{% include "components/avatar.html" with {"kind": "company", "text": "S", "size": "lg", "color_override": "bg-purple-600"} %}
```
**Mockup reference:** bundle `kit/Sidebar.jsx` lines 62–66 (user); bundle `screens/Discover.jsx:SwipeCard` (company tile).

---

### H.3 Forms / editor

#### `editor_field.html`

**Purpose:** Profile-editor field with auto-save on blur. Per INTERACTIONS.md § B.1.
**Used by:** Screen 5 (Profile editor) — every field; reused on Login (without autosave wiring).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `label` | string | yes | — | Field caption |
| `name` | string | yes | — | Field name (also used in `hx-put` URL) |
| `value` | string | no | — | Initial value |
| `type` | string | no | `text` | `text` / `email` / `number` / `textarea` / `date` |
| `placeholder` | string | no | — | |
| `mono` | bool | no | `false` | Use mono font |
| `autosave_url` | string | no | `/api/v1/profile/{name}` | HTMX PUT target |
| `autosave_enabled` | bool | no | `true` | Wire HTMX on blur (false = pure form input) |

**Visual spec:** Composes `field_label.html` + `input.html`. When `autosave_enabled=true`, input gets `hx-put="{{ autosave_url }}" hx-trigger="blur changed delay:500ms" hx-swap="none"`.
**Lucide icons:** none.
**Variants:** `text` / `textarea` / `mono` / `autosave_enabled` toggles.
**Example invocation:**
```jinja
{% include "components/editor_field.html" with {
  "label": "FULL NAME",
  "name": "full_name",
  "value": profile.full_name
} %}
```
**Mockup reference:** bundle `screens/ProfileEdit.jsx:Field` line 107.

#### `editor_card.html`

**Purpose:** Card wrapping a group of editor fields (e.g. one experience role, identity card).
**Used by:** Screen 5 (Profile editor) — identity card, experience cards, application questions section.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `title` | string | yes | — | Card title |
| `subtitle` | string | no | — | Subtitle (e.g. "Experience · Intuit") |
| `actions` | block | no | — | Top-right action buttons (Duplicate / Remove) |
| `caller` (block) | block | yes | — | Field grid |
| `anchor_id` | string | no | — | HTML id for section anchor scrolling |

**Visual spec:** Wraps `card.html` with title row + slot for action buttons + body grid. Anchor: `id="{{ anchor_id }}"` for `#application-qs` deep-linking.
**Lucide icons:** none directly.
**Variants:** with/without actions.
**Example invocation:**
```jinja
{% call editor_card(title="Experience", subtitle="Intuit", anchor_id="exp-intuit") %}
  <div class="grid grid-cols-3 gap-4">
    {% include "components/editor_field.html" with {"label": "TITLE", "name": "title", "value": role.title} %}
    <!-- ... -->
  </div>
{% endcall %}
```
**Mockup reference:** bundle `screens/ProfileEdit.jsx`.

#### `autosave_indicator.html`

**Purpose:** "Auto-saved 12s ago" / "Saving..." / "Couldn't save — retry" pill, OOB-swapped from `PUT /api/v1/profile/{field}`.
**Used by:** Screen 5 (Profile editor) — top-right of header.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `state` | enum (`saved` / `saving` / `error`) | yes | — | Drives icon + color |
| `relative_time` | string | no | — | e.g. "12s ago"; only for `saved` |
| `error_message` | string | no | — | Only for `error` |

**Visual spec:** `inline-flex items-center gap-1.5 px-2 py-1 rounded font-mono text-[11px]`. States:
- `saved`: `text-emerald-400` with `check` icon
- `saving`: `text-slate-400` with spinner (small)
- `error`: `text-rose-300 bg-rose-500/10` with `alert-circle` icon

**Lucide icons:** `check` / `loader-2` / `alert-circle`.
**Variants:** by `state`.
**Example invocation (returned from server as OOB):**
```html
<div id="autosave" hx-swap-oob="outerHTML">
  {% include "components/autosave_indicator.html" with {"state": "saved", "relative_time": "12s ago"} %}
</div>
```
**Mockup reference:** SCREENS.md § 5; bundle `screens/ProfileEdit.jsx`.

#### `modal.html`

**Purpose:** Native `<dialog>` modal wrapper. Per INTERACTIONS.md § E.
**Used by:** Bullet editor modal (Screen 6), confirm modal (any), Manual job entry modal (Phase 1.x deferred).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | string | yes | — | DOM id for `<dialog>` |
| `title` | string | yes | — | Header title |
| `subtitle` | string | no | — | Header subtitle (e.g. "· Intuit · Senior SWE") |
| `footer` | block | no | — | Action buttons block (Cancel + Save / Delete etc.) |
| `caller` (block) | block | yes | — | Body content |
| `size` | enum (`sm` / `md` / `lg`) | no | `lg` | Max-width: `sm`=480px, `md`=640px, `lg`=720px |
| `mobile_sheet` | bool | no | `true` | If true, mobile renders as bottom-sheet |

**Visual spec:** `<dialog open id="{{ id }}" class="bg-slate-900 border border-slate-800 rounded-xl shadow-2xl shadow-black/45 p-0 m-auto">`. Body wrapped in `flex flex-col max-h-[90vh] overflow-hidden`. Header: `px-6 pt-5 pb-3 flex items-center justify-between border-b border-slate-800`. Footer: `px-6 py-4 flex items-center justify-between border-t border-slate-800 bg-slate-950/30`. Backdrop: `<div class="modal-backdrop fixed inset-0 bg-black/40" hx-on:click="this.closest('dialog').close()"></div>`. Mobile (`md:` breakpoint): `mobile_sheet` toggles to `pinned-bottom w-full rounded-t-2xl rounded-b-none`.
**Lucide icons:** `x` for close button (top-right).
**Variants:** by `size`, `mobile_sheet`.
**Example invocation:**
```jinja
{% call modal(id="bullet-editor-modal", title="Edit bullet", subtitle="· Intuit · Senior SWE", size="lg") %}
  <!-- form body -->
{% endcall %}
```
**Mockup reference:** bundle `screens/BulletModal.jsx`.

#### `confirm_modal.html`

**Purpose:** Confirmation gate for destructive actions per INTERACTIONS.md § E.4. Centralized partial.
**Used by:** Cross-cutting — Delete bullet, Discard profile changes, Skip-after-detail-view, Reject offer, Disconnect Gmail, Discard DRAFT application.
**API (passed via query params on `/_modal/confirm?...`):**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `title` | string | yes | — | Modal heading |
| `message` | string | yes | — | Body explanation |
| `confirm_action_url` | string | yes | — | URL for confirm button HTMX call |
| `confirm_label` | string | no | `Confirm` | Confirm button text |
| `confirm_tone` | enum (`danger` / `warning` / `primary`) | no | `danger` | Drives confirm button class |
| `confirm_method` | enum (`post` / `delete` / `put`) | no | `post` | HTMX method |
| `cancel_label` | string | no | `Cancel` | Cancel button text |

**Visual spec:** Composes `modal.html` (size=`md`) + body `<p class="text-sm text-slate-300">{{ message }}</p>` + footer with two buttons.
**Lucide icons:** none directly.
**Variants:** by `confirm_tone`.
**Example invocation (from `GET /_modal/confirm?...` handler):**
```jinja
{% include "components/confirm_modal.html" with {
  "title": "Delete bullet",
  "message": "This can't be undone. The bullet's history will remain in audit logs.",
  "confirm_action_url": "/api/v1/bullets/42",
  "confirm_label": "Delete",
  "confirm_tone": "danger",
  "confirm_method": "delete"
} %}
```
**Mockup reference:** INTERACTIONS.md § E.4.

---

### H.4 Onboarding

#### `step_indicator.html`

**Purpose:** 3-step progress indicator at top of Onboarding wizard.
**Used by:** Screen 2 (Onboarding) — all 3 steps.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `current_step` | int (1–3) | yes | — | Active step |
| `steps` | list of `{n, label}` | no | (default 3) | Step labels |

**Visual spec:** `flex items-center gap-2`. Each step: `flex items-center gap-2 px-3 py-1.5 rounded-full`. Active: `bg-indigo-500 text-white`. Completed: `bg-emerald-500/15 text-emerald-300` with `check` icon. Queued: `bg-slate-800 text-slate-500`. Connectors: `h-px w-8 bg-slate-700`.
**Lucide icons:** `check` (completed steps).
**Variants:** by `current_step`.
**Example invocation:**
```jinja
{% include "components/step_indicator.html" with {
  "current_step": 2,
  "steps": [
    {"n": 1, "label": "Upload"},
    {"n": 2, "label": "Extracting"},
    {"n": 3, "label": "Review"}
  ]
} %}
```
**Mockup reference:** bundle `screens/Onboarding.jsx` ~line 30.

#### `dropzone.html`

**Purpose:** Drag-drop file area for resume PDF upload.
**Used by:** Screen 2 step 1 (Onboarding).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `accept` | string | no | `application/pdf` | MIME types |
| `max_size_mb` | int | no | `10` | Max file size (advisory) |
| `upload_url` | string | no | `/api/v1/extraction/upload` | HTMX POST target |

**Visual spec:** `h-96 border-2 border-dashed border-slate-700 rounded-xl flex flex-col items-center justify-center gap-4 hover:border-indigo-500/50 transition`. Inside: cloud-upload icon (48px slate-500), "Drop your resume here" (`text-base text-slate-300`), "or" divider, primary button. Below: "PDF only · max {{max_size_mb}} MB" (`text-xs text-slate-500`). Drag-drop JS forwards file to hidden `<input type="file">`. Form uses `hx-post hx-encoding="multipart/form-data"` per INTERACTIONS.md § B.5.
**Lucide icons:** `upload-cloud`.
**Variants:** `default`, `dragging-over` (border emphasized via JS class).
**Example invocation:**
```jinja
{% include "components/dropzone.html" with {"upload_url": "/api/v1/extraction/upload"} %}
```
**Mockup reference:** bundle `screens/Onboarding.jsx:Step1`.

#### `extraction_checklist.html`

**Purpose:** Live checklist showing AI extraction progress (Reading PDF → Identifying experience → ...).
**Used by:** Screen 2 step 2 (Onboarding).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `items` | list of `{label, status (done/active/queued), count?, sub?}` | yes | — | Checklist rows |

**Visual spec:** `flex flex-col gap-2`. Per row: `flex items-center gap-3 px-3 py-2.5 rounded-lg bg-slate-900 border border-slate-800`. Status icon (16px): `done` = `check-circle-2 text-emerald-400`; `active` = `loader-2 text-indigo-400 animate-spin`; `queued` = `circle text-slate-500`. Label: `text-sm text-slate-200`. Count/sub: `text-xs text-slate-500 ml-auto font-mono`. Server pushes SSE events that swap individual rows OOB.
**Lucide icons:** `check-circle-2`, `loader-2`, `circle`.
**Variants:** per `status`.
**Example invocation:**
```jinja
{% include "components/extraction_checklist.html" with {
  "items": [
    {"label": "Reading PDF structure", "status": "done", "count": "4 pages · 1.2 MB"},
    {"label": "Identifying experience", "status": "active", "count": "2 of 4 roles parsed"},
    {"label": "Categorizing bullets", "status": "queued", "count": "queued"},
  ]
} %}
```
**Mockup reference:** bundle `screens/Onboarding.jsx:Step2`.

#### `extracted_field_row.html`

**Purpose:** One row of "Extracted so far · AI · 4 of 6 fields" list — label + value + confidence score.
**Used by:** Screen 2 step 2 (Onboarding); also Phase 2+ profile-edit "AI suggestions" surface.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `id` | string | yes | — | DOM id for OOB swap |
| `label` | string | yes | — | Field name (e.g. `NAME`, `TITLE`) |
| `value` | string | no | — | Extracted value (or skeleton placeholder) |
| `confidence` | float (0–1) | no | — | Confidence score (mono, emerald-tinted) |
| `state` | enum (`extracted` / `extracting` / `queued`) | no | `extracted` | Drives skeleton vs value display |

**Visual spec:** `flex items-baseline gap-3 py-1.5 border-b border-slate-800/50 last:border-0`. Label: `font-mono text-[11px] uppercase tracking-wide text-slate-500 w-20 shrink-0`. Value: `text-sm text-slate-200 flex-1`. Confidence: `font-mono text-xs text-emerald-400 ml-auto tabular-nums`. State `extracting` shows shimmer skeleton on the value cell.
**Lucide icons:** none.
**Variants:** by `state`.
**Example invocation:**
```jinja
<div id="extracted-field-row-name" hx-swap-oob="outerHTML">
  {% include "components/extracted_field_row.html" with {
    "id": "extracted-field-row-name",
    "label": "NAME",
    "value": "Shyam Padia",
    "confidence": 0.99,
    "state": "extracted"
  } %}
</div>
```
**Mockup reference:** bundle `screens/Onboarding.jsx:Step2` extraction-card section.

#### `progress_bar.html`

**Purpose:** Linear progress bar with optional gradient fill.
**Used by:** Screen 2 step 2 (extraction overall progress); upload progress (file upload `<progress>` element variant).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | float (0–1) | yes | — | Fraction filled |
| `gradient` | bool | no | `false` | Indigo→cyan gradient (used in extraction) |
| `height` | enum (`thin` / `default` / `thick`) | no | `default` | 2 / 4 / 6 px |
| `id` | string | no | — | For OOB swap targets |

**Visual spec:** `relative w-full bg-slate-800 rounded-full overflow-hidden`. Heights: `thin` = `h-0.5`, `default` = `h-1`, `thick` = `h-1.5`. Fill: `<div class="h-full bg-indigo-500" style="width: {{ value * 100 }}%"></div>`. Gradient variant: `bg-gradient-to-r from-indigo-500 to-cyan-400`.
**Lucide icons:** none.
**Variants:** `gradient`, `height`.
**Example invocation:**
```jinja
{% include "components/progress_bar.html" with {"value": 0.42, "gradient": true} %}
```
**Mockup reference:** bundle `screens/Onboarding.jsx:Step2`.

---

### H.5 Profile / Bullet

#### `profile_hero.html`

**Purpose:** Hero card at top of Profile (Screen 4) and Profile editor (Screen 5).
**Used by:** Screen 4 (Profile), Screen 5 (Profile editor — read-only summary).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `profile` | dict | yes | — | Profile record |
| `editable` | bool | no | `false` | Show "Edit profile" + "Update resume" buttons |

**Visual spec:** `flex items-start gap-5 p-6 bg-slate-900 border border-slate-800 rounded-xl`. Avatar (`avatar.html`, kind=user, size=xl). Center: name (`text-2xl font-semibold text-slate-50`), title · company (`text-sm text-slate-300`), location pin + "Open to opportunities" (`text-xs text-slate-400`), contact chips row. Top-right: `Edit profile` (secondary) + `Update resume` (primary) when `editable=true`.

Mobile variant: stacks vertically. Visa badge "H1B · Requires sponsorship" rendered prominently below name.
**Lucide icons:** `map-pin`, `compass` (open to opportunities).
**Variants:** `editable=false` (Profile read-only), `editable=true` (Profile editor entry).
**Example invocation:**
```jinja
{% include "components/profile_hero.html" with {"profile": profile, "editable": false} %}
```
**Mockup reference:** bundle `screens/Profile.jsx` lines 3–195.

#### `contact_chip.html`

**Purpose:** Rounded-pill contact info chip (mail / phone / GitHub / LinkedIn / portfolio).
**Used by:** Screen 4 (Profile hero).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `kind` | enum (`mail` / `phone` / `github` / `linkedin` / `portfolio`) | yes | — | Drives icon |
| `value` | string | yes | — | Display value |
| `href` | string | no | — | Optional link target |

**Visual spec:** `inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-800 hover:bg-slate-700 transition text-xs text-slate-300 border border-slate-700`. Icon (12px) prefixes value.
**Lucide icons:** `mail`, `phone`, `github`, `linkedin`, `globe`.
**Variants:** by `kind`.
**Example invocation:**
```jinja
{% include "components/contact_chip.html" with {"kind": "mail", "value": "shyam@gmail.com", "href": "mailto:..."} %}
```
**Mockup reference:** bundle `screens/Profile.jsx`.

#### `experience_card.html`

**Purpose:** Single experience role card on Profile read-only view.
**Used by:** Screen 4 (Profile experience section).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `experience` | dict | yes | — | Experience row |
| `bullets` | list[Bullet] | yes | — | Attached bullets |
| `expanded` | bool | no | `false` | Show all bullets vs truncate to 3 |

**Visual spec:** `p-5 bg-slate-900 border border-slate-800 rounded-lg`. Top row: company-letter avatar + title (`text-base font-medium text-slate-50`) + "Company · Location" (`text-sm text-slate-400`). Date row: `text-xs text-slate-500 mt-1`. Bullets: `mt-3 flex flex-col gap-2` of `bullet_row.html`. Expand control: ghost button "Show all N bullets ↓" / "Collapse ↑".
**Lucide icons:** `chevron-down` / `chevron-up` for expand.
**Variants:** `expanded`, `collapsed`.
**Example invocation:**
```jinja
{% include "components/experience_card.html" with {"experience": exp, "bullets": exp.bullets, "expanded": false} %}
```
**Mockup reference:** bundle `screens/Profile.jsx`.

#### `bullet_row.html`

**Purpose:** Single bullet display row on Profile read-only — text + tag chips inline.
**Used by:** Screen 4 (Profile experience section).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `bullet` | dict | yes | — | Bullet record |

**Visual spec:** `flex gap-2 items-baseline text-sm text-slate-200 leading-relaxed`. Bullet marker: `text-slate-500 mt-0.5 shrink-0` (`•`). Body: `flex-1` text. Tag chips: `flex flex-wrap gap-1 ml-2 inline` of `tag_chip` macros.
**Lucide icons:** none.
**Variants:** none in Profile read-only (the editor uses `bullet_edit_row.html`).
**Example invocation:** `{% include "components/bullet_row.html" with {"bullet": bullet} %}`
**Mockup reference:** bundle `screens/Profile.jsx`.

#### `section_anchor_nav.html`

**Purpose:** Right-rail "ON THIS PAGE" sticky navigation with anchor links.
**Used by:** Screen 4 (Profile right rail), Screen 5 (Profile editor right rail).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `anchors` | list of `{id, label, count?}` | yes | — | Anchor entries |
| `active_id` | string | no | — | Scroll-spy active ID (set via small JS in `base.js`) |

**Visual spec:** `sticky top-6 w-60 flex flex-col gap-1`. Header: `text-xs uppercase tracking-wide text-slate-500 mb-3`. Each anchor: `block px-3 py-1.5 rounded text-sm text-slate-400 hover:bg-slate-800 hover:text-slate-100 transition`. Active: `bg-indigo-500/10 text-indigo-300 border-l-2 border-indigo-500`.
**Lucide icons:** none.
**Variants:** with/without scroll-spy active highlight.
**Example invocation:**
```jinja
{% include "components/section_anchor_nav.html" with {
  "anchors": [
    {"id": "summary", "label": "Summary"},
    {"id": "experience", "label": "Experience"},
    {"id": "application-qs", "label": "Application details"}
  ],
  "active_id": "experience"
} %}
```
**Mockup reference:** bundle `screens/Profile.jsx`.

#### `application_readiness_card.html`

**Purpose:** Right-rail card on Profile that flags missing EEO/visa fields.
**Used by:** Screen 4 (Profile right rail; only when `application_readiness < 10`).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `missing_count` | int | yes | — | Number of unfilled fields (drives header) |
| `fields` | list of `{name, label, value, filled (bool)}` | yes | — | All 10 EEO/visa fields with current state |

**Visual spec:** `p-4 bg-slate-900 border border-amber-500/30 rounded-lg`. Header: `flex items-baseline justify-between mb-3`. Title: `text-xs uppercase tracking-wide text-amber-300 font-medium "{{ missing_count }} missing"`. Subtitle: `text-xs text-slate-400 mb-4 leading-relaxed`. Field rows: `flex items-center justify-between py-1.5 border-t border-slate-800/50`. Filled: `check-circle-2 text-emerald-400`. Empty: `circle text-slate-600`. CTA: ghost button "Complete now →" linking to `/profile/edit#application-qs`.
**Lucide icons:** `check-circle-2`, `circle`.
**Variants:** `missing_count > 0` (visible), `missing_count == 0` (hidden — no render).
**Example invocation:**
```jinja
{% if application_readiness.missing_count > 0 %}
  {% include "components/application_readiness_card.html" with application_readiness %}
{% endif %}
```
**Mockup reference:** bundle `screens/Profile.jsx` right rail.

#### `application_qs_form.html`

**Purpose:** Form section for the 10 EEO/visa application questions on Profile editor.
**Used by:** Screen 5 (Profile editor) — anchored at `#application-qs`.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `profile` | dict | yes | — | Profile with EEO/visa fields populated |
| `region` | enum (`US`) | no | `US` | Phase 1: US-only; Phase 2+ adds UK/EU |

**Visual spec:** Composes `editor_card.html` (title="US application questions", subtitle="United States" `region pill`) + grid of `editor_field.html` for each EEO/visa field. Note above grid: "Most US-based job applications ask these. We answer them once and apply automatically. We never share these outside Naavik." (`text-xs text-slate-400 mb-4`).
**Field types per DATA_MODEL.md § C Profile:**
- `work_authorization`: select with `WorkAuthorization` enum
- `visa_sponsorship_needed`: select with `VisaSponsorship` enum
- `willing_to_relocate`: select with `RelocateOpenness` enum
- `notice_period_days`: number
- `salary_expectation_usd`: number
- `earliest_start`: date
- `veteran_status`, `disability_status`, `race_ethnicity`, `gender_identity`: select per enum

**Lucide icons:** `lock` (for the "We never share..." note).
**Variants:** by `region`.
**Example invocation:** `{% include "components/application_qs_form.html" with {"profile": profile} %}`
**Mockup reference:** bundle `screens/ProfileEdit.jsx` § Application questions.

#### `bullet_edit_row.html`

**Purpose:** Bullet row in Profile editor — drag handle + truncated text + tag chips + edit/delete actions.
**Used by:** Screen 5 (Profile editor experience cards).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `bullet` | dict | yes | — | Bullet record |
| `editing` | bool | no | `false` | Inline-edit mode (rare; usually opens modal) |

**Visual spec:** `flex items-start gap-2 px-3 py-2.5 rounded-lg hover:bg-slate-800/30 group`. Drag handle (`grip-vertical` icon, `text-slate-600 cursor-grab` — only visible on hover via `group-hover:opacity-100 opacity-0`). Bullet text: `flex-1 text-sm text-slate-200 line-clamp-2`. Tag chips: `flex gap-1 ml-2`. Selection-override pill (small): if `bullet.selection_override`, render `pinned · always` (emerald) or `pinned · never` (slate) chip. Action icons (visible on hover): `pencil` (opens `/_modal/bullet-editor/{id}`), `trash-2` (opens confirm modal).
**Lucide icons:** `grip-vertical`, `pencil`, `trash-2`.
**Variants:** `default`, `editing` (Phase 1.x).
**Example invocation:** `{% include "components/bullet_edit_row.html" with {"bullet": bullet} %}`
**Mockup reference:** bundle `screens/ProfileEdit.jsx:BulletRow` line 120.

#### `tag_picker.html`

**Purpose:** Fieldset of 9 tag chips (checkbox toggles) in Bullet editor modal. Per INTERACTIONS.md § B.6.
**Used by:** Screen 6 (Bullet editor modal); generalizes to any chip-toggle UI.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `selected` | list[Tag] | yes | — | Currently-selected tags |
| `vocab` | list[Tag] | no | (9-tag default) | Override for non-bullet contexts |
| `name` | string | no | `tags[]` | Form field name |

**Visual spec:** `<fieldset class="flex flex-wrap gap-1.5" data-tag-picker>`. Each chip: `<label class="tag-chip">` with hidden checkbox + `<span class="tag-chip__label">`. CSS `:has(input:checked)` drives selected state — `bg-indigo-500/15 text-indigo-200 ring-1 ring-indigo-500/40`. Hidden screen-reader legend: "Tags · {N} selected". **No HTMX round-trip per chip** — state is form-local until parent form submit.
**Lucide icons:** none.
**Variants:** none — same shape across all chip-toggle UIs.
**Example invocation:**
```jinja
{% include "components/tag_picker.html" with {"selected": bullet.tags} %}
```
**Mockup reference:** bundle `screens/BulletModal.jsx`; INTERACTIONS.md § B.6.

#### `selection_override.html`

**Purpose:** Two mutually-exclusive option cards (radios) for bullet selection_override.
**Used by:** Screen 6 (Bullet editor modal).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `current` | enum (`always_include` / `never_include` / `null`) | yes | — | Drives radio state |

**Visual spec:** `flex flex-col gap-2`. Each option: `<label class="flex items-start gap-3 p-3 rounded-lg border border-slate-700 hover:border-slate-600 cursor-pointer">` with hidden radio + content. Selected: `border-indigo-500/40 bg-indigo-500/5`. Title: `text-sm font-medium text-slate-100`. Description: `text-xs text-slate-400 mt-0.5`. Right: `auto` chip (mono, slate) showing whether selected. Default (neither selected): both unchecked = AI auto-decides.
**Lucide icons:** none.
**Variants:** `always_include` selected, `never_include` selected, neither (default).
**Example invocation:** `{% include "components/selection_override.html" with {"current": bullet.selection_override} %}`
**Mockup reference:** bundle `screens/BulletModal.jsx` § Selection override.

#### `bullet_textarea.html`

**Purpose:** Long-form bullet text input in Bullet editor modal. **Single field — no oneline/detailed split.**
**Used by:** Screen 6 (Bullet editor modal).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `value` | string | yes | — | Current bullet text |
| `name` | string | no | `text` | Form field name |
| `hint` | string | no | `write the long version — Naavik trims to fit` | Right-aligned label hint |

**Visual spec:** Composes `field_label.html` (label="BULLET", hint=`hint`) + autosizing `<textarea>` (`min-h-[120px] resize-y w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 font-sans leading-relaxed`). Below textarea: sparkle-icon explainer card (`info_card` with tone=info, sparkle icon, body: "At apply time Naavik picks the bullets that fit the JD and rewrites each one to land on a single line — keeping your numbers and verbs intact. You don't need to maintain two versions.").
**Lucide icons:** `sparkles` (cyan, in explainer card).
**Variants:** none.
**Example invocation:** `{% include "components/bullet_textarea.html" with {"value": bullet.text} %}`
**Mockup reference:** bundle `screens/BulletModal.jsx`.

---

### H.6 Overview

#### `kpi_card.html`

**Purpose:** Funnel KPI tile — uppercase mono label + large value + optional delta + sub-line.
**Used by:** Screen 3 (Overview KPI strip).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `label` | string | yes | — | Uppercase caption |
| `value` | string | yes | — | Big number / percentage |
| `delta` | string | no | — | `+2.1%` / `-0.4%` |
| `delta_trend` | enum (`up` / `down`) | no | (inferred from sign) | Color tone |
| `sub` | string | no | — | Smaller subtitle line |

**Visual spec:** `bg-slate-900 border border-slate-800 rounded-lg p-5`. Label: `text-xs uppercase tracking-wide text-slate-400 font-medium`. Value: `mt-2 font-sans text-3xl font-semibold tabular-nums text-slate-50`. Delta: `font-mono text-xs ml-2` colored emerald (up) or rose (down). Sub: `mt-1 text-xs text-slate-400`.
**Lucide icons:** none.
**Variants:** with/without `delta`, with/without `sub`.
**Example invocation:**
```jinja
{% include "components/kpi_card.html" with {
  "label": "RESPONSE RATE · 90D",
  "value": "11.3%",
  "delta": "+2.1%",
  "delta_trend": "up",
  "sub": "3× market avg"
} %}
```
**Mockup reference:** bundle `screens/Overview.jsx:Kpi` line 259.

#### `priority_action_row.html`

**Purpose:** Numbered priority action row on Overview "PRIORITY ACTIONS" list.
**Used by:** Screen 3 (Overview).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `index` | int | yes | — | Numbered prefix (`01`, `02`, ...) |
| `kind` | enum (`offer` / `interview` / `reply` / `silent`) | yes | — | Drives icon |
| `title` | string | yes | — | Main label |
| `subtitle` | string | yes | — | Secondary context |
| `urgency` | enum (`today` / `tomorrow` / `silent_n` / `relative`) | yes | — | Urgency badge |
| `urgency_label` | string | yes | — | e.g. `TODAY`, `6D SILENT` |
| `cta_label` | string | yes | — | CTA button label |
| `cta_url` | string | yes | — | CTA target |

**Visual spec:** `flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-slate-800/50 transition`. Index: `font-mono text-[11px] text-slate-500 w-7 shrink-0 tabular-nums`. Kind icon (20px, color per kind: `sparkles` emerald for offer; `video` indigo for interview; `inbox` slate for reply; `clock` rose for silent). Body: title (`text-sm font-medium text-slate-100`) + subtitle (`text-xs text-slate-400`). Urgency badge: `font-mono text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded` (rose for today/silent_n, amber for tomorrow, slate for relative). CTA: ghost button.
**Lucide icons:** `sparkles`, `video`, `inbox`, `clock`.
**Variants:** by `kind` × `urgency`.
**Example invocation:**
```jinja
{% include "components/priority_action_row.html" with {
  "index": 1,
  "kind": "offer",
  "title": "Respond to Figma offer",
  "subtitle": "$290k base + 0.04% · verbal extended Apr 28 · they expect a reply by Thu",
  "urgency": "today",
  "urgency_label": "TODAY",
  "cta_label": "Open offer",
  "cta_url": "/tracking/123"
} %}
```
**Mockup reference:** bundle `screens/Overview.jsx:PriorityRow` line 140.

#### `email_signal_row.html`

**Purpose:** Email signal row on Overview right rail (sender + subject + status pill + score + time).
**Used by:** Screen 3 (Overview), Screen 9 (Tracking integrations row variant).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `signal` | dict | yes | — | EmailThread row + computed fields |

**Visual spec:** `flex items-center gap-3 py-2.5 border-b border-slate-800/50 last:border-0`. Sender avatar (`avatar.html`, kind=company, size=sm). Body: subject preview (`text-sm text-slate-100 truncate`) + sender label (`text-xs text-slate-500 truncate`). Right: status pill (`status_badge.html` with tone matched to classification — emerald=offer, amber=interview, rose=rejection), score (mono cyan), relative time (mono slate-500).
**Lucide icons:** none directly.
**Variants:** by classification.
**Example invocation:** `{% include "components/email_signal_row.html" with {"signal": signal} %}`
**Mockup reference:** bundle `screens/Overview.jsx:SignalList` line 196.

#### `pipeline_strip.html`

**Purpose:** Compact horizontal mini-Kanban showing 5 stage counts.
**Used by:** Screen 3 (Overview bottom strip).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `counts` | dict | yes | — | `{APPLIED: 14, RECRUITER_SCREEN: 5, ONSITE_LOOP: 3, OFFER: 1, CLOSED: 6}` |

**Visual spec:** `grid grid-cols-5 gap-2 p-4 bg-slate-900 border border-slate-800 rounded-lg`. Each column: `flex flex-col gap-1.5`. Header: `flex items-center gap-1.5 text-[11px] uppercase tracking-wide font-medium text-slate-400` with `status_dot` of matching color + label + count (`text-slate-50 font-mono ml-auto`). Body (Phase 1 minimum): empty placeholder strip; Phase 1.x adds compact card render.
**Lucide icons:** none directly.
**Variants:** by counts.
**Example invocation:**
```jinja
{% include "components/pipeline_strip.html" with {
  "counts": {"APPLIED": 14, "RECRUITER_SCREEN": 5, "ONSITE_LOOP": 3, "OFFER": 1, "CLOSED": 6}
} %}
```
**Mockup reference:** bundle `screens/Overview.jsx:Pipeline` line 285.

---

### H.7 Discover

#### `swipe_card.html`

**Purpose:** Full job card on Discover — gradient top band + meta strip + signal chips + 2-column body (JD bullets + match breakdown).
**Used by:** Screen 7 (Discover).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `job` | dict | yes | — | Job record |
| `dimmed` | bool | no | `false` | Background-stack rendering |
| `swiping_dir` | enum (`left` / `right` / `up` / `null`) | no | `null` | Renders directional Stamp overlay |

**Visual spec:** `w-[460px] bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl shadow-black/45 overflow-hidden`. Top band: `h-20 px-5 py-4 flex items-center gap-3 bg-gradient-to-br from-indigo-600 to-purple-600` (color computed per company). Inside top band: company avatar + COMPANY caption + role+team text + score circle. Body: meta row (icons + values, mono via `meta_item` macro), tag row (warm-intro chip first if applicable, then standard tag chips), 2-column lower body (left=`WHAT THEY WANT` bullets, right=`MATCH · 0.86` bars from `match_breakdown.html`). Stamp overlay (when swiping): absolute-positioned `<div>` rendering `SKIP` (rose) / `APPLY` (emerald) / `SAVE` (indigo) at 24deg rotation.
**Lucide icons:** `map-pin`, `dollar-sign`, `laptop`, `users-round`, `user-check`, `clock` (per meta items).
**Variants:** `default`, `dimmed`, three swiping directions.
**Example invocation:**
```jinja
{% include "components/swipe_card.html" with {"job": top_job, "dimmed": false, "swiping_dir": none} %}
```
**Mockup reference:** bundle `screens/Discover.jsx:SwipeCard` lines 124–222.

#### `match_breakdown.html`

**Purpose:** Per-dimension match bars (`ai-ml 0.95`, `platform 0.88`, ...).
**Used by:** Screen 7 (Discover swipe card right column), Screen 8 (Discover · review left column "MATCH BREAKDOWN").
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `breakdown` | dict | yes | — | `{tag: float}` — keys ⊆ Tag values, values 0.0–1.0 |
| `overall` | float | no | — | Optional overall score for header |

**Visual spec:** `flex flex-col gap-2`. Header (if `overall`): `text-xs uppercase tracking-wide text-slate-400 font-medium "MATCH · {{ overall|round(2) }}"`. Per row: `flex items-center gap-2`. Tag label: `font-mono text-xs text-slate-300 w-20 truncate`. Bar: `flex-1 h-1 rounded-full bg-slate-800 overflow-hidden` with inner fill `h-full` colored by score-threshold (per DESIGN.md § Score circle thresholds). Value: `font-mono text-xs text-slate-300 tabular-nums`.
**Lucide icons:** none.
**Variants:** with/without overall header.
**Example invocation:**
```jinja
{% include "components/match_breakdown.html" with {
  "breakdown": {"ai-ml": 0.95, "platform": 0.88, "leadership": 0.82, "visa": 0.70},
  "overall": 0.86
} %}
```
**Mockup reference:** bundle `screens/Discover.jsx:SwipeCard`; bundle `screens/DiscoverDetail.jsx`.

#### `discover_action_bar.html`

**Purpose:** 4-button bottom action bar on Discover (Skip / Save / Review & apply / Auto-apply).
**Used by:** Screen 7 (Discover).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `job_id` | int | yes | — | Job for HTMX action URLs |

**Visual spec:** `flex items-center gap-3 mt-6`. Each button is a `swipe_action_btn.html`:
- ✕ Skip (rose outline) — keycap `←`
- 📑 Save (slate outline) — keycap `↑`
- Review & apply (primary indigo) — keycap `tap` / `⏎`
- ⚡ Auto-apply (emerald solid) — keycap `→`

Below: `keyboard_hints.html` strip.
**Lucide icons:** `x` (skip), `bookmark` (save), `sparkles` (review), `zap` (auto-apply).
**Variants:** none.
**Example invocation:** `{% include "components/discover_action_bar.html" with {"job_id": current_job.id} %}`
**Mockup reference:** bundle `screens/Discover.jsx` § action bar.

#### `swipe_action_btn.html`

**Purpose:** Single swipe action button — large, with icon + label + keycap hint.
**Used by:** Screen 7 (Discover action bar), mobile circular variant.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `icon` | string (Lucide name) | yes | — | Action icon |
| `label` | string | yes | — | Visible label |
| `tone` | enum (`skip` / `save` / `review` / `auto-apply`) | yes | — | Drives color |
| `key_hint` | string | yes | — | Keyboard cap (e.g. `←`) |
| `action_url` | string | yes | — | HTMX action target |
| `action_method` | enum (`post` / `get`) | no | `post` | |
| `mobile` | bool | no | `false` | Mobile circular variant |

**Visual spec:** `flex flex-col items-center justify-center gap-2 px-6 py-4 rounded-xl border-2 transition flex-1`. Tones:
- `skip`: `border-rose-500/40 hover:bg-rose-500/10 text-rose-300`
- `save`: `border-slate-700 hover:bg-slate-800 text-slate-300`
- `review`: `bg-indigo-500 hover:bg-indigo-400 text-white border-indigo-500` (primary)
- `auto-apply`: `bg-emerald-500 hover:bg-emerald-400 text-white border-emerald-500`

Icon: 24px. Label: `text-sm font-medium`. Keycap: `kbd` macro below.

Mobile variant: circular `h-14 w-14 rounded-full` with icon only.
**Lucide icons:** any (per `icon`).
**Variants:** by `tone` × `mobile`.
**Example invocation:**
```jinja
{% include "components/swipe_action_btn.html" with {
  "icon": "x", "label": "Skip", "tone": "skip", "key_hint": "←",
  "action_url": "/api/v1/discover/" ~ job.id ~ "/skip"
} %}
```
**Mockup reference:** bundle `screens/Discover.jsx:ActionBtn` line 279.

#### `discover_stats_strip.html`

**Purpose:** Compact stats row at top of Discover (TODAY · {n} APPLIED · ⚡ {n} AUTO · ...).
**Used by:** Screen 7 (Discover).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `stats` | dict | yes | — | `{applied, auto, manual, saved, skipped, scanned}` |

**Visual spec:** `flex items-center gap-4 px-4 py-2 bg-slate-900 border border-slate-800 rounded-lg text-xs`. Each stat: `flex items-center gap-1 font-mono text-slate-300`. Labels: `text-slate-500`. Right-aligned hint: `ml-auto text-slate-500 font-mono text-[11px] "queue refreshes hourly · {{stats.scanned}} scanned today"`.
**Lucide icons:** `zap` (auto), `pencil` (manual), `bookmark` (saved), `x` (skipped).
**Variants:** none.
**Example invocation:**
```jinja
{% include "components/discover_stats_strip.html" with {
  "stats": {"applied": 4, "auto": 2, "manual": 1, "saved": 8, "skipped": 12, "scanned": 247}
} %}
```
**Mockup reference:** bundle `screens/Discover.jsx`.

#### `up_next_card.html`

**Purpose:** Mini-card in Discover right rail showing one queued job preview, OR a stuck-in-queue DRAFT whose auto-apply submission failed and needs manual fix-up.
**Used by:** Screen 7 (Discover right rail "Up next" group + "Stuck in queue · {N}" group).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `job` | dict | yes | — | Job record (compact) |
| `state` | enum (`default` / `stuck`) | no | `default` | `default` renders the up-next variant; `stuck` renders the failed-auto-apply variant with tinted border + failure-kind chip |
| `last_failure` | dict | no | — | Required when `state="stuck"`: `{kind, message, captured_at}` from `Application.submission_artifacts.last_failure`. Drives chip label + tooltip |

**Visual spec (default):** `flex items-center gap-3 px-3 py-2.5 rounded-lg bg-slate-900 border border-slate-800 hover:border-slate-700 transition cursor-pointer`. Company avatar (`size=sm`). Body: role (`text-sm text-slate-100 truncate`), `$range` (`text-xs text-slate-400 mono`). Right: `score_circle` (size=compact). Click → `/discover/{job.id}`.
**Visual spec (stuck):** same shape but border + bg per failure-kind: `auth_required` → `border-amber-500/40 bg-amber-500/5`; `captcha` / `field_mismatch` / `unknown` → `border-rose-500/40 bg-rose-500/5`. Failure-kind chip prefixes the score circle: `inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-800 text-[10px] font-mono uppercase tracking-wide` with `alert-triangle` icon (h-3.5 w-3.5) + chip text — `auth needed` / `captcha` / `field mismatch` / `failed`. Click → `/discover/{job.id}`; the DRAFT-attached review page surfaces a failure banner with retry / discard actions.
**Lucide icons:** `alert-triangle` (stuck variant only).
**Variants:** `default`, `stuck`.
**Example invocation:**
```jinja
{# Default — Up next group #}
{% include "components/up_next_card.html" with {"job": next_job} %}

{# Stuck — failed auto-apply group #}
{% include "components/up_next_card.html" with {
  "job": stuck_job,
  "state": "stuck",
  "last_failure": stuck_job.application.submission_artifacts.last_failure,
} %}
```
**Mockup reference:** bundle `screens/Discover.jsx:DiscoverSideRail` (default). Stuck variant added 2026-05-01 per the cross-plan triage to surface failed auto-apply DRAFTs; visual derives from the default plus the amber/rose tint pattern used on `followup_banner` + `warm_intro_card`.

#### `tip_card.html`

**Purpose:** Static educational tip card in Discover right rail.
**Used by:** Screen 7 (Discover right rail).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `title` | string | yes | — | Tip title |
| `body` | string | yes | — | Tip body |
| `icon` | string (Lucide name) | no | `lightbulb` | Leading icon |

**Visual spec:** `p-3.5 rounded-lg bg-slate-950 border border-slate-800`. Icon (16px, `text-amber-400`) + title (`text-xs uppercase tracking-wide text-slate-400 font-medium`). Body: `text-xs text-slate-400 leading-relaxed mt-1.5`.
**Lucide icons:** `lightbulb` (default).
**Variants:** none.
**Example invocation:**
```jinja
{% include "components/tip_card.html" with {
  "title": "Tip",
  "body": "Tap to expand a job and refine the resume / cover letter before applying."
} %}
```
**Mockup reference:** bundle `screens/Discover.jsx`.

#### `keyboard_hints.html`

**Purpose:** Subtitle hint strip showing keyboard shortcuts on Discover.
**Used by:** Screen 7 (Discover bottom action area).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `hints` | list of `{key, action}` | no | (default Discover hints) | Shortcut entries |

**Visual spec:** `flex items-center justify-center gap-3 mt-3 text-xs text-slate-500`. Each hint: `kbd` macro + `text-slate-500 ml-1.5`. Separator: `·`.
**Lucide icons:** none.
**Variants:** Discover defaults; can be overridden for other pages.
**Example invocation:**
```jinja
{% include "components/keyboard_hints.html" with {
  "hints": [
    {"key": "←", "action": "skip"},
    {"key": "→", "action": "auto-apply"},
    {"key": "↑", "action": "save"},
    {"key": "⏎", "action": "review"}
  ]
} %}
```
**Mockup reference:** bundle `screens/Discover.jsx:KeyboardHints` line 309.

#### `filter_toolbar.html`

**Purpose:** Sticky 6-axis filter chip-row above the Discover swipe queue. Each chip maps 1:1 to a `JobFilter` field and `hx-get`s `/_fragments/discover/queue?...` with `hx-push-url="true"` so the browser URL mirrors filter state. Plan 36 (`0.2.0.11`).
**Used by:** Screen 7 (Discover), Screen 12 (Job detail — back link returns here).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `filters` | `JobFilter` | yes | — | Current filter state (Pydantic v2 model) |
| `filters_active` | int | yes | — | Count of non-default chips (drives Clear · N affordance) |

**Visual spec:** `sticky top-0 z-10 flex items-center gap-2 flex-wrap py-2 -mx-2 px-2 bg-slate-950/95 backdrop-blur`. Six chip slots: 2 toggle-style + 4 `<details>` popovers. Toggle chips: `bg-indigo-500/15 text-indigo-200 ring-1 ring-indigo-500/40` when on (amber tone for `include_duplicates`); slate when off. Popover chips invoke `filter_chip` macro from `_macros.html`. Each `<details>` contains an embedded `<form hx-get="/_fragments/discover/queue" hx-target="#discover-main" hx-swap="innerHTML" hx-push-url="true" hx-trigger="change">` that includes `_filter_hidden_inputs.html` to preserve sibling-axis state across single-axis changes. Clear · N link is a sibling at the end, only rendered when `filters_active > 0`.
**Lucide icons:** `globe` (source), `laptop` (remote_only), `user-check` (visa), `bar-chart-3` (seniority), `gauge` (score_min), `copy` (include_duplicates), `chevron-down` (popover affordance), `x` (clear).
**Variants:** none (state-driven; each chip's `active` flag is computed from `filters` ctx).
**Example invocation:**
```jinja
{% include "components/filter_toolbar.html" with {
  "filters": filters,
  "filters_active": filters_active
} %}
```
**Mockup reference:** none (Playwright capture in `traces/2026-05-19T15-42-42_833f4a/qa/0.2.0.11/`).

#### `_filter_hidden_inputs.html`

**Purpose:** Helper partial used by each chip-form in `filter_toolbar.html` to mirror the **other 5 axes** as hidden inputs so a single-axis change doesn't drop sibling state when the form submits. Underscore-prefixed name signals "internal use only — composed inside `filter_toolbar.html`, never on its own." Plan 36 Deviations row 5 records this as net-new vs the plan's surface inventory.
**Used by:** `filter_toolbar.html` (called 6×, once per chip-form).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `filters` | `JobFilter` | yes (via context) | — | Current filter state to mirror |
| `current_axis` | str | no | `None` | Axis being changed in the enclosing form — that axis is NOT mirrored as a hidden input (avoids duplicate `name=...` on the form) |

**Visual spec:** no rendered output beyond `<input type="hidden">` tags. Emits one hidden input per axis that is (a) non-default AND (b) not equal to `current_axis`. `queue_state` is always mirrored (legacy `?filter=saved` continues to work; plan 36 § E row 7).
**Lucide icons:** none.
**Variants:** with/without `current_axis` arg.
**Example invocation:**
```jinja
{% include "components/_filter_hidden_inputs.html" ignore missing with context %}
{# OR, scoped to skip an axis: #}
{% with current_axis="source" %}
  {% include "components/_filter_hidden_inputs.html" ignore missing with context %}
{% endwith %}
```
**Mockup reference:** none (helper partial; no visual surface).

#### `job_topbar.html`

**Purpose:** Read-only top context bar for `/jobs/{id}` (Screen 12). Renders back-link + company tile + role + team + company + location + salary chip + source-tone chip + match-score (or `unscored` chip) + Open posting external link. Distinct from `apply_topbar.html` (which couples to the DRAFT Application workspace at `/discover/{id}`); no Save / Skip / Submit buttons here — those live in the right-rail action card on `_job_detail_body.html`. Plan 36 (`0.2.0.11`) § F audit picked NEW over `apply_topbar` variant arg to keep each surface owning one concern.
**Used by:** Screen 12 (Job detail).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `job` | dict | yes | — | Job projection from `jobs_ctx.build_job_detail_ctx` — fields used: `id`, `company`, `company_initial`, `role`, `team`, `location`, `salary_range`, `score`, `unscored`, `source`, `source_tone`, `url`, `url_type`, `queue_state` |

**Visual spec:** `flex items-center gap-4 px-6 py-3 border-b border-slate-800 bg-slate-950 flex-wrap`. Left: back-link `<a href="/discover">` with `arrow-left` icon + "Back to Discover" copy. Center: `avatar.html` (kind=`company`, size=`sm`, color_override=`bg-slate-700`) + role meta (`role` bold, `· team` slate-300, `/ company` slate-500, `· location` slate-400, `· salary` mono slate-400). Right shrink-0: `chip` macro for source pill (`source · LINKEDIN` etc., tone driven by `job.source_tone`) + match-score (`font-mono text-xs text-cyan-300 tabular-nums "match 0.86"`) OR `chip("unscored", tone="slate")` when `job.unscored`; trailing Open posting link (external; `hx-boost="false"`).
**Lucide icons:** `arrow-left`, `external-link` (stroke 1.5).
**Variants:** unscored (replaces match-score chip with "unscored" slate chip).
**Example invocation:**
```jinja
{% with job=job %}
  {% include "components/job_topbar.html" %}
{% endwith %}
```
**Mockup reference:** none (Playwright capture in `traces/2026-05-19T15-42-42_833f4a/qa/0.2.0.11/`).

#### `score_card.html`

**Purpose:** Variant B (linear bento) composite container surfacing score + per-dimension breakdown + AI-judged STRENGTHS + WHAT'S MISSING + optional provenance footer. Wraps `score_circle.html` + `match_breakdown.html` and reads the 18-key `Job.match_breakdown` JSONB via defensive `.get()` so legacy rows render gracefully.
**Used by:** Screen 7 (Discover · `swipe_card.html` lower body), Screen 8 (Discover · review LEFT column). Designed for reuse on Screen 12 (Job detail topbar) when that surface adopts the composite.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `score` | int 0-100 | yes | — | Threaded into nested `score_circle.html` |
| `match_breakdown` | dict | yes | — | 18-key shape (see `DATA_MODEL.md § Job.match_breakdown`); subkeys read defensively: `per_dimension`, `strengths`, `gaps`, `visa_concern`, `visa_note`, `layers_run`, `layer_4_provider`, `layer_4_model`, `judge_skipped`, `scored_at` |
| `expanded` | bool | no | `false` | When `true`, renders the provenance footer (layers, layer-4 provider/model, scored_at) below the 3-zone body |
| `size` | enum (`compact` / `default` / `hero`) | no | `default` | Sizes the embedded score circle |

**Visual spec:** `grid grid-cols-1 md:grid-cols-12 gap-4 md:gap-5`. LEFT zone (md:col-span-3): `MATCH` micro-label + `score_circle` + llm-judged pulse dot (cyan) or `layer-3 only` amber chip when `judge_skipped`. MIDDLE zone (md:col-span-4): `PER-DIMENSION` micro-label + `match_breakdown.html` per-dim bars. RIGHT zone (md:col-span-5): two tinted panels stacked — `STRENGTHS` (emerald: `bg-emerald-500/5 ring-1 ring-emerald-500/20`) over `WHAT'S MISSING` (amber: `bg-amber-500/5 ring-1 ring-amber-500/20`), each with `+` / `−` semantic bullets. Optional VISA panel (rose tint) appears when `visa_concern=true` and `visa_note` is set. Expanded footer: layer-provenance chips (slate for layers_run, cyan for `provider · model`) + `scored {{ scored_at }}` right-aligned. Mobile (<md): zones stack vertically.
**Lucide icons:** none directly (composed children own icon use).
**Variants:** collapsed (`expanded=false`, default) vs expanded (provenance footer visible); each combined with size (`compact` / `default` / `hero`).
**Example invocation:**
```jinja
{% with score=86, match_breakdown=job.match_breakdown or {}, expanded=true %}
  {% include "components/score_card.html" %}
{% endwith %}
```
**Mockup reference:** `docs/design/mockups/0.3.2/score-card-variant-b-desktop.png` + `-mobile.png` (gitignored).

---

### H.8 Discover · review & apply

#### `apply_topbar.html`

**Purpose:** Top context bar on /discover/{id} — back link + company tile + role meta + match score + actions.
**Used by:** Screen 8 (Discover · review & apply).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `job` | dict | yes | — | Job record |
| `application` | dict | yes | — | DRAFT Application |

**Visual spec:** `flex items-center gap-4 px-6 py-3 border-b border-slate-800 bg-slate-950`. Left: `← Back to queue` link (ghost). Center: company avatar + role text (`text-sm text-slate-100 "{{ job.role }} · {{ job.team }} / {{ job.company }} · {{ job.location }} · ${{ job.salary_min }}-{{ job.salary_max }}k + {{ job.equity_pct }}%"`). Right: `match {{ job.score }}` (mono cyan), `🔗 JD` (link to JD URL), `Save`, `Skip`, `Discard draft` (danger ghost — opens confirm modal).
**Lucide icons:** `arrow-left`, `external-link`.
**Variants:** none.
**Example invocation:** `{% include "components/apply_topbar.html" with {"job": job, "application": draft} %}`
**Mockup reference:** bundle `screens/DiscoverDetail.jsx`.

#### `warm_intro_card.html`

**Purpose:** Warm-intro pill card on Discover · review left column when warm intro exists.
**Used by:** Screen 8 (Discover · review left column).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `contact` | dict | yes | — | Contact record (warm intro source) |
| `referrals_this_year` | int | no | — | "She's referred N hires this year" |

**Visual spec:** `p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-lg`. Header: `flex items-baseline gap-1.5 text-[11px] uppercase tracking-wide text-emerald-300 font-medium "WARM INTRO AVAILABLE"` with `users-round` icon. Body: `mt-2 text-sm text-slate-200 leading-relaxed`. Format: "{{ contact.name }} ({{ contact.title }} at {{ contact.company }}) is a {{ contact.linkedin_degree }} LinkedIn connection. She's referred {{ referrals_this_year }} hires this year." CTA: primary button "Draft intro" (sparkle icon) → opens Outreach pre-filled.
**Lucide icons:** `users-round`, `sparkles`.
**Variants:** none.
**Example invocation:**
```jinja
{% if job.warm_intro_contact %}
  {% include "components/warm_intro_card.html" with {"contact": job.warm_intro_contact, "referrals_this_year": 4} %}
{% endif %}
```
**Mockup reference:** bundle `screens/DiscoverDetail.jsx`.

#### `tailored_bullet_row.html`

**Purpose:** One bullet row on Discover · review middle column — checkbox + AI-trimmed line + chip row + optional inline rationale ledger (plan 72 § Surface 2 — Variant A).
**Used by:** Screen 8 (Discover · review tailored resume column).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `bullet` | dict | yes | — | Bullet record |
| `selected` | bool | yes | — | Whether AI selected for this resume |
| `trimmed_line` | string | no | — | The AI-trimmed line for selected; full text for excluded |
| `chips` | list[string] | no | — | Tag-like chips: `# jd`, `# personalization`, `# scale`, `# edited for jd`, `# you tweaked`, `# duplicate signal`, `# trimmed`, `# older role` |
| `rationale` | dict \| null | no | `null` | Plan 72: `{selected: bool, why_selected: str\|null, why_dropped: str\|null}`. When set, renders an italic micro-copy line below the bullet: cyan-tinted "why kept · {why_selected}" when `selected=true`; slate-tinted "why dropped · {why_dropped}" when `selected=false`. Omit (or pass `null`) for legacy bundles without `Application.generation_trace.bullet_selection_log`. |

**Visual spec:** `flex items-start gap-3 px-3 py-2.5 rounded-lg hover:bg-slate-800/30`. Checkbox: 16px, indigo-tinted when checked. Body: trimmed line (`text-sm text-slate-200 leading-relaxed` if selected, `text-slate-500 line-through` if excluded). Rationale (when set): `italic ml-5 border-l-2 pl-2 mt-1 text-xs leading-relaxed` — `text-cyan-300 border-cyan-400/40` for selected, `text-slate-400 border-slate-700` for dropped, with a mono `why kept · ` / `why dropped · ` prefix. Chips: `flex flex-wrap gap-1 mt-1.5` (smaller variants of `chip` macro). Click → opens `/_modal/bullet-editor/{{bullet.id}}` with the trimmed-for-this-JD version pre-filled.
**Lucide icons:** `pencil` (edit hover, stroke 1.5).
**Variants:** `selected` vs excluded; each combined with rationale-present vs rationale-absent.
**Example invocation:**
```jinja
{% include "components/tailored_bullet_row.html" with {
  "bullet": bullet, "selected": true,
  "trimmed_line": "Built Intuit's ML personalization platform; +23% homepage CTR / $4.2M revenue",
  "chips": ["jd", "scale", "personalization"],
  "rationale": {"selected": true, "why_selected": "matches JD ai-ml + scale signals", "why_dropped": null}
} %}
```
**Mockup reference:** bundle `screens/DiscoverDetail.jsx:DDBulletRow` line 209; rationale ledger from `docs/design/mockups/0.3.2/bullet-preview-variant-a-desktop.png` (gitignored).

#### `cover_letter_section.html`

**Purpose:** Click-to-edit section on Discover · review right column (INTRO / BODY / WHY {COMPANY} / CLOSE).
**Used by:** Screen 8 (Discover · review cover letter column).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `application_id` | int | yes | — | For HTMX URL |
| `section` | enum (`intro` / `body` / `why_company` / `close`) | yes | — | Section name |
| `label` | string | yes | — | Display label (`INTRO`, `BODY`, `WHY {COMPANY}`, `CLOSE`) |
| `text` | string | yes | — | Current section text |
| `mode` | enum (`view` / `edit`) | no | `view` | Edit mode swaps in textarea |

**Visual spec:** `p-4 rounded-lg border border-transparent hover:border-slate-700 cursor-pointer transition`. Edit mode: `border-indigo-500/40 bg-slate-900`. Label: `text-xs uppercase tracking-wide text-slate-500 font-medium mb-2`. Body view: `text-sm text-slate-200 leading-relaxed`. Body edit: textarea + Save / Cancel buttons. Per INTERACTIONS.md § B.3 click-to-edit.
**Lucide icons:** `pencil` (hover hint).
**Variants:** `view`, `edit`.
**Example invocation:**
```jinja
{% include "components/cover_letter_section.html" with {
  "application_id": app.id, "section": "intro", "label": "INTRO", "text": draft.intro
} %}
```
**Mockup reference:** bundle `screens/DiscoverDetail.jsx:DDPara` line 240.

#### `screener_question_card.html`

**Purpose:** Screener question card with status chip + answer area + AI hint.
**Used by:** Screen 8 (Discover · review screener questions area).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `answer` | dict | yes | — | ApplicationScreenerAnswer row |

**Visual spec:** `p-4 rounded-lg bg-slate-900 border border-slate-800`. Header: question text (`text-sm text-slate-100`). Status chip top-right: `drafted` indigo / `auto` slate / `user` (no chip). Body: answer text (`mt-2 text-sm text-slate-300 leading-relaxed`). For `drafted` rows without `reviewed_at`: hint "(AI drafted from your profile + JD — review before submit)" `text-xs text-slate-500 italic mt-2`. Edit on click per INTERACTIONS.md § B.3.
**Lucide icons:** `sparkles` (drafted), `check` (auto, indicating Profile-derived).
**Variants:** by `source` (drafted / auto / user) × `reviewed_at` set/unset.
**Example invocation:** `{% include "components/screener_question_card.html" with {"answer": screener_answer} %}`
**Mockup reference:** bundle `screens/DiscoverDetail.jsx:DDScreener` line 269.

#### `apply_action_bar.html`

**Purpose:** Sticky bottom bar on Discover · review with cost summary + Submit button + ATS link + Download bundle.
**Used by:** Screen 8.
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `application` | dict | yes | — | DRAFT Application |
| `screener_count` | int | yes | — | Total screener questions |
| `unreviewed_count` | int | yes | — | Required-but-unreviewed count (gates submit) |
| `cost_estimate_usd` | float | yes | — | Pre-submit cost estimate |
| `board_label` | string | yes | — | Friendly board name (e.g. "greenhouse.io") |

**Visual spec:** `sticky bottom-0 flex items-center justify-between px-6 py-4 border-t border-slate-800 bg-slate-950/95 backdrop-blur`. Left: status text (`text-sm text-slate-400 font-mono`) — "Ready to apply · resume + cover letter + {{ screener_count }} screeners · est. cost ${{ cost_estimate_usd }}". Right: ghost "Download bundle", secondary "Open ATS · {{ board_label }}" (external link, `external-link` icon), primary `Submit application` (sparkle icon, gated `disabled` when `unreviewed_count > 0` with hover tooltip).
**Lucide icons:** `download`, `external-link`, `sparkles`.
**Variants:** disabled (when `unreviewed_count > 0`), enabled.
**Example invocation:**
```jinja
{% include "components/apply_action_bar.html" with {
  "application": draft, "screener_count": 3, "unreviewed_count": 0,
  "cost_estimate_usd": 0.12, "board_label": "greenhouse.io"
} %}
```
**Mockup reference:** bundle `screens/DiscoverDetail.jsx`.

---

### H.9 Tracking

#### `view_toggle.html`

**Purpose:** Board / List segmented toggle.
**Used by:** Screen 9 (Tracking header).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `current_view` | enum (`board` / `list`) | yes | — | Active view |
| `board_url` | string | no | `/tracking?view=board` | |
| `list_url` | string | no | `/tracking?view=list` | |

**Visual spec:** `inline-flex p-0.5 rounded-lg bg-slate-900 border border-slate-800`. Each option: `px-3 py-1 rounded-md text-sm transition`. Active: `bg-slate-800 text-slate-50 shadow-sm`. Inactive: `text-slate-400 hover:text-slate-200`. Both options use `hx-get` to swap board ↔ list views.
**Lucide icons:** `kanban` (board), `list` (list).
**Variants:** by `current_view`.
**Example invocation:**
```jinja
{% include "components/view_toggle.html" with {"current_view": "board"} %}
```
**Mockup reference:** bundle `screens/Tracking.jsx`.

#### `provider_chip.html`

**Purpose:** Compact integration provider chip (`gmail · synced 2m ago`, `linkedin · @shyampadia`).
**Used by:** Screen 9 (Tracking top), Screen 10 (Outreach top).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `provider` | string | yes | — | Display name (`gmail`, `linkedin`, `outlook`) |
| `connected` | bool | yes | — | Drives tone |
| `sub` | string | no | — | Secondary line (`synced 2m ago`, `@shyampadia · 487 connections`) |
| `icon` | string (Lucide name) | yes | — | |

**Visual spec:** `inline-flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-slate-900 border border-slate-800 text-xs`. Icon (14px, color per provider — `text-rose-400` for gmail, `text-sky-400` for linkedin). Body: provider (`text-slate-300 font-medium`) + sub (`text-slate-500 ml-1`). Disconnected: muted, plus "Connect" CTA button on hover.
**Lucide icons:** `mail` (gmail / outlook), `linkedin`, `calendar`.
**Variants:** `connected`, `not-connected`.
**Example invocation:**
```jinja
{% include "components/provider_chip.html" with {
  "provider": "gmail", "icon": "mail", "connected": true, "sub": "synced 2m ago"
} %}
```
**Mockup reference:** bundle `screens/Tracking.jsx:ProviderChip` line 216.

#### `integration_card.html`

**Purpose:** Settings-tab-or-Tracking-page integration card (Gmail / Outlook / Calendar) with state + Connect/Disconnect.
**Used by:** Screen 9 (Tracking integrations row), Screen 11 (Settings · Notifications variant).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | string | yes | — | Provider name |
| `icon` | string | yes | — | Lucide icon |
| `state` | enum (`connected` / `not_connected` / `expired` / `error`) | yes | — | Drives action button + status text |
| `account` | string | no | — | Connected account label |
| `connect_url` | string | no | — | OAuth start URL |
| `disconnect_url` | string | no | — | Disconnect endpoint |
| `description` | string | no | — | Subtitle / sub-description |

**Visual spec:** `flex items-center gap-4 p-4 bg-slate-900 border border-slate-800 rounded-lg`. Icon tile (40px). Body: name + state line. Right: Connect / Disconnect button.
**Lucide icons:** `mail`, `linkedin`, `calendar`, `link-2`.
**Variants:** by `state`.
**Example invocation:**
```jinja
{% include "components/integration_card.html" with {
  "name": "Gmail", "icon": "mail", "state": "connected",
  "account": "shyam@gmail.com",
  "disconnect_url": "/api/v1/integrations/gmail/disconnect"
} %}
```
**Mockup reference:** bundle `screens/Tracking.jsx`.

#### `followup_banner.html`

**Purpose:** Yellow-tinted "NEEDS FOLLOWUP · N" banner with up-to-4 cards.
**Used by:** Screen 9 (Tracking), Screen 3 (Overview compact variant).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `count` | int | yes | — | Total followup count |
| `items` | list of `{contact, application, last_touch_label, action_label, action_url}` | yes | — | Up to 4 rows |
| `compact` | bool | no | `false` | Overview compact variant |

**Visual spec:** `bg-amber-500/10 border border-amber-500/30 rounded-lg p-4`. Header: `flex items-center justify-between mb-3` with `text-xs uppercase tracking-wide text-amber-300 font-medium "NEEDS FOLLOWUP · {{ count }}"` and `<a class="text-xs text-amber-200 hover:text-amber-100">open in outreach →</a>`. Items: `flex flex-col gap-2.5`. Per row: avatar + name + company + state + per-row "Draft reply" CTA.
**Lucide icons:** `alert-triangle` (header).
**Variants:** `default`, `compact`.
**Example invocation:**
```jinja
{% include "components/followup_banner.html" with {"count": 4, "items": followup_rows} %}
```
**Mockup reference:** bundle `screens/Tracking.jsx:FollowupsStrip` line 68.

#### `stage_column.html`

**Purpose:** Single Kanban column on Tracking board.
**Used by:** Screen 9 (Tracking board view).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `status` | ApplicationStatus | yes | — | Drives header dot + label |
| `cards` | list[Application] | yes | — | Cards in this column |
| `column_id` | string | yes | — | For Sortable.js drag-drop tag |

**Visual spec:** `flex flex-col gap-2 min-h-[400px] w-72 shrink-0 p-3 bg-slate-900 border border-slate-800 rounded-lg`. Header: `flex items-center gap-1.5 px-1 mb-2 text-xs uppercase tracking-wide font-medium`. Status dot + label + count (`ml-auto font-mono text-slate-500`). Body: `data-sortable="true" data-column="{{ status }}" hx-post="/api/v1/applications/move" hx-trigger="end"` of `tracking_card.html`s.
**Lucide icons:** none.
**Variants:** by status. Empty column shows muted "Drop cards here" hint.
**Example invocation:**
```jinja
{% include "components/stage_column.html" with {"status": "APPLIED", "cards": apps_by_status.APPLIED, "column_id": "col-applied"} %}
```
**Mockup reference:** bundle `screens/Tracking.jsx:KanbanCol` line 235.

#### `tracking_card.html`

**Purpose:** Single application card on Tracking board.
**Used by:** Screen 9 (Tracking board cards), Screen 10 (Outreach right pane reference).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `application` | dict | yes | — | Application + Job join |

**Visual spec:** `flex flex-col gap-2 p-3 bg-slate-950 border border-slate-800 rounded-lg cursor-grab hover:border-slate-700 transition`. Top: company avatar + role text (`text-sm text-slate-100 truncate`). Subtitle: `text-xs text-slate-400 truncate`. Score (`mono cyan inline-block`), `$salary` (mono slate). Status chip (`status_badge.html`) + sub-state pills (referral / docs / recruiter) inline.
**Lucide icons:** `grip-vertical` (drag handle, on hover).
**Variants:** by application sub-state combinations.
**Example invocation:** `{% include "components/tracking_card.html" with {"application": app} %}`
**Mockup reference:** bundle `screens/Tracking.jsx:KanbanCol` cards.

#### `tracking_list_row.html`

**Purpose:** Single application row on Tracking list view.
**Used by:** Screen 9 (Tracking list view).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `application` | dict | yes | — | Application |

**Visual spec:** `<tr class="border-b border-slate-800 hover:bg-slate-800/30 transition">`. Columns per SCREENS.md: Company / Role / Stage / Score / Salary / Last activity / Source / Actions. Status uses `status_badge.html`; score uses `score_circle.html` size=compact.
**Lucide icons:** `more-vertical` (actions menu).
**Variants:** none.
**Example invocation:** `{% include "components/tracking_list_row.html" with {"application": app} %}`
**Mockup reference:** bundle `screens/Tracking.jsx:ListView` line 150.

#### `tracking_board.html`

**Purpose:** Full board view composing 5 columns + Closed bucket toggle.
**Used by:** Screen 9 (Tracking).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `columns` | list of `{status, cards}` | yes | — | 4 visible + optional 5th |
| `show_closed` | bool | no | `false` | Toggle for the rejected/withdrawn/ghosted bucket |
| `closed_count` | int | no | — | Count for footer toggle label |

**Visual spec:** `flex gap-4 overflow-x-auto pb-4`. Each column via `stage_column.html`. Footer: `mt-4 flex items-center justify-between text-sm text-slate-400` with "📁 {{ closed_count }} closed (rejected · withdrawn · ghosted)" + "Show closed" toggle.
**Lucide icons:** `archive` (closed bucket).
**Variants:** with/without closed column shown.
**Example invocation:** `{% include "components/tracking_board.html" with {"columns": kanban_cols, "show_closed": false, "closed_count": 6} %}`
**Mockup reference:** bundle `screens/Tracking.jsx:BoardView` line 115.

---

### H.10 Outreach

#### `outreach_app_row.html`

**Purpose:** Application row in Outreach left pane.
**Used by:** Screen 10 (Outreach left pane).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `application` | dict | yes | — | Application + computed outreach_engagement |
| `selected` | bool | no | `false` | Highlights current row |

**Visual spec:** `flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-pointer hover:bg-slate-800/50 transition`. Selected: `bg-indigo-500/10 border-l-2 border-indigo-500`. Company avatar + body (role · team) + meta (contacts count · last touch · status chip · state pill). State pills: `AWAITING REPLY` (amber) / `CALL BOOKED` (cyan) / `REFERRED` (emerald) / `NO REPLY · 7D` (rose).
**Lucide icons:** none.
**Variants:** by `selected` × engagement state.
**Example invocation:** `{% include "components/outreach_app_row.html" with {"application": app, "selected": true} %}`
**Mockup reference:** bundle `screens/Outreach.jsx:ApplicationsList` line 47.

#### `recommended_move_card.html`

**Purpose:** AI-recommended next move card in Outreach right pane.
**Used by:** Screen 10 (Outreach right pane top).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `application` | dict | yes | — | Selected application |
| `contact` | dict | yes | — | Contact for the recommended move |
| `tone_recommendation` | string | yes | — | e.g. "warm + direct" |
| `last_touch_relative` | string | yes | — | e.g. "5d ago" |
| `context` | string | yes | — | Why this move now |
| `draft_body` | string | yes | — | Pre-generated AI message |

**Visual spec:** `bg-amber-500/10 border border-amber-500/30 rounded-lg p-4`. Header: `text-xs uppercase tracking-wide text-amber-300 font-medium "RECOMMENDED NEXT MOVE · TODAY"`. Title (`text-base font-semibold text-slate-50 mt-2 "Followup with {{ contact.name }} · {{ contact.title }}"`). Meta line (`text-xs text-slate-400 mt-1 "last touch {{ last_touch_relative }} · {{ context }} · {{ tone_recommendation }}"`). AI draft body card (cyan-tinted, like `info_card` tone=info but cyan): full draft message text with `ai_badge` qualifier. Actions: "Send via LinkedIn" (primary), Edit, Regenerate, "Skip · don't suggest again" (ghost).
**Lucide icons:** `linkedin` (send button), `pencil`, `refresh-cw`, `x`.
**Variants:** none.
**Example invocation:** `{% include "components/recommended_move_card.html" with {"application": app, "contact": next_contact, ...} %}`
**Mockup reference:** bundle `screens/Outreach.jsx:ApplicationDetail`.

#### `outreach_message_card.html`

**Purpose:** AI draft / sent / replied message card body.
**Used by:** Screen 10 (Outreach right pane drafts + history).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `message` | dict | yes | — | OutreachMessage row |
| `editable` | bool | no | `false` | Drafts are editable inline |

**Visual spec:** `p-4 rounded-lg bg-cyan-400/5 border border-cyan-400/20` (drafts) or `bg-slate-900 border border-slate-800` (sent). Top: `ai_badge` (drafted state) + status badge. Body: textarea (drafts) or read-only text (sent). Footer: timestamp + Edit / Regenerate / Send buttons (drafts) or "replied {{ relative_time }}" (replied state).
**Lucide icons:** `pencil`, `refresh-cw`, `send`.
**Variants:** by message status.
**Example invocation:** `{% include "components/outreach_message_card.html" with {"message": msg, "editable": true} %}`
**Mockup reference:** bundle `screens/Outreach.jsx:ApplicationDetail`.

#### `contact_card.html`

**Purpose:** Single contact row in Outreach contacts list.
**Used by:** Screen 10 (Outreach right pane contact list).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `contact` | dict | yes | — | Contact record |
| `state` | enum (`referred_you` / `awaiting_reply` / `no_reply_7d` / `cold`) | yes | — | Drives state pill |

**Visual spec:** `flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-slate-800/30 transition`. Avatar (`size=md`). Body: name + degree chip (`1st`, `2nd · via Priya`), school + mutuals count, role + team subtitle, last-activity sentence. Right: state pill + `more-vertical` actions menu.
**Lucide icons:** `more-vertical`.
**Variants:** by `state`.
**Example invocation:** `{% include "components/contact_card.html" with {"contact": c, "state": "referred_you"} %}`
**Mockup reference:** bundle `screens/Outreach.jsx:ApplicationDetail`.

#### `linkedin_status_chip.html`

**Purpose:** LinkedIn integration status chip with rate-limit warnings.
**Used by:** Screen 10 (Outreach top).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `connected` | bool | yes | — | Drives tone |
| `handle` | string | no | — | LinkedIn vanity handle |
| `dms_today` | int | no | — | Today's DM count toward 50/day limit |
| `connections` | int | no | — | Total LinkedIn connections |

**Visual spec:** Composes `provider_chip.html` with provider="linkedin", icon="linkedin". Tooltip on hover shows DMs today / 50 + connections count.
**Lucide icons:** `linkedin`.
**Variants:** `connected`, `not_connected`, `rate_limited` (when `dms_today >= 50`).
**Example invocation:** `{% include "components/linkedin_status_chip.html" with {"connected": true, "handle": "shyampadia", "dms_today": 7, "connections": 487} %}`
**Mockup reference:** bundle `screens/Outreach.jsx`.

#### `outreach_timeline.html`

**Purpose:** Chronological timeline of outreach + email events for selected application.
**Used by:** Screen 10 (Outreach right pane footer / accordion).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `events` | list[AppEvent] | yes | — | Filtered to outreach + email kinds |

**Visual spec:** `flex flex-col gap-3 p-4`. Each event: `flex items-start gap-3` with kind icon (16px, color per kind), body (event description + relative time), payload preview (`text-xs text-slate-500`).
**Lucide icons:** per kind: `linkedin` (DM), `mail` (email), `users-round` (referral), `phone` (interview).
**Variants:** none.
**Example invocation:** `{% include "components/outreach_timeline.html" with {"events": app_events} %}`
**Mockup reference:** bundle `screens/Outreach.jsx`.

---

### H.11 Settings

#### `settings_tabs.html`

**Purpose:** Top tabs nav for Settings page.
**Used by:** Screen 11 (Settings).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `current_tab` | enum (`account` / `llm-provider` / `notifications` / `auto-apply` / `sources` / `deployment`) | yes | — | Active tab |

**Visual spec:** `flex items-center gap-1 border-b border-slate-800 px-6`. Each tab: `<a href="/settings/{{tab}}" class="px-4 py-2.5 text-sm transition border-b-2">`. Active: `text-slate-50 border-indigo-500`. Inactive: `text-slate-400 hover:text-slate-200 border-transparent`.
**Lucide icons:** none.
**Variants:** by `current_tab`.
**Example invocation:** `{% include "components/settings_tabs.html" with {"current_tab": "llm-provider"} %}`
**Mockup reference:** bundle `screens/Settings.jsx`.

#### `provider_card.html`

**Purpose:** LLM provider option card on Settings · LLM Provider tab.
**Used by:** Screen 11 (Settings · LLM Provider).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `provider` | dict | yes | — | `{id, name, model_default, description, kind (CLOUD/LOCAL)}` |
| `selected` | bool | yes | — | Drives radio + indigo border |

**Visual spec:** `flex items-start gap-3 p-4 rounded-lg border-2 cursor-pointer transition`. Selected: `border-indigo-500 bg-indigo-500/5`. Unselected: `border-slate-700 hover:border-slate-600`. Hidden radio + body. Body: name (`text-base font-medium`), description (`text-xs text-slate-400 mt-1`), kind badge (`CLOUD` indigo or `LOCAL` emerald, mono text-[10px]).
**Lucide icons:** `circle` / `circle-check` (selected radio).
**Variants:** by `selected` × `kind`.
**Example invocation:**
```jinja
{% include "components/provider_card.html" with {
  "provider": {"id": "anthropic", "name": "Anthropic Claude", "kind": "CLOUD",
               "description": "Recommended · best resume bullet quality"},
  "selected": true
} %}
```
**Mockup reference:** bundle `screens/Settings.jsx:LLMTab` line 49.

#### `cost_card.html`

**Purpose:** Small cost/usage card (THIS MONTH, AVG / GENERATION, RATE LIMIT).
**Used by:** Screen 11 (Settings · LLM Provider).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `label` | string | yes | — | Caption |
| `value` | string | yes | — | Big value |
| `sub` | string | no | — | Smaller subtitle |

**Visual spec:** Identical structure to `kpi_card.html` but smaller. `bg-slate-900 border border-slate-800 rounded-lg p-4`. Label, value, sub same as KPI but without delta.
**Lucide icons:** none.
**Variants:** none.
**Example invocation:**
```jinja
{% include "components/cost_card.html" with {"label": "THIS MONTH", "value": "$3.42", "sub": "≈412k tokens"} %}
```
**Mockup reference:** bundle `screens/Settings.jsx:MiniStat` line 201.

#### `deployment_status_card.html`

**Purpose:** "Self-hosted · active · v0.4.2 · uptime 14d" status header on Deployment tab.
**Used by:** Screen 11 (Settings · Deployment).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `mode` | enum (`self-hosted` / `cloud`) | yes | — | Drives badge tone |
| `status` | string | yes | — | Active / paused / starting |
| `version` | string | yes | — | e.g. `0.4.2` |
| `meta` | string | yes | — | "docker-compose · uptime 14d 6h · last restart Apr 14" |
| `update_available_version` | string | no | — | If newer version exists |

**Visual spec:** `flex items-center gap-4 p-5 bg-slate-900 border border-slate-800 rounded-lg`. Left: `deployment_badge.html` + status text + version (`font-mono text-sm text-slate-300`). Center: meta (`text-sm text-slate-400`). Right: `Restart` (refresh icon, secondary) + `Update v{{update_available_version}}` (download icon, primary, only when update available).
**Lucide icons:** `refresh-ccw`, `download`.
**Variants:** by `mode` × `status` × update availability.
**Example invocation:**
```jinja
{% include "components/deployment_status_card.html" with {
  "mode": "self-hosted", "status": "active", "version": "0.4.2",
  "meta": "docker-compose · uptime 14d 6h · last restart Apr 14"
} %}
```
**Mockup reference:** bundle `screens/Settings.jsx:DeploymentTab` line 211.

#### `log_tail.html`

**Purpose:** Terminal-style streaming log display.
**Used by:** Screen 11 (Settings · Deployment).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `log_path` | string | yes | — | Header subtitle (e.g. `~/.naavik/logs · live tail`) |
| `lines` | list of `{timestamp, level, message}` | yes | — | Pre-rendered log lines |
| `streaming` | bool | no | `true` | Show pulsing STREAMING dot |

**Visual spec:** outer `bg-slate-900 border border-slate-800 rounded-xl overflow-hidden`. Header: `px-4 py-3 border-b border-slate-800 flex items-center gap-3`. macOS dots (`#EF4444`, `#F59E0B`, `#10B981`, h-3 w-3 rounded-full each). Path label (`font-mono text-xs text-slate-300`). STREAMING chip (cyan, pulsing dot). Right: Pause / Copy buttons. Body: `<pre>` element `bg-slate-950 px-4 py-3.5 max-h-[280px] overflow-auto font-mono text-xs leading-relaxed text-slate-300`. Each line via `log_line` macro: timestamp (slate-400), level (cyan/amber/rose color-coded), message.
**HTMX hook:** `hx-ext="sse" sse-connect="/api/v1/settings/deployment/logs" sse-swap="logline"` on the `<pre>` element. Pause toggles a class disabling auto-scroll.
**Lucide icons:** `pause`, `copy`.
**Variants:** `streaming` toggle.
**Example invocation:** `{% include "components/log_tail.html" with {"log_path": "~/.naavik/logs · live tail", "lines": tail_lines, "streaming": true} %}`
**Mockup reference:** bundle `screens/Settings.jsx:DeploymentTab` lines 211–264.

#### `on_disk_card.html`

**Purpose:** "On disk" path card showing data dir / secrets / config / snapshots.
**Used by:** Screen 11 (Settings · Deployment).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `paths` | list of `{label, path, sub, icon}` | yes | — | Path entries |

**Visual spec:** `grid grid-cols-2 lg:grid-cols-4 gap-4`. Each card: `p-4 bg-slate-900 border border-slate-800 rounded-lg`. Icon (16px, slate-400). Label (`text-xs uppercase tracking-wide text-slate-500 font-medium`). Path (`font-mono text-sm text-slate-200 mt-1`). Sub (`text-xs text-slate-500 mt-1`).
**Lucide icons:** any (per row's `icon`).
**Variants:** none.
**Example invocation:**
```jinja
{% include "components/on_disk_card.html" with {
  "paths": [
    {"label": "DATA DIR", "path": "~/.naavik/data", "sub": "12 MB · 47 jobs · 12 applications", "icon": "database"},
    {"label": "SECRETS", "path": "~/.naavik/secrets.enc", "sub": "aes-256-gcm · 3 keys", "icon": "lock"},
    ...
  ]
} %}
```
**Mockup reference:** bundle `screens/Settings.jsx:PathRow` line 187.

#### `connection_status_card.html`

**Purpose:** Inline status card returned from `POST /_fragments/settings/test-connection`.
**Used by:** Screen 11 (Settings · LLM Provider — Test connection response).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `ok` | bool | yes | — | Drives tone |
| `latency_ms` | int | no | — | If ok |
| `model` | string | no | — | If ok |
| `error_code` | int | no | — | If !ok |
| `error_message` | string | no | — | If !ok |

**Visual spec:** Composes `info_card.html` (tone=success when ok else danger). Body — ok: "Connection ok · responded in {{ latency_ms }}ms · model {{ model }}" (cyan-tinted). Error: "Couldn't reach {{ provider }} API: {{ error_code }} {{ error_message }} — check key" (rose-tinted).
**Lucide icons:** `check-circle-2` (ok), `alert-circle` (error).
**Variants:** `ok`, `error`.
**Example invocation (returned from server):**
```jinja
{% include "components/connection_status_card.html" with {
  "ok": true, "latency_ms": 412, "model": "claude-3.5-sonnet-20250219"
} %}
```
**Mockup reference:** SCREENS.md § 11 LLM Provider tab.

#### `_source_row.html`

**Purpose:** Per-source row on the Settings · Sources sub-tab — composes the enable toggle, configured/unconfigured indicator, last-run status chip + timestamp, schedule, resolved rate-limit, and a `<details>` popover for per-source configuration. Plan 49 / `0.2.0.16`.
**Used by:** Screen 11 (Settings · Sources). Included six times by `pages/_settings_sources.html`, once per JobSource (LinkedIn / Workday / Greenhouse / Lever / Ashby / Indeed).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `view` | dict | yes | — | Composed by `_build_sources_view` in `src/ui/routes/settings.py`. Keys: `source` (str), `label` (str), `icon` (Lucide name), `enabled` (bool), `configured` (bool), `last_run` (dict or None), `schedule` (str), `rate_limit` (dict `{rpm, delay_lo, delay_hi}`), `configure` (dict `{kind: "env"|"db", ...}`) |

**Visual spec:** `flex flex-col gap-3 py-4 sm:flex-row sm:items-start sm:gap-4`. Left cell: 32px icon tile (`bg-slate-800/80`) + label + configured chip (emerald/slate) + last-run meta (status chip tone-mapped per status; mono schedule next to it). Rate-limit caption (mono, `text-[11px] text-slate-500`) below row meta. Right cell: toggle (`peer-checked:bg-indigo-500`) stacked above `<details>` Configure popover.
**Lucide icons:** `check-circle-2`, `circle`, `chevron-down`, plus per-source icons (`linkedin`, `briefcase`, `leaf`, `git-branch`, `globe`, `search`).
**Variants:** by `view.enabled` × `view.configured` × `view.last_run.status_value` × `view.configure.kind`.
**Example invocation:**
```jinja
{% with view=v %}
  {% include "components/_source_row.html" %}
{% endwith %}
```
**Canonical contract:** `docs/design/SOURCES_UI.md` § C.

#### `_rate_limit_editor.html`

**Purpose:** Per-source rate-limit form (rpm + delay_lo + delay_hi) rendered inside each `_source_row.html` popover. HTMX form posts flat `<source>_rpm` / `_lo` / `_hi` fields to `PUT /api/v1/settings/sources`; server-side reassembles into the `scraper_rate_limits[<source>]` nested-dict shape + validates via `RateLimitConfig` (rpm in [0.1, 600]; delay in [0, 600]; lo <= hi). Plan 58 / `0.2.7.06`.
**Used by:** Screen 11 (Settings · Sources). Included once per `_source_row.html` (every source — 6 times per panel render).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `view` | dict | yes | — | Same dict the parent `_source_row.html` consumes. Reads `view.source` (used to namespace form-field names) + `view.rate_limit.{rpm, delay_lo, delay_hi}` (the resolved override-or-fallback values rendered as form defaults). |

**Visual spec:** `flex flex-col gap-2 text-xs`. Three-column grid of numeric inputs (`grid grid-cols-3 gap-2`) styled `bg-slate-900 border border-slate-800 text-slate-100 font-mono text-xs`. Hint text under inputs: `rpm in [0.1, 600]; delay in [0, 600]s; lo <= hi.`. Save button: indigo primary `px-2.5 py-1 rounded bg-indigo-500 hover:bg-indigo-400`. CSRF token injected via plan 45 Jinja context-processor (the `<body hx-boost>` parent already carries the global X-CSRF-Token header; this form also declares it explicitly for clarity).
**Lucide icons:** none.
**Variants:** none.
**Example invocation:**
```jinja
{# Rendered inside _source_row.html's popover; not a standalone include. #}
{% include "components/_rate_limit_editor.html" %}
```
**Canonical contract:** `docs/design/SOURCES_UI.md` § H (forward pointer — `0.2.7.06` ships this).

#### `_keywords_editor.html`

**Purpose:** LinkedIn / Indeed keywords + location form rendered inside the `kind="db"` branch of `_source_row.html`'s popover. Single text input takes a comma-separated keyword list; comma-split happens server-side (drops empties + strips whitespace). Free-text location with 200-char `maxlength`. HTMX POST to `PUT /api/v1/settings/sources`. Plan 58 / `0.2.7.06`.
**Used by:** Screen 11 (Settings · Sources) — included once per `kind="db"` source (LinkedIn + Indeed only; not env-kind sources, not Workday).
**API:**
| Variable | Type | Required | Default | Description |
|---|---|---|---|---|
| `view` | dict | yes | — | Same dict the parent `_source_row.html` consumes. Reads `view.source` (must be `"linkedin"` or `"indeed"`; used to namespace `<source>_keywords` + `<source>_location` form-field names) + `view.configure.keywords` (list[str]; joined with `, ` for the text input default) + `view.configure.location` (str). |

**Visual spec:** `flex flex-col gap-2 text-xs border-t border-slate-800 pt-3` (separator from the rate-limit editor above). Two stacked single-line inputs (`bg-slate-900 border border-slate-800 text-slate-100 font-mono text-xs`), keywords first then location. Save button shares the indigo primary style with `_rate_limit_editor.html`.
**Lucide icons:** none.
**Variants:** none — same shape for LinkedIn + Indeed.
**Example invocation:**
```jinja
{# Rendered inside _source_row.html's popover {% elif kind=="db" %} branch. #}
{% include "components/_keywords_editor.html" %}
```
**Canonical contract:** `docs/design/SOURCES_UI.md` § H (forward pointer — `0.2.7.06` ships this).

---

### H.12 Skeletons

Skeletons render dimensions matching their loaded counterpart, with shimmer animation (`nk-shimmer` keyframe in `base.html`). Used as `hx-indicator` targets per INTERACTIONS.md § A.5.

#### `swipe_card_skeleton.html`

**Purpose:** Loading placeholder while next-card fragment fetches.
**Used by:** Screen 7 (Discover) `hx-indicator` for `/_fragments/discover/next-card`.
**API:** none.
**Visual spec:** `w-[460px] bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden htmx-indicator`. Top band: `h-20` solid `bg-slate-800`. Body: `p-5 flex flex-col gap-3` with grey-block placeholders matching `swipe_card.html` layout dimensions. Shimmer via `nk-shimmer` 1.5s linear infinite.
**Lucide icons:** none.
**Variants:** none.
**Example invocation:** `{% include "components/swipe_card_skeleton.html" %}`
**Mockup reference:** none — defined here.

#### `tracking_card_skeleton.html`

**Purpose:** Placeholder for tracking card during board/list view-toggle swap or Sortable drop.
**Used by:** Screen 9 (Tracking).
**API:** none.
**Visual spec:** Same as `tracking_card.html` outer dimensions — `flex flex-col gap-2 p-3 bg-slate-900 border border-slate-800 rounded-lg htmx-indicator`. Inside: 3 grey blocks (avatar circle, role line, status row) with shimmer.
**Lucide icons:** none.
**Variants:** none.
**Example invocation:** `{% include "components/tracking_card_skeleton.html" %}`
**Mockup reference:** none.

#### `priority_action_row_skeleton.html`

**Purpose:** Placeholder for priority action row while list refreshes.
**Used by:** Screen 3 (Overview).
**API:** none.
**Visual spec:** `flex items-center gap-3 px-4 py-3 rounded-lg htmx-indicator`. Index slot, icon slot, two text-line shimmer rows, urgency badge slot, CTA button slot.
**Lucide icons:** none.
**Variants:** none.
**Example invocation:** `{% include "components/priority_action_row_skeleton.html" %}`
**Mockup reference:** none.

#### `email_signal_row_skeleton.html`

**Purpose:** Placeholder for email signal row while SSE first-paint or refresh.
**Used by:** Screen 3 (Overview), Screen 9 (Tracking integrations email signal feed).
**API:** none.
**Visual spec:** `flex items-center gap-3 py-2.5 htmx-indicator`. Avatar circle, two text shimmer rows, status pill slot, score slot, time slot.
**Lucide icons:** none.
**Variants:** none.
**Example invocation:** `{% include "components/email_signal_row_skeleton.html" %}`
**Mockup reference:** none.

#### `bullet_edit_row_skeleton.html`

**Purpose:** Placeholder for bullet edit row during save/regen/HTMX swap.
**Used by:** Screen 5 (Profile editor) — fragment swaps after save.
**API:** none.
**Visual spec:** `flex items-start gap-2 px-3 py-2.5 rounded-lg htmx-indicator`. Drag-handle slot, two text shimmer rows, tag chips slot, action icons slot.
**Lucide icons:** none.
**Variants:** none.
**Example invocation:** `{% include "components/bullet_edit_row_skeleton.html" %}`
**Mockup reference:** none.

---

## I · Macros (`_macros.html`)

The single macros file imported on every page via `{% from "components/_macros.html" import ... %}`. Phase 1 macros:

```jinja
{% macro tag_chip(label, selected=False) -%}
  <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono
              {% if selected %}bg-indigo-500/15 text-indigo-200 ring-1 ring-indigo-500/40
              {% else %}bg-slate-800 text-slate-300{% endif %}
              hover:bg-slate-700 transition">{{ label }}</span>
{%- endmacro %}

{% macro score_circle(score, size="default") -%}
  {# … 0–100 SVG circle, color-thresholded; size = compact|default|hero #}
{%- endmacro %}

{% macro status_dot(status) -%}
  <span class="inline-block h-2 w-2 rounded-full {{ STATUS_DOT_COLORS[status] }}"></span>
{%- endmacro %}

{% macro kbd(key) -%}
  <span class="inline-flex items-center justify-center min-w-[24px] h-6 px-1.5 rounded
              bg-slate-800 border border-slate-700 text-[11px] font-mono text-slate-300">{{ key }}</span>
{%- endmacro %}

{% macro meta_item(icon, value) -%}
  <span class="inline-flex items-center gap-1 font-mono text-xs text-slate-300">
    <i data-lucide="{{ icon }}" class="h-3.5 w-3.5 text-slate-500"></i>
    {{ value }}
  </span>
{%- endmacro %}

{% macro chip(label, tone="slate") -%}
  {# generic chip, used inline in tailored_bullet_row, swipe_card, tracking_card, etc. #}
{%- endmacro %}

{% macro log_line(timestamp, level, message) -%}
  {# single line of log_tail body #}
{%- endmacro %}

{% macro deployment_badge(mode) -%}
  {# self-hosted (emerald) | cloud (indigo) #}
{%- endmacro %}

{% macro filter_chip(name, label, value=None, active=False, icon=None) -%}
  {#
    Plan 36 (`0.2.0.11`) filter_toolbar chip primitive. Each chip is a clickable
    `<summary>` that toggles a sibling `<details>` popover. `name` is the
    JobFilter field name (e.g. `source`); `value` is the currently-selected
    value rendered next to the label. `active` flips the indigo ring.
    Used 4× per render in filter_toolbar.html (source, visa, seniority, score_min).
    Toggle-style chips (remote_only, include_duplicates) inline their own
    button/<label> markup since they don't need a popover.
  #}
{%- endmacro %}
```

Add per-domain macros only when a domain grows past ~10 macros.

---

## J · Component-to-screen index (cross-reference)

| Screen | Components used (per SCREENS.md per-screen "Components" line + this catalog) |
|---|---|
| 1 Login | `auth_shell`, `card`, `input`, `button`, `info_card`, `version_pill`, `api_status_dot`, `spinner` |
| 2 Onboarding | `auth_shell`, `step_indicator`, `dropzone`, `extraction_checklist`, `extracted_field_row`, `progress_bar`, `ai_badge`, `info_card` |
| 3 Overview | `sidebar`, `kpi_card`, `priority_action_row`, `email_signal_row`, `status_dot`, `pipeline_strip`, `followup_banner` (compact), `email_signal_row_skeleton`, `priority_action_row_skeleton` |
| 4 Profile | `sidebar`, `profile_hero`, `contact_chip`, `experience_card`, `bullet_row`, `tag_chip`, `section_anchor_nav`, `application_readiness_card`, `avatar`, `empty_state` (per-section) |
| 5 Profile editor | `sidebar`, `editor_field`, `editor_card`, `bullet_edit_row`, `application_qs_form`, `autosave_indicator`, `tag_picker`, `bullet_edit_row_skeleton`, `confirm_modal` (Discard / Remove role) |
| 6 Bullet editor (modal) | `modal`, `tag_picker`, `selection_override`, `bullet_textarea`, `field_label`, `info_card`, `confirm_modal` (Delete bullet) |
| 7 Discover | `sidebar`, `swipe_card`, `score_circle`, `match_breakdown`, `score_card` (plan 72), `discover_action_bar`, `swipe_action_btn`, `discover_stats_strip`, `up_next_card`, `tip_card`, `keyboard_hints`, `kbd`, `swipe_card_skeleton`, `empty_state`, `tag_chip`, `avatar`, `filter_toolbar` (plan 36), `_filter_hidden_inputs` (plan 36), `filter_chip` macro (plan 36) |
| 8 Discover · review & apply | `sidebar`, `apply_topbar`, `match_breakdown`, `score_card` (plan 72), `warm_intro_card`, `tailored_bullet_row` (rationale arg per plan 72), `cover_letter_section`, `screener_question_card`, `apply_action_bar`, `ai_badge`, `tag_chip`, `avatar`, `confirm_modal` (Discard draft) |
| 9 Tracking | `sidebar`, `tracking_board`, `tracking_card`, `tracking_list_row`, `integration_card`, `provider_chip`, `followup_banner`, `stage_column`, `view_toggle`, `tracking_card_skeleton`, `status_badge`, `score_circle`, `avatar`, `empty_state` |
| 10 Outreach | `sidebar`, `outreach_app_row`, `outreach_message_card`, `contact_card`, `recommended_move_card`, `linkedin_status_chip`, `provider_chip`, `outreach_timeline`, `ai_badge`, `avatar`, `confirm_modal` (Disconnect LinkedIn) |
| 11 Settings | `sidebar`, `settings_tabs`, `provider_card`, `cost_card`, `deployment_status_card`, `log_tail`, `on_disk_card`, `connection_status_card`, `_source_row` (plan 49), `integration_card`, `deployment_badge`, `confirm_modal` (Delete account / Disconnect Gmail) |
| 12 Job detail (plan 36) | `sidebar`, `job_topbar` (plan 36), `avatar`, `tag_chip`, `chip` macro, `empty_state` (when applicable), Lucide icons (`arrow-left`, `external-link`, `sparkles`, `bookmark`, `x`, `copy`). See `docs/design/JOB_UI.md` § D for the composition contract. |

Common across every authenticated screen: `sidebar`, `button`, `card`, `tag_chip`, `status_dot`, `toast` (OOB region). Common across all screens: `spinner` (in-button), `toast`.
