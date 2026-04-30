# Naavik Backend Architecture & API Design

> **Last updated:** 2026-04-30
> **Status:** Canonical — graduated from `docs/plans/04-backend-architecture.md` (archived).
> **Scope:** Entire backend surface — HTTP routes (page handlers, HTMX fragments, JSON API, SSE streams), service-layer architecture, scheduled jobs, scraping pipeline, application submission logic, document generation, external integrations, LLM provider abstraction, observability. Backend implementation (plan 10) builds against this contract.
> **Companion docs:** `DESIGN.md` (visual contract), `docs/design/SCREENS.md` (per-screen functional spec), `docs/design/DATA_MODEL.md` (entities + state axes), `docs/design/INTERACTIONS.md` (HTMX patterns), `docs/design/SAMPLE_DATA.md` (Phase 1 fixtures), `docs/design/COMPONENTS.md` (component library).

---

## A · File layout

```
src/
├── main.py                    ← FastAPI app, router mounting, global middleware, lifespan
├── config.py                  ← pydantic-settings
├── api/                       ← JSON endpoints under /api/v1/
│   ├── auth.py
│   ├── profile.py
│   ├── jobs.py
│   ├── applications.py
│   ├── tracking.py
│   ├── outreach.py
│   ├── settings.py
│   └── portfolio.py           ← /api/portfolio/* (public, no auth)
├── ui/
│   ├── routes/                ← HTMX page + fragment endpoints (HTML)
│   │   ├── auth.py            ← /login, /onboarding
│   │   ├── overview.py
│   │   ├── profile.py
│   │   ├── discover.py
│   │   ├── tracking.py
│   │   ├── outreach.py
│   │   ├── settings.py
│   │   └── fragments.py       ← cross-cutting fragments (modals, toasts)
│   ├── templates/             ← Jinja2
│   └── static/
├── services/                  ← Business logic (routes are thin; services are deep)
│   ├── auth.py
│   ├── profile_service.py
│   ├── extraction.py
│   ├── scraper_service.py     ← orchestrates scrapers, dedups, scores
│   ├── scorer.py
│   ├── document_generator.py  ← Tailored resume + cover letter pipeline
│   ├── application_service.py ← submission pipeline (auto + manual); DRAFT lifecycle
│   ├── email_monitor.py
│   ├── email_classifier.py
│   ├── contact_tracker.py
│   ├── outreach_generator.py
│   ├── notifications.py
│   ├── portfolio_sync.py
│   ├── llm_tracker.py         ← cost tracking wrapper around LLM calls
│   ├── vault.py               ← encrypted secrets vault (~/.naavik/secrets.enc)
│   ├── ats_credentials.py     ← per-board login state metadata + credential resolution
│   └── ats/                   ← Per-board submission adapters
│       ├── __init__.py        ← dispatcher: ApplicationBoard → adapter instance
│       ├── greenhouse.py
│       ├── lever.py
│       ├── ashby.py
│       ├── workday.py
│       ├── linkedin_apply.py
│       ├── indeed.py
│       └── generic.py
├── scraper/                   ← Per-source scrapers (HTML → RawJob)
│   ├── base.py                ← BaseScraper interface
│   ├── dispatch.py            ← URL → scraper instance
│   ├── linkedin.py            ← RSShub-fed; details via guest API / Playwright
│   ├── workday.py
│   ├── greenhouse.py
│   ├── lever.py
│   ├── ashby.py
│   ├── indeed.py
│   └── generic.py             ← Playwright fallback for arbitrary URLs
├── llm/                       ← LLM provider abstraction
│   ├── base.py                ← LLMProvider interface
│   ├── anthropic.py
│   ├── openai.py
│   ├── ollama.py
│   └── prompts/               ← versioned prompt modules
│       ├── extract_resume.py
│       ├── extract_job.py
│       ├── score_job.py
│       ├── select_bullets.py
│       ├── trim_bullet.py
│       ├── draft_cover_letter.py
│       ├── answer_screener.py
│       ├── classify_email.py
│       ├── draft_outreach.py
│       └── auto_tag_bullets.py
├── scheduler/                 ← APScheduler with Postgres job store
│   ├── __init__.py
│   ├── jobs.py                ← Job registry: name → service-method + trigger
│   └── lifespan.py            ← FastAPI lifespan integration; start/stop scheduler
├── integrations/              ← External services (each isolates auth + RPC)
│   ├── gmail.py               ← OAuth + IMAP
│   ├── outlook.py
│   ├── linkedin_browser.py    ← Playwright-driven DM sending (Phase 5)
│   ├── telegram.py            ← outbound + inbound (worker thread, not APScheduler)
│   ├── discord.py             ← outbound webhook
│   ├── calendar.py            ← Google Calendar OAuth
│   └── n8n_legacy.py          ← read-only sync from existing n8n DataTable
├── typst/                     ← PDF generation
│   ├── compiler.py            ← `typst compile` CLI wrapper
│   ├── validator.py           ← page-count + 1-line-bullet validation
│   └── templates/
├── models/                    ← SQLModel (per DATA_MODEL.md)
└── db/                        ← Session, seed, migrations
```

**Conventions:**

- Route handlers ≤30 lines each. Anything beyond parameter parsing + dispatch belongs in a service.
- Services own business logic. Async by default. Return Pydantic models. Raise typed exceptions caught by global handlers.
- LLM calls go through `llm/`. Never call provider SDKs directly from services.
- Scrapers conform to `BaseScraper`. Scraper code never touches the DB; `services/scraper_service.py` does.
- Background jobs are registered in `scheduler/jobs.py` and call services. Job functions stay thin.
- Integrations isolate auth state + RPC. Service code consumes integration methods, never raw SDK objects.
- **The DB stores no secret material.** Encrypted refresh tokens, ATS credentials, IMAP passwords, LinkedIn cookies — all live in `~/.naavik/secrets.enc` via `services/vault.py`. DB-side `ATSCredential` rows hold metadata only (`has_credential`, `login_status`, `last_login_at`). See § L.1 + DATA_MODEL.md § H.

---

## B · Page routes

Return `HTMLResponse` from `templates.TemplateResponse(...)`. All except `/login`, `/onboarding` require auth (JWT cookie set by `/api/v1/auth/login`). Auth is a FastAPI dependency.

| URL | Method | Template | Auth | Description |
|---|---|---|---|---|
| `/login` | GET | `pages/login.html` | none | Login form (Screen 1) |
| `/onboarding` | GET | `pages/onboarding.html` | required (post-login, pre-profile) | 3-step wizard (Screen 2). `?step=1\|2\|3`; default 1. |
| `/` | GET | `pages/overview.html` | required | Overview (Screen 3). Redirects to `/onboarding` if no profile. |
| `/profile` | GET | `pages/profile.html` | required | Profile read-only (Screen 4) |
| `/profile/edit` | GET | `pages/profile_edit.html` | required | Profile editor (Screen 5) |
| `/discover` | GET | `pages/discover.html` | required | Swipe queue + auto-apply queue card (Screen 7) |
| `/discover/{job_id}` | GET | `pages/discover_review.html` | required | Discover · review & apply (Screen 8). **Auto-creates a DRAFT Application** if one doesn't exist for `(user, job_id)` — pre-generates resume + cover letter + screener answers attached to it. Submit flips DRAFT → APPLIED. |
| `/tracking` | GET | `pages/tracking.html` | required | Tracking (Screen 9). `?view=board\|list`. DRAFT and CLOSED hidden by default per SCREENS.md visibility rule. |
| `/outreach` | GET | `pages/outreach.html` | required | Outreach (Screen 10). `?app=<id>` selects right pane. |
| `/settings` | GET | `pages/settings.html` | required | Settings (Screen 11). Default tab = `llm-provider`. |
| `/settings/{tab}` | GET | `pages/settings.html` | required | Deep-linked tab. `tab` validated against `SettingsTab` enum (`account`, `llm-provider`, `notifications`, `auto-apply`, `sources`, `deployment`). |
| `/_design/components` | GET | `pages/_design_components.html` | required + `Settings.debug` | Component fixture page. Renders every component in every variant for visual QA. Gated behind `Settings.debug`. |

