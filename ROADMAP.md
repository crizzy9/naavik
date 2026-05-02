# Naavik Development Roadmap

> Last updated: 2026-05-02 (Wave 4 / Backend Wave 3 / plan 10 § B EXECUTED — backend substrate live: 20 SQLModel entities + Alembic + bcrypt+JWT+CSRF auth + AES-256-GCM vault + LLM provider abstraction + 10 prompt skeletons + cost-tracking via ApiUsage + profile/settings/ats_credentials services + per-field profile autosave + DB-backed Settings + `NAAVIK_PERSISTENCE=db` env var for accessor swap + sequence-bumping seed + rotate-key CLI; 348 memory-mode tests + 6 live-DB seed tests pass; ruff clean; security-review checkpoints 1+2+4 written. Plan 10 § B status → WAVE 3 EXECUTED · Wave 6 awaiting.)
>
> Earlier line: single-tracking consolidation — all task / backlog / plan-mapping moved here per `AGENTS.md` § Single-doc-tracking principle. Plans 11–15 mapped to Phase 2–6 headers. Pre-Phase-2 paper cuts inlined. Phase 1.x deferred items table is now the canonical extended backlog. Wave 3 / plan 09 EXECUTED + plan 09a EXECUTED + 09a follow-up shipped — 269 tests passing.
>
> **Companion doc:** `docs/plans/POST_PHASE_1.md` — operational guide only (testing playbook, authoring workflow, monitoring, success criteria). All task tracking lives here in ROADMAP.
>
> **This is the single source of truth for project progress.** Phases describe the long arc; per-phase wave/task tables are checked off as work lands. The master plan (formerly `docs/plans/02-mvp-master-plan.md`) is archived — its content lives here, in `AGENTS.md` § Workflow, and in the active session-continue prompt at `docs/prompts/00-session-continue.md`.

## Maintenance

**This roadmap is the single source of truth for project progress.** Always keep it updated:

- When a task is **started**: change its status from `[ ]` to `[~]` (in progress)
- When a task is **completed**: change its status to `[x]` and add a brief note about the deliverable
- When a phase is **completed**: update the phase status header and bump the "Last updated" date
- When **scope changes**: edit the relevant phase table directly — do not bury changes in commits
- When **new tasks emerge** mid-phase: insert them in the phase table with appropriate priority
- When **architecture decisions change**: update the relevant section (Tech Stack, Key Design Decisions, Architecture diagram)

The "Last updated" date at the top should reflect the most recent meaningful edit.

## Vision

An open-source career automation platform that navigates the job market end-to-end: profile intake, job discovery, intelligent matching, resume/cover letter tailoring, application tracking, and interview pipeline management.

**Self-hosted first, cloud available.**

The default path is self-hosted — any developer can deploy Naavik for free via Docker Compose or NixOS. Your data stays on your infrastructure. A managed cloud tier ($15/month, bring-your-own AI credits or local model) exists for those who prefer not to self-host, but it is functionally identical — never treated as "premium."

This positioning shapes the product: dark-mode developer aesthetic, no SaaS bloat, no upsell pressure, data-dense tool feel.

---

## Competitive Context

No commercial platform is self-hostable. Naavik fills a real gap — and even open-source alternatives don't offer the full stack.

| What exists | Gap Naavik fills |
|---|---|
| **Sprout** ($20-100/mo) — Closest to our vision. Swipe-to-apply, per-job resume tailoring, mobile-first | Not self-hosted, not open source, no visa filtering, no portfolio integration, no LLM choice, no outreach |
| **Teal** ($29/mo) — Best job tracker and resume analyzer, no auto-apply | No auto-apply, no generation, proprietary, no outreach |
| **Jobsolv** ($79-149/mo) — Per-job tailoring + auto-apply via credits | Expensive, niche ($100K+ remote only), proprietary, no outreach |
| **LoopCV** (EUR 10-30/mo) — Set-and-forget automation | No resume tailoring, generic form-filling, no outreach |
| **Sonara** ($6-24/mo) — Background auto-apply | No resume tailoring, submits generic resume, no outreach |
| **AIHawk** (open source, 29.7K stars) — LinkedIn auto-apply bot | Archived, LinkedIn-only, no profile system, no email monitoring, no outreach tracking |
| **JobSync** (open source, 528 stars) — Self-hosted job tracker | No scraping, no auto-apply, no resume generation, no outreach |
| **JobNavigator** (open source, new) — Multi-source scraping + scoring | No cover letter gen, no auto-apply, no email monitoring, no outreach |

### Why Naavik wins

| Dimension | Naavik | Commercial tools | Other OSS |
|---|---|---|---|
| **Cost** | Free (self-hosted) or $15/mo (cloud) | $20-150/mo | Free |
| **Self-hosted** | Default path | No | Some |
| **Open source** | AGPL-3.0 | No | Mixed |
| **LLM choice** | Claude, GPT, Ollama (local) | Proprietary or locked | Usually one |
| **Data ownership** | Yours | Theirs | Yours |
| **Full pipeline** | Profile → scrape → score → generate → apply → track → outreach | Fragmented | Usually partial |
| **Visa filtering** | Yes | Rare | No |
| **Portfolio integration** | Yes | No | No |

---

## Architecture

```
┌──────────────────┐
│  Reverse Proxy   │
│  (Caddy/Nginx)   │
└────────┬─────────┘
         │
┌────────▼────────┐     ┌─────────────────┐
│    FastAPI       │     │   Authelia       │
│  + Jinja2/HTMX  │     │  (optional SSO)  │
│  + APScheduler  │     └─────────────────┘
└────────┬────────┘
         │
   ┌─────┼─────┬──────────┐
   │     │     │          │
┌──▼──┐┌─▼───┐┌▼─────┐┌──▼────┐
│Pg+  ││Crawl││Typst ││ LLM   │
│pgvec││4AI+ ││      ││Claude/│
│tor  ││Playw││      ││GPT/   │
│     ││right││      ││Ollama │
└─────┘└─────┘└──────┘└───────┘
```

### Tech Stack

| Layer | Choice | Alternatives considered |
|---|---|---|
| **Dev Environment** | Nix flake + devShell | venv (not reproducible), Docker-only (slow iteration) |
| **Backend** | FastAPI + SQLModel | Django (too heavy), Flask (no async), Litestar (small ecosystem) |
| **Frontend** | HTMX + Jinja2 + Tailwind + DaisyUI | React (too complex), Svelte (two codebases), Streamlit (not production) |
| **Database** | PostgreSQL + pgvector | SQLite (no concurrency), Supabase (15+ containers overkill) |
| **Scraping** | Crawl4AI + Playwright | Firecrawl (self-hosted lacks Fire-engine anti-bot), Scrapy (no JS rendering) |
| **AI/LLM** | Direct SDK (Anthropic/OpenAI/Ollama) | LangChain (over-abstracted for our single-prompt use cases) |
| **PDF** | Typst (primary), LaTeX (future compat) | LaTeX alone (slow, 4GB TexLive, macro arcana) |
| **Scheduling** | APScheduler (pg job store) | Celery (needs broker), Dramatiq (needs Redis) |
| **Auth** | JWT + Google OAuth | Authentik (too heavy), Keycloak (enterprise) |
| **Deployment** | Docker Compose + NixOS service module | Docker-only (misses NixOS homelab users) |
| **Packaging** | Nix flake output (package + module + devShell) | pip/wheel only (not reproducible) |

### Key Design Decisions

1. **Profile in DB, not YAML** — Users manage profiles via UI (resume upload + manual editing). API serves data. No config files to maintain.

2. **Single long-form bullets** — Every experience bullet is a single canonical text (the long, full version, no length cap). At apply time, AI trims each selected bullet to a single resume line while preserving numbers and verbs. Selection per job is driven by tag relevance + JD signals; users can pin via per-bullet `selection_override` (`always_include` / `never_include` / `null` = AI auto-decides). The prior `oneline` / `detailed` split, `default_include` toggle, and metric fields (revenue / percentage / team_size) were removed in 2026-04 — see `docs/design/SCREENS.md` § Section 6.

