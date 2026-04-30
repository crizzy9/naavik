---
Status: APPROVED
Type: design
Authored: 2026-04-30
Last updated: 2026-04-30
Approved: 2026-04-30
Depends on: 02-mvp-master-plan, 05-data-model
---

# 04 · Backend architecture & API design

## Goal

Define the entire backend surface — HTTP routes (page handlers, HTMX fragments, JSON API, SSE streams), service-layer architecture, scheduled jobs, scraping pipeline, application submission logic, document generation, external integrations (email, LinkedIn, Discord, Telegram, Calendar), LLM provider abstraction, and observability — as a single cohesive contract. Backend implementation (plan 10) builds against this contract; routes, services, scrapers, jobs, and integrations all flow from it. When approved, this plan's content graduates to `docs/design/BACKEND.md`.

## Context / why

The original scope was "route table" (HTTP endpoints only). Review feedback: that's a small slice of the actual backend — most of Naavik's value (scraping, scoring, document generation, email classification, outreach automation) runs in services and scheduled jobs that the routes merely surface. Designing routes without designing services / cron / integrations means re-discovering the architecture during implementation, which causes drift. This plan covers everything end-to-end so plan 10 has a single contract.

`ROADMAP.md` describes phases (Phase 2 scrapers, Phase 3 scoring, Phase 4 tracking, Phase 5 outreach) but doesn't define service interfaces or job catalogs. `SCREENS.md` describes per-screen interactions narratively. This plan stitches them together with the data model from plan 05.

## Proposal

