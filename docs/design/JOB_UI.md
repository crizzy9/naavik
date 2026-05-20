# Naavik · Job UI

> **Canonical reference** — graduated from `docs/plans/archive/36-0.2.0.11-htmx-job-ui.md` per `AGENTS.md` § Workflow step 4 (filed as ROADMAP row `0.2.0.11a`).
> **Status:** Active. This is the single source for the Discover-queue filter toolbar, the `/jobs/{id}` read-only Job-detail surface, the 6-axis JobFilter URL contract, and the HTMX patterns + IDOR boundaries the Job-domain UI relies on.
> **Last updated:** 2026-05-20 (plan 36 / `0.2.0.11` graduated; `0.2.0.11a` ships this doc).
> **Companion docs:** `docs/design/SCREENS.md` (functional spec per screen — entries #7 Discover + #12 Job detail), `docs/design/COMPONENTS.md` (component catalog — registers the 4 new Job-UI partials in § H.7 + § I), `docs/design/JOB_MODEL.md` (canonical `Job` + `JobScrapeRun` + `JobFilter` field reference + `job_service` 8-function contract), `docs/design/INTERACTIONS.md` (HTMX swap conventions referenced from § F below), `docs/design/BACKEND.md` § D.3 (Jobs / Discover route catalog).
> **Downstream plans depending on this contract:** `0.2.0.11b` (CSRF + IDOR on `save/skip` endpoints), `0.2.0.11c` (`JobRead` projection swap), `0.2.0.12` (notifications — may consume `/_fragments/jobs/{id}` for preview surfaces), future Phase 2.5 rows (multi-select source filter, tag-based filter chips, list-view toggle).

---

## A · One-paragraph contract

The Job UI is the operator-facing read surface for everything the scraper chain (`0.2.0.06`–`0.2.0.10`) persists into the `job` + `job_scrape_run` tables. It comprises two distinct screens — the existing Discover swipe queue (`/discover`, SCREENS.md § 7), wrapped with a 6-axis HTMX-driven filter chip-row toolbar that round-trips through `services.job_service.list_jobs(...)`, and a new read-only Job-detail page (`/jobs/{id}`, SCREENS.md § 12) that renders a single persisted Job in isolation with its source / scrape-run metadata and an action rail. The Discover queue is the entry point (Tinder-style swipe = filtered list with one big card at a time); `/jobs/{id}` is a destination reachable via "More info" affordances on the swipe card and from any future Tracking deep-link to a source Job. Both routes scope through the same IDOR boundary (`user_id` partitions on every query; cross-user requests return 404, never 403). All filter state is querystring-driven (`?source=&visa=&seniority=&remote_only=&score_min=&include_duplicates=`); chip clicks are `hx-get`s with `hx-push-url="true"` so the URL bar mirrors filter state and a hard refresh restores it. No new env var, on-disk path, CLI command, port, schedule, or operational surface is introduced by this contract — all wiring is route + template + service-call.

---

## B · Surface inventory

| Surface | Path | Kind | Implemented in |
|---|---|---|---|
| Discover (live + filtered) | `GET /discover` | full HTML page (`base.html`) | `src/ui/routes/discover.py:get_discover` |
| Discover queue fragment (chip round-trips swap here) | `GET /_fragments/discover/queue` | HTMX fragment (no chrome) | `src/ui/routes/discover.py:fragment_queue` |
| Job detail (full page, link-shareable) | `GET /jobs/{job_id}` | full HTML page (`base.html`) | `src/ui/routes/jobs.py:get_job_detail` |
| Job detail body fragment (drawer-ready, no chrome) | `GET /_fragments/jobs/{job_id}` | HTMX fragment | `src/ui/routes/jobs.py:get_job_detail_fragment` |
| Job JSON read | `GET /api/v1/jobs/{job_id}` | JSON | `src/ui/routes/jobs.py:get_job_json` (moved here from `discover.py` per plan 36 § A) |

Pre-existing surfaces this contract does **not** modify:

- `/discover/{id}` and `/_fragments/discover/expanded/{id}` — the application-workspace surface (SCREENS.md § 8). `/jobs/{id}` is a distinct, lower-fidelity read of the same Job.
- `/api/v1/discover/{job_id}/save`, `/api/v1/discover/{job_id}/skip`, `/api/v1/applications/{job_id}/auto-submit` — these continue to live in `src/ui/routes/discover.py`. The Job-detail page wires its right-rail action buttons to these existing endpoints (`docs/plans/archive/36-*.md` Deviations row 7; ROADMAP rows `0.2.0.11b` + `0.2.0.11c` track follow-up hardening).

---

## C · The 6-axis JobFilter URL contract

Plan 36 § D.3 surfaced 6 of `JobFilter`'s 11 fields for the MVP filter chip-row toolbar. The mapping (querystring key → `JobFilter` field) is canonical and the source of truth for both `parse_filters_from_query` and the per-chip `<input name=...>` attribute:

| Querystring key | `JobFilter` field | Type | Default | Chip kind | Default rendered chip text |
|---|---|---|---|---|---|
| `source` | `source` | `JobSource | None` (10 values) | `None` | `<details>` popover (radio list of 10 sources + "Any source") | "Source · ·" |
| `remote_only` | `remote_only` | `bool` | `False` | toggle (`indigo-tinted when on`) | "Remote only" |
| `visa` | `visa` | `VisaRestriction | None` (4 values) | `<details>` popover | "Visa · ·" |
| `seniority` | `seniority` | `SeniorityLevel | None` (7 values) | `<details>` popover | "Seniority · ·" |
| `score_min` | `score_min` | `float` (0.0–1.0) | `0.0` | `<details>` popover with `<input type="range">` slider | "Score ≥ ·" |
| `include_duplicates` | `include_duplicates` | `bool` | `False` | toggle (`amber-tinted when on`) | "Show duplicates" |

**Deferred axes** (intentionally not surfaced this contract; locked per plan 36 § D.3):

| `JobFilter` field | Why deferred | Future row |
|---|---|---|
| `company` | Too freeform for a chip; substring matching needs separate text-search UX. | `0.2.0.11d` (or similar) when text search lands. |
| `board` | Overlaps with `source` for MVP. | Defer indefinitely. |
| `queue_state` | Already handled by the existing Saved/Skipped/Up-next sidebar + legacy `?filter=saved` link. The chip toolbar honors `?queue_state=…` if present, but no chip surfaces it. | Defer; if needed, fold into the right-rail Saved card. |
| `score_max` | Single `score_min` slider is sufficient pre-scoring; range slider belongs to `0.3.0+`. | `0.3.0` scoring milestone. |
| `tag` | Tag chips need a multi-select with AND/OR semantics; tags become first-class at `0.3.0`. | `0.3.0`. |
| `posted_within_days` | Needs preset-chip UX design (24h / 7d / 30d). | Future Phase 2.5 row. |

### C.1 URL example

```
/discover?source=linkedin&remote_only=1&visa=sponsorship_available&seniority=senior&score_min=0.55&include_duplicates=0
```

- Values are lowercase (`source.value` strings; `parse_filters_from_query` lower-cases all enum-bound axes).
- Booleans are `1` / `0` (or `true` / `false` / `yes` / `on` — coerced via `_TRUE_TOKENS` per `src/ui/discover_ctx.py`).
- `score_min` is a decimal in `[0.0, 1.0]`; the slider step is `0.05`.
- Unknown values raise `pydantic.ValidationError` → HTTP 422 at the route boundary.

### C.2 Legacy querystring compatibility

The pre-existing `/discover?filter=saved` URL (header chip in `discover.html` line 17) continues to work. `parse_filters_from_query` maps `?filter=saved` → `queue_state=SAVED` when `?queue_state=` is absent. This is the only legacy alias; any future legacy aliasing requires a deviation note here.

### C.3 Querystring source of truth — why this matters

The browser URL is the canonical filter-state holder. Implications:

- **Refresh restores filter state** (the browser sends the querystring; the page rebuilds the chip-row's "active" chips from the parsed `JobFilter`).
- **Back / forward** between filter states works without client-side state. Each `hx-push-url="true"` swap pushes a new history entry.
- **Bookmarking** a filtered Discover view is supported by design.
- **No server-side session state** is needed for filter persistence; if a future row wants "remember my filters across sessions," persist `JobFilter` JSON to a user-prefs table — don't introduce a server-side filter cookie.

---

## D · Component composition

### D.1 Net-new partials (the 4 components `0.2.0.11a` registers)

| Component | Path | Kind | Reuses |
|---|---|---|---|
| `filter_toolbar` | `src/ui/templates/components/filter_toolbar.html` | composite include | `filter_chip` macro, `_filter_hidden_inputs.html`, `_macros.html` |
| `filter_chip` (macro) | `src/ui/templates/components/_macros.html:104–126` | macro | (atomic — no dependencies) |
| `_filter_hidden_inputs.html` | `src/ui/templates/components/_filter_hidden_inputs.html` | include (helper) | (atomic — operates on `filters` ctx + optional `current_axis` arg) |
| `job_topbar.html` | `src/ui/templates/components/job_topbar.html` | composite include | `chip` macro, `avatar.html` |

Plus 2 new page templates (not components — they live in `pages/` per the directory split per `AGENTS.md` § Architecture):

| Template | Path | Kind |
|---|---|---|
| `job_detail.html` | `src/ui/templates/pages/job_detail.html` | full page, `extends base.html` |
| `_job_detail_body.html` | `src/ui/templates/pages/_job_detail_body.html` | chrome-less body (shared by full page + fragment) |

### D.2 Existing-partial reuse audit

The Job UI surfaces are heavy on reuse. Per `docs/design/COMPONENTS.md` § Inventory (85-partial closed-by-default catalog):

| Surface | Existing partial reused | Notes |
|---|---|---|
| Job source pill on topbar | `chip` macro (`_macros.html`) | `{{ chip("source · LINKEDIN", tone="indigo") }}` — tone driven by `_SOURCE_TONE` table in `jobs_ctx.py:18` |
| Company-letter tile on topbar | `avatar.html` | called with `kind="company", text=initial, size="sm"` |
| Tags row on detail page right rail | `tag_chip` macro | `{% for t in j.tags %}{{ tag_chip(t) }}{% endfor %}` |
| Skills required pill list | `tag_chip` macro | reused for skill chips (visual parity with tag chips intentional) |
| Empty-result state on filtered Discover | `empty_state.html` | `icon="search-x"`, copy "No jobs match these filters." |
| Scrape-status pill on detail page | `chip` macro | tone derived from `_scrape_status_tone(status)` |
| Score circle on swipe card | `score_circle.html` (atomic) | unchanged from `0.2.0.11`; renders `—` placeholder + "unscored" badge when `Job.score == 0.0` |

### D.3 What we explicitly chose NOT to add

- **`job_card.html` (dense list-card variant of `swipe_card`)** — scaffolded in plan 36 § A as "placeholder only; not shipped." Plan 36 Deviations row 6 confirms it was deferred entirely (no scaffolded file). When a future row adds a "table view" toggle on Discover, that row authors `job_card.html` against plan 36 § A's proposed structure.
- **`apply_topbar.html` variant arg `mode="view"`** — initially considered (plan 36 § F.3). Picked `job_topbar.html` (NEW) instead. `apply_topbar.html` stays coupled to the application workspace at `/discover/{id}`; `job_topbar.html` stays coupled to the read-only `/jobs/{id}`. Each surface owns one concern.
- **A dedicated `/jobs` list route** — Discover IS the job list (per § A). No sidebar nav entry for `/jobs/...`; the route is a destination, not an index.

---

## E · HTMX patterns

Cross-reference: `docs/design/INTERACTIONS.md` § A (swap conventions) is the canonical pattern catalog; this section names the specific contracts the Job UI relies on.

### E.1 Filter chip round-trip (per-chip-form pattern)

```html
<form hx-get="/_fragments/discover/queue"
      hx-target="#discover-main"
      hx-swap="innerHTML"
      hx-push-url="true"
      hx-trigger="change">
  {% include "components/_filter_hidden_inputs.html" ignore missing with context %}
  <!-- the chip's own input here (e.g. <input name="source" type="radio" ...>) -->
</form>
```

Each chip-form is independent (per `filter_toolbar.html`). The `_filter_hidden_inputs.html` partial mirrors **the other 5 axes** as hidden inputs so a single-axis change doesn't drop sibling state when the form submits. The partial accepts an optional `current_axis` arg (`{% with current_axis="source" %}...{% endwith %}`) to skip mirroring the field being changed; when absent, every axis is mirrored.

Plan 36 Deviations row 5 records this as net-new vs the plan's § A surface inventory: the plan didn't anticipate that independent per-chip forms would need cross-axis state mirroring. The hidden-inputs partial is the resolution.

### E.2 Visible-by-default toolbar + collapse via `Filters · N` button

Plan 36 § D.2 picked the chip-row toolbar but didn't specify default visibility. Plan 36 Deviations row 4 codifies: **visible by default**, with the existing `Filters · N` button in the Discover header (where N = `_active_chip_count(filters)`) toggling the toolbar's `hidden` class via a 2-line inline JS handler. Rationale: scanning the active chips at a glance is more valuable than an extra click.

The N count is computed by `_active_chip_count(filters)` in `discover_ctx.py:357` and rendered alongside the Filters button.

### E.3 `hx-push-url="true"` on every chip-form

The browser URL is the filter-state source of truth (§ C.3). Every chip-form sets `hx-push-url="true"`. The `Clear · N` affordance uses `hx-push-url="/discover"` (literal string, not `true`) to explicitly push the bare-URL state.

### E.4 Job detail action-rail wiring

The right-rail action buttons on `/jobs/{id}` (`_job_detail_body.html` lines 145–176) target existing endpoints in `discover.py`:

| Action | Method | Target | Notes |
|---|---|---|---|
| Review & apply | GET (`<a>`) | `/discover/{j.id}` | Full page nav to application-workspace |
| Open on `{SOURCE}` | GET (`<a>` with `target="_blank"` + `hx-boost="false"`) | `j.url` | External board; never HTMX-swap |
| Save for later | HTMX POST | `/api/v1/discover/{j.id}/save` | Pre-existing endpoint |
| Skip | HTMX POST | `/api/v1/discover/{j.id}/skip` | Pre-existing endpoint |

The `hx-target="closest [data-job-section]"` + `hx-swap="none"` combo on Save/Skip is intentional: the action's success is observable via a future toast (Phase 2.5 polish row); for now the click is fire-and-forget. The `0.2.0.11b` row tightens these endpoints with `Depends(require_csrf)` + `user_id`-bound mutations.

### E.5 Duplicate-of banner contract

When a Job's `duplicate_of_id` is non-null (tier-3 fuzzy dedup, plan 34), `_job_detail_body.html` lines 12–23 render an amber inline alert linking to the canonical Job: `<a href="/jobs/{duplicate_of_id}">`. The canonical Job (the row with the lower scraper-determined fingerprint) is what surfaces in Discover by default; the duplicate is only reachable via direct URL or the `?include_duplicates=1` filter chip.

---

## F · Data accessors + IDOR boundary

### F.1 `services.job_service.list_jobs` is the only read path for the Discover queue

`src/ui/discover_ctx.py:build_discover_ctx` calls `job_service.list_jobs(session, user_id=..., filters=..., page=0, page_size=50)`. The Discover route's `/_fragments/discover/queue` also flows through `build_discover_ctx`. No `db.sample_data` is read once the umbilical is cut. The single regression lint guard (`tests/test_no_legacy_jobsource_imports.py`) was extended in plan 36 to assert `job_service.list_jobs` is called from `discover_ctx.py` (the umbilical the plan actually cut). When a future row migrates the remaining sample-data callers in `discover.py` (save/skip/saved/skipped/by-url/auto-submit flows), the lint can tighten to a full import ban — this is acknowledged in plan 36 Deviations row 1.

**Empty-DB UX path:** when `job_service.list_jobs(...)` returns `[]`, `build_discover_ctx` falls through to `_filter_shadow_queue(await sd.discover_queue(), filters)` — applying the same `JobFilter` axes against `db.sample_data.JOBS` in memory. This preserves the dev experience (a fresh DB before crons fire still shows Discover content) without shipping demo rows to self-hoster prod DBs. Plan 36 Deviations row 3 documents this choice (the original plan § E.1 mitigation proposed an alembic data migration; the shadow-data fallback is simpler + safer).

### F.2 `services.job_service.get_job` is the only read path for `/jobs/{id}`

`src/ui/routes/jobs.py:_job_or_404` wraps `job_service.get_job(session, job_id)` and enforces:

1. `job is None` → 404
2. `job.user_id != effective_user_id` → 404 (NOT 403 — see § F.4)
3. `job.deleted_at is not None` → 404 (soft-deleted jobs don't surface)

All three failures collapse to the same status code so the surface doesn't leak whether a Job ID belongs to a different user or doesn't exist at all.

### F.3 `archive_job` / `restore_job` now carry `user_id` boundary

Plan 36 folded in ROADMAP row `0.7.0.15` (hacker PR #95 MEDIUM finding). The signature is now:

```python
async def archive_job(session: AsyncSession, job_id: int, *, user_id: int) -> None
async def restore_job(session: AsyncSession, job_id: int, *, user_id: int) -> Job
```

Both raise `PermissionError` on cross-user mutation. The contract is symmetric with `_job_or_404`'s read-side IDOR mitigation. New IDOR tests in `tests/test_job_service.py` exercise both directions; the lint surface in `tests/test_no_legacy_jobsource_imports.py` stays valid.

### F.4 IDOR-by-404 over IDOR-by-403 — rationale

`/jobs/{id}` returns 404 on cross-user access (not 403). Rationale: a 403 leaks the existence of the Job ID (the requester now knows "ID 47 exists for some other user"), enabling enumeration attacks. A 404 collapses three signal channels into one: "this Job ID doesn't exist *for you*." The pattern is mirrored from FastAPI's standard guidance and is consistent across `_job_or_404` (reads) + `archive_job` / `restore_job` (mutations raise `PermissionError` which the route layer translates to 404 at the boundary).

### F.5 `_effective_user_id` — the fake-session bridge

Both Discover and `/jobs/{id}` accept `user: User | None = Depends(require_authed_session)`. The transitional fake-session stub (pre-CLI-sunset) returns `None` for the test surrogate. The two routes resolve `None` differently:

- **Discover** (`src/ui/routes/discover.py:_effective_user_id`) returns `None` when user is `None` — this signals `build_discover_ctx` to skip the live-DB pivot and use sample data, preserving the memory-mode test surface (`test_pages.py`, `test_discover_redesign.py`).
- **Job detail** (`src/ui/routes/jobs.py:_effective_user_id`) returns `1` when user is `None` — `/jobs/{id}` has no sample-data fallback, so the seeded owner (`db.sample_data.USER.id == 1`) is the correct surrogate.

Plan 36 Deviations row 2 documents the asymmetry. Both helpers' docstrings cite each other for cross-reference. Plan `0.2.0.02` (CLI sunset + fake-session retirement) collapses both to `user.id` straight.

---

## G · Build invariants

The Job UI surfaces compose with the existing stack invariants. Listed here for cross-reference; full statements live in `docs/ARCHITECTURE.md`.

| Invariant | Where it applies |
|---|---|
| All DB reads via `AsyncSession` (no sync `Session`) | Both `jobs.py` + `discover.py` route handlers |
| All Job reads via `job_service` (no raw SQL in route handlers) | `_job_or_404` wraps `job_service.get_job`; `build_discover_ctx` calls `job_service.list_jobs`; `_last_scrape_run` is the lone direct-`select()` because `JobScrapeRun` isn't yet a service-managed entity (a future row may add `job_service.get_last_scrape_run`) |
| HTMX + Jinja + Tailwind + DaisyUI; no React / Vue; no inline `style="..."` | All 4 new partials |
| Lucide icons, stroke width 1.5 | All icons in `filter_toolbar.html`, `job_topbar.html`, `_job_detail_body.html` (`globe`, `laptop`, `user-check`, `bar-chart-3`, `gauge`, `copy`, `chevron-down`, `arrow-left`, `external-link`, `sparkles`, `bookmark`, `x`, `search-x`) |
| No new CLI subcommand, no vault extension | None added |
| No new env var, on-disk path, port, schedule | None added |
| Alpine.js only if needed for complex client-state | Not needed; `<details>` popovers + inline JS handlers suffice |

---

## H · Mockup status

Plan 36 was implemented without committed mockups (the existing `swipe_card.html` + sibling Discover components carried over from plan 09a + plan 08 covered the visual contract). Playwright captures of the shipped state live as `traces/2026-05-19T15-42-42_833f4a/qa/0.2.0.11/*.png` (1440×900 + 375×812 for both `/discover` filtered and `/jobs/{id}`). Future polish rows may commit canonical mockups under `docs/design/mockups/`; the SCREENS.md entries (§ 7 + § 12) reference Playwright captures until then.

---

## I · Forward-pointers — what stays in plan 36 vs what graduates here

Per `AGENTS.md` § Workflow step 4, design-doc graduation lifts the **contract** content from the plan into the permanent doc. The plan stays at `docs/plans/archive/36-0.2.0.11-htmx-job-ui.md` as the **lifecycle record** (Authored / Shipped / Deviations from plan). This split:

| Content | Lives in | Why |
|---|---|---|
| 6-axis URL contract | **JOB_UI.md § C** | Stable cross-reference target |
| Component composition + 4 new partials | **JOB_UI.md § D** | Stable cross-reference target |
| HTMX patterns (chip round-trip, hidden-inputs partial, action rail) | **JOB_UI.md § E** | Stable cross-reference target |
| IDOR boundary + `_effective_user_id` semantics | **JOB_UI.md § F** | Stable cross-reference target |
| Decision matrices (D.1 route choice, D.2 toolbar style, etc.) | Plan archive § B | Decision rationale + alternatives — relevant for "why" archaeology |
| Wave 1–5 build sequence | Plan archive § D | Implementation chronology — irrelevant to future readers |
| Risk + mitigation table | Plan archive § E | Implementation-time risk register — irrelevant once shipped |
| Test inventory | Plan archive § G | Test coverage at ship time — actual tests live in `tests/test_job_routes.py` |
| 8 Deviations from plan | Plan archive § Deviations from plan | Canonical record of "what we promised vs what shipped" |

Follow-up rows tracked separately in ROADMAP (mentioned where the contract intersects, NOT duplicated here):

- `0.2.0.11b` — CSRF + IDOR on `/api/v1/discover/save/skip` (referenced § E.4).
- `0.2.0.11c` — `JobRead` projection swap on `GET /api/v1/jobs/{id}` (referenced § B implicitly via "moved here from `discover.py`").
- `0.2.0.10a` — `/api/v1/scheduler/*` endpoints + Settings · Sources UI panel (referenced in plan 36 § E row 7, NOT in JOB_UI.md scope).

---

## J · Pointer index

- **Functional spec per screen:** `docs/design/SCREENS.md` § 7 (Discover) + § 12 (Job detail).
- **Component catalog (canonical):** `docs/design/COMPONENTS.md` § H.7 (Discover group, where `filter_toolbar.html` + `_filter_hidden_inputs.html` + `job_topbar.html` are registered) + § I (Macros, where `filter_chip` is registered).
- **Job entity + service contract:** `docs/design/JOB_MODEL.md` § F (`job_service` 8-function contract — `list_jobs`, `get_job`, `archive_job`, `restore_job` cited).
- **HTMX swap conventions (parent doc):** `docs/design/INTERACTIONS.md` § A.
- **Route table:** `docs/design/BACKEND.md` § D.3 (Jobs / Discover) — page routes for `/discover`, `/jobs/{id}` + fragments + JSON API.
- **Lifecycle record (plan archive):** `docs/plans/archive/36-0.2.0.11-htmx-job-ui.md`.
- **Roadmap row:** `ROADMAP.md` Phase 2 row `0.2.0.11` (closed via PR #112 squash `47d78ec`) + `0.2.0.11a` (this graduation, ships via PR alongside this doc).