---

## C · HTMX fragment routes

Return HTML partials. Triggered by `hx-get` / `hx-post`. Prefix `/_fragments/...` (or `/_modal/...` for modals).

| URL | Method | Returns | Triggered by | Used on |
|---|---|---|---|---|
| `/_modal/bullet-editor/{bullet_id}` | GET | bullet editor modal | edit pencil | Profile editor, Discover · review |
| `/_modal/confirm` | GET | confirm dialog (rendered from query params: `?title=&message=&action=&label=&tone=&method=`) | destructive actions | (any) |
| `/_fragments/profile/bullet-row/{bullet_id}` | GET | `bullet_edit_row` | OOB after save | Profile editor |
| `/_fragments/discover/next-card` | GET | `swipe_card` | after skip / save / auto-apply / submit | Discover |
| `/_fragments/discover/match-breakdown/{job_id}` | GET | `match_breakdown` | filter change | Discover |
| `/_fragments/apply/tailored-bullets/{job_id}` | GET | list of `tailored_bullet_row` | bullet toggle / regen | Discover · review |
| `/_fragments/apply/cover-letter-section/{application_id}/{section}` | GET / POST | `cover_letter_section` | inline edit save / regen | Discover · review |
| `/_fragments/apply/screener/{application_id}/{question_id}` | GET / PUT | `screener_question_card` | inline edit save | Discover · review |
| `/_fragments/tracking/board` | GET | `tracking_board` | view toggle, drag-drop OOB | Tracking |
| `/_fragments/tracking/list` | GET | list of `tracking_list_row` | view toggle, sort | Tracking |
| `/_fragments/tracking/followup-banner` | GET | `followup_banner` | SSE refresh | Tracking, Overview |
| `/_fragments/outreach/app-detail/{app_id}` | GET | partial of right pane | row click | Outreach |
| `/_fragments/outreach/draft/{contact_id}` | POST | `outreach_message_card` | regenerate / edit save | Outreach |
| `/_fragments/settings/test-connection` | POST | inline status card | Test connection | Settings · LLM |
| `/_fragments/overview/priority-actions` | GET | list of `priority_action_row` | refresh / mark done | Overview |
| `/_fragments/overview/email-signal` | GET | list of `email_signal_row` | SSE refresh | Overview, Tracking |
| `/_fragments/overview/pipeline-strip` | GET | `pipeline_strip` | refresh | Overview |
| `/_fragments/onboarding/step/{n}` | GET | step partial | step nav | Onboarding |
| `/_fragments/toast` | (OOB target) | `toast` | OOB swap from any state-changing endpoint | (any) |

**Conventions:**

- The confirm modal route (`/_modal/confirm`) is the canonical destructive-action gate. Per INTERACTIONS.md § E.4 it takes query params (title, message, action_url, label, tone, method) — **not a path-param `action_id`**. Query-params are flexible (any combo without registering action types); path-params would force pre-registration.
- The autosave indicator is delivered as an OOB swap inside the JSON API response at `PUT /api/v1/profile/{field}` — there's no separate `/_fragments/profile/autosave` endpoint, since the field PUT itself returns both the field payload and the OOB indicator.
- HTMX page routes that need parameterized URL keys (`/discover/:id`) set `<body data-template="/discover/:id">` so client-side keyboard handlers can dispatch correctly. See INTERACTIONS.md § F.1.

---

## D · JSON API routes

Under `/api/v1/`, return Pydantic models.

### D.1 Auth

| URL | Method | Request | Response |
|---|---|---|---|
| `/api/v1/auth/login` | POST | `{email, password, keep_signed_in}` | `204` + cookie + `{redirect_to}` |
| `/api/v1/auth/logout` | POST | — | `204`, clears cookie |
| `/api/v1/auth/me` | GET | — | `User` |
| `/api/v1/auth/csrf` | GET | — | `{csrf_token}` (rotated on auth events) |

### D.2 Profile / extraction / bullets

| URL | Method | Request | Response |
|---|---|---|---|
| `/api/v1/profile` | GET / PUT | — / `Profile` | `Profile` |
| `/api/v1/profile/{field}` | PUT | `{value}` | `{field, value, saved_at}` + OOB autosave indicator partial (per-field autosave) |
| `/api/v1/profile/from-extraction` | POST | extracted profile JSON | `Profile` |
| `/api/v1/profile/application-questions` | PUT | `ApplicationQuestionsPayload` (maps to flat columns on Profile per DATA_MODEL.md § B) | `ApplicationQuestionsPayload` |
| `/api/v1/extraction/upload` | POST | multipart PDF (`application/pdf`, ≤10 MB) | `{extraction_id, status: "queued"}` |
| `/api/v1/extraction/{id}` | GET | — | `Extraction` |
| `/api/v1/extraction/{id}/stream` | GET (SSE) | — | extraction events (per § E) |
| `/api/v1/bullets` | POST | `Bullet` | `Bullet` |
| `/api/v1/bullets/{id}` | PUT / DELETE | `Bullet` / — | `Bullet` / `204` |
| `/api/v1/bullets/{id}/rewrite` | POST | `{tone}` | `Bullet` (LLM-rewritten) |
| `/api/v1/bullets/reorder` | POST | `{bullet_ids: list[int]}` (in display order) | `204` |

### D.3 Jobs / Discover

| URL | Method | Request | Response |
|---|---|---|---|
| `/api/v1/jobs` | GET | `?queue_state=&score_min=&cursor=` | `{items: Job[], next_cursor}` |
| `/api/v1/jobs/{id}` | GET | — | `Job` |
| `/api/v1/jobs/by-url` | POST | `{url}` | scraped + scored `Job` (`+ Add by URL`) |
| `/api/v1/jobs/{id}/rescore` | POST | — | rescored `Job` (re-run scorer) |
| `/api/v1/discover/{job_id}/skip` | POST | — | `Job` (queue_state=skipped) |
| `/api/v1/discover/{job_id}/save` | POST | — | `Job` (queue_state=saved) |
| `/api/v1/discover/{job_id}/auto-submit` | POST | — | `{application_id, status: "queued"}` — flips Job.queue_state=queued_for_auto_apply, creates DRAFT Application, queues for next cron run |
| `/api/v1/discover/saved` | GET | — | saved `Job[]` |
| `/api/v1/discover/skipped` | GET | — | skipped `Job[]` |

### D.4 Applications

