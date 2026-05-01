---
Status: APPROVED
Type: implementation
Authored: 2026-04-30
Last updated: 2026-05-01
Approved: 2026-05-01
Depends on: 03-component-catalog (graduated → docs/design/COMPONENTS.md), 06-interactions-spec (graduated → docs/design/INTERACTIONS.md)
Follow-up: switch CDN-pinned libraries (Lucide / HTMX / Sortable / Tailwind) to bundled deps once a real frontend build pipeline lands — recorded as a deferred concern, no active plan yet.
---

# 08 · Stage 2 component library implementation

## Goal

Implement `docs/design/COMPONENTS.md` 1:1 — produce 85 Jinja partials at `src/ui/templates/components/`, the `_macros.html` bundle (8 macros), the rewritten `src/ui/templates/base.html` per COMPONENTS.md § F.1, the cross-cutting JS handlers (`src/ui/static/base.js` + `src/ui/static/keys.js` skeleton + `src/ui/static/styles.css`), the `GET /_modal/confirm` fragment endpoint, and the `GET /_design/components` fixture page that renders every component in every variant. After this lands, plan 09 (Stage 3 page implementation) can compose every Phase 1 screen entirely from these partials without inventing one-off markup.

## Context / why

Plan 03 graduated to `docs/design/COMPONENTS.md` (2,111 lines, 85 component specs across 12 groups, full per-component API + visual spec + variants + example invocation + bundle reference). The component library doesn't exist yet on disk — the directory `src/ui/templates/components/` is empty, there is no `_macros.html`, no `static/base.js`, no `static/keys.js`, no `static/styles.css`, no `/_design/components` fixture, and no `/_modal/confirm` endpoint. Plan 09 (page templates) cannot start.

The existing `src/main.py` + `src/ui/templates/{base,placeholder}.html` scaffold is a Phase 0 stub that:

- Loads DaisyUI from CDN and uses the DaisyUI `drawer` for mobile (the new contract uses Tailwind utilities + a tiny JS drawer toggle).
- Renders the sidebar with **inline custom SVG icons** (the new contract uses Lucide via `<i data-lucide="name">`).
- Drives the active sidebar item via `request.url.path` string compares (the new contract takes an explicit `active` arg on `sidebar.html`).
- Mounts every placeholder route from `main.py` directly (the new contract splits routes per-domain under `src/ui/routes/*.py`).
- Lacks the persistent IDs (`#modal-region`, `#toast-region`, `#sidebar-badge-jobs`, `#sidebar-badge-tracking`) that COMPONENTS.md § F.1 + INTERACTIONS.md § A.4 require.
- Lacks the `data-template`, `hx-boost`, `hx-headers`, `hx-ext="sse,response-targets"` body-level attributes that INTERACTIONS.md § I depends on.
- Has no `<meta name="csrf-token">` tag.

Plan 08 replaces the scaffold cleanly in one coherent unit so plan 09 has a clean substrate.

## Proposal

### A · Scope

**In scope (this plan ships these files):**

| Surface               | Files                                                                                                                                                                                                             |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Component partials    | 85 `*.html` files at `src/ui/templates/components/` per COMPONENTS.md § A inventory                                                                                                                               |
| Macros                | `src/ui/templates/components/_macros.html` with 8 macros (`tag_chip`, `score_circle`, `status_dot`, `kbd`, `meta_item`, `chip`, `log_line`, `deployment_badge`) per COMPONENTS.md § I                             |
| Base layout           | `src/ui/templates/base.html` rewritten per COMPONENTS.md § F.1                                                                                                                                                    |
| Auth-shell base       | (handled by `components/auth_shell.html`, which Login + Onboarding will extend in plan 09)                                                                                                                        |
| Static JS             | `src/ui/static/base.js` (6 cross-cutting handlers per COMPONENTS.md § F.2 + INTERACTIONS.md § I.1), `src/ui/static/keys.js` (registry skeleton — Discover handlers added in plan 09)                              |
| Static CSS            | `src/ui/static/styles.css` — animation keyframes (`nk-pulse`, `nk-shimmer`, `nk-blink`), tag-picker `:has(input:checked)` styles, mobile-drawer styles, plus a couple of utilities Tailwind can't cleanly express |
| Fragment route        | `GET /_modal/confirm?title=&message=&action=&label=&tone=&method=` returning `components/confirm_modal.html`                                                                                                      |
| Fixture route         | `GET /_design/components` returning `pages/_design_components.html` (every component × every variant)                                                                                                             |
| Fixture page          | `src/ui/templates/pages/_design_components.html` — single file, inline sample data, no `sample_data.py` dependency                                                                                                |
| Route split           | `src/ui/routes/{auth,overview,profile,discover,tracking,outreach,settings,fragments,design}.py` modules; `main.py` shrinks to lifespan + middleware + router mounting + health                                    |
| Placeholder migration | `src/ui/templates/placeholder.html` migrated to `{% extends "base.html" %}` with `{% block main %}` and explicit `active_sidebar` arg — placeholder pages still respond 200 across the transition                 |
| Tests                 | `tests/test_components.py` (per-component render test), `tests/test_design_components_route.py` (fixture page integration test)                                                                                   |

**Out of scope (deferred):**