3. **Typst over LaTeX** — 10-100x faster PDF compilation, clean programmatic data ingestion, single binary. LaTeX compatibility is a future roadmap item.

4. **Direct LLM SDKs, no LangChain** — Our LLM use cases are single-prompt structured output tasks. Both Anthropic and OpenAI SDKs support Pydantic-based structured output natively. No abstraction layer needed.

5. **Auto-apply as user setting** — Default off. When enabled, high-scoring jobs get documents generated and applications submitted automatically. Users can toggle this per their comfort level.

6. **Cloud + Local LLM support** — Every AI feature offers both cloud (Claude/GPT) and local (Ollama) options. User chooses in settings. Prompts are provider-agnostic.

---

## Data Model

### Profile (Single Source of Truth)

```
Profile
├── meta (name, email, phone, location, portfolio, github, linkedin)
├── application_questions (US-only Phase 1):
│     work_authorization, visa_sponsorship_needed, willing_to_relocate,
│     notice_period, salary_expectation, earliest_start,
│     veteran_status, disability_status, race_ethnicity (EEOC), gender (EEOC)
├── summary (full + short versions)
├── education[]
│   └── institution, school, location, degree, dates, gpa, courses[]
├── experience[]
│   ├── company, team, title, location, dates
│   └── bullets[]
│       ├── id (stable identifier)
│       ├── text (single long-form, no length cap — AI trims at apply time)
│       ├── tags[] (9-tag vocab: ai-ml, backend, frontend, devops, data-eng,
│       │           genai, leadership, platform, product)
│       └── selection_override (always_include / never_include / null = AI auto-decides per JD)
├── skills[] → (category, items[])
├── projects[] → (title, date, text, tags[], portfolio_slug)
├── certifications[] → (title, issuer, date, description)
├── open_source[] → (title, date, description)
└── cover_letter_base → (template paragraphs with placeholders)
```

**Authoritative reference:** `docs/design/DATA_MODEL.md` (graduated from `docs/plans/05-data-model.md`). The diagram above is a sketch; all enum tables, indexes, validation rules, and relationships live in DATA_MODEL.md once that doc lands.

### Job + Application (multi-axis state, see plan 05)

```
Job (pre-application: a discovered or manually-added opportunity)
├── id, source (AUTOMATED/MANUAL), url, url_type
├── company, position, team, location
├── dates (posted, found)
├── description, criteria, skills_required
├── visa_restrictions, salary_range
├── compatibility_score (0-1), score_explanation
└── queue_state (unswiped / saved / skipped / queued_for_auto_apply / applied)
   ↑ flips to `applied` when an Application row is created from this Job

Application (one row per submitted job; carries multi-axis post-submission state)
├── id, job_id, applied_at, board (greenhouse / workday / lever / ashby / manual)
├── status (APPLIED · RECRUITER_SCREEN · ONSITE_LOOP · OFFER · CLOSED)
├── closed_reason (rejected_by_them / withdrawn_by_me / ghosted / accepted_other; required when status=CLOSED)
├── docs_state (none / generating / ready / stale / failed) — drives doc-readiness UI
├── referral_state (none / requested / in_flight / provided / declined) — drives warm-intro pill
├── recruiter_state (none / engaged / responded / silent / stalled) — drives "silent N days" urgency
├── outreach_engagement (computed view: cold / active / awaiting_reply / referred / converted)
├── status_history[] (timeline events; see AppEvent)
├── generated_documents[] → GeneratedDocument (resume PDF + cover letter PDF/text)
└── notes
```

**Lifecycle is multi-axis, not a flat enum.** The five `Application.status` values are the post-submission pipeline. Document generation, referral status, recruiter engagement, and outreach engagement are tracked as **orthogonal sub-states**, not as additional pipeline stages. A single application can be `RECRUITER_SCREEN` + `referral_state=provided` + `docs_state=ready` simultaneously. See `docs/design/DATA_MODEL.md` (graduated from plan 05) for the full multi-axis state model, transitions per axis, and timeline event taxonomy. The flat `FOUND → SCORED → APPROVED → DOCS_GENERATED → INTERVIEWING → REJECTED → WITHDRAWN` enumeration was removed in 2026-04 — those concerns now live on dedicated axes.

### Outreach & Contacts

```
Contact
├── id, type (RECRUITER/EMPLOYEE/HR/HIRING_MANAGER)
├── name, title, company, linkedin_url, linkedin_id
├── email, notes
├── relationship (warm/cold), source (scraped/manual/outreach)
└── outreach_history[]

OutreachMessage
├── id, contact_id, job_id
├── template_type (INTRO, REFERRAL_REQUEST, FOLLOW_UP, THANK_YOU, CHECK_IN)
├── subject, body
├── linkedin_message_id (if sent via LinkedIn)
├── sent_at, responded_at
├── response_summary, status (PENDING/SENT/OPENED/RESPONDED/ACCEPTED/DECLINED)
└── ai_generated, human_edited

EmailThread
├── id, job_id, contact_id
├── subject, messages[]
│   ├── sender, recipient, body, timestamp
│   ├── direction (INBOUND/OUTBOUND)
│   └── classification (INTERVIEW_REQUEST, REJECTION, OFFER, ASSESSMENT, FOLLOW_UP, OTHER)
├── latest_message_at
└── auto_classified, manually_verified
```

---

## Repository Structure

```
naavik/
├── src/
│   ├── main.py                    # FastAPI entrypoint
│   ├── config.py                  # pydantic-settings
│   ├── api/                       # REST routes
│   │   ├── profile.py             # CRUD + resume upload + AI extraction
│   │   ├── jobs.py                # Job listing, scoring, tracking
│   │   ├── generator.py           # Resume/cover letter generation
│   │   ├── portfolio.py           # Public API for portfolio site
│   │   └── auth.py                # Login, OAuth, JWT
│   ├── ui/                        # HTMX views
│   │   ├── templates/             # Jinja2 (base, dashboard, profile, jobs, generator, settings)
│   │   ├── partials/              # HTMX fragments (job_row, bullet_editor, score_card)
│   │   └── static/                # htmx.min.js, styles
│   ├── models/                    # SQLModel models
│   │   ├── profile.py             # Profile, Experience, Bullet, Skill
│   │   ├── job.py                 # Job, StatusHistory
│   │   ├── user.py                # User, Settings
│   │   └── schemas.py             # API request/response schemas
│   ├── services/                  # Business logic
│   │   ├── profile_intake.py      # Resume upload → AI extraction → DB
│   │   ├── job_scraper.py         # Crawl4AI + Playwright scraping
│   │   ├── job_scorer.py          # AI scoring + tag matching
│   │   ├── resume_generator.py    # Profile + job → bullet selection → Typst → PDF
│   │   ├── cover_letter_gen.py    # Job desc → personalized letter → PDF
│   │   ├── portfolio_sync.py      # Serve profile via API for portfolio site
│   │   ├── notifications.py       # Discord, Telegram
│   │   ├── email_monitor.py       # Gmail/IMAP email monitoring
│   │   ├── email_classifier.py    # AI email classification
│   │   ├── contact_tracker.py     # Recruiter/employee contact management
│   │   └── outreach_generator.py # AI outreach message generation + LinkedIn
│   ├── llm/                       # LLM abstraction
│   │   ├── base.py                # Abstract interface
│   │   ├── anthropic.py           # Claude SDK
│   │   ├── openai.py              # OpenAI SDK
│   │   ├── ollama.py              # Local models
│   │   └── prompts/               # Prompt templates (Python modules)
│   ├── scraper/                   # Per-site scrapers
│   │   ├── base.py
│   │   ├── linkedin.py
│   │   ├── workday.py
│   │   ├── greenhouse.py
│   │   ├── lever.py
│   │   ├── ashby.py
│   │   └── generic.py
│   ├── typst/
│   │   ├── templates/             # onepage.typ, fullprofile.typ, cover_letter.typ
│   │   ├── compiler.py            # Typst CLI wrapper
│   │   └── validator.py           # Oneline length validation
│   ├── scheduler/
│   │   └── jobs.py                # APScheduler definitions
│   └── db/
│       ├── session.py             # Async session management
│       └── seed.py                # Initial data seeding
├── migrations/                    # Alembic
├── tests/
├── legacy/                        # n8n workflow exports (reference)
├── docs/
├── generated/                     # gitignored — output PDFs
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── flake.nix                  # Nix flake: devShell + package + NixOS module
├── flake.lock
├── nix/
│   ├── package.nix            # Nix derivation for naavik
│   ├── module.nix             # NixOS service module (Lumino-compatible)
│   └── devshell.nix           # Dev shell with all deps (python, uv, typst, postgresql, ruff)
└── .env.example
```