| URL | Method | Request | Response |
|---|---|---|---|
| `/api/v1/applications` | GET | `?status=&closed=&cursor=` | `{items: Application[], next_cursor}` |
| `/api/v1/applications/{id}` | GET | — | full `Application` with sub-states (incl. `submission_artifacts`) |
| `/api/v1/applications/{id}/submit` | POST | — | `Application` (DRAFT → APPLIED transition; uses pre-existing screener answers + generated documents on the DRAFT row) |
| `/api/v1/applications/{id}/discard` | DELETE | — | `204` (DRAFT → CLOSED `withdrawn_by_me`; soft delete) |
| `/api/v1/applications/{id}/status` | PUT | `{status, closed_reason?}` | `Application` (manual status override; closed_reason required when status=CLOSED) |
| `/api/v1/applications/manual` | POST | manual entry payload (no Job row) | `Application` (status=APPLIED, board=MANUAL; `+ Add manually` from Tracking) |
| `/api/v1/applications/{id}/bundle` | GET | — | ZIP (`resume.pdf`, `cover-letter.pdf`, `screener-answers.json`, `metadata.json`) |
| `/api/v1/applications/{id}/cover-letter/generate` | POST | `{tone}` | `text/event-stream` (SSE: `chunk`, `done`) — POST initiates, response is upgraded to SSE; HTMX consumes via `sse-connect` |
| `/api/v1/applications/{id}/cover-letter/sections/{section}` | PUT | `{text}` | section payload |
| `/api/v1/applications/{id}/screeners/{question_id}` | PUT | `{answer}` | `ApplicationScreenerAnswer` (sets `reviewed_at`) |
| `/api/v1/applications/{id}/resume/regen` | POST | — | `GeneratedDocument` |
| `/api/v1/applications/{id}/notes` | PUT | `{notes}` | `Application` |
| `/api/v1/applications/move` | POST | `{application_id, target_status}` | `Application` (Kanban drag-drop) |

**DRAFT lifecycle (cross-reference to § K):**

- Application rows are created in DRAFT status when a user opens `/discover/{job_id}` (manual review path) or right-swipes on Discover (auto-apply path).
- Pre-submission edits live on the DRAFT row: ScreenerAnswer rows, GeneratedDocument rows, cover-letter section text — all FK to the DRAFT Application.
- `/api/v1/applications/{id}/submit` is the only state-change endpoint that flips DRAFT → APPLIED. It composes the existing bundle and dispatches via `services/ats/__init__.py:dispatch(board)`.
- `/api/v1/applications/{id}/discard` deletes the DRAFT (status=CLOSED `withdrawn_by_me`, soft-delete via `deleted_at`). The user-facing label is "Discard draft".

### D.5 Tracking integrations + email

| URL | Method | Request | Response |
|---|---|---|---|
| `/api/v1/integrations/gmail/connect` | GET | OAuth start | redirect to Google |
| `/api/v1/integrations/gmail/callback` | GET | OAuth code | `{connected, account}` |
| `/api/v1/integrations/gmail/disconnect` | POST | — | `204` |
| `/api/v1/integrations/outlook/{action}` | (same shape: connect / callback / disconnect) | — | — |
| `/api/v1/integrations/calendar/{action}` | (same shape) | — | — |
| `/api/v1/integrations` | GET | — | list of `Integration` (provider, account, last_sync_at, status) |
| `/api/v1/email/threads` | GET | `?app_id=&classification=` | `EmailThread[]` |
| `/api/v1/email/threads/{id}` | GET | — | `EmailThread` with messages |
| `/api/v1/email/threads/{id}/draft-reply` | POST | `{intent}` | drafted reply text |
| `/api/v1/tracking/email-signals` | GET (SSE) | — | live signal events |

### D.6 Contacts / outreach

| URL | Method | Request | Response |
|---|---|---|---|
| `/api/v1/contacts` | GET / POST | `?company=&app_id=` / `Contact` | `Contact[]` / `Contact` |
| `/api/v1/contacts/{id}` | GET / PUT / DELETE | — / `Contact` / — | `Contact` / `Contact` / `204` |
| `/api/v1/contacts/find` | POST | `{company, role_filters}` | `Contact[]` (LinkedIn search via integration) |
| `/api/v1/outreach/messages` | GET | `?app_id=&contact_id=` | `OutreachMessage[]` |
| `/api/v1/outreach/draft` | POST | `{app_id, contact_id, intent}` | drafted `OutreachMessage` (status=draft) |
| `/api/v1/outreach/send` | POST | `{message_id, channel}` | sent `OutreachMessage` (status=sent, rate-limited) |
| `/api/v1/outreach/skip` | POST | `{contact_id, reason}` | `204` |

### D.7 Settings

| URL | Method | Request | Response |
|---|---|---|---|
| `/api/v1/settings/llm` | GET / PUT | — / `LLMSettings` | `LLMSettings` |
| `/api/v1/settings/llm/test` | POST | — | `{ok, latency_ms, model, error?}` |
| `/api/v1/settings/llm/usage` | GET | `?period=month` | `{tokens, cost_usd, breakdown}` |
| `/api/v1/settings/auto-apply` | GET / PUT | — / `AutoApplySettings` | `AutoApplySettings` |
| `/api/v1/settings/sources` | GET / PUT | — / `SourceSettings[]` | per-source enable/schedule |
| `/api/v1/settings/notifications` | GET / PUT | — / `NotificationSettings` | discord webhook + telegram bot config |
| `/api/v1/settings/notifications/test` | POST | `{channel}` | `{ok, error?}` |
| `/api/v1/settings/deployment` | GET | — | `DeploymentInfo` (mode, version, uptime, paths, scheduler status) |
| `/api/v1/settings/deployment/restart` | POST | — | `202 Accepted` (self-hosted only; `405 Method Not Allowed` on cloud) |
| `/api/v1/settings/deployment/logs` | GET (SSE) | — | log line events |
| `/api/v1/settings/account` | GET / PUT | — / `Account` | `Account` |
| `/api/v1/settings/account/password` | PUT | `{current, new}` | `204` |
| `/api/v1/settings/account/delete` | POST | `{confirm: "DELETE"}` | `204` (cascades) |

### D.8 Scheduler / admin

| URL | Method | Request | Response |
|---|---|---|---|
| `/api/v1/scheduler/jobs` | GET | — | list of registered jobs with next_run, last_run, status |
| `/api/v1/scheduler/jobs/{name}/run` | POST | — | `202` (manually trigger) |
| `/api/v1/scheduler/jobs/{name}/{action}` | POST | — | `204` (action: pause / resume) |

### D.9 Public (no auth)

| URL | Method | Request | Response |
|---|---|---|---|
| `/api/portfolio/cv` | GET | — | `Profile` JSON (filtered for public fields) |
| `/api/portfolio/resume.pdf` | GET | — | latest generic 1-page PDF |
| `/api/health` | GET | — | `{status, db, llm, scheduler, integrations}` |

---

## E · SSE streams

Per INTERACTIONS.md § C; 4 streams in scope.

| Stream URL | Trigger | Events | Consumer |
|---|---|---|---|
| `/api/v1/extraction/{id}/stream` | Onboarding step 2 | `progress`, `field`, `done`, `error` | `pages/onboarding.html` |
| `POST /api/v1/applications/{id}/cover-letter/generate` | Cover letter regen | `chunk`, `done` | `pages/discover_review.html` |
| `/api/v1/tracking/email-signals` | When on `/tracking` or `/` | `signal`, `stage_change` | `pages/tracking.html`, `pages/overview.html` |
| `/api/v1/settings/deployment/logs` | When on Settings · Deployment | `logline` | `pages/settings.html` |

The cover-letter stream is a `POST` that returns `text/event-stream` — HTMX `hx-ext="sse"` consumes it via `sse-connect` after the POST initiates. All other streams are plain `GET` SSE endpoints.

---

## F · Per-screen interaction map