- ❌ Real page templates at `src/ui/templates/pages/<screen>.html` other than the `_design_components` fixture — plan 09.
- ❌ Real route handlers consuming sample data — plan 09.
- ❌ HTMX wiring of actual page interactions (Discover swipes, Profile autosave, Tracking Kanban drops, etc.) — plan 09 / plan 10 Wave 6.
- ❌ DB models, Alembic migrations, auth — plan 10 Wave 3.
- ❌ `src/db/sample_data.py` — plan 10 Wave 3 (the fixture page hardcodes its own sample data inline).
- ❌ `Settings.debug` real persistence — Phase 1 the fixture-page gate is the env var `NAAVIK_DEBUG=1`; plan 10 Wave 3 swaps to the persisted `Settings.debug`.
- ❌ CSRF token issuing — Phase 1 plan 08 defaults `csrf_token` to empty string; plan 10 Wave 3 wires the real value.
- ❌ Mobile bottom-sheet variant for components beyond `modal.html` — covered already in `modal.html` per COMPONENTS.md § H.3.

### B · Build batches (per COMPONENTS.md § G)

12 batches, ordered so primitives land before composites depend on them. **Each batch passes its own acceptance gate before the next batch begins** — runs `uv run ruff check`, `uv run ruff format --check`, the dev server boots without warning, and every batch's components render in `/_design/components` without 500 / browser console errors.

| #   | Batch                                    | Components / files                                                                                                                                                                                                                                                                                                                                                                           | Acceptance gate                                                                                                                                                                                                                        |
| --- | ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Shell + base.html + JS / CSS scaffolding | base.html (rewrite per § F.1), `auth_shell.html`, `sidebar.html`, `version_pill.html`, `api_status_dot.html`, `deployment_badge.html`, `_macros.html` (just `deployment_badge` macro at this stage), `static/styles.css`, `static/base.js` (skeleton — all 6 handlers stubbed), `static/keys.js` (empty registry), placeholder.html migrated, route modules created and mounted from main.py | Server boots; every existing placeholder route responds 200; sidebar renders with the right active item; Lucide icons paint; mobile drawer toggles                                                                                     |
| 2   | Atomics (15)                             | `button`, `input`, `card`, `tag_chip`, `status_dot`, `status_badge`, `score_circle`, `ai_badge`, `kbd`, `field_label`, `info_card`, `spinner`, `toast`, `empty_state`, `avatar`; remaining 7 macros (`tag_chip`, `score_circle`, `status_dot`, `kbd`, `meta_item`, `chip`, `log_line`) added to `_macros.html`                                                                               | `/_design/components` Atomics gallery renders every variant — every button tone × size, all 6 status dots, score circle at 3 sizes × 4 thresholds, all 4 toast tones, every avatar size + shape                                        |
| 3   | Forms (5)                                | `editor_field`, `editor_card`, `autosave_indicator`, `modal`, `confirm_modal`; `GET /_modal/confirm` route lands in `src/ui/routes/fragments.py`                                                                                                                                                                                                                                             | Confirm modal opens via query-param trigger; backdrop click + Escape both close; Save returns `HX-Trigger: closeModal` round-trip works; modal mobile-bottom-sheet variant renders at <768px                                           |
| 4   | Onboarding (5)                           | `step_indicator`, `dropzone`, `extraction_checklist`, `extracted_field_row`, `progress_bar`                                                                                                                                                                                                                                                                                                  | Step indicator renders at each of 3 steps; checklist shows all 3 statuses (done / active / queued) on one row each; gradient progress bar fills correctly                                                                              |
| 5   | Profile / Bullet (11)                    | `profile_hero`, `contact_chip`, `experience_card`, `bullet_row`, `section_anchor_nav`, `application_readiness_card`, `application_qs_form`, `bullet_edit_row`, `tag_picker`, `selection_override`, `bullet_textarea`                                                                                                                                                                         | Hero card renders with sample profile inline; bullet edit row hover reveals drag handle + edit/delete actions; tag picker `:has(input:checked)` selected-state CSS works; selection_override radio behavior works                      |
| 6   | Overview (4)                             | `kpi_card`, `priority_action_row`, `email_signal_row`, `pipeline_strip`                                                                                                                                                                                                                                                                                                                      | KPI delta colors emerald (positive) / rose (negative); priority action row renders all 4 kinds (offer / interview / reply / silent) with matching urgency badges; pipeline_strip shows 5 visible stages with status_dot colors         |
| 7   | Discover (8)                             | `swipe_card`, `match_breakdown`, `discover_action_bar`, `swipe_action_btn`, `discover_stats_strip`, `up_next_card`, `tip_card`, `keyboard_hints`                                                                                                                                                                                                                                             | Swipe card top band gradient renders; score circle thresholds work at compact size; action bar shows 4 buttons with keycap hints; keyboard_hints macro composes correctly                                                              |
| 8   | Discover · review (6)                    | `apply_topbar`, `warm_intro_card`, `tailored_bullet_row`, `cover_letter_section`, `screener_question_card`, `apply_action_bar`                                                                                                                                                                                                                                                               | Tailored bullet row renders both selected and excluded variants; cover letter section view + edit modes both render; screener card shows `drafted`, `auto`, and `user` source variants; apply action bar renders disabled state        |
| 9   | Tracking (8)                             | `view_toggle`, `provider_chip`, `integration_card`, `followup_banner`, `stage_column`, `tracking_card`, `tracking_list_row`, `tracking_board`                                                                                                                                                                                                                                                | Board view renders 4 visible columns + closed toggle; list view renders as `<table>` with all 8 columns; followup banner amber tint correct; provider chip connected vs disconnected variants both render                              |
| 10  | Outreach (6)                             | `outreach_app_row`, `recommended_move_card`, `outreach_message_card`, `contact_card`, `linkedin_status_chip`, `outreach_timeline`                                                                                                                                                                                                                                                            | Recommended move card renders amber tint with AI draft body; contact card renders all 4 state pill variants (`referred_you`, `awaiting_reply`, `no_reply_7d`, `cold`); message card renders draft (cyan) vs sent (slate) variants      |
| 11  | Settings (7)                             | `settings_tabs`, `provider_card`, `cost_card`, `deployment_status_card`, `log_tail`, `on_disk_card`, `connection_status_card`                                                                                                                                                                                                                                                                | Tabs render with active underline; provider_card selected vs unselected variants both render; log_tail renders sample lines with macOS traffic-light dots + STREAMING pulse; connection_status_card renders both ok and error variants |
| 12  | Skeletons (5)                            | `swipe_card_skeleton`, `tracking_card_skeleton`, `priority_action_row_skeleton`, `email_signal_row_skeleton`, `bullet_edit_row_skeleton`                                                                                                                                                                                                                                                     | Each skeleton's outer dimensions match its loaded counterpart's (manual visual check in /\_design/components — overlay each skeleton next to its real component); shimmer animation visible via `nk-shimmer` keyframe                  |