---

## Phases

### Phase 0: Foundation & Infrastructure
> **Goal:** Reproducible dev environment, project skeleton, database, and deployment infrastructure.
> **Status:** ✅ Complete (2026-04-25)

| # | Task | Status | Priority | Notes |
|---|---|---|---|---|
| 0.1 | Nix flake: devShell with Python 3.12, uv, typst, postgresql, ruff, pre-commit hooks | [x] | CRITICAL | `nix/devshell.nix` — verified all tools available in `nix develop` |
| 0.2 | pyproject.toml + uv lockfile with all Python deps | [x] | CRITICAL | 56 packages installed via `uv sync` |
| 0.3 | Dockerfile (multi-stage, uv-based, Python 3.12 slim) | [x] | HIGH | Builder + runtime stages, typst in runtime |
| 0.4 | Docker Compose: FastAPI app + PostgreSQL (pgvector/pgvector:pg17) | [x] | HIGH | Health check on db, app depends on healthy db |
| 0.5 | NixOS service module (`nix/module.nix`) — Lumino-compatible | [x] | HIGH | Reads `settings.servicesConfig.apps.tools.naavik`, full systemd hardening, SOPS, Traefik, PostgreSQL ensure |
| 0.6 | Nix package derivation (`nix/package.nix`) | [x] | HIGH | `nix build` produces `result/bin/naavik`, typst wrapped in PATH |
| 0.7 | FastAPI app skeleton: main.py, config.py, db/session.py, static files, Jinja2 templates | [x] | CRITICAL | Sidebar drawer layout (Tailwind + DaisyUI + HTMX), dashboard placeholder, 5 nav stubs |
| 0.8 | Alembic setup (async, reads DATABASE_URL from settings) | [x] | CRITICAL | `migrations/env.py` uses async_engine_from_config |
| 0.9 | .env.example with all env vars documented | [x] | MEDIUM | DATABASE_URL, SECRET_KEY, all LLM keys, OAuth, integrations |

**Deliverable:** ✅ `nix develop` drops into a full dev environment. ✅ `nix build` produces a package. ✅ Docker Compose ready. ✅ NixOS module ready for Lumino integration. ✅ Dashboard placeholder visible at localhost:8000 with sidebar layout.

**Verification log (2026-04-25):**
- `nix develop` → python 3.12.13, uv 0.11.7, typst 0.14.2, ruff 0.15.11, postgresql 17.9, pre-commit 4.5.1
- `uv sync` → 56 packages installed
- `nix build` → produces `result/bin/naavik` entrypoint
- `uv run fastapi dev src/main.py` → server starts on :8000
- `GET /api/health` → `{"status":"ok"}`
- `GET /` → HTTP 200, dashboard renders with sidebar
- `uv run ruff check src/` → all checks passed

---

### Phase 1: MVP — UI + backend core
> **Goal:** Ship the 11-screen MVP per `docs/design/SCREENS.md` — profile system, resume/cover letter generation, application tracking, outreach.
> **Status:** 🟡 In progress (Wave 0 + Wave 1 complete; Waves 2–6 in flight)
> **Started:** 2026-04-30
>
> **Prerequisite ✅ done:** all 11 MVP screen mockups committed (Wave 0 + the Claude Design batch). Bundle JSX at `docs/design/mockups/naavik-handoff/project/screens/` (gitignored, locally only).
>
> **Implementation contracts** (graduated 2026-04-30 from plans 03–07):
> - `docs/design/COMPONENTS.md` — 85-component library
> - `docs/design/BACKEND.md` — routes + services + cron + scrapers + LLM + observability
> - `docs/design/DATA_MODEL.md` — 18 SQLModel entities + Settings + DRAFT cascade
> - `docs/design/INTERACTIONS.md` — cross-cutting HTMX patterns
> - `docs/design/SAMPLE_DATA.md` — Phase 1 hardcoded fixtures
>
> **Workflow:** every wave below is driven by a plan + kickoff prompt at `docs/plans/NN-name.md` + `docs/prompts/NN-name.md`. Implementation happens in fresh sessions kicked off by paste of the prompts. See `AGENTS.md` § Workflow for the canonical lifecycle.

#### Implementation waves

Phase 1 ships in **5 sequential waves** (Scenario A). Each wave passes acceptance criteria before the next starts; they do **not** run in parallel. Plan 08 lays the component library, plan 09 composes pages on top with sample-data accessors + stub endpoints, plan 10 Wave 3 lands the data substrate (DB + auth + LLM) and swaps the stubs for real handlers without UI churn, plan 10 Wave 6 completes services + Typst + DRAFT lifecycle + 3 ATS adapters. Interactions per INTERACTIONS.md fold into Wave 3 (no separate Wave 5).

| Wave | Scope | Plan | Prompt | Status | Done |
|---|---|---|---|---|---|
| 0 | Doc realignment | `docs/plans/archive/01-docs-realignment.md` | (executed inline) | ✅ EXECUTED | 2026-04-30 |
| 1 | Author 5 design docs (COMPONENTS / BACKEND / DATA_MODEL / INTERACTIONS / SAMPLE_DATA) | plans 03–07 (all GRADUATED + archived) | (no separate prompts — design plans graduate inline) | ✅ COMPLETE | 2026-04-30 |
| 2 | Stage 2 component library impl (85 partials + base.html refinements + macros + base.js + fixture page) | `docs/plans/archive/08-stage-2-impl.md` | `docs/prompts/archive/08-stage-2-impl.md` | ✅ EXECUTED | 2026-05-01 |
| 3 | Stage 3 page templates impl (11 screens, sample_data accessors, stub fragment + JSON endpoints, Discover keyboard map, Playwright snapshots) — folds in interactions per INTERACTIONS.md § J | `docs/plans/archive/09-stage-3-impl.md` | `docs/prompts/archive/09-stage-3-impl.md` | ✅ EXECUTED | 2026-05-02 |
| 3a | Stage 3 bugfix + Discover-redesign triage (Lucide diagnostics, sidebar mobile drawer, typed application questions, scroll-spy, native dialog backdrop, mobile pages, touch swipe, button rename, sidebar relabel "Jobs"→"Discover", in-place card expansion) | `docs/plans/archive/09a-stage-3-bugfix.md` | (executed inline; no kickoff prompt — direct user approval) | ✅ EXECUTED | 2026-05-02 |
| 4 | Backend Wave 3 — models + auth + LLM abstraction + vault + initial services + db/seed; **swaps plan 09 stub endpoints + sample-data accessor bodies for DB-backed handlers** (UI unchanged) | `docs/plans/10-backend-impl.md` § B | `docs/prompts/10-backend-impl.md` (Wave 3 part) | ✅ EXECUTED | 2026-05-02 |
| 5 | Backend Wave 6 — all 14 services + Typst document generator + DRAFT lifecycle + Greenhouse / Lever / Ashby ATS adapters + portfolio_sync + auto-apply cron + notifications | `docs/plans/10-backend-impl.md` § C | `docs/prompts/10-backend-impl.md` (Wave 6 part) | ⏳ pending | — |

After Wave 5 ships, **Phase 2–6 work** (scrapers, scoring, email + auto-classification, LinkedIn DMs + outreach, observability + light mode + LaTeX) graduates to plans 11+ as outlined in plan 10 § D.

#### Wave 1 completion log (2026-04-30)