### A · File layout

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
│   ├── application_service.py ← submission pipeline (auto + manual)
│   ├── email_monitor.py
│   ├── email_classifier.py
│   ├── contact_tracker.py
│   ├── outreach_generator.py
│   ├── notifications.py
│   ├── portfolio_sync.py
│   ├── llm_tracker.py         ← cost tracking wrapper around LLM calls
│   └── ats/                   ← Per-board submission adapters
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
│       └── draft_outreach.py
├── scheduler/                 ← APScheduler with Postgres job store
│   ├── __init__.py
│   ├── jobs.py                ← Job registry: name → service-method + trigger
│   └── lifespan.py            ← FastAPI lifespan integration; start/stop scheduler
├── integrations/              ← External services (each isolates auth + RPC)
│   ├── gmail.py               ← OAuth + IMAP
│   ├── outlook.py
│   ├── linkedin_browser.py    ← Playwright-driven DM sending
│   ├── discord.py             ← outbound webhook
│   ├── telegram.py            ← outbound + inbound poll
│   ├── calendar.py            ← Google Calendar OAuth
│   └── n8n_legacy.py          ← read-only sync from existing n8n DataTable
├── typst/                     ← PDF generation
│   ├── compiler.py            ← `typst compile` CLI wrapper
│   ├── validator.py           ← page-count + 1-line-bullet validation
│   └── templates/
├── models/                    ← SQLModel (per plan 05)
└── db/                        ← Session, seed, migrations
```

**Conventions:**
- Route handlers ≤30 lines each. Anything beyond parameter parsing + dispatch belongs in a service.
- Services own business logic. Async by default. Return Pydantic models. Raise typed exceptions caught by global handlers.
- LLM calls go through `llm/`. Never call provider SDKs directly from services.
- Scrapers conform to `BaseScraper`. Scraper code never touches the DB; `services/scraper_service.py` does.
- Background jobs are registered in `scheduler/jobs.py` and call services. Job functions stay thin.
- Integrations isolate auth state + RPC. Service code consumes integration methods, never raw SDK objects.

### B · Page routes

Return `HTMLResponse` from `templates.TemplateResponse(...)`. All except `/login`, `/onboarding` require auth (JWT cookie set by `/api/v1/auth/login`). Auth is a FastAPI dependency.

| URL | Method | Template | Auth | Description |
|---|---|---|---|---|
| `/login` | GET | `pages/login.html` | none | Login form (Screen 1) |
| `/onboarding` | GET | `pages/onboarding.html` | required (post-login, pre-profile) | 3-step wizard (Screen 2). `?step=1\|2\|3`; default 1. |
| `/` | GET | `pages/overview.html` | required | Overview (Screen 3). Redirects to `/onboarding` if no profile. |
| `/profile` | GET | `pages/profile.html` | required | Profile read-only (Screen 4) |
| `/profile/edit` | GET | `pages/profile_edit.html` | required | Profile editor (Screen 5) |
| `/discover` | GET | `pages/discover.html` | required | Swipe queue (Screen 7) |
| `/discover/{job_id}` | GET | `pages/discover_review.html` | required | Discover · review & apply (Screen 8) |
| `/tracking` | GET | `pages/tracking.html` | required | Tracking (Screen 9). `?view=board\|list`. |
| `/outreach` | GET | `pages/outreach.html` | required | Outreach (Screen 10). `?app=<id>` selects right pane. |
| `/settings` | GET | `pages/settings.html` | required | Settings (Screen 11). Default tab = `llm-provider`. |
| `/settings/{tab}` | GET | `pages/settings.html` | required | Deep-linked tab. |
| `/_design/components` | GET | `pages/_design_components.html` | required + `settings.debug` | Component fixture page (per plan 03 § E). |

### C · HTMX fragment routes

Return HTML partials. Triggered by `hx-get` / `hx-post`. Prefix `/_fragments/...` (locked decision; see § G).

| URL | Method | Returns | Triggered by | Used on |
|---|---|---|---|---|
| `/_modal/bullet-editor/{bullet_id}` | GET | bullet editor modal | edit pencil | Profile editor, Discover · review |
| `/_modal/confirm/{action_id}` | GET | confirm dialog | destructive actions | (any) |
| `/_fragments/profile/bullet-row/{bullet_id}` | GET | `bullet_edit_row` | OOB after save | Profile editor |
| `/_fragments/profile/autosave` | POST | `autosave_indicator` | OOB after field PUT | Profile editor |
| `/_fragments/discover/next-card` | GET | `swipe_card` | after skip / save / auto-apply / submit | Discover |
| `/_fragments/discover/match-breakdown/{job_id}` | GET | `match_breakdown` | filter change | Discover |
| `/_fragments/apply/tailored-bullets/{job_id}` | GET | list of `tailored_bullet_row` | bullet toggle / regen | Discover · review |
| `/_fragments/apply/cover-letter-section/{job_id}/{section}` | GET / POST | `cover_letter_section` | inline edit save / regen | Discover · review |
| `/_fragments/apply/screener/{job_id}/{question_id}` | GET / POST | `screener_question_card` | inline edit save | Discover · review |
| `/_fragments/tracking/board` | GET | `tracking_board` | view toggle, drag-drop OOB | Tracking |
| `/_fragments/tracking/list` | GET | list of `tracking_list_row` | view toggle, sort | Tracking |
| `/_fragments/tracking/followup-banner` | GET | `followup_banner` | SSE refresh | Tracking, Overview |
| `/_fragments/outreach/app-detail/{app_id}` | GET | partial of right pane | row click | Outreach |
| `/_fragments/outreach/draft/{contact_id}` | POST | `outreach_message_card` | regenerate / edit save | Outreach |
| `/_fragments/settings/test-connection` | POST | inline status card | Test connection | Settings · LLM |
| `/_fragments/settings/log-line` | (SSE event) | log line element | SSE stream | Settings · Deployment |
| `/_fragments/overview/priority-actions` | GET | list of `priority_action_row` | refresh / mark done | Overview |
| `/_fragments/overview/email-signal` | GET | list of `email_signal_row` | SSE refresh | Overview, Tracking |
| `/_fragments/overview/pipeline-strip` | GET | `pipeline_strip` | refresh | Overview |
| `/_fragments/onboarding/step/{n}` | GET | step partial | step nav | Onboarding |
| `/_fragments/onboarding/extraction` | (SSE event) | extraction progress | SSE stream | Onboarding step 2 |
| `/_fragments/toast` | (OOB target) | `toast` | OOB swap from any state-changing endpoint | (any) |

### D · JSON API routes

Under `/api/v1/`, return Pydantic models.

#### D.1 Auth

| URL | Method | Request | Response |
|---|---|---|---|
| `/api/v1/auth/login` | POST | `{email, password, keep_signed_in}` | `204` + cookie + `{redirect_to}` |
| `/api/v1/auth/logout` | POST | — | `204`, clears cookie |
| `/api/v1/auth/me` | GET | — | `User` |
| `/api/v1/auth/csrf` | GET | — | `{csrf_token}` (rotated on auth events) |

#### D.2 Profile / extraction / bullets

| URL | Method | Request | Response |
|---|---|---|---|
| `/api/v1/profile` | GET / PUT | — / `Profile` | `Profile` |
| `/api/v1/profile/{field}` | PUT | `{value}` | `{field, value, saved_at}` (per-field autosave) |
| `/api/v1/profile/from-extraction` | POST | extracted profile JSON | `Profile` |
| `/api/v1/profile/application-questions` | PUT | `ApplicationQuestions` | `ApplicationQuestions` |
| `/api/v1/extraction/upload` | POST | multipart PDF | `{extraction_id, status: "queued"}` |
| `/api/v1/extraction/{id}` | GET | — | `Extraction` |
| `/api/v1/extraction/{id}/stream` | GET (SSE) | — | extraction events |
| `/api/v1/bullets` | POST | `Bullet` | `Bullet` |
| `/api/v1/bullets/{id}` | PUT / DELETE | `Bullet` / — | `Bullet` / `204` |
| `/api/v1/bullets/{id}/rewrite` | POST | `{tone}` | `Bullet` (LLM-rewritten) |
| `/api/v1/bullets/reorder` | POST | `[bullet_ids in order]` | `204` |

#### D.3 Jobs / Discover

| URL | Method | Request | Response |
|---|---|---|---|
| `/api/v1/jobs` | GET | `?queue_state=&score_min=&cursor=` | `{items: Job[], next_cursor}` |
| `/api/v1/jobs/{id}` | GET | — | `Job` |
| `/api/v1/jobs/by-url` | POST | `{url}` | scraped + scored `Job` (`+ Add by URL`) |
| `/api/v1/jobs/{id}/rescore` | POST | — | rescored `Job` (re-run scorer) |
| `/api/v1/discover/{job_id}/skip` | POST | — | `Job` (queue_state=skipped) |
| `/api/v1/discover/{job_id}/save` | POST | — | `Job` (queue_state=saved) |
| `/api/v1/discover/{job_id}/auto-submit` | POST | — | `{application_id, status: "queued"}` |
| `/api/v1/discover/saved` | GET | — | saved `Job[]` |
| `/api/v1/discover/skipped` | GET | — | skipped `Job[]` |

#### D.4 Applications

| URL | Method | Request | Response |
|---|---|---|---|
| `/api/v1/applications` | GET | `?status=&closed=&cursor=` | `{items: Application[], next_cursor}` |
| `/api/v1/applications` | POST | `{job_id, bullets, cover_letter, screener_answers}` | `Application` (manual review-and-apply) |
| `/api/v1/applications/{id}` | GET | — | full `Application` with sub-states |
| `/api/v1/applications/{id}/status` | PUT | `{status, closed_reason?}` | `Application` |
| `/api/v1/applications/{id}/manual` | POST | manual entry payload | `Application` (no Job row) |
| `/api/v1/applications/{id}/bundle` | GET | — | ZIP (`resume.pdf`, `cover-letter.pdf`, `screener-answers.json`, `metadata.json`) |
| `/api/v1/applications/{id}/cover-letter/generate` | POST | `{tone}` | SSE stream (`chunk`, `done`) |
| `/api/v1/applications/{id}/cover-letter/sections/{section}` | PUT | `{text}` | section payload |
| `/api/v1/applications/{id}/screeners/{question_id}` | PUT | `{answer}` | answer payload |
| `/api/v1/applications/{id}/resume/regen` | POST | — | `GeneratedDocument` |
| `/api/v1/applications/{id}/notes` | PUT | `{notes}` | `Application` |
| `/api/v1/applications/move` | POST | `{application_id, target_status}` | `Application` (Kanban drag-drop) |

#### D.5 Tracking integrations + email

| URL | Method | Request | Response |
|---|---|---|---|
| `/api/v1/integrations/gmail/connect` | GET | OAuth start | redirect to Google |
| `/api/v1/integrations/gmail/callback` | GET | OAuth code | `{connected, account}` |
| `/api/v1/integrations/gmail/disconnect` | POST | — | `204` |
| `/api/v1/integrations/outlook/{connect\|callback\|disconnect}` | (same shape) | | |
| `/api/v1/integrations/calendar/{connect\|callback\|disconnect}` | (same shape) | | |
| `/api/v1/integrations` | GET | — | list of `Integration` (provider, account, last_sync_at, status) |
| `/api/v1/email/threads` | GET | `?app_id=&classification=` | `EmailThread[]` |
| `/api/v1/email/threads/{id}` | GET | — | `EmailThread` with messages |
| `/api/v1/email/threads/{id}/draft-reply` | POST | `{intent}` | drafted reply text |
| `/api/v1/tracking/email-signals` | GET (SSE) | — | live signal events |

#### D.6 Contacts / outreach

| URL | Method | Request | Response |
|---|---|---|---|
| `/api/v1/contacts` | GET / POST | `?company=&app_id=` / `Contact` | `Contact[]` / `Contact` |
| `/api/v1/contacts/{id}` | GET / PUT / DELETE | — / `Contact` / — | `Contact` / `Contact` / `204` |
| `/api/v1/contacts/find` | POST | `{company, role_filters}` | `Contact[]` (LinkedIn search via integration) |
| `/api/v1/outreach/messages` | GET | `?app_id=&contact_id=` | `OutreachMessage[]` |
| `/api/v1/outreach/draft` | POST | `{app_id, contact_id, intent}` | drafted `OutreachMessage` (status=draft) |
| `/api/v1/outreach/send` | POST | `{message_id, channel}` | sent `OutreachMessage` (status=sent, rate-limited) |
| `/api/v1/outreach/skip` | POST | `{contact_id, reason}` | `204` |

#### D.7 Settings

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
| `/api/v1/settings/deployment/restart` | POST | — | `202 Accepted` (self-hosted only; 405 on cloud) |
| `/api/v1/settings/deployment/logs` | GET (SSE) | — | log line events |
| `/api/v1/settings/account` | GET / PUT | — / `Account` | `Account` |
| `/api/v1/settings/account/password` | PUT | `{current, new}` | `204` |
| `/api/v1/settings/account/delete` | POST | `{confirm: "DELETE"}` | `204` (cascades) |

#### D.8 Scheduler / admin

| URL | Method | Request | Response |
|---|---|---|---|
| `/api/v1/scheduler/jobs` | GET | — | list of registered jobs with next_run, last_run, status |
| `/api/v1/scheduler/jobs/{name}/run` | POST | — | `202` (manually trigger) |
| `/api/v1/scheduler/jobs/{name}/{pause\|resume}` | POST | — | `204` |

#### D.9 Public (no auth)

| URL | Method | Request | Response |
|---|---|---|---|
| `/api/portfolio/cv` | GET | — | `Profile` JSON (filtered for public fields) |
| `/api/portfolio/resume.pdf` | GET | — | latest generic 1-page PDF |
| `/api/health` | GET | — | `{status, db, llm, scheduler, integrations}` |

### E · SSE streams

Per plan 06 § C; 4 streams in scope:

| Stream URL | Trigger | Events | Consumer |
|---|---|---|---|
| `/api/v1/extraction/{id}/stream` | Onboarding step 2 | `progress`, `field`, `done`, `error` | `pages/onboarding.html` |
| `/api/v1/applications/{id}/cover-letter/generate` | Cover letter regen | `chunk`, `done` | `pages/discover_review.html` |
| `/api/v1/tracking/email-signals` | When on `/tracking` or `/` | `signal`, `stage_change` | `pages/tracking.html`, `pages/overview.html` |
| `/api/v1/settings/deployment/logs` | When on Settings · Deployment | `logline` | `pages/settings.html` |

### F · Per-screen interaction map

| Screen | Outbound routes |
|---|---|
| 1 Login | `POST /api/v1/auth/login` |
| 2 Onboarding | `POST /api/v1/extraction/upload` → SSE `/api/v1/extraction/{id}/stream` → `POST /api/v1/profile/from-extraction` → redirect `/` |
| 3 Overview | SSE `/api/v1/tracking/email-signals`; HTMX `/_fragments/overview/priority-actions`, `/_fragments/overview/pipeline-strip` |
| 4 Profile | (read-only) |
| 5 Profile editor | `PUT /api/v1/profile/{field}`; `GET /_modal/bullet-editor/{id}` → `PUT /api/v1/bullets/{id}` → OOB swap; `POST /api/v1/bullets/reorder`; `POST /api/v1/bullets`; `DELETE /api/v1/bullets/{id}`; `PUT /api/v1/profile/application-questions` |
| 6 Bullet editor (modal) | (uses parent's HTMX hooks) |
| 7 Discover | `GET /api/v1/jobs?queue_state=unswiped`; `POST /api/v1/discover/{id}/skip\|save\|auto-submit` → `GET /_fragments/discover/next-card`; `POST /api/v1/jobs/by-url` |
| 8 Discover · review & apply | `GET /_fragments/apply/tailored-bullets/{id}`; `GET\|POST /_fragments/apply/cover-letter-section/{id}/{section}`; `POST /api/v1/applications/{id}/cover-letter/generate` (SSE); `PUT /_fragments/apply/screener/{id}/{q}`; `POST /api/v1/applications`; `GET /api/v1/applications/{id}/bundle` |
| 9 Tracking | SSE `/api/v1/tracking/email-signals`; `GET /_fragments/tracking/board\|list`; `POST /api/v1/applications/move`; `GET /_fragments/tracking/followup-banner`; `POST /api/v1/applications/{id}/manual` |
| 10 Outreach | `GET /_fragments/outreach/app-detail/{id}`; `POST /api/v1/outreach/draft`; `POST /api/v1/outreach/send`; `POST /api/v1/contacts/find` |
| 11 Settings | `PUT /api/v1/settings/*`; `POST /api/v1/settings/llm/test`; `POST /api/v1/settings/notifications/test`; SSE `/api/v1/settings/deployment/logs`; `POST /api/v1/settings/deployment/restart` |

### G · HTTP conventions (decided 2026-04-30)

1. **JSON envelope** — Pydantic models direct serialization. Collections wrap in `{ items: [...], next_cursor }` for cursor pagination, bare arrays for fixed-size lists.
2. **Error envelope** — `{ "error": { "code", "message", "details" } }` via global exception handler. Standard codes (400, 401, 403, 404, 409, 422, 429, 500).
3. **HTMX vs JSON** — UI-update routes under `/_fragments/...`; programmatic routes under `/api/v1/...`. Don't double-route by default.
4. **Auth dependency** — `get_current_user` reads JWT cookie, raises 401 if missing/expired. Public routes skip explicitly.
5. **CSRF** — JWT cookie + `X-CSRF-Token` double-submit. Token rotated on auth events only. HTMX reads token from `<meta>` via `hx-headers` on `<body>`.
6. **CORS** — disabled for the main app; enabled only for `/api/portfolio/*` (allow `https://crypticsoul.dev`).
7. **Rate limiting** — applied at outbound integration boundaries (LinkedIn DM, scraping). Internal routes unthrottled in Phase 1.
8. **Pagination** — cursor-based for jobs / applications / messages (large, append-mostly); offset-based for contacts (small, static).
9. **Public portfolio API** — Phase 1 surface = `/cv` + `/resume.pdf` only. Section-level endpoints when crypticsoul.dev needs them.
10. **Bundle download** — synchronous Typst compile (typical <500ms). Async (download token) only if compile times grow.
11. **Cloud-only restart** — UI hides on cloud (read `DeploymentInfo.mode`); endpoint returns 405 if invoked.

### H · Service layer architecture

Services own all business logic. Routes parse → call service → return response.

#### H.1 Service catalog

| Service | File | Responsibility |
|---|---|---|
| `auth` | `services/auth.py` | Login, password hashing (bcrypt), JWT issue/verify, session management |
| `profile_service` | `services/profile_service.py` | Profile CRUD, application questions, bullet ops, tag inference (LLM) |
| `extraction` | `services/extraction.py` | PDF → AI extraction → structured Profile. Owns SSE event emission for Onboarding step 2 |
| `scraper_service` | `services/scraper_service.py` | Orchestrates scrapers, dedups, scores, persists. Calls `scraper/*` and `scorer` |
| `scorer` | `services/scorer.py` | AI scoring (`prompts/score_job`), tag matching, visa filter |
| `document_generator` | `services/document_generator.py` | Resume + cover letter generation; bullet selection + trimming; Typst compilation |
| `application_service` | `services/application_service.py` | Submission pipeline (auto + manual), state transitions, ATS dispatch |
| `email_monitor` | `services/email_monitor.py` | Sync via Gmail/Outlook integrations; persist new messages |
| `email_classifier` | `services/email_classifier.py` | LLM classification → `EmailClassification`; auto-derive Application sub-states |
| `contact_tracker` | `services/contact_tracker.py` | Contact CRUD, dedup, state inference from outreach messages |
| `outreach_generator` | `services/outreach_generator.py` | AI draft via `prompts/draft_outreach`; send via integration; track replies |
| `notifications` | `services/notifications.py` | Discord webhook, Telegram bot, in-app toast dispatch |
| `portfolio_sync` | `services/portfolio_sync.py` | Public profile API filtering; Netlify rebuild webhook |
| `llm_tracker` | `services/llm_tracker.py` | Wrap every LLM call: log tokens, dollars, latency to `ApiUsage` |

#### H.2 Service patterns

- **Async-first.** All service methods `async def`. DB ops via `AsyncSession`.
- **Pydantic in / out.** No raw dicts at service boundaries.
- **Dependency injection.** Services declared as FastAPI dependencies; sessions via `Depends(get_session)`.
- **Typed exceptions.** `services/exceptions.py` defines `NaavikError` base + per-domain subclasses (`AuthError`, `ScrapingError`, `LLMProviderError`, `ATSError`). Global handler maps to HTTP status.
- **Event emission.** Any state change emits `AppEvent` (per plan 05 § D `AppEventKind`). Single source for Tracking + Outreach timelines.
- **Idempotency.** Background-job-callable services accept an idempotency key; re-running same op = no-op.

#### H.3 Cross-service flows (examples)

**New job arrives via scraper:**
```
scheduler/scrape_jobs_<source>
  → scraper_service.scrape(source)
    → scraper/<source>.list_jobs() → fetch_detail()
    → llm.extract_job(html)
    → scraper_service.dedup()
    → scorer.score(job, profile)
    → AppEvent emitted
    → notifications.notify_new_high_score_job() if score ≥ threshold
```

**Manual review-and-apply (foreground):**
```
ui.routes.discover.review_apply
  → application_service.submit(job, edited_bundle)
    → document_generator.compile(bundle)
    → ats.<board>.submit(bundle)
    → application_service.persist(application)
    → AppEvent (STATUS_CHANGE: APPLIED)
    → notifications.notify_application_submitted()
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

### I · Scheduled jobs (cron)

APScheduler with `PostgresJobStore` (jobs survive restarts). Lifespan-managed: starts on FastAPI startup, stops on shutdown.

#### I.1 Catalog by phase

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
| `applications.auto_apply` | every 10min | `application_service.process_auto_apply_queue()` |

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

#### I.2 Job conventions

- **Idempotent.** Re-running same job = no-op or extension. Service-level dedup via idempotency key.
- **Logged.** Each job's stdout/stderr captured to `~/.naavik/logs/jobs/<job_name>.log`.
- **Failure handling.** APScheduler retry: 3 attempts, exponential backoff (5s, 30s, 5min). After 3 failures, fires `notifications.notify_admin(...)` and pauses.
- **Manually triggerable.** `POST /api/v1/scheduler/jobs/{name}/run` invokes immediately. Pause/resume via `/{pause\|resume}`.
- **Configurable schedule.** Per-source schedules editable via Settings · Sources tab; persisted to `Settings.source_schedules` (JSON).
- **Concurrency.** `max_instances=1` per job-name to prevent concurrent same-source scrapes; cross-source parallelism allowed.

### J · Scraping architecture

Three layers: dispatcher → per-source scraper → service.

#### J.1 `BaseScraper` interface (`scraper/base.py`)

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

#### J.2 Per-source modules

| Module | Strategy | Notes |
|---|---|---|
| `scraper/linkedin.py` | RSShub for listings (`rsshub.luminolab.net/linkedin/...`); LinkedIn guest API for details; Crawl4AI fallback | n8n migration source. Listings only — DM scraping is `integrations/linkedin_browser.py` |
| `scraper/workday.py` | Crawl4AI on `/job/<id>` URL pattern; per-company watchlist via `Settings.workday_companies` | |
| `scraper/greenhouse.py` | Crawl4AI on `https://boards.greenhouse.io/<company>/jobs/<id>`; lists via `https://boards.greenhouse.io/<company>` | |
| `scraper/lever.py` | Crawl4AI on `https://jobs.lever.co/<company>/<job_id>` | |
| `scraper/ashby.py` | Crawl4AI on `https://jobs.ashbyhq.com/<company>/<job_id>` | |
| `scraper/indeed.py` | Crawl4AI; rate-limited heavily (1 req / 30s) | |
| `scraper/generic.py` | Playwright fallback; user-supplied URL → headless render → HTML → AI extraction | "+ Add by URL" path |

#### J.3 Pipeline (`services/scraper_service.py`)

```
scrape(source):
  1. Fetch listings via scraper.list_jobs(query)
  2. For each new URL not in DB:
     a. Fetch detail via scraper.fetch_detail(url)
     b. Extract structured Job via llm.extract_job(html)
     c. Dedup (URL match + fuzzy title/company via edit-distance)
     d. Score via scorer.score(job, profile)
     e. Visa-filter: auto-zero score if profile.visa_sponsorship_needed AND
        job requires US-citizen / no-sponsorship
     f. Persist Job(queue_state=unswiped)
     g. Emit AppEvent
     h. If score ≥ Settings.notify_threshold: notifications.notify_new_high_score(job)
  3. Log run summary to ~/.naavik/logs/jobs/scraping.<source>.log
```

#### J.4 Anti-detection

- **Per-source rate limits** — respect `BaseScraper.rate_limit_seconds`.
- **Random jitter** — sleep `rate_limit_seconds + uniform(0, rate_limit_seconds*0.5)`.
- **User-Agent rotation** — Phase 2.x optional; per-request UA from a small pool.
- **Playwright headless mode** — generic scraper opts out of `navigator.webdriver` fingerprint.
- **Proxy support** — Phase 6+; `Settings.scraper_proxy_url` (optional).

#### J.5 n8n migration

Phase 2 retires the existing n8n workflow (`Lw1uK5APIhIeUeem`):
1. Export n8n DataTable + Google Sheet as CSV (one-time).
2. `services/legacy_import.py` reads CSV → creates `Job` + `Application` rows.
3. RSShub feed (`rsshub.luminolab.net`) stays — it's just an upstream API; LinkedIn scraper continues to consume it.
4. Discord webhook stays — `services/notifications.py` takes over from n8n.
5. n8n Main Workflow disabled after Phase 2 ships and runs clean for 1 week.

### K · Application logic / submission pipeline

Two paths: auto-apply (background) and manual review-and-apply (foreground). Both share the same submission machinery.

#### K.1 Auto-apply (background)

Triggered by user right-swipe on Discover OR by `applications.auto_apply` cron job (if `Settings.auto_apply.enabled`).

```
process_auto_apply_queue:
  For each Job(queue_state=queued_for_auto_apply, score >= Settings.auto_apply.threshold):
    1. Application(status=APPLIED, docs_state=GENERATING) created
    2. document_generator.generate_resume(job, profile) → GeneratedDocument(resume.pdf)
    3. document_generator.generate_cover_letter(job, profile) → GeneratedDocument(cover_letter.pdf+.txt)
    4. document_generator.answer_screeners(job, profile) → ScreenerAnswers
    5. ats.dispatch(job.board).submit(application, bundle)
       - Success: Application.docs_state = READY; AppEvent(STATUS_CHANGE: APPLIED)
       - Failure (CAPTCHA / rate limit / bot detect): docs_state = READY but stays as DRAFT;
         move to manual review queue; user picks up via Discover · review & apply
    6. notifications.notify_application_submitted(application)
    7. Job.queue_state = APPLIED
```

#### K.2 Manual review-and-apply (foreground)

User taps Discover card → `/discover/{job_id}` → Discover · review & apply.

```
load_review_screen(job_id):
  - Fetch Job
  - If Application doesn't exist for (user, job): create draft (status=DRAFT, docs_state=GENERATING)
  - Pre-generate optimistic resume + cover letter (cached)
  - User edits inline; each edit persists via /_fragments/apply/* endpoints

submit_application(job_id, edited_bundle):
  1. application_service.submit(job, edited_bundle)
     - Same as K.1 step 5 (ats.dispatch).submit()
     - On success: Application.status = APPLIED; emit AppEvent
     - On failure: same fallback as K.1
  2. Optionally: copy bundle to clipboard (UI) if board doesn't auto-submit; user pastes manually into ATS
```

#### K.3 Document generation pipeline

`document_generator.generate_resume(job, profile)`:
1. **Bullet selection** (`select_bullets` prompt): `profile.bullets[]` + `job` → list of selected bullet IDs (8-12 typical), respecting `selection_override`. Always-include pinned; never-include skipped.
2. **Bullet trimming** (`trim_bullet` prompt): for each selected bullet, trim to one resume line, preserving numbers + verbs.
3. **Typst compilation** (`typst/compiler.py`): Profile + selected/trimmed bullets + `template="onepage"` → PDF.
4. **Validation** (`typst/validator.py`): verify page count = 1; if overflows, drop lowest-priority bullet and re-compile (max 3 retries).
5. **Persist** as `GeneratedDocument(application_id, kind=resume, path)` at `~/.naavik/data/applications/<id>/resume.pdf`.

`document_generator.generate_cover_letter(job, profile, tone="enthusiastic")`:
1. AI prompt (`draft_cover_letter`): profile + JD + tone → 4-section letter (intro / body / why_company / close).
2. If `output_mode == "pdf"`: Typst compile letter template → PDF.
3. Persist as `GeneratedDocument(kind=cover_letter)`.

`document_generator.answer_screeners(job, profile)`:
1. For each screener question on the application form (extracted from JD or known per-board):
   - If matches a known field on Profile (start date, salary expectation): auto-fill from Profile. Status = `auto`.
   - Else: AI prompt (`answer_screener`): profile + JD + question → drafted answer. Status = `drafted` (user must review before submit).

#### K.4 ATS submission per board (`services/ats/`)

| Board | Method | Module |
|---|---|---|
| Greenhouse | Public Boards API + Embedded API | `services/ats/greenhouse.py` |
| Lever | Public API | `services/ats/lever.py` |
| Ashby | Public API | `services/ats/ashby.py` |
| Workday | Playwright form-fill (no API) | `services/ats/workday.py` |
| LinkedIn (Easy Apply) | Playwright (requires user session cookie) | `services/ats/linkedin_apply.py` |
| Indeed | Playwright | `services/ats/indeed.py` |
| Custom (company-direct) | Playwright generic form-fill | `services/ats/generic.py` |
| Manual fallback | UI-side: "Open ATS" button + clipboard paste | (no module) |

Uniform interface:

```python
class ATSAdapter(ABC):
    @abstractmethod
    async def submit(self, application: Application, bundle: ApplicationBundle) -> SubmissionResult: ...

    @abstractmethod
    def can_submit(self, job: Job) -> bool: ...
```

`SubmissionResult = {ok, external_id, error?, retry_after?}`. Failures classify into `captcha`, `rate_limit`, `auth_required`, `field_mismatch`, `unknown` — drives the manual-review-fallback decision.

### L · External integrations

#### L.1 Email (Gmail + Outlook)

**Gmail OAuth flow:**
1. User clicks "Connect Gmail" on Settings · Notifications or Tracking integrations bar.
2. `GET /api/v1/integrations/gmail/connect` → redirects to Google's OAuth consent with scopes `gmail.readonly` + `gmail.metadata`.
3. Callback at `/api/v1/integrations/gmail/callback`:
   - Exchange code for refresh + access tokens.
   - Encrypt + persist refresh token to `~/.naavik/secrets.enc` (AES-256-GCM, key from `Settings.encryption_key`).
   - Store access token in `Integration` row (refreshed every 6h via cron).
4. `tracking.sync_gmail` cron pulls new messages every 10min.

**IMAP fallback** for non-Gmail/Outlook providers: manual setup on Settings · Notifications (host, port, username, password). Sync mechanism identical.

**Outlook OAuth** identical pattern (Phase 5).

#### L.2 LinkedIn

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

#### L.3 Discord webhook (outbound only)

URL stored encrypted in `Settings.notification_webhooks.discord`. `services/notifications.py` posts on:
- New high-score job (≥ `Settings.notify_threshold`)
- Application submitted
- Interview invitation received (auto-classified)
- Offer received
- Rejection received (configurable; default OFF — too noisy)

Body: rich embed with company logo, role, score, link.

#### L.4 Telegram bot (outbound + inbound)

Bot token in `Settings.notification_webhooks.telegram`. Outbound: same events as Discord. Inbound (Phase 5): `/status`, `/today`, `/silent` commands query the pipeline. Implemented as a tiny long-poll loop in a Telegram-specific scheduled job (every 60s).

#### L.5 Google Calendar (Phase 5)

OAuth identical to Gmail. On `EmailClassification.INTERVIEW_REQUEST`, auto-create event + invite (if user opts in). Integration only writes events; no read.

#### L.6 n8n legacy (Phase 2 transition)

Read-only sync to import historical applications:
- `integrations/n8n_legacy.py` reads from `n8n.luminolab.net` DataTable `hfvivTlQThpPytkl` + Google Sheet `14pgCto2OAQxmb9w6ciOsReb3iQGE1V9XECU-o6E_c7M`.
- One-time CSV export → `services/legacy_import.py` → DB.
- After import succeeds + verified, n8n Main Workflow disabled.

### M · LLM provider abstraction

#### M.1 `LLMProvider` interface (`llm/base.py`)

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

#### M.2 Implementations

| Provider | Module | Default model | Structured output method |
|---|---|---|---|
| Anthropic Claude | `llm/anthropic.py` | `claude-3.5-sonnet-20250219` | Tool use |
| OpenAI GPT | `llm/openai.py` | `gpt-4o` | `response_format=json_schema` |
| Ollama (local) | `llm/ollama.py` | `llama3.1:70b` | JSON mode |

Provider selection: per-user `Settings.llm_provider` + `Settings.llm_model`. Resolved via `llm/__init__.py:get_provider()` factory.

#### M.3 Prompt templates (`llm/prompts/`)

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

#### M.4 Cost tracking

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

`ApiUsage` table aggregated daily by `admin.aggregate_costs` cron → surfaces in Settings · LLM Provider cost cards.

#### M.5 Error handling + fallback

LLM calls go through `llm_tracker.tracked_call(...)` with retry policy:
- Rate limit (429): exponential backoff, max 3 retries.
- Timeout (504): retry once with longer timeout.
- Provider error (500): if `Settings.llm_fallback_provider` set, try fallback once; else raise `LLMProviderError`.
- Schema validation failure: re-prompt with stricter instructions (max 1 re-prompt).

### N · Observability

Phase 1 (MVP minimum):
- **Request logging.** FastAPI middleware logs `{method, path, status, latency_ms, user_id}` per request to `~/.naavik/logs/access.log`.
- **LLM call tracking.** Per § M.4, `ApiUsage` table.
- **Background job status.** Visible in Settings · Deployment log tail (live SSE) and `GET /api/v1/scheduler/jobs`.
- **Error reporting.** Stack traces to `~/.naavik/logs/error.log`. Critical errors → Discord (gated by `Settings.notify_on_errors`).
- **Health check.** `/api/health` returns `{status, db, llm, scheduler, integrations}` with each checked via real ping (DB query, LLM trivial completion, scheduler heartbeat, integrations refresh check).

Phase 6 additions:
- Optional Prometheus metrics endpoint `/metrics`.
- Optional Sentry integration via `SENTRY_DSN` env.
- Performance tracing (OpenTelemetry) for LLM / scraper / ATS submission paths.

### O · Phase mapping

This plan describes the full backend across all phases. Implementation lands in waves per `02-mvp-master-plan.md`:

| Wave | Plan 04 sections in scope | ROADMAP phase |
|---|---|---|
| 3 (initial backend) | A, B-G (HTTP routes), H (services skeleton — auth, profile, settings, application_service partial), N (basic observability) | Phase 1 |
| 6 (real backend) | H complete (all services), M (LLM abstraction), Typst compilation | Phase 1.x |
| Phase 2 | I (job-scraping cron), J (scrapers), partial K (auto-apply pipeline) | Phase 2 |
| Phase 3 | K complete (scoring, document_generator, ats/*) | Phase 3 |
| Phase 4 | I (tracking cron), L.1 (Gmail/Outlook), email_classifier | Phase 4 |
| Phase 5 | I (outreach cron), L.2 (LinkedIn browser), L.3-L.5 (Discord/Telegram/Calendar), outreach_generator | Phase 5 |
| Phase 6 | N expansion (Prometheus, Sentry, OTel) | Phase 6 |

## Decisions (locked in 2026-04-30)

### From original open-question section (HTTP routes, 7 decisions)

Resolved per frontend-community consensus:

1. **Fragment URL prefix** — `/_fragments/...`.
2. **Modal route shape** — per-modal route (`/_modal/bullet-editor/{id}`).
3. **SSE vs polling** — SSE primary; polling fallback on disconnect.
4. **Pagination** — cursor for jobs/applications/messages; offset for contacts.
5. **Public portfolio API** — only `/cv` + `/resume.pdf` for Phase 1.
6. **Bundle download** — synchronous Typst compile.
7. **Cloud-only restart** — UI hides on cloud; endpoint returns 405.

### From § H–N expansion (13 decisions)

1. **APScheduler** for Phase 1–2. In-process, Postgres job store, no broker. Move to Arq (Redis) only if concurrency or persistence semantics outgrow APScheduler.
2. **Services for business logic; FastAPI dependencies for transport.** `get_current_user` is a dependency; `auth_service.login()` is a service.
3. **Document generation: pre-generate inline on page load + cache; background regen on user-initiated regen.** Auto-apply runs in cron (already async).
4. **ATS submission failures: classified retry** per § K.4 `SubmissionResult` error type. Auto-retry on transient errors (`rate_limit`, timeout); punt to manual review on CAPTCHA / auth_required / unknown.
5. **LinkedIn risk handling: (a) aggressive rate limits + user opt-in for Phase 5 Playwright DMs; (b) draft-only fallback always available.** Account-ban risk disclosed in Settings.
6. **`ApiUsage` as top-level model** (not a sub-table on Settings). Queryable for analytics + cost dashboards.
7. **Encryption-key bootstrap from `SECRET_KEY` env.** Rotate via env change + re-encryption migration. Per-user key derived from password hash is rejected (blocks account recovery).
8. **Integration token storage: single `~/.naavik/secrets.enc`** with structured JSON (provider → token blob). One file, one key.
9. **Job concurrency: `max_instances=1` per job-name.** Prevents concurrent same-source scrapes; cross-source parallelism allowed.
10. **Admin scheduler routes: same JWT** for Phase 1 (single-user); add admin role in Phase 2+ multi-user.
11. **Prompt versioning: filename suffix on breaking changes** (`extract_resume_v2.py`). Minor changes use git history.
12. **Cloud-tier scrapers disabled.** Cloud users get `+ Add by URL` only. Privacy + IP-reputation concerns. Surfaced in Settings · Sources with explanation.
13. **Email body retention: metadata + first 500 chars persisted; full body fetched on-demand** from Gmail.

## Approval checklist

### HTTP routes (originally plan 04 v1, locked)

- [x] File layout (§ A) — services / api / ui.routes / scraper / llm / scheduler / integrations / typst clear.
- [x] Page routes (§ B) — 11 page routes + `/_design/components`.
- [x] Fragment routes (§ C) — `/_fragments/...` prefix.
- [x] JSON API routes (§ D) — auth, profile/extraction/bullets, jobs/discover, applications, tracking integrations + email, contacts/outreach, settings, scheduler admin, public.
- [x] SSE streams (§ E) — 4 streams.
- [x] Per-screen interaction map (§ F) — accurate against SCREENS.md.
- [x] HTTP conventions (§ G) — 11 decisions locked.

### Backend architecture expansion (locked 2026-04-30)

- [x] Service layer (§ H) — 14 services + 7 ATS adapters; responsibilities split right.
- [x] Scheduled jobs (§ I) — full catalog across phases 2-6; APScheduler choice; idempotency + failure handling.
- [x] Scraping architecture (§ J) — `BaseScraper` interface; 7 per-source scrapers; pipeline; anti-detection; n8n migration story.
- [x] Application logic (§ K) — auto-apply + manual paths; document generation pipeline; ATS adapter pattern; per-board strategies.
- [x] External integrations (§ L) — Gmail/Outlook OAuth; LinkedIn Playwright; Discord/Telegram/Calendar; n8n legacy import.
- [x] LLM provider abstraction (§ M) — `LLMProvider` interface; 3 implementations; prompt template structure; cost tracking; error handling.
- [x] Observability (§ N) — Phase 1 minimum (request logging, LLM tracking, scheduler status, error reporting, health check); Phase 6 expansion.
- [x] Phase mapping (§ O) — wave dependencies match plan 02 § C.
- [x] All 13 open questions decided — see § Decisions above.
- [ ] **Next step (graduation):** plan content graduates to `docs/design/BACKEND.md`. Plan archived. Plan 10 (backend impl) consumes this directly across multiple sub-waves (initial, scrapers, scoring, tracking, outreach, observability). Triggered after plans 05, 06, 07 are also approved.
