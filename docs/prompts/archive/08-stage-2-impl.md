---
Status: USED
Type: implementation kickoff
Plan: docs/plans/archive/08-stage-2-impl.md
Authored: 2026-05-01
Used: 2026-05-01
---

# Naavik · Stage 2 component library — implementation kickoff

Paste this entire file as the first message of a fresh Claude Code session. The repo is at `/home/nightwatcher/personal/dev/naavik`.

## Goal

Implement `docs/design/COMPONENTS.md` 1:1 — produce 85 Jinja partials at `src/ui/templates/components/`, the `_macros.html` bundle (8 macros), the rewritten `src/ui/templates/base.html` per COMPONENTS.md § F.1, the cross-cutting JS handlers (`src/ui/static/base.js` + `src/ui/static/keys.js` + `src/ui/static/styles.css`), the `GET /_modal/confirm` fragment endpoint, and the `GET /_design/components` fixture page that renders every component in every variant. After this lands, plan 09 (Stage 3 page implementation) can compose every Phase 1 screen entirely from these partials.

## Required reading (in order)

1. `AGENTS.md` — agent guide, workflow lifecycle. Read § Workflow carefully.
2. `CLAUDE.md` — Claude Code conventions for this repo.
3. `ROADMAP.md` § Phase 1 § Implementation waves → Wave 2 row + the per-wave checklist.
4. `docs/plans/08-stage-2-impl.md` — **THE PLAN.** Status: APPROVED. Read end-to-end. The build batches in § B are your ship sequence.
5. `DESIGN.md` (root) — visual contract: tokens, typography, components, voice. v1.3 (DRAFT row in Status Pipeline).
6. `docs/design/COMPONENTS.md` — 2,125-line component catalog. § A inventory (85 components × 12 groups). § F.1 base.html structure. § F.2 base.js handlers. § G build order. § H per-component specs. § I macros. § J component-to-screen index.
7. `docs/design/INTERACTIONS.md` — cross-cutting HTMX patterns. § A.4 persistent IDs. § B.6 tag picker `:has()`. § E.4 confirm modal route shape. § G toast region. § I.1 required base.js scripts.
8. `docs/design/SCREENS.md` — context for what each component is used for; you don't ship screens here, but you will look up which variants each screen needs.
9. `docs/design/mockups/README.md` — bundle JSX layout (gitignored locally; if missing, fall back to the per-component visual specs in COMPONENTS.md § H).

Skim only after reading the above:
- `docs/design/BACKEND.md` § B (page routes — context for the route reorganization in plan 08 § I) and § C (`/_modal/confirm` endpoint).
- `docs/design/DATA_MODEL.md` § D (enums — `ApplicationStatus`, etc.; `STATUS_DOT_COLORS` map needs all 6 keys).

Open question answers (locked by user 2026-05-01): stay on Tailwind CDN for plan 08 (switch to PostCSS in a follow-up plan); DaisyUI fully removed; mobile drawer replicated in plain Tailwind+JS; `keys.js` ships empty registry (Discover map is plan 09); `/_design/components` env-var-gated (`NAAVIK_DEBUG=1`) — Wave 4 swaps to `Settings.debug`; per-batch enforcement happens here in this prompt; no Playwright snapshots of the fixture page in plan 08.

## Deliverables