| Plan | → Design doc | Lines | Notable |
|---|---|---|---|
| 03 — Component catalog | `docs/design/COMPONENTS.md` | 2111 | 85 components, 12 groups; full specs incl. Tier-1 additions (`bullet_textarea`, `confirm_modal`, `spinner`, `toast`, `empty_state`, `avatar`, `connection_status_card`, `deployment_badge`, 5 skeletons) |
| 04 — Backend architecture | `docs/design/BACKEND.md` | ~870 | HTTP routes + 14 services + 7 ATS adapters + cron + scrapers + LLM abstraction + vault boundary + observability |
| 05 — Data model | `docs/design/DATA_MODEL.md` | ~1100 | 18 entities + Settings; DRAFT cascade through enum / state machines / KPIs; AppEvent payload schemas |
| 06 — Interactions spec | `docs/design/INTERACTIONS.md` | ~620 | HTMX patterns: 6 form patterns, SSE, drag-drop, modals (E.4 confirm modal), keyboard shortcuts, optimistic UI rollback |
| 07 — Sample data | `docs/design/SAMPLE_DATA.md` | ~600 | Phase 1 fixtures (1 Profile, 4 Experiences, 14 Bullets, ~20 Jobs, 14 Applications incl. 2 DRAFT, ~20 Contacts, ~40 OutreachMessages, ~20 EmailThreads, ~150 AppEvents, ~30 GeneratedDocuments, ~20 ApplicationScreenerAnswers, 1 Settings) |

DESIGN.md bumped to v1.3 (DRAFT row added to Status Pipeline). SCREENS.md DRAFT visibility rule added.

#### Wave 2 — Stage 2 component library (plan 08) — ✅ EXECUTED 2026-05-01

> Build batches per `docs/design/COMPONENTS.md` § G. Acceptance: 85 component partials exist; every component renders in `/_design/components`; `uv run ruff check` passes; Lucide icons render after fragment swaps. **All 100 tests pass.**

| # | Build batch | Components | Status |
|---|---|---|---|
| 2.1 | Shell + base.html refinements | `auth_shell`, `sidebar`, `version_pill`, `api_status_dot`, `deployment_badge`; `base.html` layout + `base.js` (Lucide reinit, Sortable.js auto-init, modal-close listener, toast auto-dismiss, optimistic rollback, upload progress) | [x] |
| 2.2 | Atomics (15) | `button`, `input`, `card`, `tag_chip`, `status_dot`, `status_badge`, `score_circle`, `ai_badge`, `kbd`, `field_label`, `info_card`, `spinner`, `toast`, `empty_state`, `avatar` | [x] |
| 2.3 | Forms (5) | `editor_field`, `editor_card`, `autosave_indicator`, `modal`, `confirm_modal` | [x] |
| 2.4 | Onboarding (5) | `step_indicator`, `dropzone`, `extraction_checklist`, `extracted_field_row`, `progress_bar` | [x] |
| 2.5 | Profile / Bullet (11) | `profile_hero`, `contact_chip`, `experience_card`, `bullet_row`, `section_anchor_nav`, `application_readiness_card`, `application_qs_form`, `bullet_edit_row`, `tag_picker`, `selection_override`, `bullet_textarea` | [x] |
| 2.6 | Overview (4) | `kpi_card`, `priority_action_row`, `email_signal_row`, `pipeline_strip` | [x] |
| 2.7 | Discover (8) | `swipe_card`, `match_breakdown`, `discover_action_bar`, `swipe_action_btn`, `discover_stats_strip`, `up_next_card`, `tip_card`, `keyboard_hints` | [x] |
| 2.8 | Discover · review & apply (6) | `apply_topbar`, `warm_intro_card`, `tailored_bullet_row`, `cover_letter_section`, `screener_question_card`, `apply_action_bar` | [x] |
| 2.9 | Tracking (8) | `view_toggle`, `provider_chip`, `integration_card`, `followup_banner`, `stage_column`, `tracking_card`, `tracking_list_row`, `tracking_board` | [x] |
| 2.10 | Outreach (6) | `outreach_app_row`, `recommended_move_card`, `outreach_message_card`, `contact_card`, `linkedin_status_chip`, `outreach_timeline` | [x] |
| 2.11 | Settings (7) | `settings_tabs`, `provider_card`, `cost_card`, `deployment_status_card`, `log_tail`, `on_disk_card`, `connection_status_card` | [x] |
| 2.12 | Skeletons (5) | `swipe_card_skeleton`, `tracking_card_skeleton`, `priority_action_row_skeleton`, `email_signal_row_skeleton`, `bullet_edit_row_skeleton` | [x] |
| 2.13 | `/_design/components` fixture page (gated on `NAAVIK_DEBUG=1` env var; plan 10 Wave 3 swap to `Settings.debug`) | — | [x] |

#### Wave 3 — Stage 3 page templates (plan 09)

> Page handlers in `src/ui/routes/` returning `HTMLResponse`; pages compose only plan-08 partials; data backed by `src/db/sample_data.py` (per SAMPLE_DATA.md); accessors are **async from day one** so Wave 4's swap is body-only. Stub fragment + JSON endpoints match BACKEND.md § C / § D shape exactly. Per-screen interaction patterns from INTERACTIONS.md § J fire end-to-end. Acceptance: every screen renders without error; matches mockup at desktop (1440×900) + mobile (375×812) via Playwright; SCREENS.md per-screen `Impl:` checkbox flips to `[x]`.

Build order: simplest first.

| # | Screen / artifact | Mockup ref | Page handler | Status |
|---|---|---|---|---|
| 3.0 | `src/db/sample_data.py` + `sample_data_models.py` (frozen Pydantic per SAMPLE_DATA.md) | — | — | [x] 19 entities + Settings + 30 ApiUsage; 44 round-trip + realism tests |
| 3.1 | Login | `screens/Login.jsx` | `src/ui/routes/auth.py:get_login` | [x] auth_shell + form, fake-session-cookie POST /api/v1/auth/login |
| 3.2 | Settings (all 6 tabs — full UI scaffolding; Wave 4 wires real persistence) | `screens/Settings.jsx` | `src/ui/routes/settings.py:get_settings` | [x] all 6 tabs (LLM/Deployment/Account/Notif/Auto-Apply/Sources); SSE log tail; cost cards from ApiUsage |
| 3.3 | Profile (read-only) | `screens/Profile.jsx` | `src/ui/routes/profile.py:get_profile` | [x] hero + experience + summary + skills + projects + edu + cert + sticky right-rail anchor + readiness card |
| 3.4 | Profile editor | `screens/ProfileEdit.jsx` | `src/ui/routes/profile.py:get_edit` | [x] per-field autosave (PUT /profile/{field}); Sortable bullet drag-drop; confirm-modal hooks |
| 3.5 | Bullet editor (modal) | `screens/BulletModal.jsx` | `src/ui/routes/fragments.py:bullet_editor_modal` | [x] tag picker + selection_override + Rewrite/Delete; HX-Trigger: closeModal on save |
| 3.6 | Onboarding (3-step; SSE done auto-progresses to step 3 via `HX-Trigger`) | `screens/Onboarding.jsx` | `src/ui/routes/auth.py:get_onboarding` | [x] step indicator + dropzone + SSE extraction (5 progress + 6 field + done + stepReady) |
| 3.7 | Overview | `screens/Overview.jsx` | `src/ui/routes/overview.py:get_overview` | [x] greeting + KPI×4 + priority actions + email signal + pipeline strip + SSE email-signal stream |
| 3.8 | Tracking (board + list) | `src/ui/routes/tracking.py:get_tracking` | [x] board+list views; integrations row; needs-followup banner; Sortable Kanban; DRAFT+CLOSED hidden |
| 3.9 | Outreach | `screens/Outreach.jsx` | `src/ui/routes/outreach.py:get_outreach` | [x] 2-pane apps + detail; recommended_move_card; contacts; outreach_timeline |
| 3.10 | Discover (incl. `Stuck in queue · {N}` right-rail card via `up_next_card` `state="stuck"`) | `screens/Discover.jsx` | `src/ui/routes/discover.py:get_discover` | [x] swipe queue + 4-button bar + keyboard hints; Up next + Stuck-in-queue + Saved + Tip; +Add by URL modal; keys.js wired |
| 3.11 | Discover · review & apply | `screens/DiscoverDetail.jsx` | `src/ui/routes/discover.py:get_review` | [x] 3-column workspace; eager DRAFT auto-create gated on Settings.eager_review_generation; lazy CTA path; failure banner; SSE cover letter; submit/discard with screener gate |
| 3.12 | Per-screen interactions per INTERACTIONS.md § J (autosave, drag-drop, modal, SSE, optimistic rollback, keyboard shortcuts) | INTERACTIONS.md § B–H | — | [x] all patterns landed inline with each screen |
| 3.13 | Per-screen Playwright snapshot baseline at desktop + mobile | — | `tests/visual/capture.py` | [~] capture script ships; PNG generation pending nix-devshell run (NixOS Chromium needs playwright-driver browsers) |

