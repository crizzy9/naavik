# Naavik · Architecture Guide

> **Last updated:** 2026-05-19
> **Audience:** architect + engineer agents reading the system before authoring plans or shipping code.
> **Companion docs:** `docs/design/BACKEND.md` (canonical backend reference — services, routes, cron, scrapers, LLM, observability), `docs/design/DATA_MODEL.md` (canonical data model — 18 entities, state machines, indexes, validation), `docs/design/INTERACTIONS.md` (HTMX patterns), `DESIGN.md` (visual contract — tokens, type, voice), `docs/design/WORKFLOW.md` (UI sub-process — skill routing, checklists, common patterns).

This is the entry-point guide. The deep references live in `docs/design/`. Read this first to understand WHERE things live and WHY; read the deep docs when implementing.

---

## 1. One-paragraph system

Naavik is a Python 3.12 FastAPI monolith with an HTMX frontend, backed by PostgreSQL + pgvector. Profile data, jobs, applications, contacts, and AI-generated content all persist in Postgres. LLM calls go through a thin provider abstraction (Anthropic / OpenAI / Ollama). PDF generation uses Typst (10–100× faster than LaTeX). Scheduling uses APScheduler with a Postgres job store. Everything ships as a Nix flake (`devShell` + `package` + `nixosModule`) AND as a Docker Compose stack. Self-hosted first; cloud tier is the same codebase.

---

## 2. System diagram

```
┌─────────────────────────────────────────────────────────────┐
│  Reverse proxy (Caddy/Nginx/Traefik — self-hosted only)     │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTPS
┌──────────────────────▼──────────────────────────────────────┐
│  FastAPI (uvicorn)                                          │
│  ├── api/v1/...   (REST, JSON)                              │
│  ├── api/portfolio/...  (public, no auth)                   │
│  ├── ui/routes/... (HTMX fragment swaps, HTML responses)    │
│  └── lifespan: APScheduler init + lifespan credential echo  │
└──────┬──────────────┬──────────────┬──────────────┬─────────┘
       │              │              │              │
┌──────▼──────┐ ┌─────▼─────┐ ┌─────▼────┐ ┌──────▼──────┐
│ services/   │ │ llm/      │ │ typst/   │ │ scraper/    │
│ (business   │ │ (Anthropic│ │ (PDF     │ │ (LinkedIn/  │
│  logic)     │ │  OpenAI/  │ │  compile)│ │  Workday/   │
│             │ │  Ollama)  │ │          │ │  Greenhouse)│
└──────┬──────┘ └─────┬─────┘ └──────────┘ └─────────────┘
       │              │
┌──────▼──────────────▼─────────────────────────────────────┐
│ db/session (AsyncSession)                                 │
│ models/ (SQLModel — Pydantic + SQLAlchemy)                │
└──────────────────────┬────────────────────────────────────┘
                       │
┌──────────────────────▼────────────────────────────────────┐
│ PostgreSQL 17 + pgvector                                  │
│ Migrations: alembic (async env.py via psycopg sync)       │
│ Scheduler: apscheduler_jobs table (PostgresJobStore)      │
└────────────────────────────────────────────────────────────┘

On-disk state at ~/.naavik/:
  data/documents/      per-app + portfolio PDF outputs
  data/snapshots/      daily DB snapshot markers
  dev-credentials      mode 0600 plaintext dev creds (debug + SELF_HOSTED gated, plan 10c)

Secrets (API keys, webhook URLs, bot tokens) load from `.env` in the repo /
deployment root via `pydantic-settings` in `src/config.py`. `.env` is
gitignored; operators run `chmod 0600 .env`. The previous AES-256-GCM vault
(`~/.naavik/secrets.enc` + `~/.naavik/key.bin` + `~/.naavik/logs/vault-audit.log`)
was deleted in plan 26 / `0.2.0.01` (2026-05-19) — see § 4.2.
```

---

## 3. Layer responsibilities

Strict layering — each layer only depends on those below it.

### 3.1 `src/main.py` — FastAPI entrypoint + lifespan