| Path | Description |
|---|---|
| `src/ui/templates/base.html` | Rewrite per COMPONENTS.md § F.1 — DaisyUI removed; Lucide icons via `<i data-lucide="...">`; persistent IDs (`#modal-region`, `#toast-region`, `#sidebar-badge-jobs`, `#sidebar-badge-tracking`); body-level `hx-boost`, `hx-headers`, `hx-ext="sse,response-targets"`, `data-template`; CSRF meta tag; pinned CDN versions per plan § C |
| `src/ui/templates/components/*.html` | 85 Jinja partials per COMPONENTS.md § A inventory — flat directory, snake_case filenames matching the catalog exactly |
| `src/ui/templates/components/_macros.html` | 8 macros per COMPONENTS.md § I (`tag_chip`, `score_circle`, `status_dot`, `kbd`, `meta_item`, `chip`, `log_line`, `deployment_badge`) |
| `src/ui/templates/pages/_design_components.html` | Single-file fixture page; 12 anchored sections matching the build batches; renders every component × every variant with hardcoded inline sample data |
| `src/ui/templates/placeholder.html` | Migrated to `{% extends "base.html" %}` + `{% block main %}` + explicit `active_sidebar` arg from each placeholder route |
| `src/ui/static/base.js` | 6 cross-cutting handlers + mobile drawer toggle per plan § E |
| `src/ui/static/keys.js` | Empty registry skeleton per plan § E (Discover handlers added in plan 09) |
| `src/ui/static/styles.css` | Animation keyframes (`nk-pulse`, `nk-shimmer`, `nk-blink`); tag-picker `:has(input:checked)` rules; HTMX loading utilities; mobile sidebar drawer rules |
| `src/ui/templates_setup.py` | Shared `Jinja2Templates` instance + `templates.env.globals` registrations (e.g. `STATUS_DOT_COLORS`, the 9-tag vocabulary list) |
| `src/ui/routes/__init__.py` | Empty marker |
| `src/ui/routes/auth.py` | `GET /login`, `GET /onboarding` — placeholder handlers passing `active_sidebar=None` for Login (auth shell), `active_sidebar="overview"` for Onboarding |
| `src/ui/routes/overview.py` | `GET /` — placeholder; `active_sidebar="overview"` |
| `src/ui/routes/profile.py` | `GET /profile`, `GET /profile/edit` — placeholders; `active_sidebar="profile"` |
| `src/ui/routes/discover.py` | `GET /discover`, `GET /discover/{job_id}` — placeholders; `active_sidebar="jobs"` |
| `src/ui/routes/tracking.py` | `GET /tracking` — placeholder; `active_sidebar="tracking"` |
| `src/ui/routes/outreach.py` | `GET /outreach` — placeholder; `active_sidebar="outreach"` |
| `src/ui/routes/settings.py` | `GET /settings`, `GET /settings/{tab}` — placeholders; `active_sidebar="settings"` |
| `src/ui/routes/fragments.py` | `GET /_modal/confirm?title=&message=&action=&label=&tone=&method=` — returns `confirm_modal.html` from query params |
| `src/ui/routes/design.py` | `GET /_design/components` — gated on `NAAVIK_DEBUG=1` env var; renders the fixture page |
| `src/main.py` | Shrunk to lifespan + middleware + router mounting + `/api/health`. Mounts every router from `src/ui/routes/`. |
| `tests/test_components.py` | Parametrized over all 85 components — renders each via Jinja `Environment.get_template(...).render(**example_kwargs)` with kwargs from COMPONENTS.md per-component example invocation |
| `tests/test_design_components_route.py` | TestClient: `GET /_design/components` returns 200 with all 12 anchor IDs when `NAAVIK_DEBUG=1`; 404 without |
| `tests/test_confirm_modal_route.py` | TestClient: `GET /_modal/confirm?...` query-param round-trip works; missing required param → 422 |

## Build sequence (ship per-batch, gate on each)

Execute the 12 batches per plan 08 § B and COMPONENTS.md § G. **Each batch passes the per-batch acceptance gate before the next batch starts.**

For each batch:
1. Implement the components (and any infra changes for that batch — e.g. batch 1 includes `base.html` + `_macros.html` + `static/*` + route reorg).
2. Add the components to the `_design/components` fixture page section.
3. Run `uv run ruff check .` + `uv run ruff format --check .` — must pass.
4. Run `uv run fastapi dev src/main.py` — must boot without warning.
5. `curl -s "http://localhost:8000/_design/components"` (with `NAAVIK_DEBUG=1`) — must return 200; HTML body must contain that batch's anchor section.
6. Open `http://localhost:8000/_design/components` in a browser — every variant in the section must render without 500 / Jinja error / browser console error / missing icon.
7. Trigger one HTMX swap on the fixture page (e.g. confirm modal open) — Lucide icons must paint in the swapped fragment.
8. Move to the next batch.

The 12 batches in order (5 + 15 + 5 + 5 + 11 + 4 + 8 + 6 + 8 + 6 + 7 + 5 = **85 components**):