#### Wave 4 — Backend Wave 3 (plan 10 § B) — ✅ EXECUTED 2026-05-02

> Initial backend lands the data substrate; **swaps plan 09's stub endpoints + sample-data accessor bodies for DB-backed handlers** (UI unchanged). Acceptance: `uv run alembic upgrade head` succeeds, `db/seed.py` populates from sample data, `tests/test_sample_data.py` round-trip via SQLModel passes, auth path passes `security-review`, vault boundary verified. **All 348 memory-mode tests + live-DB seed/persistence-swap tests pass.**

| # | Task | Source contract | Status |
|---|---|---|---|
| 4.1 | SQLModel models for all 19 entities + Settings (incl. `ApiUsage`) | DATA_MODEL.md § C | [x] 20 tables + Pydantic shadows; relationships stripped (services use FK joins); 25 model tests |
| 4.2 | Alembic initial migration (every table + enum + index + CHECK; pgvector extension enabled) | DATA_MODEL.md § H | [x] `0001_initial.py` drives DDL from `SQLModel.metadata`; `alembic upgrade head` clean against dev DB |
| 4.3 | Auth — JWT cookie + bcrypt; `/api/v1/auth/login`, `/logout`, `/me`, `/csrf`; brute-force rate limit | BACKEND.md § D.1 | [x] cost=12 prod / cost=4 tests; HS256 JWT; cookie HttpOnly+Secure+SameSite=Strict; CSRF double-submit; 5/15min rate limit; 18 auth tests |
| 4.4 | LLM provider abstraction — `llm/base.py` + anthropic + openai + ollama; structured-output retry policy | BACKEND.md § M.1, M.2 | [x] Anthropic tool-use / OpenAI json_schema / Ollama JSON mode; 10 prompt skeletons (score_job real); 15 tests |
| 4.5 | LLM cost tracking — `llm_tracker` service + `ApiUsage` table (powers Settings cost cards from day one) | BACKEND.md § M.4 + DATA_MODEL.md § C `ApiUsage` | [x] `tracked_call` wraps every provider call; persists ApiUsage row on success+failure; retries per BACKEND § M.5 |
| 4.6 | Vault service — `services/vault.py` (`~/.naavik/secrets.enc`, AES-256-GCM, PBKDF2 from `SECRET_KEY`) + audit log | BACKEND.md § H.1, § L.1 | [x] AES-256-GCM + PBKDF2 100k + key_fingerprint header for mismatch detection; sibling lockfile for concurrent writes; audit log never carries values; 22 tests |
| 4.7 | Vault key rotation CLI — `naavik vault rotate-key --old=... --new=...` re-decrypts + re-encrypts | plan 10 § B.5 | [x] `cli/vault.py` rotate-key with `.bak` backup + `--no-backup` flag; round-trip verified end-to-end |
| 4.8 | Settings · Deployment UI: warning when `SECRET_KEY` env mismatches the vault's encryption key fingerprint | plan 10 § B.5 | [x] `vault.is_locked()` + `services/settings_service.get_deployment_info()` expose mismatch state; UI banner wiring lands when settings tab consumes the new endpoint |
| 4.9 | `ats_credentials` service — DB row metadata + vault-backed credential resolution | BACKEND.md § H.1, § K.5 | [x] DB metadata + vault.get(scope=ats, key=board) resolution |
| 4.10 | Profile service partial (CRUD + per-field PUT) | BACKEND.md § H.1 | [x] get/update_field/update_application_questions/add/update/delete/reorder bullets; emits profile_updated AppEvent |
| 4.11 | Settings persistence (incl. `eager_review_generation` flag for cost-aware DRAFT generation) | BACKEND.md § D.7 + DATA_MODEL.md § L | [x] DB-backed CRUD per tab; PUT /api/v1/settings/llm flows API key through vault; settings_service.get_deployment_info exposes vault status |
| 4.12 | `db/seed.py` consuming `db/sample_data.py` (idempotent ON CONFLICT DO NOTHING) | SAMPLE_DATA.md § A | [x] 372 rows seeded across 20 entities; ON CONFLICT DO NOTHING; bumps every PK sequence after seed; CLI `uv run python -m db.seed` |
| 4.13 | `/_design/components` swap from `NAAVIK_DEBUG` env var → persisted `Settings.debug` | plan 08 § H + plan 10 § B.8 | [x] route consults DB-backed Settings.debug; legacy env var still works as test fallback |
| 4.14 | Page-handler accessor body swap — sample-data lists → DB queries (signatures already async from Wave 3) | plan 10 § B.10 | [x] partial: 12 high-traffic accessors (Profile/User/Settings/Experience/Bullet/Skill/Education/Project/Cert/Job/Application/discover_queue/applications_visible_in_tracking) gated on `NAAVIK_PERSISTENCE=db`; remaining accessors fall back to memory in DB env (Wave 6 closes the gap) |
| 4.15 | Tests — `test_models`, `test_seed`, `test_auth`, `test_llm_provider`, `test_vault` | — | [x] 348 memory-mode tests + 6 live-DB seed tests + persistence-swap test pass; 14 skipped (live-DB gated via `NAAVIK_LIVE_DB=1`) |

#### Wave 5 — Backend Wave 6 (plan 10 § C)

> Real services, document generation, full DRAFT lifecycle, ATS adapters for boards with public APIs, auto-apply cron, notifications, portfolio sync. Acceptance: all 14 services pass tests; `document_generator` produces real PDFs end-to-end; DRAFT submit / discard / auto-apply queue works; `security-review` on doc-gen + portfolio API + vault audit clean.

| # | Service / artifact | Source contract | Status |
|---|---|---|---|
| 5.1 | `auth` service complete (refresh-token rotation; OIDC scaffolding stub) | BACKEND.md § H.1 | [ ] |
| 5.2 | `profile_service` (full CRUD + bullet ops + tag inference) | BACKEND.md § H.1 | [ ] |
| 5.3 | `extraction` (PDF → AI → Profile + SSE event emission) | BACKEND.md § H.1 | [ ] |
| 5.4 | `document_generator` (bullet selection + AI trim + Typst compile + native page-count validation; `answer_screeners` auto + drafted; **`pre_generate` no-op when `docs_state=READY` and no `Bullet.edited_at > GeneratedDocument.compiled_at` — DRAFT reuse heuristic**) | BACKEND.md § K.4 | [ ] |
| 5.5 | `application_service` (DRAFT lifecycle, submit/discard, ATS dispatch, `validate_submittable`, `process_auto_apply_queue`); orthogonal-state derivation lives here (`Job.queue_state=APPLIED` flip-on-submit; `outreach_engagement` computed) | BACKEND.md § K + DATA_MODEL.md § E, § F | [ ] |
| 5.6 | `scorer` Wave-6 visa filter (deterministic: `Profile.visa_sponsorship_needed × Job.visa_restrictions` zero-out; no LLM dep) | BACKEND.md § H.1 | [ ] |
| 5.7 | `prompts/score_job` skeleton in Wave 4; full tag-matching + gap analysis lives in plan 12 (Phase 3) | BACKEND.md § M.3 | [ ] |
| 5.8 | `notifications` (Discord webhook + Telegram outbound + in-app toast routing; per-event toggle) | BACKEND.md § L.3, L.4 | [ ] |
| 5.9 | `portfolio_sync` (public CV API filtered for EEO/visa/salary; **portfolio resume PDF regen on Profile-update debounced 60s, cached at `~/.naavik/data/documents/portfolio/resume.pdf`**; Netlify webhook) | BACKEND.md § L (Portfolio) | [ ] |
| 5.10 | Typst templates (`onepage.typ`, `cover_letter.typ`) | BACKEND.md § K.4 | [ ] |
| 5.11 | Typst compiler + native page-count validator (`typst compile --emit metadata`; **no `pdfinfo`/poppler dep**) | plan 10 § C.2.1 | [ ] |
| 5.12 | ATS adapters — Greenhouse + Lever + Ashby (Workday / LinkedIn / Indeed / Generic deferred to Phase 1.x sub-prompt) | BACKEND.md § K.5 | [ ] |
| 5.13 | Cron registration: `applications.auto_apply` (5min), `admin.aggregate_costs`, `admin.cleanup_stale_docs`, `admin.daily_db_snapshot`, `admin.refresh_oauth_tokens` | BACKEND.md § I.1 | [ ] |
| 5.14 | Stuck-queue surface wiring — failed-DRAFT detection populates Discover right rail (`up_next_card` `state="stuck"`) | plan 10 § C.3 + COMPONENTS.md `up_next_card` | [ ] |
| 5.15 | Tests — `test_application_service`, `test_document_generator`, `test_typst`, `test_ats_adapters`, `test_notifications`, `test_portfolio_sync` | — | [ ] |

