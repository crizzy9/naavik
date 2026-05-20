# Naavik · Sources UI

> **Canonical reference** — graduated from `docs/plans/49-0.2.0.16-first-run-walkthrough.md` per `AGENTS.md` § Workflow step 4 (filed as ROADMAP row `0.2.0.16`).
> **Status:** Active. Single source for the Settings · Sources sub-tab — the per-source row contract, the env-vs-DB configured-state composition, the `list_recent_scrape_runs_by_source` projection, and the IDOR + CSRF boundaries the panel relies on.
> **Last updated:** 2026-05-20 (`0.2.0.16` ships this doc).
> **Companion docs:** `docs/design/SCREENS.md` § 11 (Settings tab spec), `docs/design/COMPONENTS.md` § H.11 (Settings group — registers `_source_row.html`), `docs/design/JOB_MODEL.md` § F (`job_service` + `JobScrapeRun` references), `docs/design/SCRAPER_BASE.md` § G (rate-limit substrate surfaced read-only).
> **Downstream plans depending on this contract:** `0.2.0.10a` (operator scheduler control buttons compose into the row's `<details>` popover), `0.2.5.04` (recent-runs history table — "View history →" link from each row), `0.2.5.05` (rate-limit JSONB editor — replaces the read-only `<details>` popover with a writable form), `0.2.5.06` (LinkedIn/Indeed keywords editor — replaces the keywords `<details>` popover with chip-add UX).

---

## A · One-paragraph contract

The Settings · Sources sub-tab is the operator-facing surface for "is each scraper configured, when did it last run, what state is it in." It renders 6 source rows (LinkedIn / Workday / Greenhouse / Lever / Ashby / Indeed) — each row composes (a) the per-source enable toggle from `Settings.sources_enabled`, (b) an env-vs-DB configured indicator (env-var watchlist for the four ATS sources; per-user keywords for LinkedIn + Indeed), (c) the latest `JobScrapeRun` status chip + relative timestamp, (d) the read-only resolved rate-limit surfaced from `scraper.rate_limit.resolve_rate_limit`, and (e) a `<details>` popover with the configuration surface (env-var name + CSV example OR current keywords + Edit-via-API hint). The panel is mounted at `GET /settings/sources` with `Depends(require_authed_session)` + `Depends(get_session)`; reads use `services.settings_service.get_or_create` + `services.job_service.list_recent_scrape_runs_by_source` + `services.env_secrets.scraper_source_configured` + `scraper.rate_limit.resolve_rate_limit`. No new env var, on-disk path, port, schedule, or CLI surface introduced — the contract is route + partial + service-call composition only.

---

## B · Surface inventory

| Surface | Path | Kind | Implemented in |
|---|---|---|---|
| Sources page (full HTML) | `GET /settings/sources` | full page (`base.html`) | `src/ui/routes/settings.py:get_settings_sources` |
| Sources fragment (HX-Request: true) | `GET /settings/sources` (HX-Request header) | HTMX fragment | same handler — branches on `request.headers["HX-Request"]` |
| Per-source row partial | `src/ui/templates/components/_source_row.html` | include | registered in COMPONENTS.md § H.11 (count 7 → 8; total 88 → 89) |
| Tab body | `src/ui/templates/pages/_settings_sources.html` | include from `pages/settings.html` | rewritten in `0.2.0.16`; orchestrates 6 `_source_row.html` includes |

Pre-existing surfaces this contract does **not** modify:

- `PUT /api/v1/settings/sources` — write path for `Settings.sources_enabled` / `linkedin_keywords` / `indeed_keywords` / `scraper_rate_limits` / etc. (`src/api/settings.py`). Stays as-is; the panel's toggle wires to this endpoint via existing HTMX swap.
- `Settings.workday_companies` column path — Workday's per-tenant watchlist remains on the per-user Settings row (legacy from before `WORKDAY_COMPANIES` env var existed); the env-var slot exists in `src/config.py` but Workday's cron currently reads `settings.workday_companies`, not env. This asymmetry is intentional — Workday is per-tenant operator config; Greenhouse / Lever / Ashby are deployment-wide.

---

## C · Per-row contract

Each of the 6 source rows renders these 6 cells per the `_source_row.html` partial. The `view` arg is a dict built by `_build_sources_view` in the route module:

| Cell | Source of truth | Rendering |
|---|---|---|
| Icon + label | Hard-coded `_SOURCES_PANEL` list (label + Lucide icon name) | 32px `inline-flex` tile + 14px label |
| Enabled toggle | `Settings.sources_enabled[source.value]` (defaults to `True` when key absent) | DaisyUI-flavored toggle; `hx-put` wires the change to `PUT /api/v1/settings/sources` |
| Configured indicator | `services.env_secrets.scraper_source_configured(source, settings)` composition (see § D) | Emerald chip when configured; slate-dimmed chip when not |
| Last-run state | `services.job_service.list_recent_scrape_runs_by_source(session, user_id=...)[source]` | Status chip (emerald/amber/rose/indigo per status) + relative timestamp ("Nm/Nh/Nd ago"); `never run` when no row present |
| Schedule | `Settings.source_schedules[source.value]` with cron-string fallback table | Mono caption next to last-run state |
| Resolved rate limit | `scraper.rate_limit.resolve_rate_limit(settings, source)` | Mono caption `X.XX rpm · A.A–B.Bs` below row meta |
| Configure popover | `<details>` element keyed by `view.configure.kind` ("env" or "db") | Env-kind: env-var name + CSV example + current value list. DB-kind: current keywords + location + "Edit via PUT /api/v1/settings/sources" hint until `0.2.5.06` ships the editor |

### C.1 Status chip tone table

| `JobScrapeStatus` value | Chip tone | Label |
|---|---|---|
| `running` | indigo | `running…` (no timestamp — chip stands in) |
| `success` | emerald | `SUCCESS` + relative timestamp |
| `partial` | amber | `PARTIAL` + relative timestamp |
| `failed` | rose | `FAILED` + relative timestamp |
| `timed_out` | rose | `TIMED OUT` + relative timestamp |

`finished_at IS NULL` is treated as `running` regardless of stored status — defense in depth against a row that crashed mid-write.

---

## D · Env-vs-DB configured-state composition

`services.env_secrets.scraper_source_configured(source: JobSource, settings: Settings) -> bool` is the chokepoint helper. Per source:

| Source | Truthy condition |
|---|---|
| LinkedIn | `settings.linkedin_keywords` non-empty |
| Workday | `settings.workday_companies` non-empty |
| Greenhouse | `config.settings.greenhouse_companies` (env-loaded) non-empty |
| Lever | `config.settings.lever_companies` (env-loaded) non-empty |
| Ashby | `config.settings.ashby_companies` (env-loaded) non-empty |
| Indeed | `settings.indeed_keywords` non-empty |
| Other (COMPANY_DIRECT / RSSHUB / N8N_LEGACY / MANUAL) | always False — not surfaced on the panel |

The rationale for the split: env vars carry deployment-wide config (the company list a Workday tenant tracks is a deployment concern, even if it lives on the Settings row pre-`0.2.0.07`); per-user Settings carry search intent (keywords + location, scoped to one user). LinkedIn and Indeed are intent-based scrapers; the rest are watchlist-based.

`scraper_source_configured` reads attributes directly (no `getattr` defaults) — the route guarantees a SQL `Settings` row is passed (via `settings_service.get_or_create`), not the shadow.

---

## E · `list_recent_scrape_runs_by_source` query semantics

The new service function in `services/job_service.py`:

```python
async def list_recent_scrape_runs_by_source(
    session: AsyncSession,
    *,
    user_id: int,
) -> dict[JobSource, JobScrapeRun]
```

Returns the latest `JobScrapeRun` row per `(user_id, source)` tuple. Empty dict when no runs exist.

Cross-backend implementation:

- **Postgres path:** single statement using `DISTINCT ON (source)` + `ORDER BY source, started_at DESC`. Picks up the highest-recency row per source in one round-trip.
- **SQLite test path:** two-statement fallback — first SELECT `source, MAX(started_at) GROUP BY source`, then per-source row fetch. `DISTINCT ON` is Postgres-only.

Dialect detection via `session.bind.dialect.name == "postgresql"`. The two-statement fallback is `n+1` in source count (max 6 sources) — acceptable for tests; production reads always take the single-statement path.

The function does NOT honor soft-delete because `JobScrapeRun` rows are not soft-deleteable (no `deleted_at` column). Every run row counts regardless of subsequent rerun-state.

---

## F · IDOR + CSRF boundary

- **`GET /settings/sources`** — read-only; gated by `Depends(require_authed_session)`. The fake-session cookie path (`naavik_session=fake-1`) resolves to `_user=None`; the route uses `user_id=1` (the seeded owner — same pattern as `_effective_user_id` in `src/ui/routes/jobs.py:F.5`). Real-auth users pass through with their `_user.id`. Cross-user reads are not currently possible because Settings is keyed by `user_id` and the helper hard-codes 1; multi-user expansion (post-fake-session) lifts this to `_user.id` at the route boundary.
- **CSRF** — GET endpoint; no CSRF token required (the existing pattern from JOB_UI.md § F applies). The per-row toggle's `hx-put="/api/v1/settings/sources"` request inherits the global `X-CSRF-Token` header from `base.html` (plan 45 / `0.2.0.11d` Jinja context-processor).
- **XSS guard** — the panel does not render `JobScrapeRun.raw_meta` or `JobScrapeRun.errors` directly (last-run UI surfaces status + timestamp only). Jinja autoescape catches any scraper-controlled string that does land in template context. Regression test in `tests/test_settings_sources_route.py::test_get_xss_payload_in_raw_meta_escaped` seeds `<script>` + `<img src=x onerror=…>` payloads into `raw_meta` and `errors` and asserts the literal payload does not appear in response body.

---

## G · HTMX swap pattern

The dedicated `/settings/sources` route branches on `request.headers["HX-Request"]`:

- `HX-Request: true` → return only `pages/_settings_sources.html` (panel body, no chrome). Used by future deep-link surfaces (Settings sidebar HTMX swap targets the panel area).
- Otherwise → return `pages/settings.html` (full page with `base.html` chrome + tab nav). Used by direct browser navigation, refresh, bookmarking.

This mirrors the JOB_UI.md § B fragment-vs-page pattern from `0.2.0.11`.

---

## H · Forward pointers — what stays in plan 49 vs what graduates here

Per `AGENTS.md` § Workflow step 4, this design doc holds the **contract**. The plan at `docs/plans/archive/49-0.2.0.16-first-run-walkthrough.md` (post-archive) holds the **lifecycle record** + decisions + risks + the README narrative.

| Content | Lives in | Why |
|---|---|---|
| Per-row cell contract (D.1) | **SOURCES_UI.md § C** | Stable cross-reference target for downstream plans |
| Env-vs-DB composition (D.3) | **SOURCES_UI.md § D** | Stable cross-reference target for `env_secrets` helper |
| `list_recent_scrape_runs_by_source` semantics (D.4) | **SOURCES_UI.md § E** | Stable cross-reference target for `job_service` |
| IDOR + CSRF boundary (D.5) | **SOURCES_UI.md § F** | Stable cross-reference target |
| HTMX swap pattern (D.4) | **SOURCES_UI.md § G** | Stable cross-reference target |
| README narrative inserts (C.1 + C.2) | `README.md` § Configuration + § Operations | Operator-facing prose; the README is its own canonical surface |
| Rate-limit editor option matrix (A) | Plan archive § A | Decision rationale — relevant for "why" archaeology |
| Risk + mitigation table (Risk + mitigation) | Plan archive | Implementation-time register; irrelevant once shipped |
| Test inventory (F) | Plan archive § F | Test coverage at ship time — actual tests live in `tests/test_settings_sources_route.py` |
| Deviations from plan | Plan archive § Deviations from plan | Canonical record of "what we promised vs what shipped" |

Follow-up rows tracked separately in ROADMAP:

- `0.2.0.10a` (shipped) — `/api/v1/scheduler/*` endpoints; the Sources panel may grow Run / Pause / Resume buttons per row in a future polish row.
- `0.2.5.04` (shipped) — Scraper-run history table — landed as a single bottom-of-tab table aggregating recent N runs across all sources (vs. anticipated per-row "View history →" link). Surface lives in `pages/_settings_sources.html` § history section. Plan 56 / `0.2.7.21` doc-pointer correction.
- `0.2.5.05` — Rate-limit JSONB editor at `/settings/rate-limits`; replaces the read-only `<details>` popover on the rate-limit cell.
- `0.2.5.06` — Writable LinkedIn / Indeed keywords editor; replaces the read-only `<details>` popover for those sources.

Manager files `0.2.5.05` + `0.2.5.06` as new ROADMAP rows during BOOKKEEPING per plan 49 OQ.3 lock.

---

## I · Pointer index

- **Screen functional spec:** `docs/design/SCREENS.md` § 11 (Settings tab).
- **Component catalog:** `docs/design/COMPONENTS.md` § H.11 (Settings group — `_source_row.html` entry).
- **Job entity + service contract:** `docs/design/JOB_MODEL.md` § F (`job_service` 8-function surface — now 9 functions including `list_recent_scrape_runs_by_source`).
- **Rate-limit substrate:** `docs/design/SCRAPER_BASE.md` § G (the `RateLimitConfig` model + `resolve_rate_limit` resolver Sources surfaces read-only).
- **Settings model:** `src/models/settings.py` (`sources_enabled`, `source_schedules`, `linkedin_keywords`, `linkedin_location`, `indeed_keywords`, `indeed_location`, `workday_companies`, `scraper_rate_limits`).
- **Env-loaded scraper config:** `src/config.py` (`greenhouse_companies` / `lever_companies` / `ashby_companies` / `scraper_rsshub_url`).
- **Cron composition pattern (mirrors what the panel surfaces):** `src/scheduler/scraping.py:_compose_query`.
- **Lifecycle record (plan archive):** `docs/plans/archive/49-0.2.0.16-first-run-walkthrough.md` (post-archive).
- **Roadmap row:** `ROADMAP.md` Phase 2 row `0.2.0.16`.