The fixture page (`pages/_design_components.html`) grows incrementally with each batch — start it with batch 1's section stubs, fill in each section as its batch lands.

### C · base.html rewrite (per COMPONENTS.md § F.1)

Full structure replaces the existing v1. Key changes from v1:

| v1 (current)                                       | v2 (this plan)                                                                                                    |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | ----------------- |
| DaisyUI loaded from CDN                            | DaisyUI **removed** — Tailwind utilities only                                                                     |
| Inline custom SVG icons in sidebar                 | Lucide icons via `<i data-lucide="name">`                                                                         |
| Sidebar inline (~110 lines in base.html)           | Sidebar via `{% include "components/sidebar.html" with {...} %}`                                                  |
| Active item via `request.url.path` string compares | Active item via explicit `active` arg on sidebar                                                                  |
| `{% block content %}` only                         | `{% block main %}` for sidebar layout; `{% block body %}` overridable for auth shell                              |
| No persistent IDs                                  | `#modal-region`, `#toast-region`, `#sidebar-badge-jobs`, `#sidebar-badge-tracking`                                |
| No body-level HTMX attrs                           | `hx-boost="true"`, `hx-headers='{"X-CSRF-Token": "..."}'`, `hx-ext="sse,response-targets"`, `data-template="..."` |
| No CSRF meta tag                                   | `<meta name="csrf-token" content="{{ csrf_token                                                                   | default('') }}">` |
| HTMX 2.0.4 only                                    | HTMX 2.0.4 + sse extension + response-targets extension + Sortable.js + Lucide                                    |
| No external CSS                                    | `<link rel="stylesheet" href="/static/styles.css">`                                                               |
| No base.js / keys.js                               | `<script src="/static/keys.js">` + `<script src="/static/base.js">` at bottom                                     |

Sketch (full file rendered in the kickoff prompt):

```html
<!doctype html>
<html lang="en" data-theme="naavik">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Naavik{% endblock %}</title>
  <meta name="csrf-token" content="{{ csrf_token | default('') }}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/styles.css">
  <script src="https://cdn.tailwindcss.com"></script>
  <script>tailwind.config = { theme: { extend: { fontFamily: { sans: ['Inter', ...], mono: ['"JetBrains Mono"', ...] } } } };</script>
</head>
<body
  hx-boost="true"
  hx-headers='{"X-CSRF-Token": "{{ csrf_token | default('') }}"}'
  hx-ext="sse,response-targets"
  data-template="{{ active_template_path | default('') }}"
  class="bg-slate-950 text-slate-100">

  {% block body %}
    <div class="flex min-h-screen">
      {% include "components/sidebar.html" with {
        "active": active_sidebar | default(none),
        "user_name": current_user_name | default("Shyam Padia"),
        "user_initials": current_user_initials | default("SP"),
        "deployment_mode": deployment_mode | default("self-hosted"),
        "unswiped_count": unswiped_count | default(0),
        "followup_count": followup_count | default(0),
      } %}
      <main class="flex-1 p-6 lg:p-8">
        {% block main %}{% endblock %}
      </main>
    </div>
  {% endblock %}

  <div id="modal-region"></div>
  <div id="toast-region" class="fixed top-4 right-4 z-50 flex flex-col gap-2 max-w-md pointer-events-none"></div>
  <div id="sidebar-badge-jobs" hx-swap-oob="true"></div>
  <div id="sidebar-badge-tracking" hx-swap-oob="true"></div>

  <script src="https://unpkg.com/[email protected]/dist/umd/lucide.min.js"></script>
  <script src="https://unpkg.com/htmx.org@2.0.4"></script>
  <script src="https://unpkg.com/htmx.org@2.0.4/dist/ext/sse.js"></script>
  <script src="https://unpkg.com/htmx.org@2.0.4/dist/ext/response-targets.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/[email protected]/Sortable.min.js"></script>
  <script src="/static/keys.js"></script>
  <script src="/static/base.js"></script>
</body>
</html>
```

**No `{% block content %}`.** Plan 08 migrates `placeholder.html` to `{% block main %}` in the same change so there is no transitional shim. Removing the v1 block name is part of this batch.

**Auth-shell pages** (Login, Onboarding) override `{% block body %}` with the centered-card layout from `auth_shell.html`. Plan 09 wires that override on the page templates; `auth_shell.html` itself is just the centered wrapper.

### D · `_macros.html` (per COMPONENTS.md § I)

8 macros, single file imported per page: `{% from "components/_macros.html" import tag_chip, score_circle, status_dot, kbd, meta_item, chip, log_line, deployment_badge %}`.