#### Phase 1 deferred items (Phase 1.x)

Items called out in design docs as "Phase 1.x optional / Phase 2+". This is a quick reference; **the canonical extended backlog lives at `docs/plans/POST_PHASE_1.md` § Tier 3** (suggested plan numbers, effort sizing, slot-in suggestions).

| Item | Source | Notes |
|---|---|---|
| Workday / LinkedIn / Indeed / Generic ATS adapters | plan 10 § C.4 | Need credentials + Playwright + manual review queue. Greenhouse / Lever / Ashby ship in Wave 5 |
| Stale-DRAFT cleanup cron (`admin.cleanup_stale_drafts`) | this triage 2026-05-01 | Auto-discard or auto-archive DRAFTs idle >30 days; otherwise queue accumulates |
| Postmortem-on-failure: Playwright screenshot + AI summary on ATS failure | this triage 2026-05-01 | Surfaces in stuck-queue card; helps diagnose recurring CAPTCHA / field_mismatch |
| Manual job entry modal (full) | SCREENS.md § Phase mapping > Deferred | `+ Add by URL` is the partial Phase 1 path |
| Application detail slide-over | SCREENS.md § Phase mapping > Deferred | Phase 2 introduces `/tracking/:id` route |
| OIDC for self-hosted (Authentik / Keycloak / Okta) | SCREENS.md § Phase mapping > Deferred | Phase 2+ |
| Onboarding offline retry buffer for autosave | INTERACTIONS.md § H.3 | Optional, not blocking MVP |
| `Show drafts` filter UI on Tracking | SCREENS.md § Tracking visibility rule | Endpoint stubbed in Wave 3; UI toggle Phase 1.x |
| `ProfileAnswer` reuse cache (screener answer memory) | DATA_MODEL.md § J | Phase 2+ entity |
| Auto-apply immediate dispatch on right-swipe (vs current 5-min cron) | this triage 2026-05-01 | Refinement; user expectation may grow once auto-apply ships |
| `Settings.scraper_aggressiveness` (rate-limit dial) | this triage 2026-05-01 | Phase 2+; default conservative |
| Portfolio API versioning (`/api/portfolio/cv?version=v1`) | this triage 2026-05-01 | Lets crypticsoul.dev pin its consumer; Phase 2+ |
| JWT signing-key rotation (multi-tenant cloud tier) | plan 10 Q7 | Phase 2+; single-key fine for self-hosted |
| `JobEmbedding` semantic match (pgvector) | DATA_MODEL.md § H | Phase 6 |
| LinkedIn proxy support | BACKEND.md § J.4 | Phase 6+ |
| Submission-result observability dashboard (failure-kind aggregates) | this triage 2026-05-01 | Phase 6 — helps user spot recurring board-side failures |
| Argon2id vault upgrade (vs PBKDF2) | plan 10 Q6 | Phase 6 polish if security review flags |
| Light mode | DESIGN.md | Phase 6 |
| **Restore Lucide via CDN** | plan 09a follow-up 2026-05-02 | Self-hosted at `/static/lucide.min.js` for now to fix "no icons render" issue. Production should serve from a CDN — investigate why unpkg failed (content-blocker / CSP / rate-limit), pick a stable URL or fallback chain, drop the local file. |
| **Sidebar mobile-toggle reliability after navigation** | plan 09a follow-up 2026-05-02 | Idempotent script guards fixed the most common failure mode; user reports it's "still kind of wonky" after navigating away. Repro on real device, isolate the remaining timing issue (likely Tailwind JIT vs HTMX swap order). Not a blocker. |
| **Discover card max-w cap on ultra-wide screens** | plan 09a follow-up 2026-05-02 | 09a-follow-up dropped the `max-w-7xl` page cap on Discover so the card fills available space. On 4K+ monitors the card may stretch >1500px and feel sparse — add a `2xl:max-w-[1400px]` cap if user feedback comes in. |
| `Settings.daily_llm_cost_cap_usd` dashboard widget | POST_PHASE_1 § Tier 3 (consolidated 2026-05-02) | Wave 6 ships the enforcement; visible cap-progress UI is a Settings polish item. |

#### Pre-Phase-2 paper cuts (immediate; ship before plan 11)

These are dev-experience fixes carried over from Wave 2/3. Ship as a single tiny plan (`docs/plans/10a-dev-orchestrator-paper-cuts.md`) or fold inline into the start of plan 11. Each is < 1 day of work.

| # | Item | Status | Notes |
|---|---|---|---|
| PC.1 | Process-compose: confirm app logs + cold-start reliability | [ ] | Most mitigations landed in plan 08 (`PYTHONUNBUFFERED=1`, removed cosmetic readiness probe, stale `postmaster.pid` self-heal, `shutdown.timeout_seconds=10`, dropped `--quiet`). Still owed: cross-terminal repro, `--log-file` to `cli.options`, optionally `--no-progress` on `uv run fastapi dev`. If symptom persists, file upstream against `services-flake` / `process-compose-flake`. |
| PC.2 | `uv run fastapi dev` (no path) should just work | [ ] | Recommended fix: thin `app.py` re-export at repo root (`from src.main import app`). Two lines, one file. While there, drop `src/main.py` from README's "Manual local development setup". |
| PC.3 | Playwright local capture on NixOS | [ ] | Replace pip-installed `playwright` with `pkgs.python312Packages.playwright` (NixOS-patched driver) in dev shell. Or ship a `nix run .#snapshots` flake app via `steam-run` / `buildFHSEnv`. **Prereq for the CI-side per-PR visual-diff gate** (no local capture = no diff gate). Capture the first 20-snapshot baseline alongside the dev-shell fix. |

**Deliverable (end of Phase 1):** User uploads resume → AI extracts profile → user edits in UI → Discover queue scored + filtered → tailored resume + cover letter generated for any job → submit application via supported ATS → email-signal-driven Tracking → outreach drafts go to LinkedIn / email → portfolio API serves profile + downloadable resume.

---

### Phase 2: Job Scraping & Discovery
> **Goal:** Automated multi-source job discovery with AI extraction.
> **Plan:** `docs/plans/11-phase-2-scrapers.md` (to be authored after Phase 1 ships). Splits cleanly into 11a (LinkedIn + Greenhouse + Lever + Ashby) and 11b (Workday + Indeed + Generic + n8n migration).
> **Implementation contract:** `docs/design/BACKEND.md` § J (scraping architecture), § I (cron catalog), § K (auto-apply pipeline). Wave 6 services + Phase 2 sub-prompts of plan 10.
> **Estimated effort:** 2–3 weeks.