| Screen | Outbound routes |
|---|---|
| 1 Login | `POST /api/v1/auth/login` |
| 2 Onboarding | `POST /api/v1/extraction/upload` → SSE `/api/v1/extraction/{id}/stream` → `POST /api/v1/profile/from-extraction` → redirect `/` |
| 3 Overview | SSE `/api/v1/tracking/email-signals`; HTMX `/_fragments/overview/priority-actions`, `/_fragments/overview/pipeline-strip` |
| 4 Profile | (read-only) |
| 5 Profile editor | `PUT /api/v1/profile/{field}`; `GET /_modal/bullet-editor/{id}` → `PUT /api/v1/bullets/{id}` → OOB swap; `POST /api/v1/bullets/reorder`; `POST /api/v1/bullets`; `DELETE /api/v1/bullets/{id}`; `PUT /api/v1/profile/application-questions` |
| 6 Bullet editor (modal) | (uses parent's HTMX hooks) |
| 7 Discover | `GET /api/v1/jobs?queue_state=unswiped`; `POST /api/v1/discover/{id}/skip\|save\|auto-submit` → `GET /_fragments/discover/next-card`; `POST /api/v1/jobs/by-url` |
| 8 Discover · review & apply | (DRAFT auto-created on page load) `GET /_fragments/apply/tailored-bullets/{job_id}`; `GET\|POST /_fragments/apply/cover-letter-section/{app_id}/{section}`; `POST /api/v1/applications/{id}/cover-letter/generate` (SSE); `PUT /_fragments/apply/screener/{app_id}/{q}`; `POST /api/v1/applications/{id}/submit`; `DELETE /api/v1/applications/{id}/discard`; `GET /api/v1/applications/{id}/bundle` |
| 9 Tracking | SSE `/api/v1/tracking/email-signals`; `GET /_fragments/tracking/board\|list`; `POST /api/v1/applications/move`; `GET /_fragments/tracking/followup-banner`; `POST /api/v1/applications/manual` |
| 10 Outreach | `GET /_fragments/outreach/app-detail/{id}`; `POST /api/v1/outreach/draft`; `POST /api/v1/outreach/send`; `POST /api/v1/contacts/find` |
| 11 Settings | `PUT /api/v1/settings/*`; `POST /api/v1/settings/llm/test`; `POST /api/v1/settings/notifications/test`; SSE `/api/v1/settings/deployment/logs`; `POST /api/v1/settings/deployment/restart` |

---

## G · HTTP conventions

1. **JSON envelope** — Pydantic models direct serialization. Collections wrap in `{ items: [...], next_cursor }` for cursor pagination, bare arrays for fixed-size lists.
2. **Error envelope** — `{ "error": { "code", "message", "details" } }` via global exception handler. Standard codes (400, 401, 403, 404, 409, 422, 429, 500).
3. **HTMX vs JSON** — UI-update routes under `/_fragments/...` and `/_modal/...`; programmatic routes under `/api/v1/...`. Don't double-route by default.
4. **Auth dependency** — `get_current_user` reads JWT cookie, raises 401 if missing/expired. Public routes skip explicitly.
5. **CSRF** — JWT cookie + `X-CSRF-Token` double-submit. Token rotated on auth events only. HTMX reads token from `<meta>` via `hx-headers` on `<body>`.
6. **CORS** — disabled for the main app; enabled only for `/api/portfolio/*` (allow `https://crypticsoul.dev`).
7. **Rate limiting** — applied at outbound integration boundaries (LinkedIn DM, scraping). Internal routes unthrottled in Phase 1.
8. **Pagination** — cursor-based for jobs / applications / messages (large, append-mostly); offset-based for contacts (small, static).
9. **Public portfolio API** — Phase 1 surface = `/cv` + `/resume.pdf` only. Section-level endpoints when crypticsoul.dev needs them.
10. **Bundle download** — synchronous Typst compile (typical <500ms). Async (download token) only if compile times grow.
11. **Cloud-only restart** — UI hides on cloud (read `DeploymentInfo.mode`); endpoint returns 405 if invoked.
12. **Path-param enums** — `/settings/{tab}` validates `tab` against the `SettingsTab` enum. Unknown values return 404.

---

## H · Service layer architecture

Services own all business logic. Routes parse → call service → return response.

### H.1 Service catalog

| Service | File | Responsibility |
|---|---|---|
| `auth` | `services/auth.py` | Login, password hashing (bcrypt), JWT issue/verify, session management |
| `profile_service` | `services/profile_service.py` | Profile CRUD, application questions, bullet ops, tag inference (LLM) |
| `extraction` | `services/extraction.py` | PDF → AI extraction → structured Profile. Owns SSE event emission for Onboarding step 2 |
| `scraper_service` | `services/scraper_service.py` | Orchestrates scrapers, dedups, scores, persists. Calls `scraper/*` and `scorer` |
| `scorer` | `services/scorer.py` | AI scoring (`prompts/score_job`), tag matching, visa filter |
| `document_generator` | `services/document_generator.py` | Resume + cover letter generation; bullet selection + trimming; Typst compilation; ScreenerAnswer drafting |
| `application_service` | `services/application_service.py` | DRAFT lifecycle, submission pipeline (auto + manual), state transitions, ATS dispatch |
| `email_monitor` | `services/email_monitor.py` | Sync via Gmail/Outlook integrations; persist new messages |
| `email_classifier` | `services/email_classifier.py` | LLM classification → `EmailClassification`; auto-derive Application sub-states |
| `contact_tracker` | `services/contact_tracker.py` | Contact CRUD, dedup, state inference from outreach messages |
| `outreach_generator` | `services/outreach_generator.py` | AI draft via `prompts/draft_outreach`; send via integration; track replies |
| `notifications` | `services/notifications.py` | Discord webhook, Telegram bot, in-app toast dispatch |
| `portfolio_sync` | `services/portfolio_sync.py` | Public profile API filtering; Netlify rebuild webhook |
| `llm_tracker` | `services/llm_tracker.py` | Wrap every LLM call: log tokens, dollars, latency to `ApiUsage` |
| `vault` | `services/vault.py` | Read/write encrypted secrets at `~/.naavik/secrets.enc` (AES-256-GCM). Master key from `SECRET_KEY` env. Single source for API keys, OAuth refresh tokens, IMAP passwords, ATS cookies |
| `ats_credentials` | `services/ats_credentials.py` | `ATSCredential` row CRUD; resolves credential metadata for UI; dispatches to `vault.get(board=...)` for actual secret material |

### H.2 Service patterns

- **Async-first.** All service methods `async def`. DB ops via `AsyncSession`.
- **Pydantic in / out.** No raw dicts at service boundaries.
- **Dependency injection.** Services declared as FastAPI dependencies; sessions via `Depends(get_session)`.
- **Typed exceptions.** `services/exceptions.py` defines `NaavikError` base + per-domain subclasses (`AuthError`, `ScrapingError`, `LLMProviderError`, `ATSError`, `VaultError`). Global handler maps to HTTP status.
- **Event emission.** Any state change emits `AppEvent` (per DATA_MODEL.md `AppEventKind`). Single source for Tracking + Outreach timelines.
- **Idempotency.** Background-job-callable services accept an idempotency key; re-running same op = no-op.
- **Vault boundary.** Any service that touches a secret (API key, OAuth token, ATS cookie, IMAP password) reads via `vault.get(scope, key)` — never directly from filesystem or env. Same write path: `vault.set(scope, key, value)`.

### H.3 Cross-service flows (examples)

**New job arrives via scraper:**
```
scheduler/scrape_jobs_<source>
  → scraper_service.scrape(source)
    → scraper/<source>.list_jobs() → fetch_detail()
    → prompts.extract_job(provider, html)
    → scraper_service.dedup()
    → scorer.score(job, profile)
    → AppEvent emitted
    → notifications.notify_new_high_score_job() if score ≥ threshold
```

**Manual review-and-apply (foreground):**
```
ui.routes.discover.review_apply (GET /discover/{job_id})
  → application_service.get_or_create_draft(user, job)  # creates DRAFT if missing
    → document_generator.pre_generate(draft)            # resume + cover letter + screeners
    → AppEvent (STATUS_CHANGE: None → DRAFT, triggered_by: "draft_creation")
  ─[user edits inline via /_fragments/apply/*]→
  ─[user clicks Submit]→
ui.routes.discover.submit (POST /api/v1/applications/{id}/submit)
  → application_service.submit_draft(application_id)
    → ats.dispatch(application.board).submit(application, bundle)
    → application.status = APPLIED
    → AppEvent (STATUS_CHANGE: DRAFT → APPLIED, triggered_by: "draft_submitted")
    → notifications.notify_application_submitted()
```

**Auto-apply queue (background):**
```
user right-swipe on Discover (POST /api/v1/discover/{job_id}/auto-submit)
  → application_service.queue_auto_apply(user, job)
    → Job.queue_state = QUEUED_FOR_AUTO_APPLY
    → Application created with status=DRAFT
    → AppEvent (STATUS_CHANGE: None → DRAFT, triggered_by: "auto_apply_queued")
  ─[next cron run, up to 10 min later]→
scheduler/applications.auto_apply
  → application_service.process_auto_apply_queue()
    → For each DRAFT with Job.queue_state=QUEUED_FOR_AUTO_APPLY:
      → document_generator.ensure_bundle_ready(draft)
      → ats.dispatch(application.board).submit(application, bundle)
      → On success: status=APPLIED; Job.queue_state=APPLIED
      → On failure (CAPTCHA / auth_required / rate_limit): keep DRAFT;
        write submission_artifacts.last_failure; surface in Discover · review queue
```

**Email signal triggers status update:**
```
scheduler/sync_gmail
  → email_monitor.sync()
    → email_classifier.classify(message) for each new
    → application_service.update_recruiter_state(app_id, signal)
    → AppEvent (RECRUITER_STATE_CHANGE)
    → notifications.notify_priority(app, signal)
```

---

## I · Scheduled jobs (cron)

APScheduler with `PostgresJobStore` (jobs survive restarts). Lifespan-managed: starts on FastAPI startup, stops on shutdown.

### I.1 Catalog by phase

**Phase 2 (job scraping + scoring):**

| Job name | Trigger | Service method |
|---|---|---|
| `scraping.linkedin` | every 30min | `scraper_service.scrape("linkedin")` |
| `scraping.workday` | every 60min | `scraper_service.scrape("workday")` |
| `scraping.greenhouse` | every 60min | `scraper_service.scrape("greenhouse")` |
| `scraping.lever` | every 60min | `scraper_service.scrape("lever")` |
| `scraping.ashby` | every 60min | `scraper_service.scrape("ashby")` |
| `scraping.indeed` | every 90min | `scraper_service.scrape("indeed")` |
| `jobs.dedup` | every 60min | `scraper_service.dedup_recent()` |
| `jobs.score_pending` | every 15min | `scorer.score_unscored_jobs()` |

**Phase 3 (auto-apply):**

| Job name | Trigger | Service method |
|---|---|---|
| `applications.auto_apply` | every 5min | `application_service.process_auto_apply_queue()` (was 10min in earlier draft; tightened so right-swipe submission feels timely) |

**Phase 4 (tracking):**

| Job name | Trigger | Service method |
|---|---|---|
| `tracking.sync_gmail` | every 10min | `email_monitor.sync("gmail")` |
| `tracking.sync_outlook` | every 10min | `email_monitor.sync("outlook")` |
| `tracking.classify_emails` | after each sync | `email_classifier.classify_unprocessed()` |
| `tracking.derive_recruiter_state` | every 30min | `application_service.derive_recruiter_states()` |
| `tracking.flag_followups` | every 60min | `outreach_generator.flag_needs_followup()` |

**Phase 5 (outreach):**

| Job name | Trigger | Service method |
|---|---|---|
| `outreach.send_linkedin_dms` | every 5min batch | `outreach_generator.send_pending_dms()` (max 50/day) |
| `outreach.check_dm_replies` | every 60min | `outreach_generator.check_replies()` |
| `outreach.suggest_next_moves` | every 24h | `outreach_generator.suggest_followups()` |

**Phase 6 (admin):**

| Job name | Trigger | Service method |
|---|---|---|
| `admin.daily_db_snapshot` | daily 02:00 | snapshot service |
| `admin.weekly_summary` | Sun 09:00 | `notifications.send_weekly_summary()` |
| `admin.aggregate_costs` | daily 00:30 | `llm_tracker.aggregate()` |
| `admin.cleanup_stale_docs` | weekly Sun 03:00 | `document_generator.cleanup_stale()` |
| `admin.refresh_oauth_tokens` | every 6h | each integration's refresh method |

### I.2 Job conventions

- **Idempotent.** Re-running same job = no-op or extension. Service-level dedup via idempotency key.
- **Logged.** Each job's stdout/stderr captured to `~/.naavik/logs/jobs/<job_name>.log`.
- **Failure handling.** APScheduler retry: 3 attempts, exponential backoff (5s, 30s, 5min). After 3 failures, fires `notifications.notify_admin(...)` and pauses.
- **Manually triggerable.** `POST /api/v1/scheduler/jobs/{name}/run` invokes immediately. Pause/resume via `/{action}` (action ∈ {pause, resume}).
- **Configurable schedule.** Per-source schedules editable via Settings · Sources tab; persisted to `Settings.source_schedules` (JSON).
- **Concurrency.** `max_instances=1` per job-name to prevent concurrent same-source scrapes; cross-source parallelism allowed.

### I.3 Telegram inbound (not on APScheduler)

Telegram inbound (Phase 5: `/status`, `/today`, `/silent` commands) uses long-polling via `aiogram` running as a **separate worker task**, not an APScheduler job. APScheduler cron triggers don't fit the long-poll model. The worker is mounted via the FastAPI lifespan alongside the scheduler — same start/stop semantics — but kept as a distinct task in `integrations/telegram.py`.

---

## J · Scraping architecture

Three layers: dispatcher → per-source scraper → service.

### J.1 `BaseScraper` interface (`scraper/base.py`)

```python
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ScrapeQuery(BaseModel):
    keywords: list[str] = []
    location: Optional[str] = None
    company_filter: Optional[list[str]] = None


class RawJob(BaseModel):
    source: str
    url: str
    company: str
    title: str
    location: Optional[str]
    salary_text: Optional[str]
    description_html: str
    posted_at: Optional[datetime]
    raw_meta: dict  # source-specific extras


class BaseScraper(ABC):
    rate_limit_seconds: float = 1.0  # min delay between requests

    @abstractmethod
    async def list_jobs(self, query: ScrapeQuery) -> list[RawJob]:
        """Return abbreviated job rows; details fetched separately."""

    @abstractmethod
    async def fetch_detail(self, url: str) -> RawJob:
        """Return full job detail for one URL."""

    @abstractmethod
    def matches(self, url: str) -> bool:
        """True if this scraper handles the URL."""
```

### J.2 Per-source modules

| Module | Strategy | Notes |
|---|---|---|
| `scraper/linkedin.py` | RSShub for listings (`rsshub.luminolab.net/linkedin/...`); LinkedIn guest API for details; Crawl4AI fallback | n8n migration source. Listings only — DM scraping is `integrations/linkedin_browser.py` |
| `scraper/workday.py` | Crawl4AI on `/job/<id>` URL pattern; per-company watchlist via `Settings.workday_companies` | |
| `scraper/greenhouse.py` | Crawl4AI on `https://boards.greenhouse.io/<company>/jobs/<id>`; lists via `https://boards.greenhouse.io/<company>` | |
| `scraper/lever.py` | Crawl4AI on `https://jobs.lever.co/<company>/<job_id>` | |
| `scraper/ashby.py` | Crawl4AI on `https://jobs.ashbyhq.com/<company>/<job_id>` | |
| `scraper/indeed.py` | Crawl4AI; rate-limited heavily (1 req / 30s) | |
| `scraper/generic.py` | Playwright fallback; user-supplied URL → headless render → HTML → AI extraction | "+ Add by URL" path |

### J.3 Pipeline (`services/scraper_service.py`)

```
scrape(source):
  1. Fetch listings via scraper.list_jobs(query)
  2. For each new URL not in DB:
     a. Fetch detail via scraper.fetch_detail(url)
     b. Extract structured Job via prompts.extract_job(provider, html)
     c. Dedup (URL match + fuzzy title/company via edit-distance)
     d. Score via scorer.score(job, profile)
     e. Visa-filter: auto-zero score if profile.visa_sponsorship_needed AND
        job requires US-citizen / no-sponsorship
     f. Persist Job(queue_state=unswiped)
     g. Emit AppEvent
     h. If score ≥ Settings.notify_threshold: notifications.notify_new_high_score(job)
  3. Log run summary to ~/.naavik/logs/jobs/scraping.<source>.log
```

### J.4 Anti-detection

- **Per-source rate limits** — respect `BaseScraper.rate_limit_seconds`.
- **Random jitter** — sleep `rate_limit_seconds + uniform(0, rate_limit_seconds*0.5)`.
- **User-Agent rotation** — Phase 2.x optional; per-request UA from a small pool.
- **Playwright headless mode** — generic scraper opts out of `navigator.webdriver` fingerprint.
- **Proxy support** — Phase 6+; `Settings.scraper_proxy_url` (optional).

### J.5 n8n migration

Phase 2 retires the existing n8n workflow (`Lw1uK5APIhIeUeem`):

1. Export n8n DataTable + Google Sheet as CSV (one-time).
2. `services/legacy_import.py` reads CSV → creates `Job` + `Application` rows.
3. RSShub feed (`rsshub.luminolab.net`) stays — it's just an upstream API; LinkedIn scraper continues to consume it.
4. Discord webhook stays — `services/notifications.py` takes over from n8n.
5. n8n Main Workflow disabled after Phase 2 ships and runs clean for 1 week.

---

## K · Application logic / submission pipeline

Two paths: auto-apply (background) and manual review-and-apply (foreground). Both share the same DRAFT lifecycle and submission machinery.

### K.1 DRAFT lifecycle

Application rows are created in `status=DRAFT` from two entry points:

1. **User opens `/discover/{job_id}`** — `application_service.get_or_create_draft(user, job)` creates a DRAFT if one doesn't exist for `(user, job)`. The DRAFT carries:
   - `docs_state=GENERATING` initially
   - `applied_at=None` until submitted
   - All ScreenerAnswer rows attached (FK → application_id)
   - All GeneratedDocument rows attached (resume + cover letter)
2. **User right-swipes on Discover** (`POST /api/v1/discover/{job_id}/auto-submit`) — same `get_or_create_draft` pathway, then sets `Job.queue_state = QUEUED_FOR_AUTO_APPLY`. The cron job (`applications.auto_apply`) processes the queue.

DRAFT applications are **hidden from Tracking by default** per SCREENS.md visibility rule. They surface on:

- `/discover/{job_id}` (the active manual review pane)
- `/discover` "auto-apply queue" card (the right rail's Up next pane shows DRAFT-with-queued-state count)
- Phase 1.x `Show drafts` filter on Tracking

Transitions:

```
None  ─────[get_or_create_draft]────→  DRAFT
DRAFT ─────[submit_draft, success]───→  APPLIED
DRAFT ─────[discard, user]────────────→  CLOSED (closed_reason=withdrawn_by_me)
DRAFT ─────[auto-apply failure (CAPTCHA / auth_required), persistent]→ stays DRAFT;
                                       writes Application.submission_artifacts.last_failure;
                                       surfaces in /discover review queue for manual fix-up
APPLIED → RECRUITER_SCREEN → ONSITE_LOOP → OFFER → CLOSED
```

### K.2 Auto-apply (background)

```
process_auto_apply_queue (runs every 5min, see § I.1):
  For each Application(status=DRAFT) WHERE Job.queue_state=QUEUED_FOR_AUTO_APPLY:
    1. document_generator.ensure_bundle_ready(application)
       — re-runs generation if docs_state in {NONE, FAILED, STALE};
         otherwise reuses existing GeneratedDocument rows
    2. ats.dispatch(application.board).submit(application, bundle)
       — bundle = resume.pdf + cover_letter.pdf + screener_answers (existing rows)
       - Success: application.status=APPLIED; application.applied_at=utcnow();
         submission_artifacts.board_application_id set;
         AppEvent(STATUS_CHANGE: DRAFT → APPLIED, triggered_by="auto_apply_submitted")
         Job.queue_state = APPLIED
       - Failure (transient: rate_limit / timeout): retry per AdapterResult.retry_after
       - Failure (persistent: CAPTCHA / auth_required / unknown):
         submission_artifacts.last_failure = {kind, message, captured_at}
         submission_artifacts.retry_count += 1
         keep status=DRAFT; user picks up via Discover · review & apply
         AppEvent(DOCS_FAILED or AUTO_APPLY_FAILED depending on cause)
    3. notifications.notify_application_submitted(application) on success
```

### K.3 Manual review-and-apply (foreground)

```
load_review_screen(job_id) (GET /discover/{job_id}):
  - application_service.get_or_create_draft(user, job)  → DRAFT row
  - If new draft: document_generator.pre_generate(draft) returns
    {resume: GeneratedDocument, cover_letter: GeneratedDocument, screeners: list[ApplicationScreenerAnswer]}
  - Render pages/discover_review.html with the bundle pre-loaded

user edits inline:
  - cover letter sections → PUT /api/v1/applications/{id}/cover-letter/sections/{section}
  - screener answers → PUT /api/v1/applications/{id}/screeners/{question_id} (sets reviewed_at)
  - bullet selection → PUT /_fragments/apply/tailored-bullets/{job_id} updates
    GeneratedDocument.bullet_selection JSON

user clicks Submit (POST /api/v1/applications/{id}/submit):
  1. application_service.validate_submittable(application)
     — all required ScreenerAnswers reviewed (reviewed_at IS NOT NULL)?
     — docs_state=READY?
     — fail with 409 + remediation hint if not
  2. ats.dispatch(application.board).submit(application, bundle)
     - Success: status=APPLIED; applied_at=utcnow();
       submission_artifacts.board_application_id set;
       AppEvent(STATUS_CHANGE: DRAFT → APPLIED, triggered_by="draft_submitted")
       Job.queue_state = APPLIED
     - Failure: same fallback as K.2
  3. Optionally (for boards we can't auto-submit): "Open ATS · {boardname}" + clipboard paste

user clicks Discard draft (DELETE /api/v1/applications/{id}/discard):
  - confirm modal → DELETE → application.status=CLOSED, closed_reason=withdrawn_by_me, deleted_at=utcnow()
  - AppEvent(STATUS_CHANGE: DRAFT → CLOSED)
```

### K.4 Document generation pipeline

`document_generator.generate_resume(application)`:

1. **Bullet selection** (`prompts.select_bullets`): `profile.bullets[]` + `application.job` → list of selected bullet IDs (8-12 typical), respecting `Bullet.selection_override`. Always-include pinned; never-include skipped.
2. **Bullet trimming** (`prompts.trim_bullet`): for each selected bullet, trim to one resume line, preserving numbers + verbs.
3. **Typst compilation** (`typst/compiler.py`): Profile + selected/trimmed bullets + `template="onepage"` → PDF.
4. **Validation** (`typst/validator.py`): verify page count = 1; if overflows, drop lowest-priority bullet and re-compile (max 3 retries).
5. **Persist** as `GeneratedDocument(application_id, kind=resume, path)` at `~/.naavik/data/documents/<app_id>/resume.pdf`. Sets `bullet_selection` JSONB to the selected IDs + trimmed lines (audit trail).

`document_generator.generate_cover_letter(application, tone="enthusiastic")`:

1. AI prompt (`prompts.draft_cover_letter`): profile + JD + tone → 4-section letter (intro / body / why_company / close).
2. Typst compile letter template → PDF.
3. Persist as `GeneratedDocument(kind=cover_letter)`.

`document_generator.answer_screeners(application)`:

1. For each screener question on the application form (extracted from JD or known per-board taxonomy):
   - **Auto-fill candidates** — questions matching a canonical Profile field (start date, salary expectation, work authorization, visa sponsorship, race, gender, veteran, disability): create `ApplicationScreenerAnswer(source=AUTO, answer=<profile.field>, reviewed_at=utcnow())`.
   - **AI-drafted** — all other questions: `prompts.answer_screener(profile, job, question)` → drafted answer. Create `ApplicationScreenerAnswer(source=DRAFTED, answer=<drafted>, drafted_by_model=provider.model_name, reviewed_at=None)`. Submit blocks until user reviews.
2. Each row carries `question_text`, `question_fingerprint` (normalized hash for Phase 2+ reuse cache), `question_type`, `choices` (for select types), `required`, `order_index` (preserves ATS form order).

### K.5 ATS submission per board (`services/ats/`)

Dispatcher: `services/ats/__init__.py` exposes `dispatch(board: ApplicationBoard) -> ATSAdapter`. Returns the per-board adapter instance.

| Board | Method | Module | Credential needed |
|---|---|---|---|
| Greenhouse | Public Boards API + Embedded API | `services/ats/greenhouse.py` | none (or company-scoped API key for direct submission) |
| Lever | Public API | `services/ats/lever.py` | none |
| Ashby | Public API | `services/ats/ashby.py` | none |
| Workday | Playwright form-fill (no API) | `services/ats/workday.py` | per-tenant session (login + 2FA) |
| LinkedIn (Easy Apply) | Playwright (requires user session cookie) | `services/ats/linkedin_apply.py` | LinkedIn cookie + session |
| Indeed | Playwright | `services/ats/indeed.py` | Indeed account session |
| Custom (company-direct) | Playwright generic form-fill | `services/ats/generic.py` | varies |
| Manual fallback | UI-side: "Open ATS" button + clipboard paste | (no module) | n/a |

Boards needing credentials look up state via `ats_credentials.get_credential(user_id, board)`:

- DB row `ATSCredential(user_id, board, has_credential, login_status, last_login_at)` provides metadata for UI rendering.
- Secret material (cookies, tokens) resolved via `vault.get(scope="ats", key=board)`.
- If `has_credential=False` or `login_status != OK`: adapter returns `SubmissionResult(ok=False, error="auth_required")`. UI surfaces "Connect {board}" prompt.

Uniform interface:

```python
class ATSAdapter(ABC):
    @abstractmethod
    async def submit(self, application: Application, bundle: ApplicationBundle) -> SubmissionResult: ...

    @abstractmethod
    def can_submit(self, job: Job) -> bool: ...

    @abstractmethod
    def requires_credential(self) -> bool: ...
```

`SubmissionResult = {ok, board_application_id, error?, retry_after?}`. Failures classify into `captcha`, `rate_limit`, `auth_required`, `field_mismatch`, `unknown` — drives the manual-review-fallback decision and the value of `Application.submission_artifacts.last_failure.kind`.

**Resume-parsing override (Workday-style boards).** Boards that auto-extract Profile fields from the uploaded PDF (Workday is the worst offender) get worked around: the adapter posts canonical Profile fields explicitly via the structured form-field API, **never relying on the board's PDF parser**. The adapter still uploads the PDF for the human reviewer, but every "First name / Last name / Email / Phone / Location" field is set programmatically from `Profile`.

---

## L · External integrations

### L.1 Email (Gmail + Outlook)

**Gmail OAuth flow:**

1. User clicks "Connect Gmail" on Settings · Notifications or Tracking integrations bar.
2. `GET /api/v1/integrations/gmail/connect` → redirects to Google's OAuth consent with scopes `gmail.readonly` + `gmail.metadata`.
3. Callback at `/api/v1/integrations/gmail/callback`:
   - Exchange code for refresh + access tokens.
   - `vault.set(scope="integrations", key="gmail.refresh_token", value=<encrypted>)` — refresh token persisted to `~/.naavik/secrets.enc`.
   - DB-side `Integration` row holds metadata only: `(provider, account_email, last_sync_at, status)`.
4. `tracking.sync_gmail` cron pulls new messages every 10min. Token refresh via `admin.refresh_oauth_tokens` every 6h.

**IMAP fallback** for non-Gmail/Outlook providers: manual setup on Settings · Notifications (host, port, username, password). Password stored via `vault.set(scope="integrations", key="imap.<account>.password", ...)`. Sync mechanism identical.

**Outlook OAuth** identical pattern (Phase 5).

### L.2 LinkedIn

LinkedIn has no public API for DMs / referral discovery / connection search. Strategies:

- **Listings:** RSShub already (Phase 2).
- **DMs / search / profile data:** Playwright with user-provided session cookie (Phase 5). Account-ban risk disclosed in Settings.
- **Rate limits:** max 50 DMs/day; max 100 profile views/day; jittered timing.

`integrations/linkedin_browser.py` exposes:

```python
async def send_dm(self, recipient_handle: str, body: str) -> SendResult: ...
async def search_employees(self, company: str, role_filters: list[str]) -> list[Contact]: ...
async def check_replies(self) -> list[Reply]: ...
```

Session cookie persisted via `vault.set(scope="integrations", key="linkedin.session_cookie", ...)`.

### L.3 Discord webhook (outbound only)

URL stored via `vault.set(scope="notifications", key="discord_webhook_url", ...)`. `services/notifications.py` posts on:

- New high-score job (≥ `Settings.notify_threshold`)
- Application submitted
- Interview invitation received (auto-classified)
- Offer received
- Rejection received (configurable; default OFF — too noisy)

Body: rich embed with company logo, role, score, link.

### L.4 Telegram bot (outbound + inbound)

Bot token via `vault.set(scope="notifications", key="telegram_bot_token", ...)`. Outbound: same events as Discord. Inbound (Phase 5): `/status`, `/today`, `/silent` commands query the pipeline.

**Implementation note:** the inbound long-poll runs as a **separate worker task** under the FastAPI lifespan, not as an APScheduler job (see § I.3). Outbound notifications use APScheduler as needed.

### L.5 Google Calendar (Phase 5)

OAuth identical to Gmail. On `EmailClassification.INTERVIEW_REQUEST`, auto-create event + invite (if user opts in). Integration only writes events; no read.

### L.6 n8n legacy (Phase 2 transition)

Read-only sync to import historical applications:

- `integrations/n8n_legacy.py` reads from `n8n.luminolab.net` DataTable `hfvivTlQThpPytkl` + Google Sheet `14pgCto2OAQxmb9w6ciOsReb3iQGE1V9XECU-o6E_c7M`.
- One-time CSV export → `services/legacy_import.py` → DB.
- After import succeeds + verified, n8n Main Workflow disabled.

---

## M · LLM provider abstraction

### M.1 `LLMProvider` interface (`llm/base.py`)

```python
from abc import ABC, abstractmethod
from typing import Type, TypeVar, AsyncIterator
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, max_tokens: int = 1024) -> str:
        """Plain text completion."""

    @abstractmethod
    async def structured(self, prompt: str, schema: Type[T]) -> T:
        """Structured output via tool use / json_schema / json mode."""

    @abstractmethod
    async def stream(self, prompt: str, max_tokens: int = 1024) -> AsyncIterator[str]:
        """Streaming text completion (chunks of partial output)."""

    @abstractmethod
    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """USD cost estimate."""

    @property
    @abstractmethod
    def model_name(self) -> str: ...
```

### M.2 Implementations

| Provider | Module | Default model | Structured output method |
|---|---|---|---|
| Anthropic Claude | `llm/anthropic.py` | `claude-3.5-sonnet-20250219` | Tool use |
| OpenAI GPT | `llm/openai.py` | `gpt-4o` | `response_format=json_schema` |
| Ollama (local) | `llm/ollama.py` | `llama3.1:70b` | JSON mode |

Provider selection: per-user `Settings.llm_provider` + `Settings.llm_model`. API keys resolved via `vault.get(scope="llm", key=<provider>)` — never from `Settings` directly. Provider factory: `llm/__init__.py:get_provider()`.

### M.3 Prompt templates (`llm/prompts/`)

Each prompt is a Python module with: a versioned prompt string, a Pydantic schema for the structured response, and a callable that takes domain inputs and returns the response.

```python
# llm/prompts/score_job.py
from pydantic import BaseModel, Field

class JobScore(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    explanation: str
    matched_tags: list[str]
    gaps: list[str]
    visa_concern: bool

PROMPT = """
You are scoring a job for a candidate. Given the candidate profile and the job
description, return a structured score 0.0-1.0...
"""

async def score_job(provider: LLMProvider, profile: Profile, job: Job) -> JobScore:
    rendered = PROMPT.format(profile=..., job=...)
    return await provider.structured(rendered, JobScore)
```

Phase 1 prompts: `extract_resume`, `extract_job`, `score_job`, `select_bullets`, `trim_bullet`, `draft_cover_letter`, `answer_screener`, `classify_email`, `draft_outreach`, `auto_tag_bullets` (auto-generates 9-tag set per bullet during resume parse).

**Versioning:** breaking changes get a filename suffix (`extract_resume_v2.py`). Minor changes use git history.

### M.4 Cost tracking

`services/llm_tracker.py` wraps every LLM call:

```python
async def tracked_call(provider: LLMProvider, method: str, *args, **kwargs):
    start = time.time()
    result = await getattr(provider, method)(*args, **kwargs)
    cost = provider.estimate_cost(input_tokens, output_tokens)
    await ApiUsage.create(
        provider=provider.model_name, method=method,
        input_tokens=input_tokens, output_tokens=output_tokens,
        cost_usd=cost, latency_ms=(time.time() - start) * 1000,
    )
    return result
```

`ApiUsage` table (DATA_MODEL.md Phase 2+ entity) aggregated daily by `admin.aggregate_costs` cron → surfaces in Settings · LLM Provider cost cards.

### M.5 Error handling + fallback

LLM calls go through `llm_tracker.tracked_call(...)` with retry policy:

- Rate limit (429): exponential backoff, max 3 retries.
- Timeout (504): retry once with longer timeout.
- Provider error (500): if `Settings.llm_fallback_provider` set, try fallback once; else raise `LLMProviderError`.
- Schema validation failure: re-prompt with stricter instructions (max 1 re-prompt).

---

## N · Observability

Phase 1 (MVP minimum):

- **Request logging.** FastAPI middleware logs `{method, path, status, latency_ms, user_id}` per request to `~/.naavik/logs/access.log`.
- **LLM call tracking.** Per § M.4, `ApiUsage` table.
- **Background job status.** Visible in Settings · Deployment log tail (live SSE) and `GET /api/v1/scheduler/jobs`.
- **Error reporting.** Stack traces to `~/.naavik/logs/error.log`. Critical errors → Discord (gated by `Settings.notify_on_errors`).
- **Health check.** `/api/health` returns `{status, db, llm, scheduler, integrations}` with each checked via real ping (DB query, LLM trivial completion, scheduler heartbeat, integrations refresh check).
- **Vault audit trail (Phase 1.x).** Every `vault.get` / `vault.set` writes a line to `~/.naavik/logs/vault-audit.log` with `{timestamp, op, scope, key, caller_service}`. Secret value never logged.

Phase 6 additions:

- Optional Prometheus metrics endpoint `/metrics`.
- Optional Sentry integration via `SENTRY_DSN` env.
- Performance tracing (OpenTelemetry) for LLM / scraper / ATS submission paths.

---

## O · Settings shape consumed by services

The full `Settings` model shape is canonical in DATA_MODEL.md § L. Cross-references for the fields services in this doc consume:

| Field | Consumer | Notes |
|---|---|---|
| `llm_provider`, `llm_model` | `llm/__init__.py:get_provider()` | API key resolved via vault, not stored here |
| `llm_fallback_provider` | `llm_tracker.tracked_call` § M.5 | Optional |
| `auto_apply_enabled`, `auto_apply_score_threshold`, `auto_apply_daily_cap` | `application_service.process_auto_apply_queue()` | |
| `notify_threshold` | `scraper_service.scrape()` § J.3 | High-score Discord/Telegram notification gate |
| `notify_on_errors` | `services/notifications.py` § N | Critical-error Discord gate |
| `notifications_enabled` (dict per event type) | `services/notifications.py` | Per-event-type toggles |
| `sources_enabled`, `source_schedules` | `scheduler/jobs.py`, `scraper_service` | Per-source enable + cron override |
| `workday_companies` | `scraper/workday.py` | Per-tenant watchlist |
| `scraper_proxy_url` | `scraper/base.py` § J.4 | Phase 6+ |
| `deployment_mode`, `deployment_version` | `services/portfolio_sync.py`, Settings UI | |
| `portfolio_webhook_url` | `services/portfolio_sync.py` | Netlify rebuild trigger |
| `debug` | `/_design/components` route gate | |

**Secret material is NOT on Settings.** Every secret (LLM API keys, OAuth refresh tokens, IMAP passwords, Discord webhook URL, Telegram bot token, ATS cookies, LinkedIn session) lives in `~/.naavik/secrets.enc` via `services/vault.py`. Settings stores at most a fingerprint (`llm_api_key_fingerprint: sha256:...`) so the UI can show "key set" without holding the key.

---

## P · Phase mapping

This contract describes the full backend across all phases. Implementation lands in waves per `ROADMAP.md` § Phase 1 § Implementation waves:

| Wave | Sections in scope | ROADMAP phase |
|---|---|---|
| 3 (initial backend) | A, B-G (HTTP routes), H (services skeleton — auth, profile, settings, application_service partial, vault, ats_credentials), N (basic observability) | Phase 1 |
| 6 (real backend) | H complete (all services), M (LLM abstraction), Typst compilation, full DRAFT lifecycle (K.1) | Phase 1.x |
| Phase 2 | I (job-scraping cron), J (scrapers), partial K (auto-apply pipeline) | Phase 2 |
| Phase 3 | K complete (scoring, document_generator, ats/*) | Phase 3 |
| Phase 4 | I (tracking cron), L.1 (Gmail/Outlook), email_classifier | Phase 4 |
| Phase 5 | I (outreach cron), L.2 (LinkedIn browser), L.3-L.5 (Discord/Telegram/Calendar), outreach_generator | Phase 5 |
| Phase 6 | N expansion (Prometheus, Sentry, OTel) | Phase 6 |