The `STATUS_DOT_COLORS` dict (`{"DRAFT": "bg-slate-500", "APPLIED": "bg-indigo-500", ...}`) is registered in `templates.env.globals` from FastAPI startup so the `status_dot` macro can look up the color class without arg threading.

### E · `base.js` handlers (per INTERACTIONS.md § I.1)

Single file at `src/ui/static/base.js`. Six handlers, attached on `DOMContentLoaded`:

| Handler               | Trigger event                                             | Behavior                                                                                                                                                                             |
| --------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Lucide reinit         | `htmx:afterSwap` on `body`                                | `lucide.createIcons()` — paints SVG icons in newly-swapped DOM. Also called once on `DOMContentLoaded`.                                                                              |
| Sortable.js auto-init | `htmx:afterSettle` on `body` + once on `DOMContentLoaded` | For every `[data-sortable="true"]` not already initialized, `Sortable.create(el, { handle: '.drag-handle', animation: 150 })`. Mark with `el._sortable = true` to avoid double-init. |
| Modal-close listener  | `closeModal` event on `body`                              | `document.querySelectorAll('dialog[open]').forEach(d => d.close())`. Fires when any HTMX response carries `HX-Trigger: closeModal`.                                                  |
| Toast auto-dismiss    | `htmx:oobAfterSwap` on `body`                             | If `e.target.querySelector('.toast-success, .toast-info')` matches, `setTimeout(() => toast.remove(), 4000)`. Warning + danger toasts persist until manual dismiss.                  |
| Optimistic rollback   | `htmx:responseError` + `htmx:sendError` on `body`         | If `e.detail.target?.dataset.rollback`, restore stash via `e.detail.target.outerHTML = decodeURIComponent(stash)` + show danger toast "Couldn't save — restored. Try again?".        |
| Upload progress       | `htmx:xhr:progress` on `body`                             | If `progress = document.getElementById('upload-progress')` and `e.detail.lengthComputable`, set `progress.value = (e.detail.loaded / e.detail.total) * 100`.                         |

Plus one **mobile drawer toggle** handler (because DaisyUI is removed): listens for clicks on `[data-sidebar-toggle]` (the mobile hamburger button), toggles `data-sidebar-open` on `<body>`. CSS in `styles.css` translates that into the sidebar slide-in.

`keys.js` ships with an **empty handlers registry** — Discover (`'/discover'`) and Discover · review (`'/discover/:id'`) maps land in plan 09 when those pages exist:

```javascript
// src/ui/static/keys.js
const handlers = {};

function activeTabIs(tab) {
  return document.querySelector("[data-active-tab]")?.dataset.activeTab === tab;
}

window.addEventListener("keydown", (e) => {
  const page = document.body.dataset.template;
  const map = handlers[page];
  if (!map) return;
  const key = (e.metaKey ? "meta+" : "") + (e.ctrlKey ? "ctrl+" : "") + e.key;
  if (map[key]) {
    e.preventDefault();
    map[key]();
  }
});
```

### F · `styles.css`

Minimal supplementary stylesheet at `src/ui/static/styles.css`:

```css
/* Animation keyframes referenced by skeletons + AI shimmer + status pulse */
@keyframes nk-shimmer {
  /* skeleton shimmer 1.5s linear infinite */
}
@keyframes nk-pulse {
  /* AI generation glow 2s ease-in-out infinite */
}
@keyframes nk-blink {
  /* STREAMING dot 1.2s linear infinite */
}

/* Tag picker selected variant — Tailwind doesn't compile :has() in v3 CDN mode */
.tag-chip:has(input:checked) {
  background: rgba(99, 102, 241, 0.15);
  color: rgb(196, 181, 253);
  box-shadow: 0 0 0 1px rgba(99, 102, 241, 0.4);
}

/* HTMX loading-state CSS (companion to .htmx-indicator) */
.htmx-request .htmx-show-loading {
  display: inline-flex;
}
.htmx-request .htmx-hide-loading {
  display: none;
}

/* Mobile sidebar drawer (DaisyUI removed) */
@media (max-width: 1023px) {
  body[data-sidebar-open="false"] aside.sidebar {
    transform: translateX(-100%);
  }
  body[data-sidebar-open="true"] aside.sidebar {
    transform: translateX(0);
  }
  aside.sidebar {
    transition: transform 250ms ease;
  }
}
```

### G · `/_modal/confirm` endpoint

Lives in `src/ui/routes/fragments.py`:

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="src/ui/templates")

@router.get("/_modal/confirm", response_class=HTMLResponse)
async def confirm_modal(
    request: Request,
    title: str,
    message: str,
    action: str,
    label: str = "Confirm",
    tone: str = "danger",
    method: str = "post",
):
    return templates.TemplateResponse(request, "components/confirm_modal.html", {
        "title": title,
        "message": message,
        "confirm_action_url": action,
        "confirm_label": label,
        "confirm_tone": tone,
        "confirm_method": method,
    })
```

Mounted from `main.py` with no auth dep (Phase 1 plan 08 has no auth yet; plan 10 Wave 3 adds the gate).

### H · `/_design/components` fixture page

`src/ui/routes/design.py` renders `pages/_design_components.html`. Phase 1 gate: env var `NAAVIK_DEBUG=1`. Plan 10 Wave 3 swaps to `Settings.debug`.

```python
import os
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/_design/components", response_class=HTMLResponse)
async def design_components(request: Request):
    if not os.environ.get("NAAVIK_DEBUG"):
        raise HTTPException(404)
    return templates.TemplateResponse(request, "pages/_design_components.html", {
        "active_template_path": "/_design/components",
        "active_sidebar": None,  # not in main IA
    })