- Mounts `src/api/*` and `src/ui/routes/*` routers.
- Lifespan: starts APScheduler, echoes dev credential ~750 ms after boot (plan 10c).
- Static files (`src/ui/static/`).
- CORS for `/api/portfolio/*` (allows the portfolio site to fetch).

**Don't add business logic here.** It belongs in `services/`.

### 3.2 `src/config.py` — pydantic-settings

- Single `app_settings` instance (singleton). Read everywhere via `from src.config import app_settings`.
- All env vars optional; defaults in code.
- Critical fields: `DATABASE_URL`, `SECRET_KEY`, `DATA_DIR`, `NAAVIK_DEBUG`, `NAAVIK_DEV_PASSWORD`, `NAAVIK_BCRYPT_COST`.
- `Settings.debug` reads `NAAVIK_DEBUG` / `DEBUG` (plan 10c).

### 3.3 `src/api/` — REST endpoints

- All routes under `/api/v1/`.
- Pydantic models for every input + output (no raw dicts).
- FastAPI dependency injection for `AsyncSession`, current user, current settings, LLM provider.
- **Never** call SQLAlchemy or write raw SQL here — call into `services/`.
- Auth: `api/v1/auth/*` is the only unauthenticated surface besides `/api/portfolio/*`.

**Subdirs:** `auth.py` · `profile.py` · `applications.py` · `portfolio.py` · `settings.py` · `jobs.py` (future, Phase 2) · `generator.py` (future).

### 3.4 `src/ui/` — HTMX views

- `routes/`: page handlers + fragment handlers. Return `HTMLResponse` (Jinja-rendered) or partial HTML.
- `templates/`: base layout + components/ (reusable partials) + pages/ (composed screens).
- `static/`: htmx.min.js, lucide.min.js, base.js, styles.
- **Components are NEVER duplicated.** If a screen needs a variant, extend the existing partial via macro args; don't fork.
- Per-screen accessor pattern (plan 09 / refined plan 60): each page handler builds a context dict via a `discover_ctx()` / `tracking_ctx()` / `_build_profile_ctx()` helper. Post-plan-60 routes either read through the `services/*` layer (Postgres) or — for routes not yet migrated — fall through to fixture data in `src/db/sample_data.py`. The dual env-gated mode is gone; future plans incrementally rewire the remaining routes onto `services/*`.

### 3.5 `src/services/` — business logic

The middle layer. Every business operation lives here.

**Service catalog** (post-plan-10 Wave 6):
- `auth.py` — bcrypt + JWT + CSRF + rate-limit.
- `profile_service.py` — CRUD + bullet ops + tag inference.
- `extraction.py` — PDF → AI → Profile + SSE.
- `application_service.py` — DRAFT lifecycle + state transitions + computed orthogonal states + auto-apply queue.
- `document_generator.py` — bullet selection + AI trim + Typst compile + page-count validation + DRAFT reuse heuristic.
- `scorer.py` — visa filter (Wave 6); LLM scoring (Phase 3).
- `contact_tracker.py` — recruiter/employee contact management.
- `notifications.py` — Discord embed + Telegram outbound + toast queue.
- `portfolio_sync.py` — public CV API + debounced generic resume regen + Netlify webhook.
- `settings_service.py` — per-tab CRUD for non-secret Settings fields. API keys / webhook URLs / bot tokens are env-loaded post plan 26 / `0.2.0.01`; this service no longer mediates secret material.
- `ats_credentials.py` — metadata only (board, login_status, has_credential flag). Plan 26 removed `store_secret` / `resolve_secret` / `delete_secret`; Phase 2.X ATS adapter plans re-introduce a DB-side encrypted column when concrete adapters need persistent cookies.
- `env_secrets.py` — env-presence indicators (post-vault). `llm_provider_configured(provider)` / `discord_webhook_configured()` / `telegram_bot_configured()` / `portfolio_webhook_configured()` + tab bundles for the Settings UI. Returns bools, never values.
- `llm_tracker.py` — wraps every LLM call with `tracked_call`; persists ApiUsage.

**Rule:** services consume `AsyncSession` via DI. Services don't import `api/` or `ui/` — they're called BY those layers, not the other way around.

### 3.6 `src/llm/` — LLM provider abstraction