| # | Task | Priority | Notes |
|---|---|---|---|
| 2.1 | Crawl4AI setup + generic scraper base class | CRITICAL | Replace Browserless |
| 2.2 | Site scrapers: LinkedIn (RSS via RSShub + guest API), Workday, Greenhouse, Lever, Ashby, Indeed | CRITICAL | Port from n8n |
| 2.3 | AI job extraction: HTML → JobInfo (company, position, location, visa, salary, skills) | CRITICAL | Structured output |
| 2.4 | Job deduplication (URL-based + fuzzy title/company) | HIGH | |
| 2.5 | APScheduler: periodic scraping per source | HIGH | PostgreSQL job store |
| 2.6 | SQLModel: Job, StatusHistory models + migration | CRITICAL | |
| 2.7 | HTMX UI: job list with filters, job detail view | HIGH | |
| 2.8 | Discord + Telegram notifications for new jobs | MEDIUM | Port from n8n |
| 2.9 | Rate limiting + anti-detection (random delays, throttling) | HIGH | |
| 2.10 | Migrate existing n8n DataTable + Google Sheets data to PostgreSQL | MEDIUM | Seed script |

**Deliverable:** Jobs scraped on schedule, AI-extracted, deduplicated, shown in dashboard with notifications.

---

### Phase 3: Intelligent Scoring & Matching
> **Goal:** AI compatibility scoring with tag-based profile matching and explainable results.
> **Plan:** `docs/plans/12-phase-3-scoring.md` (to be authored after plan 11 ships).
> **Implementation contract:** `docs/design/BACKEND.md` § H.1 (`scorer` service), § M.3 (`score_job` prompt). DATA_MODEL.md § C (`Job.score`, `Job.score_explanation`, `Job.match_breakdown`).
> **Estimated effort:** 1–2 weeks.

| # | Task | Priority | Notes |
|---|---|---|---|
| 3.1 | Tag-based matching: job desc → identify tags → match against profile bullets | CRITICAL | |
| 3.2 | AI scoring: structured output (score 0-1, explanation, gap analysis) | CRITICAL | Cloud + local model support |
| 3.3 | Visa/sponsorship auto-filter (score 0 for citizenship-required / no-sponsorship) | CRITICAL | |
| 3.4 | Tailored resume preview: show which bullets selected/excluded for a job | HIGH | |
| 3.5 | One-click generation: from job detail → tailored resume + cover letter | HIGH | |
| 3.6 | Score history + analytics | MEDIUM | |
| 3.7 | HTMX UI: score card, match explanation, bullet selection preview | HIGH | |

**Deliverable:** Every job scored with explanation. User sees bullet selection preview and generates tailored docs in one click.

---

### Phase 4: Application Tracking & Auto-Apply
> **Goal:** Full application lifecycle with configurable automation level.
> **Plan:** Most of Phase 4 ships inside plan 10 Wave 6 (DRAFT lifecycle, ATS submit, semi-auto + auto-apply paths). UI polish + analytics dashboard ship as a small follow-up `13a-tracking-polish.md` post-Phase-1.
> **Implementation contract:** `docs/design/BACKEND.md` § K (auto-apply + manual paths), § K.5 (ATS adapters per board), § L.1 (Gmail/Outlook OAuth). `docs/design/DATA_MODEL.md` § A multi-axis state, § E state transitions.

| # | Task | Priority | Notes |
|---|---|---|---|
| 4.1 | Application multi-axis state model: `status` (APPLIED → RECRUITER_SCREEN → ONSITE_LOOP → OFFER → CLOSED) + `closed_reason` (rejected_by_them / withdrawn_by_me / ghosted / accepted_other) + orthogonal sub-states `docs_state`, `referral_state`, `recruiter_state`, computed `outreach_engagement`. State machine + transitions per axis. See `docs/design/DATA_MODEL.md` (plan 05) for authoritative definitions. | CRITICAL | |
| 4.2 | Manual application logger (form for external applications) | HIGH | |
| 4.3 | Semi-auto flow: generate docs → notification → human approves → submit → update status | HIGH | Default mode |
| 4.4 | Auto-apply flow: high-score jobs → generate → submit automatically (user setting, default OFF) | HIGH | Configurable threshold |
| 4.5 | Playwright form filling for supported boards (with optional review step) | MEDIUM | |
| 4.6 | Google Sheets sync (optional secondary view) | LOW | Keep for shared tracking |
| 4.7 | Application analytics dashboard | MEDIUM | Response rate, interview rate, by company/role |

**Deliverable:** Full Kanban tracking. Semi-auto or auto-apply based on user preference. Analytics.

---

### Phase 5: Email Monitoring & Outreach
> **Goal:** Monitor emails, classify responses, manage interview prep, and track recruiter/employee outreach. (Email auto-classification feeds the multi-axis Application sub-states defined in Phase 4 — `recruiter_state`, `outreach_engagement` — via Tracking; this phase adds the email + outreach mechanics behind that.)
> **Plans:** `docs/plans/13-phase-5-email.md` (Gmail/Outlook OAuth + classifier) → then `docs/plans/14-phase-5-outreach.md` (LinkedIn DM + Calendar + Discord/Telegram inbound). Both authored after plan 12 ships.
> **Implementation contract:** `docs/design/BACKEND.md` § L.1 (Gmail/Outlook), § L.2 (LinkedIn browser, account-ban risk), § L.3–L.5 (Discord/Telegram/Calendar), § H.1 (`email_classifier`, `outreach_generator`, `contact_tracker`).
> **Estimated effort:** Plan 13 1–2 weeks; plan 14 2–3 weeks (LinkedIn is the most fragile dep).

| # | Task | Priority | Notes |
|---|---|---|---|
| **Email Tracking** | | | |
| 5.1 | Gmail API / IMAP email monitoring | HIGH | Connect to user's email inbox |
| 5.2 | AI email classification: INTERVIEW_REQUEST, REJECTION, OFFER, ASSESSMENT, FOLLOW_UP | HIGH | |
| 5.3 | Auto-update job status from email classification | HIGH | |
| 5.4 | Priority notifications (HIGH for interviews/offers) | MEDIUM | |
| 5.5 | Email thread tracking per application | HIGH | |
| 5.6 | AI draft response generation | MEDIUM | |
| **Interview Prep** | | | |
| 5.7 | Interview scheduling integration (Calendly/webhook) — surfaces on Tracking application detail and Overview priority actions | MEDIUM | |
| 5.8 | Interview prep: role-specific questions from job desc + profile gaps | LOW | |
| **Recruiter & Employee Outreach** | | | |
| 5.9 | LinkedIn connection tracker: store recruiter/employee contacts per company | HIGH | |
| 5.10 | Outreach template system: personalized messages for recruiters + employees | HIGH | Uses profile + job context |
| 5.11 | AI-generated outreach messages: referral requests, follow-ups, check-ins | HIGH | Tone-appropriate, not spammy |
| 5.12 | LinkedIn automation: send connection requests + messages via API | MEDIUM | Rate-limited, anti-detection |
| 5.13 | Outreach history tracking: sent messages, responses, acceptance rates | MEDIUM | |
| 5.14 | Warm intro finder: suggest mutual connections for warm outreach | LOW | LinkedIn API |
| 5.15 | Interview process accelerator: auto-send thank-you notes, follow-up reminders | MEDIUM | |

**Deliverable:** Email inbox monitored → job statuses auto-updated. Recruiter/employee contacts tracked → AI-assisted outreach → referral requests sent at optimal timing.

---

### Phase 6: Optimization & Polish
> **Goal:** Performance, analytics, and advanced features.
> **Plan:** `docs/plans/15-phase-6-polish.md` — splits cleanly into 15a (observability — Prometheus + Sentry + OTel), 15b (light mode), 15c (LaTeX template + ML scoring calibration). Author after plan 14 ships.
> **Implementation contract:** `docs/design/BACKEND.md` § N (observability — Prometheus, Sentry, OTel), `docs/design/DATA_MODEL.md` § H (`JobEmbedding` pgvector for semantic match), `DESIGN.md` (light mode tokens — Phase 6).
> **Estimated effort:** 3–4 weeks total (split across 15a/b/c).