```

The fixture template is single-file, ~600–900 lines, with 12 `<section id="batch-N-...">` blocks (matching § B's batches). Each section renders every variant of every component in that batch with hardcoded inline sample data:

```jinja
{% from "components/_macros.html" import tag_chip, score_circle, status_dot, kbd, meta_item, chip %}
{% extends "base.html" %}
{% block main %}
<header class="mb-8">
  <h1 class="text-3xl font-semibold text-slate-50">Component fixture</h1>
  <p class="text-sm text-slate-400 mt-1">Every component in every variant, gated on <code>NAAVIK_DEBUG=1</code>. Used for visual QA during plan 08 implementation.</p>
  <nav class="mt-4 flex flex-wrap gap-2 text-xs">
    <a href="#batch-1-shell" class="...">1 Shell</a>
    <a href="#batch-2-atomics" class="...">2 Atomics</a>
    ... # 12 anchor links total
  </nav>
</header>

<section id="batch-2-atomics" class="mt-12">
  <h2 class="text-xl font-semibold text-slate-50 mb-4">2 · Atomics</h2>

  <h3 class="text-sm uppercase tracking-wide text-slate-500 mt-6 mb-3">Buttons</h3>
  <div class="flex flex-wrap gap-3">
    {% include "components/button.html" with {"variant": "primary", "label": "Primary"} %}
    {% include "components/button.html" with {"variant": "secondary", "label": "Secondary"} %}
    {% include "components/button.html" with {"variant": "ghost", "label": "Ghost"} %}
    {% include "components/button.html" with {"variant": "danger", "label": "Delete", "icon": "trash-2"} %}
    {% include "components/button.html" with {"variant": "icon", "icon": "x"} %}
    {% include "components/button.html" with {"variant": "primary", "label": "Disabled", "disabled": true} %}
  </div>

  <h3 class="text-sm uppercase tracking-wide text-slate-500 mt-6 mb-3">Score circles</h3>
  <div class="flex items-center gap-4">
    {{ score_circle(score=92, size="hero") }}     {# emerald, hero #}
    {{ score_circle(score=72, size="default") }}  {# indigo, default #}
    {{ score_circle(score=51, size="default") }}  {# amber #}
    {{ score_circle(score=28, size="compact") }}  {# rose, compact #}
  </div>

  ... # all 15 atomic components × variants
</section>

... # 12 sections total
{% endblock %}
```

The fixture page is the **single source of truth** for "this component renders". Plan 08's per-batch acceptance gate is satisfied by this page rendering without 500 + browser console errors.

### I · main.py / route reorganization

Existing `src/main.py` mounts placeholder routes inline (~130 lines). Plan 08 splits into per-domain routers:

```
src/ui/routes/
├── __init__.py
├── auth.py         # GET /login, GET /onboarding (placeholder)
├── overview.py     # GET / (placeholder)
├── profile.py      # GET /profile, GET /profile/edit (placeholder)
├── discover.py     # GET /discover, GET /discover/{job_id} (placeholder)
├── tracking.py     # GET /tracking (placeholder)
├── outreach.py     # GET /outreach (placeholder)
├── settings.py     # GET /settings, GET /settings/{tab} (placeholder)
├── fragments.py    # GET /_modal/confirm + future fragments
└── design.py       # GET /_design/components fixture
```

Each placeholder route migrates to its domain module and explicitly passes `active_sidebar` + `screen` + `route` + `section`:

```python
# src/ui/routes/overview.py
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def overview(request: Request):
    return templates.TemplateResponse(request, "placeholder.html", {
        "screen": "Overview",
        "route": "/",
        "section": "3",
        "active_sidebar": "overview",
        "active_template_path": "/",
    })
```

`main.py` shrinks to:

```python
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from config import settings
from ui.routes import auth, overview, profile, discover, tracking, outreach, settings as ui_settings, fragments, design

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="Naavik", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="src/ui/static"), name="static")

app.include_router(auth.router)
app.include_router(overview.router)
app.include_router(profile.router)
app.include_router(discover.router)
app.include_router(tracking.router)
app.include_router(outreach.router)
app.include_router(ui_settings.router)
app.include_router(fragments.router)
app.include_router(design.router)

@app.get("/api/health")
async def health():
    return {"status": "ok"}
```

`Jinja2Templates(directory="src/ui/templates")` becomes a shared instance — exposed via a small helper module (`src/ui/templates_setup.py`) so all routers import the same instance and `templates.env.globals` registrations (e.g. `STATUS_DOT_COLORS`) take effect everywhere.

### J · Token compliance + forbidden patterns (matches DESIGN.md + COMPONENTS.md)

Every component must:

| Rule                                                                                                               | Enforcement                                                                                                                                                                |
| ------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tailwind classes only — no `[#abc123]` arbitrary values                                                            | Manual review + grep in CI (`rg -g '*.html' '\[#[0-9a-fA-F]'` returns empty)                                                                                               |
| No inline `style="..."`                                                                                            | Single documented exception: `progress_bar.html` `style="width: {{ value * 100 }}%"` (Tailwind can't express a runtime fraction). Grep in CI tolerates the one occurrence. |
| Lucide icons only via `<i data-lucide="name" stroke-width="1.5">`                                                  | Two documented exceptions: `compass` brand mark + `score_circle` SVG ring; both inline `<svg>` for layout reasons                                                          |
| No `<script>` tags inside any component partial                                                                    | Grep CI                                                                                                                                                                    |
| No `<script>` tags inside any HTMX fragment response                                                               | All fragment endpoints return HTML-only; modal close uses `HX-Trigger: closeModal` header per INTERACTIONS.md § E.2                                                        |
| Tag chips: `font-mono`, slate or indigo — **no AI sparkle on tag chips**                                           | `tag_chip.html` body has no `<i data-lucide="sparkles">`. Grep CI: in the file `tag_chip.html`, sparkle is forbidden.                                                      |
| Score circles: 0–100 number, **no `%`, no "match" word**                                                           | `score_circle` macro / partial output asserted in unit test                                                                                                                |
| Status pipeline: 6 values exactly                                                                                  | `STATUS_DOT_COLORS` registry has DRAFT + APPLIED + RECRUITER_SCREEN + ONSITE_LOOP + OFFER + CLOSED keys (not 5, not 7)                                                     |
| Sidebar Tracking icon = `inbox`                                                                                    | `sidebar.html` literal grep                                                                                                                                                |
| Sidebar width = `w-64` (256px)                                                                                     | `sidebar.html` literal grep                                                                                                                                                |
| No light-mode variants (`dark:` prefixes)                                                                          | Grep CI returns empty                                                                                                                                                      |
| No DaisyUI classes (`drawer`, `btn`, `badge`, etc.)                                                                | Grep CI returns empty                                                                                                                                                      |
| 9-tag vocabulary only (`ai-ml · backend · frontend · devops · data-eng · genai · leadership · platform · product`) | `tag_chip` macro asserts label ⊆ vocab in dev mode                                                                                                                         |

### K · Tests

`tests/test_components.py`:

For each of the 85 components, render the partial via `Environment.get_template("components/<name>.html").render(**example_kwargs)` where `example_kwargs` matches the example invocation in COMPONENTS.md. Failure modes caught:

- Component file missing → `TemplateNotFound`
- Template syntax error → Jinja parse error
- Required variable missing → `UndefinedError` (Jinja in strict mode)
- Token compliance violations (sparkle on tag chip, `%` on score circle) → assertion on rendered HTML

The test file is a single parametrized test function with 85 cases.

`tests/test_design_components_route.py`:

- Boot the FastAPI app in test mode (TestClient).
- Set `NAAVIK_DEBUG=1`.
- `GET /_design/components` returns 200.
- Body contains `id="batch-1-shell"` through `id="batch-12-skeletons"` (12 anchors).
- Body contains every component group's heading text.
- Body contains zero `[#` arbitrary-hex tokens (sanity check).
- Without `NAAVIK_DEBUG`, route returns 404.

`tests/test_confirm_modal_route.py`:

- `GET /_modal/confirm?title=Foo&message=Bar&action=/api/x&label=Yes&tone=danger&method=delete` returns 200 with `<dialog>`, "Foo" title, "Bar" message, button with `hx-delete="/api/x"`.
- Missing required `title` → 422.

Run via `uv run pytest`.

### L · Risks + mitigations

| Risk                                            | Mitigation                                                                                                                                                                                                                          |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **DaisyUI removal breaks v1 mobile drawer**     | Plan 08 implements the drawer in plain Tailwind + `base.js` (`[data-sidebar-toggle]` toggles `data-sidebar-open` on `<body>`; `styles.css` translates to slide-in). Acceptance: clicking the mobile menu opens the sidebar overlay. |
| **CDN libraries are moving targets**            | Pin every CDN URL: HTMX 2.0.4, Lucide 0.469.0, Sortable.js 1.15.6, htmx-ext-sse 2.2.2, htmx-ext-response-targets 2.0.2. Tailwind CDN stays unpinned (it's the only one with no API surface).                                        |
| **`csrf_token` defaults to empty string**       | OK in Phase 1 — no auth dep yet, no backend rejects empty token. Plan 10 Wave 3 wires the real value.                                                                                                                               |
| **Tailwind CDN no-purge bundle is ~3 MB**       | Acceptable for plan 08's iteration speed. Plan 09 (or a follow-up plan) switches to a real PostCSS build. Document this trade-off in plan 08's archival note.                                                                       |
| **`:has(input:checked)` browser support**       | All evergreen browsers since Jan 2023. No IE / pre-2023-Safari fallback needed. Document in `styles.css` comment.                                                                                                                   |
| **`Settings.debug` doesn't exist yet**          | Phase 1: env var `NAAVIK_DEBUG=1`. Plan 10 Wave 3 swaps to `Settings.debug`. The fixture-page handler is one line of change.                                                                                                        |
| **Lucide icons fail to paint on first load**    | The `lucide.createIcons()` call on `DOMContentLoaded` covers initial paint; the `htmx:afterSwap` handler covers swap-time paint. Test both paths in `tests/test_design_components_route.py` via Playwright (optional Phase 1.x).    |
| **Sortable.js double-init on the same element** | `base.js` checks `el._sortable` before init.                                                                                                                                                                                        |
| **Component drift from COMPONENTS.md**          | `tests/test_components.py` parametrizes over the catalog; if a component's API changes in COMPONENTS.md but the partial isn't updated, the test fails.                                                                              |
| **Visual QA without Playwright**                | Plan 08 ships unit-render tests but doesn't require Playwright screenshots — that's plan 09's job (per-page visual diff against bundle JSX). Plan 08's visual QA is manual: open `/_design/components` and eyeball each section.    |

### M · Build order (informational)

The kickoff prompt sequences these batches; this plan doesn't prescribe a calendar. Rough shape:

```
Day 1: Batch 1 — shell + base.html + macros + base.js + styles.css + route reorganization
       Acceptance: server boots; placeholder routes 200; sidebar renders; Lucide icons paint.

Day 2: Batch 2 — atomics × 15 + remaining 7 macros
       Start /_design/components fixture page (sections 1–2 filled).

Day 3: Batches 3 + 4 — forms × 5 (incl. /_modal/confirm) + onboarding × 5
Day 4: Batches 5 + 6 — profile/bullet × 11 + overview × 4
Day 5: Batches 7 + 8 — discover × 8 + discover · review × 6
Day 6: Batches 9 + 10 — tracking × 8 + outreach × 6
Day 7: Batches 11 + 12 — settings × 7 + skeletons × 5
Day 8: Final ruff sweep, test pass, manual QA against bundle JSX, archive plan + prompt.
```

8 working days is generous — the actual ship time depends on the implementer.

### N · Out-of-scope items explicitly forbidden in this plan

- ❌ Real page templates beyond `pages/_design_components.html` — plan 09.
- ❌ HTMX wiring for actual page interactions (Discover swipes, Profile autosave, Tracking Kanban drops, etc.) — plan 09 / plan 10 Wave 6.
- ❌ DB models, Alembic migrations — plan 10 Wave 3.
- ❌ Auth (JWT, bcrypt, login flow) — plan 10 Wave 3.
- ❌ LLM provider abstraction — plan 10 Wave 3.
- ❌ Sample data module (`src/db/sample_data.py`) — plan 10 Wave 3 (the fixture page hardcodes inline).
- ❌ Real cover-letter SSE generation — plan 10 Wave 6.
- ❌ Light mode — Phase 6 only.
- ❌ Re-introducing oneline/detailed bullet split — removed in plan 01; permanently dropped.
- ❌ `/generate/cover-letter` or `/generate/resume` standalone routes — folded into Discover · review & apply (plan 09).
- ❌ `kanban-square` icon for Tracking — uses `inbox` per SCREENS.md.
- ❌ Sparkle on `tag_chip` — sparkle is for AI-generated **content** only.
- ❌ `%` mark on score circles, "match" word adjacent to scores.
- ❌ DaisyUI `drawer` / `btn` / `badge` / etc. classes anywhere.
- ❌ Theme toggle in sidebar (single dark mode v1).
- ❌ Funnel / BarChart / LineChart components (Phase 6 — Analytics-on-Overview era leftovers).

## Open questions

1. **Tailwind: stay on CDN or build now?** The CDN script (`cdn.tailwindcss.com`) disables purge, ships ~3 MB bundle. A real PostCSS build is more production-y but adds a Node toolchain. Recommendation: **stay on CDN for plan 08** (iteration speed > bundle size during a greenfield component build); switch to a real Tailwind build in a follow-up plan once Phase 1 page templates exist (probably plan 11). Risk if we never switch: production bundle bloat. Cost to switch later: low (component classes don't change, only the build pipeline).

2. **DaisyUI: remove fully or keep for one-offs?** COMPONENTS.md uses zero DaisyUI classes. DESIGN.md has a DaisyUI theme block but it's only consumed by `daisy-themes` — unused in MVP. Recommendation: **remove DaisyUI from base.html in plan 08**; flag the DESIGN.md DaisyUI theme block for cleanup in DESIGN.md v1.4 (post-plan-08 doc-realignment). The block doesn't actively break anything, but it's dead code.

3. **Mobile sidebar drawer: replicate v1 in plain JS or punt?** v1 used DaisyUI's drawer for mobile. Removing DaisyUI removes the drawer. Recommendation: **replicate in plan 08** — small `base.js` toggle (`[data-sidebar-toggle]` → `data-sidebar-open` on `<body>`) + a few `styles.css` rules. Cost: ~20 lines. Without this, mobile sidebar is broken until plan 09.

4. **Does `keys.js` ship empty or with the Discover handlers stubbed?** Plan 09 owns Discover. Recommendation: **ship empty registry** in plan 08; plan 09 adds the Discover map when the page lands.

5. **Should the fixture page require auth?** Plan 08 has no auth dep yet. Phase 1: env-var gate (`NAAVIK_DEBUG=1`) only. Plan 10 Wave 3 adds the auth + `Settings.debug` gate.

6. **Per-batch ship vs all-at-once ship?** The kickoff prompt is the right place to enforce "each batch must pass before the next starts". Recommendation: **kickoff prompt enforces per-batch ruff + render gates**; plan 08 documents the gate but doesn't enforce a calendar.

7. **Visual QA discipline.** Plan 08 doesn't require Playwright screenshots (that's plan 09's per-page concern). Manual QA against `/_design/components` is sufficient. Should we still take Playwright snapshots of the fixture page for diff-detection across iterations? Recommendation: **defer**. Plan 09's per-screen Playwright runs catch regressions; the fixture page is internal-only.

## Approval checklist

User ticks each item before plan moves to APPROVED. Agent does NOT author the kickoff prompt until all are ticked.

### Scope coherence

- [x] § A — Building 85 partials + base.html + macros + 2 routes + fixture page + tests is one coherent unit (not too big to land cleanly, not so small that plan 09 starts before primitives exist).
- [x] § A out-of-scope list correctly defers DB / auth / page templates / sample data to plans 09 + 10.

### Build batches (§ B)

- [x] 12 batches in COMPONENTS.md § G order — Shell first, Skeletons last.
- [x] Each batch's components match COMPONENTS.md § A inventory exactly (counts: 5 / 15 / 5 / 5 / 11 / 4 / 8 / 6 / 8 / 6 / 7 / 5 = 85).
- [x] Per-batch acceptance gates are concrete + falsifiable.

### base.html rewrite (§ C)

- [x] Removes DaisyUI; replaces with Tailwind utilities + Lucide icons + custom `styles.css` mobile drawer.
- [x] Adds persistent IDs (`#modal-region`, `#toast-region`, `#sidebar-badge-jobs`, `#sidebar-badge-tracking`).
- [x] Adds body-level HTMX attrs (`hx-boost`, `hx-headers`, `hx-ext`, `data-template`).
- [x] Adds CSRF meta tag.
- [x] Pinned CDN versions (HTMX 2.0.4, Lucide 0.469.0, Sortable 1.15.6, sse 2.2.2, response-targets 2.0.2).
- [x] Migrates `placeholder.html` to `{% block main %}` in the same plan (no `{% block content %}` shim).

### Macros (§ D)

- [x] 8 macros per COMPONENTS.md § I (`tag_chip`, `score_circle`, `status_dot`, `kbd`, `meta_item`, `chip`, `log_line`, `deployment_badge`).
- [x] `STATUS_DOT_COLORS` registered as Jinja global.

### `base.js` + `keys.js` + `styles.css` (§ E + § F)

- [x] 6 cross-cutting handlers per INTERACTIONS.md § I.1 (Lucide reinit, Sortable auto-init, modal-close, toast auto-dismiss, optimistic rollback, upload progress).
- [x] Plus mobile drawer toggle (`[data-sidebar-toggle]`).
- [x] `keys.js` ships empty registry skeleton (Discover handlers in plan 09).
- [x] `styles.css` minimal: 3 keyframes + tag-picker `:has()` + HTMX loading utility + mobile drawer rules.

### Fragment + fixture routes (§ G + § H)

- [x] `GET /_modal/confirm?title=&message=&action=&label=&tone=&method=` — query params, not path-param `{action_id}` (per BACKEND.md / INTERACTIONS.md).
- [x] `GET /_design/components` gated on `NAAVIK_DEBUG=1` env var (Phase 1) → `Settings.debug` (plan 10 Wave 3 swap, one-line change).
- [x] Fixture page is single-file with hardcoded inline sample data (no `sample_data.py` dependency).
- [x] 12 anchored sections matching § B's batches.

### Route reorganization (§ I)

- [x] `src/ui/routes/{auth,overview,profile,discover,tracking,outreach,settings,fragments,design}.py` modules.
- [x] `main.py` shrinks to lifespan + middleware + router mounting + health.
- [x] Shared `templates` Jinja2Templates instance via `src/ui/templates_setup.py`.
- [x] All placeholder routes still respond 200 across the transition.

### Token compliance + forbidden patterns (§ J)

- [x] No `[#hex]` Tailwind arbitrary values (single `progress_bar` width style exception documented).
- [x] No inline `style="..."` outside the documented exception.
- [x] No `<script>` tags inside any component partial OR fragment response.
- [x] No DaisyUI classes anywhere.
- [x] No light-mode `dark:` prefixes anywhere.
- [x] `kanban-square` icon NEVER used for Tracking — `inbox` only.
- [x] Sparkle icon NEVER on `tag_chip` — only on `ai_badge` and AI-content surfaces.
- [x] Score circles render `0–100` integer only — no `%`, no "match" word.
- [x] 6-value status pipeline (DRAFT + 5 visible) — not 5, not 7.
- [x] Sidebar width `w-64` (256px), not `w-60` (240px).
- [x] 9-tag vocabulary only — no invented tags.

### Tests (§ K)

- [x] `tests/test_components.py` parametrized over all 85 components — renders each via Jinja Environment with example kwargs from COMPONENTS.md.
- [x] `tests/test_design_components_route.py` — fixture page returns 200 with all 12 anchors with `NAAVIK_DEBUG=1`; 404 without.
- [x] `tests/test_confirm_modal_route.py` — query-param round-trip works; missing required param → 422.
- [x] All tests run via `uv run pytest`.

### Risks (§ L)

- [x] DaisyUI removed; mobile drawer replicated in plain Tailwind + JS.
- [x] CDN libraries pinned to specific versions. (comment: this is okay for now but we should plan for this at a later point)
- [x] `csrf_token` defaults to empty string (auth not yet wired).
- [x] Tailwind CDN trade-off documented; switch to PostCSS deferred to follow-up plan.
- [x] Lucide icon paint covered both on `DOMContentLoaded` AND `htmx:afterSwap`.
- [x] Sortable.js double-init guarded.

### Out-of-scope explicit list (§ N)

- [x] No real page templates (plan 09).
- [x] No DB models / Alembic / auth (plan 10 Wave 3).
- [x] No sample_data module (plan 10 Wave 3).
- [x] No Playwright screenshots (plan 09 per-screen).
- [x] No light mode / theme toggle.
- [x] No oneline/detailed bullet split, no `/generate/*` routes, no `kanban-square`, no sparkle on tags, no `%` on scores, no Funnel/BarChart/LineChart on Overview.

### Open questions (§ Open questions)

- [x] Q1 Tailwind CDN vs build — recommend stay CDN; agree? - stay cdn
- [x] Q2 DaisyUI fully removed — agree? - yes
- [x] Q3 Mobile drawer replicated in plan 08 — agree? - yes
- [x] Q4 `keys.js` empty registry — agree? - yes
- [x] Q5 `/_design/components` env-var gate Phase 1 — agree? - yes
- [x] Q6 Per-batch enforcement in kickoff prompt — agree? - yes
- [x] Q7 No fixture-page Playwright snapshots in plan 08 — agree? - yes

Once every box is ticked, plan moves to APPROVED. Agent then authors `docs/prompts/08-stage-2-impl.md` driving a fresh implementation session.