- `base.py` — abstract `LLMProvider` interface: `complete(prompt) → str`, `structured(prompt, schema) → BaseModel`, `cost_estimate(input_tokens, output_tokens, model) → Decimal`.
- `anthropic.py` — tool-use for structured output.
- `openai.py` — `response_format=json_schema` for structured output.
- `ollama.py` — `format=json` for structured output.
- `prompts/` — Python modules per prompt (e.g., `score_job.py`, `extract_resume.py`, `tailor_resume.py`, `answer_screener.py`). Each module exports a Pydantic schema + a `build_prompt(*args)` function. No raw f-strings of user input — schema validates everything.

**Wrap every LLM call in `tracked_call` from `services/llm_tracker.py`.** Drops an `ApiUsage` row on success + failure with cost + latency + model.

### 3.7 `src/models/` — SQLModel models

- One file per entity domain (`profile.py`, `application.py`, `job.py`, `job_scrape_run.py`, `event.py`, etc.).
- `SQLModel` inherits Pydantic BaseModel + SQLAlchemy declarative. ONE class definition serves both API schemas + DB rows.
- Pydantic API-only models (e.g. `JobCreate` / `JobRead` / `JobFilter` / `JobScrapeRunRead`) co-locate with the SQLModel of the same domain rather than living in a separate `api/schemas/` directory — matches the existing `profile.py` convention.
- Relationships **stripped** in current implementation — services do FK joins explicitly. (Plan 10 Wave 3 deviation: SQLModel 0.0.22's forward-ref resolution failed under our circular FK graph.)
- Enums live in `src/models/enums.py` for cross-entity reuse. Plan 27 (`0.2.0.05`) added `VisaRestriction` / `RemotePolicy` / `SeniorityLevel` / `JobScrapeStatus` + replaced the 2-value `JobSource` enum with the 10-value per-source form. Canonical Job + JobScrapeRun reference: `docs/design/JOB_MODEL.md`.

### 3.8 `src/scraper/` — site adapters

Canonical reference: `docs/design/SCRAPER_BASE.md` (plan 29 / `0.2.0.06`).

- `types.py` — `RawJob` boundary DTO (17 fields, Pydantic v2, `extra="forbid"`) + `ScrapeQuery`.
- `base.py` — abstract `ScraperBase(ABC)` with `async def scrape(query) -> AsyncIterator[RawJob]`. Subclasses declare `source` + `board` class attrs and stream `RawJob` instances; per-listing errors go into `self._errors`, scraper-fatal raise to the service layer.
- `crawl4ai_client.py` — `Crawl4AIClient` wraps `AsyncWebCrawler` (`enable_stealth=True` default; `fetch_html(url)` + `stream_many(urls)`). Single upgrade surface for Crawl4AI version bumps; test injection point.
- `sites/` — per-source subclasses populate `sites/__init__.py:scrapers` registry. `sample.py` is a test fixture only.
- `services/scraper_service.py:run_scraper` is the only caller. Scrapers never touch the DB.
- Per-source scrapers (LinkedIn / Workday / Greenhouse / Lever / Ashby / Indeed) ship in `0.2.0.07`; AI extraction in `0.2.0.08`; scheduler in `0.2.0.10`; rate-limit Settings UI in `0.2.0.13`.
- Anti-detection layered: Crawl4AI stealth + `rate_limit_per_minute` class attr + `random_delay_seconds` jitter; `UndetectedAdapter` reserved for `0.2.0.13`.

### 3.9 `src/typst/` — PDF compilation

- `templates/onepage.typ` — NEU-style 1-page resume.
- `templates/cover_letter.typ` — 4-section letter.
- `compiler.py` — wraps `typst compile` CLI + `typst query` for `<naavik-meta>` page-count metadata (plan 10 § C deviation: the spec'd `--emit metadata` flag doesn't exist in 0.14; same effect via `typst query`).
- Templates consume JSON from `services/document_generator.py`. Untrusted JD text is escaped before injection.

### 3.10 `src/scheduler/` — APScheduler jobs

- `jobs.py` — job definitions (`applications.auto_apply` 5min, `admin.aggregate_costs` hourly, `admin.cleanup_stale_docs` daily, `admin.daily_db_snapshot` daily, `admin.refresh_oauth_tokens` hourly).
- `__init__.py` — lifespan-managed scheduler init with `PostgresJobStore`.
- Jobs are imported by name (string ref) so APScheduler can survive restarts via the job store.

### 3.11 `src/db/` — session management + seeds

- `session.py` — `AsyncSession` factory + `get_session()` dependency.
- `seed.py` — populates from `sample_data.py`; bumps each table's autoincrement sequence past seeded max so subsequent inserts don't collide. Writes `~/.naavik/dev-credentials` when debug + SELF_HOSTED + generated-password (plan 10c).
- `sample_data.py` + `sample_data_models.py` — frozen Pydantic per `SAMPLE_DATA.md` (372 rows across 20 entities). Post-plan-60 (0.2.7.17): the legitimate consumers are `seed.py` (production seeding) and the pytest fixture suite + transitional route call sites that haven't yet migrated to `services/*`. The `NAAVIK_PERSISTENCE` env var is removed; new route code MUST read through `services/*` (enforced via `tests/test_no_sample_data_imports_in_routes.py`).

---

## 4. Cross-cutting concerns

### 4.1 Authentication + Authorization

- JWT cookie (HttpOnly, Secure, SameSite=Strict) issued by `POST /api/v1/auth/login`.
- HS256 signing via `SECRET_KEY`. Cookie expiry 7 days; refresh-token rotation deferred to Phase 1.x backlog.
- CSRF: double-submit token via `/csrf` endpoint. Every POST route reads `X-CSRF-Token` header (HTMX `hx-headers` carries it).
- Brute-force rate limit: 5 attempts / 15 min / IP. Applied to `/login` AND `/signup`.
- bcrypt cost: 12 (production), 4 (tests via `NAAVIK_BCRYPT_COST=4`).
- **Open signup:** first signup becomes admin (`is_admin=True`); subsequent signups are regular users (`is_admin=False`). No gate (plan 0.7.0.48). Operators who need to lock down signups gate externally via firewall / reverse-proxy / OIDC, or wait on a future `Settings.allow_signups` admin toggle (`0.7.0.50` follow-up).

### 4.2 Secret handling

- **Source of truth:** gitignored `.env` at the repo / deployment root, consumed by `pydantic-settings` in `src/config.py`. Operators run `chmod 0600 .env` — filesystem permissions are the operative defense, matching the standard self-hosted pattern (n8n, Grafana, Authentik).
- **Surface in the UI:** `services/env_secrets.py` exposes per-scope presence helpers (`llm_provider_configured(provider)`, `discord_webhook_configured()`, `telegram_bot_configured()`, `portfolio_webhook_configured()`) returning bools. The Settings UI's LLM Provider + Notifications tabs render configured / not-set indicators from these; values never leave the env.
- **API guard:** `PUT /api/v1/settings/llm` and `PUT /api/v1/settings/notifications` reject (422) any payload carrying `api_key` / `ollama_base_url` / `discord_webhook_url` / `telegram_bot_token` / `telegram_chat_id`, with a hint pointing at the relevant env vars + `.env`.
- **Sunset history:** the AES-256-GCM vault (`~/.naavik/secrets.enc` + `~/.naavik/key.bin` + `~/.naavik/logs/vault-audit.log`) and `src/services/vault.py` (436 LOC) were deleted in plan 26 / `0.2.0.01` (2026-05-19). The master key was derived from `SECRET_KEY` (same env var the JWT signer reads), so the vault added no defense beyond what env + filesystem perms provide; it was theater. `tests/test_no_vault_imports.py` is a regression lint that fails if anything reintroduces `from services import vault` / `vault_svc` references in `src/`.
- **Rule:** do NOT reintroduce encrypted-at-rest secret storage (no new AES-GCM / PBKDF2 / `key.bin` / `secrets.enc` code paths). New operator-facing secrets land as `.env` slots in `.env.example` + Settings UI presence indicators.

### 4.3 Async + DB

- All endpoints, all service methods, all DB ops are `async`.
- `AsyncSession` injected via FastAPI DI. One session per request.
- **No raw SQL in route handlers.** Pull into a service method.
- Connection pool: NullPool for tests (plan 10 deviation — avoids cross-test cross-talk); standard pool in production.
- After `db/seed.py` populates with hardcoded IDs, each table's autoincrement sequence is bumped past the max ID so subsequent app inserts don't collide.

### 4.4 LLM observability

- Every provider call wrapped in `services/llm_tracker.tracked_call(provider, model, kind, fn)`.
- Persists `ApiUsage(user_id, provider, model, kind, input_tokens, output_tokens, cost_usd, latency_ms, ok, error_code, occurred_at)` on success AND failure.
- Settings · LLM Provider's cost cards read from this table (this-month aggregate).
- Daily cost cap enforced in tracked_call via `Settings.daily_llm_cost_cap_usd` (default $5).
- Retry policy per BACKEND.md § M.5: 2 retries with exponential backoff on transient errors (network, 429, 5xx). No retry on auth (401, 403).

### 4.5 HTMX patterns

Per `docs/design/INTERACTIONS.md` § B–H:

- **Form pattern:** `<form hx-post="..." hx-swap="outerHTML" hx-target="#form-id">`. Server returns the form with new state (success badge, error inline).
- **Per-field autosave:** `<input hx-put="/profile/{field}" hx-trigger="change delay:300ms" hx-swap="none">`. Pairs with `autosave_indicator` component cycling `saving → saved`.
- **Modal:** `<button hx-get="..." hx-target="#modal-root" hx-swap="innerHTML">` returns modal HTML. `HX-Trigger: closeModal` header on save closes it.
- **SSE:** `<div hx-ext="sse" sse-connect="/sse/..." sse-swap="message">` for live updates (extraction progress, email signal, cover letter generation).
- **Drag-drop:** Sortable.js on bullet lists + Kanban columns; fires `hx-post` on reorder.
- **Optimistic UI with rollback:** `hx-swap="outerHTML" hx-swap-oob="true"` for primary swap + `<div id="rollback-handler" hx-swap="..." hx-trigger="htmx:responseError">` for error.
- **Keyboard shortcuts:** `src/ui/static/keys.js` — Discover screen uses ← ↑ → for skip / save / auto-apply.

### 4.6 Visual contract (DESIGN.md tokens)

- **Dark mode primary** (light mode is Phase 6). Slate-950 page BG, slate-900 surfaces, slate-800 elevated.
- **Brand:** indigo-500 (`#6366F1`) primary, cyan-400 (`#22D3EE`) AI accent.
- **Type:** Inter (400/500/600/700) + JetBrains Mono.
- **Icons:** Lucide only, stroke width 1.5. No mixing icon sets.
- **Voice:** developer tool you self-host, not SaaS you rent. No upsell pressure.

### 4.7 External integrations

Two external systems are first-class integrations: the portfolio website (`crypticsoul.dev`) we serve data TO, and n8n (`n8n.luminolab.net`) we're migrating data + workflows FROM.

#### Portfolio website (crypticsoul.dev) — permanent

Naavik exposes a public-no-auth API consumed by the portfolio site at build time:

```
Naavik DB ──► GET /api/portfolio/cv         ──► crypticsoul.dev cv.astro (build-time fetch)
         ──► GET /api/portfolio/resume.pdf  ──► Download link on CV page
```

- **Filter:** allowlist-based (hacker agent enforces this in PR reviews). Specifically excluded from the public payload: email, phone, EEO answers (race/ethnicity, gender, disability, veteran status), visa, salary expectation, application questions.
- **Resume regen:** Profile updates in Naavik debounce 60s and regenerate the generic resume to `~/.naavik/data/documents/portfolio/resume.pdf` (plan 10 § C.5.9). The `/api/portfolio/resume.pdf` endpoint serves this cached file.
- **Webhook:** `PORTFOLIO_WEBHOOK_URL` env var (optional) triggers a Netlify rebuild on Profile update. Configured per-deployment.
- **Versioning:** none today. Phase 2+ adds `?version=v1` so the portfolio repo can pin a consumer (ROADMAP § Phase 1 deferred: `DEF-12`).

**Coordination:** any change to `/api/portfolio/cv`'s shape MUST coordinate with the portfolio repo (separate codebase). Until versioning ships, the API is the implicit contract — break it and the portfolio's next build fails.

#### n8n (n8n.luminolab.net) — transitional, decommissions after Phase 2

n8n hosted the legacy job-discovery automation. Naavik replaces all of it across Phase 2 + Phase 4 + Phase 5.

| n8n component | Naavik equivalent | Phase |
|---|---|---|
| Main Workflow (`Lw1uK5APIhIeUeem`) | `src/scheduler/` + `src/services/job_scraper.py` | 2 |
| Manual Logger (`xSIGv47G2Porc0S9`) | `src/api/applications.py` + `+ Add by URL` + Tracking `+ Add manually` | 4 |
| Job Page Parser (`PQAGv5qUajzBP5wm`) | `src/scraper/*.py` | 2 |
| DataTable "Job Applications" (`hfvivTlQThpPytkl`) | PostgreSQL `jobs` + `applications` tables | 2 (data migration: task 2.10) |
| Google Sheets sync (`14pgCto2OAQxmb9w6ciOsReb3iQGE1V9XECU-o6E_c7M`) | Optional secondary view in Phase 4 | 4 |
| Discord notifications | `src/services/notifications.py` | 2 |
| OpenAI extraction | `src/llm/` (multi-provider) | 0 — already shipped |
| Browserless | Crawl4AI + Playwright | 2 |
| RSShub feed (`rsshub.luminolab.net`) | Naavik consumes directly | 2 — kept as a source |

**Migration order:**

1. Build profile + tracking system (Phase 0–1) independently of n8n. ✅ Done.
2. Build scrapers (Phase 2) → validate pipeline runs clean for 1 week → disable n8n Main Workflow.
3. Build tracking (Phase 4) → disable n8n Manual Logger.
4. Fully decommission n8n after Phase 4 ships.

**RSShub stays.** It's a self-hosted job-feed source Naavik consumes directly — not part of the n8n workflow surface.

**Devops MCP wiring:** `mcp__plugin_claude-code-home-manager_n8n__*` is on the devops agent ONLY, transitionally, for verifying migration completeness (per `docs/AGENT_OPS.md` § 5). Goes away after Phase 2 ships clean.

#### Future integrations (Phase 5+)

Gmail / Outlook / LinkedIn / Calendar all land in Phase 5 (plans 13–14). Each will get a `§ 4.7.x` subsection here when shipped. Authentication patterns will follow OAuth + refresh-token persistence; post plan 26 / `0.2.0.01`, persistent OAuth tokens live in DB rows (likely encrypted via a dedicated column type at Phase 5 design time, not in the deleted vault).

---

## 5. Key design decisions (frozen)

From `ROADMAP.md` § Architecture > Key Design Decisions:

1. **Profile in DB, not YAML/JSON.** Users edit via UI; API serves data. No config files.
2. **Single long-form bullets.** No oneline/detailed split. AI trims at apply time. 9-tag vocabulary (`ai-ml · backend · frontend · devops · data-eng · genai · leadership · platform · product`). Per-bullet `selection_override` (`always_include` / `never_include` / `null`).
3. **Typst over LaTeX** for PDF. 10–100× faster, single binary, clean JSON ingestion. LaTeX compat in Phase 6.
4. **Direct LLM SDKs, no LangChain.** Our use cases are single-prompt structured output. Both Anthropic + OpenAI SDKs support Pydantic natively.
5. **Auto-apply as user setting.** Default off. Semi-auto = generate docs + notify + human approves.
6. **Cloud + Local LLM.** Every AI feature offers both. User chooses in settings.
7. **Multi-axis Application state.** `status` (APPLIED → RECRUITER_SCREEN → ONSITE_LOOP → OFFER → CLOSED) + orthogonal sub-states (`docs_state`, `referral_state`, `recruiter_state`, computed `outreach_engagement`). NOT a flat enum.

---

## 6. Pattern catalog (with file pointers)

When implementing a pattern that already exists in the codebase, **read the existing usage first** — don't redesign.

| Pattern | First instance | Notes |
|---|---|---|
| HTMX form with autosave | `src/ui/routes/profile.py:get_edit` + `src/ui/templates/pages/profile_edit.html` | Plan 09 / plan 10b form wiring |
| SSE for long-running AI op | `src/ui/routes/auth.py:get_onboarding` (extraction) | 5 progress + 6 field + done + stepReady |
| LLM structured output | `src/llm/prompts/score_job.py` + `src/llm/prompts/extract_resume.py` | Pydantic schema + per-provider mode |
| LLM cost tracking | `src/services/llm_tracker.py:tracked_call` | Wraps every provider call |
| DRAFT lifecycle | `src/services/application_service.py` (plan 10 § C.5) | submit / discard / auto-apply queue + reuse heuristic |
| ATS adapter | `src/services/ats/greenhouse.py` + `lever.py` + `ashby.py` | Factory in `services/ats/__init__.py` |
| Per-field PUT autosave | `src/api/v1/profile.py:update_field` | Triggers `profile_updated` AppEvent |
| Stub fragment + JSON dual endpoint | `src/db/sample_data.py` + `src/ui/routes/*` (transitional) | Plan 60 / 0.2.7.17 removed the `NAAVIK_PERSISTENCE` env gate; routes incrementally migrate to `services/*` |
| Optimistic rollback | `src/ui/static/base.js` (htmx:responseError listener) | Pairs with `hx-swap-oob` |
| Lifespan-managed scheduler | `src/main.py` lifespan + `src/scheduler/__init__.py` | APScheduler PostgresJobStore |
| Env-presence indicator | `src/services/env_secrets.py:llm_provider_configured` + `_settings_llm.html` / `_settings_notifications.html` | Replaces deleted vault scope booleans (plan 26 / `0.2.0.01`); never returns values |

---

## 7. What this architecture is NOT

- **Not microservices.** One process. One DB. Scale vertically; if you need horizontal, run multiple instances behind the reverse proxy with sticky sessions.
- **Not event-driven.** APScheduler is the only async-job mechanism. No Kafka, no SQS, no message bus.
- **Not multi-tenant (yet).** Every entity has `user_id`; the model is multi-tenant-ready. But cron jobs assume `user_id=1`. Cloud tier ships with a `for user in users` loop wrapping each cron — Phase 2+.
- **Not horizontally scaled.** Single-instance deploy. If load grows, the bottleneck is LLM cost, not request throughput — fix the cost cap before scaling out.
- **Not framework-heavy.** No DRF, no Django admin, no Celery, no Redis (Postgres handles the queue via APScheduler). Each abstraction was a deliberate "no."

---

## 8. Pointer index

For deeper dives:

| Topic | Canonical doc |
|---|---|
| HTTP routes (every endpoint) | `docs/design/BACKEND.md` § C–D |
| Services (14 services, contracts) | `docs/design/BACKEND.md` § H–L |
| Cron jobs | `docs/design/BACKEND.md` § I |
| LLM abstraction (signatures + prompts) | `docs/design/BACKEND.md` § M |
| Observability (logging + metrics) | `docs/design/BACKEND.md` § N |
| Data entities (18 + Settings) | `docs/design/DATA_MODEL.md` § C |
| Application multi-axis state | `docs/design/DATA_MODEL.md` § A + § E |
| DRAFT cascade through state machines | `docs/design/DATA_MODEL.md` § E + F |
| HTMX patterns (autosave, SSE, modal, drag-drop) | `docs/design/INTERACTIONS.md` § B–H |
| Per-screen interactions | `docs/design/INTERACTIONS.md` § J |
| Component library (85 partials) | `docs/design/COMPONENTS.md` § G |
| Sample data fixtures | `docs/design/SAMPLE_DATA.md` |
| Visual contract (tokens, voice) | `DESIGN.md` |
| Design workflow (mockup → component → page) + agent process (skill routing, checklists, anti-patterns) | `docs/design/WORKFLOW.md` |
| Devops runbook | `docs/RUNBOOK.md` |
| Agent system | `docs/AGENT_OPS.md` |
| Roadmap | `ROADMAP.md` (folded ROADMAP_OVERVIEW.md content into § Index + § Phase status as of 0.7.0.22) |

When in doubt, **list the directory** and find by filename. The doc set evolves; a maintained table drifts.