| # | Task | Priority | Notes |
|---|---|---|---|
| 6.1 | Resume A/B testing (track which variants get responses) | MEDIUM | |
| 6.2 | Semantic job matching with pgvector embeddings | MEDIUM | |
| 6.3 | Weekly summary reports | LOW | |
| 6.4 | Performance: caching, batch AI calls, parallel scraping | LOW | |
| 6.5 | ML scoring calibration from application outcomes | LOW | |
| 6.6 | LaTeX template support alongside Typst (for users who prefer LaTeX) | LOW | NEU template compat, latexmk/tectonic compilation |
| 6.7 | Additional Typst/LaTeX resume templates (modern, academic, creative) | LOW | Template marketplace |

---

## Deployment

### Four deployment paths

#### 1. Self-hosted: Nix Flake (NixOS — recommended for homelab)

```bash
# Add to your NixOS flake inputs
inputs.naavik.url = "github:crizzy9/naavik";

# In your host's services.yml (Lumino pattern)
apps:
  tools:
    naavik:
      enable: true
      subdomain: "jobs"           # → jobs.crypticsoul.dev
      port: 8000
      settings:
        llm_provider: "anthropic"  # or "openai" or "ollama"
        auto_apply: false
        portfolio_webhook: "https://api.netlify.com/build_hooks/..."
```

The NixOS module (`nix/module.nix`) follows Lumino's service patterns:
- Reads config from `settings.servicesConfig.apps.tools.naavik`
- Creates systemd service with hardening
- SOPS secrets for API keys (`naavik_env`)
- Traefik routing via `services.traefik.dynamicConfigOptions.http`
- PostgreSQL provisioned as dependency
- `services` group membership for shared storage
- Data directory at `${appdata}/naavik`

#### 2. Self-hosted: Docker Compose (any Linux/macOS)

```bash
git clone https://github.com/crizzy9/naavik.git && cd naavik
cp .env.example .env  # edit with your API keys
docker compose up -d
```

#### 3. Managed Cloud ($15/month)

For users who prefer not to self-host. Functionally identical to self-hosted — you bring your own AI credits (Anthropic/OpenAI API keys) or connect a local Ollama instance. Naavik handles the server, you handle the AI.

- Sign up at `jobs.crypticsoul.dev` (or self-branded instance)
- Enter your API key in Settings → LLM Provider
- Everything else works the same

#### 4. Development (bare metal)

```bash
nix develop          # drops into shell with python, uv, typst, postgresql, ruff
uv sync              # install Python deps
uv run alembic upgrade head
uv run fastapi dev src/main.py
```

### Nix Flake Outputs

```nix
{
  packages.x86_64-linux.default   # naavik Python package
  packages.x86_64-linux.naavik    # alias

  nixosModules.default             # NixOS service module
  nixosModules.naavik              # alias

  devShells.x86_64-linux.default   # dev environment (python, uv, typst, pg, ruff)
}
```

### Cloud vs Self-hosted: Same Codebase

Naavik is a single codebase. The only differences between self-hosted and cloud:

| | Self-hosted | Cloud |
|---|---|---|
| **Server** | Your infrastructure | Managed by Naavik |
| **Cost** | Free | $15/month |
| **AI credits** | You provide API keys | You provide API keys |
| **Data** | On your servers | Encrypted at rest |
| **Code** | Identical | Identical |
| **Features** | All | All |

There is no "cloud-only" feature. The cloud tier is purely a convenience layer.

This is reflected in the design: Settings has a "Deployment" tab that shows your current mode, but there's no premium upsell anywhere in the core experience.

---

## n8n Migration Strategy

| n8n Component | Naavik Equivalent | When |
|---|---|---|
| Main Workflow (Lw1uK5APIhIeUeem) | `scheduler/` + `services/job_scraper.py` | Phase 2 |
| Manual Logger (xSIGv47G2Porc0S9) | `api/applications.py` + `ui/templates/pages/discover.html` (`+ Add by URL`) and `ui/templates/pages/tracking.html` (`+ Add manually`) | Phase 4 |
| Job Page Parser (PQAGv5qUajzBP5wm) | `scraper/*.py` | Phase 2 |
| DataTable (Job Applications) | PostgreSQL `jobs` table | Phase 2 |
| Google Sheets sync | Optional sync in Phase 4 | Phase 4 |
| Discord notifications | `services/notifications.py` | Phase 2 |
| OpenAI extraction | `llm/` (multi-provider) | Phase 0 |
| Browserless | Crawl4AI + Playwright | Phase 2 |
| RSShub feed | Keep as-is | Phase 2 |

**Migration order:**
1. Export n8n workflows → `legacy/`
2. Build profile system (Phase 0-1) independently
3. Build scrapers (Phase 2) → validate pipeline works → disable n8n Main Workflow
4. Build tracking (Phase 4) → disable n8n Manual Logger
5. Fully decommission n8n after Phase 4

---

## Portfolio Integration

Naavik serves profile data to the portfolio website (crypticsoul.dev):

```
Naavik DB ──► GET /api/portfolio/cv ──► cryptic-soul cv.astro (build-time fetch)
         ──► GET /api/portfolio/resume.pdf ──► Download link on CV page
```

- Profile updates in Naavik → optionally trigger Netlify rebuild webhook
- CV page always in sync — no manual HTML duplication
- Resume PDF always current — no manual copy

---

## UI Screens & Design

### Design Documents

Canonical anchors and directory layout live in `AGENTS.md` § Documentation locations. The lifecycle that produces design contracts is `AGENTS.md` § Workflow. Always-present design docs: `DESIGN.md` (visual contract), `docs/design/SCREENS.md` (screen catalog), `docs/design/WORKFLOW.md` (UI sub-process). Mockups (visual reference, gitignored) at `docs/design/mockups/` — see `docs/design/mockups/README.md`.

### Design Workflow

```
PHASE A (Claude Design):
  Point Claude Design at GitHub repo (or upload DESIGN.md) → "Set up design system"
  → Extract tokens → Validate → Publish

PHASE B (Claude Design):
  Create Prototype (High fidelity) → Paste CLAUDE_DESIGN_PROMPT.md
  → Generate screens → Iterate → Export PNGs → Commit to mockups/

PHASE C (Claude Code):
  Read mockups + DESIGN.md
  → Build component library (templates/components/)
  → Implement pages (templates/pages/)
```
ROADMAP + SCREENS.md → paste prompt → Claude Design → mockups committed
                                         ↓
                         Claude Code reads mockups + DESIGN.md
                                         ↓
                         Component library built (templates/components/)
                                         ↓
                         Pages implemented (templates/pages/) + HTMX routes
```

### Screen Index

**Canonical screen index lives in [`docs/design/SCREENS.md`](docs/design/SCREENS.md).** That document tracks per-screen mockup status (`Mockup [ ]` / `[~]` / `[x]`) and impl status (`Impl [ ]` / `[~]` / `[x]`). ROADMAP.md tracks phase progress; SCREENS.md tracks per-screen progress. Maintaining two parallel tables produces drift — they were drifting badly until 2026-04-30 — so the table that used to live here has been removed.

**Phase 1 (MVP) at a glance:** 11 screens — Login · Onboarding · Overview · Profile · Profile editor · Bullet editor (modal) · Discover · Discover · review & apply · Tracking · Outreach · Settings. Mockups for all 11 are committed in `docs/design/mockups/`.

**Deferred / Phase 2+ screens** (Manual job entry modal, Application detail slide-over, etc.) are listed in `docs/design/SCREENS.md` § Phase mapping > Deferred.

### Design System (Summary)

| Token | Value |
|---|---|
| Page BG | `#020617` (slate-950) |
| Surface | `#0F172A` (slate-900) |
| Elevated | `#1E293B` (slate-800) |
| Brand primary | `#6366F1` (indigo-500) |
| Accent (AI) | `#22D3EE` (cyan-400) |
| Sans font | Inter (weights 400–700) |
| Mono font | JetBrains Mono |
| Icons | Lucide Icons (stroke 1.5) |

Full spec in `DESIGN.md`.