1. **Shell + base.html + JS/CSS scaffolding** — base.html rewrite, `auth_shell`, `sidebar`, `version_pill`, `api_status_dot`, `deployment_badge`, `_macros.html` (`deployment_badge` macro only at this stage), `static/styles.css`, `static/base.js` skeleton (all 6 handlers stubbed), `static/keys.js` empty registry, route reorganization, `placeholder.html` migration.
2. **Atomics (15)** — `button`, `input`, `card`, `tag_chip`, `status_dot`, `status_badge`, `score_circle`, `ai_badge`, `kbd`, `field_label`, `info_card`, `spinner`, `toast`, `empty_state`, `avatar`. Add the remaining 7 macros to `_macros.html` (`tag_chip`, `score_circle`, `status_dot`, `kbd`, `meta_item`, `chip`, `log_line`).
3. **Forms (5)** — `editor_field`, `editor_card`, `autosave_indicator`, `modal`, `confirm_modal`. Add the `GET /_modal/confirm` route in `src/ui/routes/fragments.py`.
4. **Onboarding (5)** — `step_indicator`, `dropzone`, `extraction_checklist`, `extracted_field_row`, `progress_bar`.
5. **Profile / Bullet (11)** — `profile_hero`, `contact_chip`, `experience_card`, `bullet_row`, `section_anchor_nav`, `application_readiness_card`, `application_qs_form`, `bullet_edit_row`, `tag_picker`, `selection_override`, `bullet_textarea`.
6. **Overview (4)** — `kpi_card`, `priority_action_row`, `email_signal_row`, `pipeline_strip`.
7. **Discover (8)** — `swipe_card`, `match_breakdown`, `discover_action_bar`, `swipe_action_btn`, `discover_stats_strip`, `up_next_card` (with **both** `state="default"` AND `state="stuck"` variants per COMPONENTS.md `up_next_card` API), `tip_card`, `keyboard_hints`.
8. **Discover · review (6)** — `apply_topbar`, `warm_intro_card`, `tailored_bullet_row`, `cover_letter_section`, `screener_question_card`, `apply_action_bar`.
9. **Tracking (8)** — `view_toggle`, `provider_chip`, `integration_card`, `followup_banner`, `stage_column`, `tracking_card`, `tracking_list_row`, `tracking_board`.
10. **Outreach (6)** — `outreach_app_row`, `recommended_move_card`, `outreach_message_card`, `contact_card`, `linkedin_status_chip`, `outreach_timeline`.
11. **Settings (7)** — `settings_tabs`, `provider_card`, `cost_card`, `deployment_status_card`, `log_tail`, `on_disk_card`, `connection_status_card`.
12. **Skeletons (5)** — `swipe_card_skeleton`, `tracking_card_skeleton`, `priority_action_row_skeleton`, `email_signal_row_skeleton`, `bullet_edit_row_skeleton`.

## Quality bar (final gate before hand-back)

Run all in the dev shell (`nix develop` then):

```bash
uv run ruff check .                    # must be clean
uv run ruff format --check .           # must be clean
uv run pytest tests/                   # all tests pass
NAAVIK_DEBUG=1 uv run fastapi dev src/main.py  # server boots in <2s, no warnings
```

Manual checks (browser at `http://localhost:8000`):

- Every placeholder route (`/`, `/login`, `/onboarding`, `/profile`, `/profile/edit`, `/discover`, `/discover/123`, `/tracking`, `/outreach`, `/settings`, `/settings/llm-provider`) returns 200 with the right active sidebar item.
- `/_design/components` renders all 12 sections without 500 / Jinja error.
- Confirm modal: visit fixture page, click the demo trigger, modal opens; press Escape — closes; click backdrop — closes; click "Cancel" — closes.
- Resize browser to mobile width (≤768px) — sidebar collapses to drawer; hamburger toggle reveals it.
- Network tab clean: no 404s for `/static/*` files; no failed CDN script loads.
- DevTools console clean across every route + the fixture page: no `lucide is not defined`, no `Sortable is undefined`, no Jinja undefined-variable errors.
- Trigger one fragment swap (HTMX confirm-modal open from the fixture page) — Lucide icons in the swapped DOM render correctly.

`grep` checks (must all return empty):

```bash
rg --no-config '\[#[0-9a-fA-F]' src/ui/templates/                # no arbitrary Tailwind hex
rg --no-config 'style="[^"]+"' src/ui/templates/components/      # no inline styles
rg --no-config '<script' src/ui/templates/components/             # no <script> tags in components
rg --no-config 'kanban-square' src/ui/templates/components/sidebar.html  # Tracking icon must be `inbox`, not kanban-square
rg --no-config 'data-lucide="sparkles"' src/ui/templates/components/tag_chip.html  # tag_chip must NOT have sparkle
rg --no-config 'class="[^"]*\bdark:' src/ui/templates/            # no light-mode prefixes
rg --no-config 'class="[^"]*\b(drawer|btn-|badge-)' src/ui/templates/  # no DaisyUI classes
```

Single documented exception: `progress_bar.html` may use `style="width: {{ value * 100 }}%"` (Tailwind can't express runtime fractions cleanly). All other `style=` are forbidden.

## Forbidden patterns

These will fail review — do not introduce:

- ❌ Any framework other than HTMX + Jinja2 + Tailwind (no React, Vue, Svelte, Solid, Alpine.js without explicit reason).
- ❌ DaisyUI classes (`drawer`, `btn`, `btn-primary`, `badge`, `card-body`, `divider`, etc.) — Tailwind utilities only.
- ❌ Heroicons / Phosphor / FontAwesome / inline custom SVGs (except `compass` brand mark + `score_circle` SVG ring — both documented in plan 08 § J).
- ❌ Light-mode `dark:` Tailwind prefixes (single dark mode in MVP; light mode is Phase 6).
- ❌ Inline `style="..."` attributes (one exception: `progress_bar.html` width).
- ❌ Arbitrary Tailwind hex (`bg-[#abc123]`, `text-[#fff]`, etc.) — every value must come from DESIGN.md tokens.
- ❌ `<script>` tags inside any component partial.
- ❌ `<script>` tags inside any HTMX fragment response — modal close uses `HX-Trigger: closeModal` response header per INTERACTIONS.md § E.2.
- ❌ Sparkle (`<i data-lucide="sparkles">`) on `tag_chip.html`. Sparkle is reserved for AI-generated **content** (cover-letter paragraphs, drafted screener answers, recommended outreach moves, model attribution chips) and lives in `ai_badge.html` only.
- ❌ `%` mark on score circles. The score is `0–100`, no `%`, no "match" word.
- ❌ `kanban-square` icon for the Tracking sidebar item — use `inbox` (per SCREENS.md § Sidebar IA).
- ❌ Sidebar width `w-60` (240px) — use `w-64` (256px) per DESIGN.md § Spacing & Layout.
- ❌ Theme toggle in the sidebar bottom — single dark mode in MVP. Sidebar bottom shows `deployment_badge` only.
- ❌ `oneline` / `detailed` bullet split on `bullet_textarea.html` — single long-form text only. AI trims at apply time.
- ❌ `default_include` toggle on bullets — use `selection_override` per `selection_override.html`.
- ❌ Metric sub-fields (`revenue`, `percentage`, `team_size`) on bullets.
- ❌ `/generate/cover-letter` or `/generate/resume` standalone routes — both flows live inside `/discover/{id}` only.
- ❌ Funnel / BarChart / LineChart components on Overview — explicitly NOT in MVP, deferred to Phase 6.
- ❌ Modal-confirm route at path-param `/_modal/confirm/{action_id}` — must be query-param `/_modal/confirm?title=&message=&action=&label=&tone=&method=` per BACKEND.md § C / INTERACTIONS.md § E.4.
- ❌ Reverting any of plan 08's 7 open-question decisions without explicit user instruction.

## Pinned CDN versions

Use exactly these (newer or older silently break things):

```html
<script src="https://unpkg.com/[email protected]/dist/umd/lucide.min.js"></script>
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
<script src="https://unpkg.com/htmx.org@2.0.4/dist/ext/sse.js"></script>
<script src="https://unpkg.com/htmx.org@2.0.4/dist/ext/response-targets.js"></script>
<script src="https://cdn.jsdelivr.net/npm/[email protected]/Sortable.min.js"></script>
```

Tailwind CDN stays on `https://cdn.tailwindcss.com` (no version pin — there's no API surface). PostCSS build is a follow-up plan.

## Hand-back format

When complete, post a single message to the user containing:

1. **File list** — every file created or modified, grouped by directory. Should be ~95 files (85 components + ~10 infra).
2. **Test results** — paste the output of `uv run pytest tests/ -v` (must be all green) and `uv run ruff check .` (must be clean).
3. **Fixture screenshot** — describe the `/_design/components` page contents (12 sections, each with N components, no console errors, Lucide icons render). If you can attach a screenshot, do — otherwise list which sections rendered cleanly.
4. **Manual smoke summary** — placeholder routes (200/each), mobile sidebar drawer toggles, confirm modal opens/closes, Lucide icons paint after swap.
5. **Any deviations from the plan** — every divergence with reason. If you discovered a bug in COMPONENTS.md or had to revise a component spec mid-implementation, list it here so the user can fold the correction into COMPONENTS.md.
6. **Archive step done** — confirm:
   - `mv docs/plans/08-stage-2-impl.md docs/plans/archive/08-stage-2-impl.md` and front-matter `Status: APPROVED` → `Status: EXECUTED`.
   - `mv docs/prompts/08-stage-2-impl.md docs/prompts/archive/08-stage-2-impl.md` and front-matter `Status: ACTIVE` → `Status: USED`.
   - `ROADMAP.md` § Phase 1 § Wave 2 row marked `[x]` with deliverable note + bumped `Last updated:`.
7. **Next** — confirm Wave 3 (plan 09) is now unblocked. The user pastes `docs/prompts/09-stage-3-impl.md` next.

If you hit a blocker (CDN library doesn't pin to the listed version, a component spec contradicts a screen spec, etc.), STOP and post a question to the user instead of making a judgment call. Mid-flight scope creep is the most common way these sessions drift.

Good luck.
