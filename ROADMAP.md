# Naavik Development Roadmap

> Last updated: 2026-04-25

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

2. **Two-form bullets** — Every experience bullet has `oneline` (strict 1-line for 1-page resume) and `detailed` (full description for portfolio/extended CV). AI selects bullets per job using tags.

3. **Typst over LaTeX** — 10-100x faster PDF compilation, clean programmatic data ingestion, single binary. LaTeX compatibility is a future roadmap item.

4. **Direct LLM SDKs, no LangChain** — Our LLM use cases are single-prompt structured output tasks. Both Anthropic and OpenAI SDKs support Pydantic-based structured output natively. No abstraction layer needed.

5. **Auto-apply as user setting** — Default off. When enabled, high-scoring jobs get documents generated and applications submitted automatically. Users can toggle this per their comfort level.

6. **Cloud + Local LLM support** — Every AI feature offers both cloud (Claude/GPT) and local (Ollama) options. User chooses in settings. Prompts are provider-agnostic.

---

## Data Model

### Profile (Single Source of Truth)

```
Profile
├── meta (name, email, phone, location, portfolio, github, linkedin, visa_status)
├── summary (full + short versions)
├── education[]
│   └── institution, school, location, degree, dates, gpa, courses[]
├── experience[]
│   ├── company, team, title, location, dates
│   └── bullets[]
│       ├── id (stable identifier)
│       ├── oneline (validated: must render as exactly 1 line in Typst)
│       ├── detailed (no length constraint)
│       ├── tags[] (ai-ml, backend, devops, frontend, leadership, genai, data-eng, platform)
│       ├── default_include (appears in generic 1-page resume)
│       └── metrics{} (revenue, percentage, team_size — for AI reference)
├── skills[] → (category, items[])
├── projects[] → (title, date, oneline, detailed, tags[], portfolio_slug)
├── certifications[] → (title, issuer, date, detailed)
├── open_source[] → (title, date, detailed)
└── cover_letter_base → (template paragraphs with placeholders)
```

### Job Application

```
Job
├── id, source (AUTOMATED/MANUAL), url, url_type
├── company, position, team, location
├── dates (posted, found, applied)
├── description, criteria, skills_required
├── visa_restrictions, salary_range
├── compatibility_score (0-1), score_explanation
├── status (FOUND → SCORED → APPROVED → DOCS_GENERATED → APPLIED → INTERVIEWING → OFFER → REJECTED → WITHDRAWN)
├── status_history[]
├── generated_resume_path, generated_cover_letter_path
└── referral info, notes
```

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
├── src/naavik/
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
- `uv run fastapi dev src/naavik/main.py` → server starts on :8000
- `GET /api/health` → `{"status":"ok"}`
- `GET /` → HTTP 200, dashboard renders with sidebar
- `uv run ruff check src/naavik/` → all checks passed

---

### Phase 1: Profile System & Resume Generation
> **Goal:** Profile intake, editing, resume/cover letter generation, and portfolio sync.
> **Status:** Not started
>
> **Prerequisite (blocking UI work):** Screens 1–9 must be designed (mockups committed to `docs/design/mockups/`) before any UI templates are built. See UI Screens & Design section above.

| # | Task | Status | Priority | Notes |
|---|---|---|---|---|
| **UI & Design** | | | | |
| D.1 | Generate mockups for Phase 1 screens (Claude Design) | [ ] | CRITICAL | Screens 1–9: login, dashboard, onboarding, profile view, profile editor, bullet editor, resume generator, cover letter generator, settings |
| D.2 | Derive component library from mockups (Claude Code) | [ ] | CRITICAL | Build `templates/components/` — button, card, input, tag, badge, stat_card, bullet_editor, etc. |
| D.3 | Implement Phase 1 UI pages (Claude Code) | [ ] | CRITICAL | One mockup → one page per screen. See `docs/design/WORKFLOW.md` |
| **Profile System** | | | | |
| 1.1 | SQLModel models: Profile, Experience, Bullet, Skill, Education, Project, Certification | [ ] | CRITICAL | `oneline` + `detailed` + `tags` + `default_include` |
| 1.2 | Profile CRUD API (`/api/v1/profile/`) | [ ] | CRITICAL | |
| 1.3 | LLM provider abstraction (`llm/base.py` + anthropic + openai + ollama) | [ ] | HIGH | Structured output via Pydantic |
| 1.4 | Resume upload + AI extraction service (PDF → LLM → structured profile → DB) | [ ] | CRITICAL | Core onboarding flow |
| 1.6 | Inline bullet editor (oneline/detailed side-by-side, tag chips, default_include toggle) | [ ] | HIGH | HTMX partials |
| 1.7 | Auth: Google OAuth + JWT, multi-user | [ ] | MEDIUM | FastAPI security |
| 1.8 | Seed existing profile data from cryptic-soul resume files | [ ] | HIGH | Consolidate OnePage + FullProfile |
| **Resume & Cover Letter Generation** | | | | |
| 1.9 | Typst template: NEU-style 1-page resume (`onepage.typ`) | [ ] | CRITICAL | Match existing LaTeX output |
| 1.10 | Typst template: full profile CV (`fullprofile.typ`) | [ ] | HIGH | All bullets, all sections |
| 1.11 | Typst template: cover letter (`cover_letter.typ`) | [ ] | HIGH | Placeholder-based |
| 1.12 | Typst compiler wrapper (`typst/compiler.py`) | [ ] | CRITICAL | `typst compile` CLI |
| 1.13 | Oneline validator: render bullet in Typst, verify 1-line fit | [ ] | HIGH | Reject with preview if overflow |
| 1.14 | Resume generator service: profile + tag filters → select bullets → Typst → PDF | [ ] | CRITICAL | Core product feature |
| 1.15 | Cover letter generator: profile + job desc → AI fills placeholders → Typst → PDF | [ ] | CRITICAL | |
| **Portfolio Integration** | | | | |
| 1.17 | Portfolio API: `GET /api/portfolio/cv` (public, no auth) | [ ] | HIGH | JSON profile for crypticsoul.dev |
| 1.18 | Portfolio resume endpoint: `GET /api/portfolio/resume.pdf` | [ ] | HIGH | Serves latest generic OnePage |
| 1.19 | Add download button to cryptic-soul CV page (links to Naavik API) | [ ] | MEDIUM | Minimal change to portfolio |

**Deliverable:** User uploads resume → AI extracts profile → user edits in UI → generates tailored resume/cover letter PDFs → portfolio API serves profile + downloadable resume.

---

### Phase 2: Job Scraping & Discovery
> **Goal:** Automated multi-source job discovery with AI extraction.

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

| # | Task | Priority | Notes |
|---|---|---|---|
| 4.1 | Status pipeline: FOUND → SCORED → APPROVED → DOCS_GENERATED → APPLIED → INTERVIEWING → OFFER/REJECTED/WITHDRAWN | CRITICAL | |
| 4.2 | Manual application logger (form for external applications) | HIGH | |
| 4.3 | Semi-auto flow: generate docs → notification → human approves → submit → update status | HIGH | Default mode |
| 4.4 | Auto-apply flow: high-score jobs → generate → submit automatically (user setting, default OFF) | HIGH | Configurable threshold |
| 4.5 | Playwright form filling for supported boards (with optional review step) | MEDIUM | |
| 4.6 | Google Sheets sync (optional secondary view) | LOW | Keep for shared tracking |
| 4.7 | Application analytics dashboard | MEDIUM | Response rate, interview rate, by company/role |

**Deliverable:** Full Kanban tracking. Semi-auto or auto-apply based on user preference. Analytics.

---

### Phase 5: Email Monitoring & Interview Pipeline
> **Goal:** Monitor emails, classify responses, manage interviews, and track recruiter/employee outreach.

| # | Task | Priority | Notes |
|---|---|---|---|
| **Email Tracking** | | | |
| 5.1 | Gmail API / IMAP email monitoring | HIGH | Connect to user's email inbox |
| 5.2 | AI email classification: INTERVIEW_REQUEST, REJECTION, OFFER, ASSESSMENT, FOLLOW_UP | HIGH | |
| 5.3 | Auto-update job status from email classification | HIGH | |
| 5.4 | Priority notifications (HIGH for interviews/offers) | MEDIUM | |
| 5.5 | Email thread tracking per application | HIGH | |
| 5.6 | AI draft response generation | MEDIUM | |
| **Interview Pipeline** | | | |
| 5.7 | Interview scheduling integration (Calendly/webhook) | MEDIUM | |
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
uv run fastapi dev src/naavik/main.py
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
| Manual Logger (xSIGv47G2Porc0S9) | `api/jobs.py` + `ui/templates/jobs/` | Phase 4 |
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

| Document | Purpose |
|---|---|
| `docs/design/DESIGN_SYSTEM.md` | Color tokens, typography, components, voice, motion, accessibility — the visual contract |
| `docs/design/DESIGN_SYSTEM_UPLOAD.md` | Formatted specifically for Claude Design's "Set up design system" feature — upload this file |
| `docs/design/SCREENS.md` | Complete screen catalog (19 screens, all phases) with routes, layout specs, interactions, states |
| `docs/design/CLAUDE_DESIGN_PROMPT.md` | Screen descriptions for Claude Design prototype projects (assumes design system already published) |
| `docs/design/WORKFLOW.md` | Design → implementation pipeline: design system → mockups → component library → pages |
| `docs/design/mockups/` | Committed mockup PNGs — never implement without one |

### Design Workflow

```
PHASE A (Claude Design):
  Upload DESIGN_SYSTEM_UPLOAD.md → "Set up design system"
  → Extract tokens → Validate → Publish

PHASE B (Claude Design):
  Create Prototype (High fidelity) → Paste CLAUDE_DESIGN_PROMPT.md
  → Generate screens → Iterate → Export PNGs → Commit to mockups/

PHASE C (Claude Code):
  Read mockups + DESIGN_SYSTEM.md
  → Build component library (templates/components/)
  → Implement pages (templates/pages/)
```
ROADMAP + SCREENS.md → paste prompt → Claude Design → mockups committed
                                         ↓
                         Claude Code reads mockups + DESIGN_SYSTEM.md
                                         ↓
                         Component library built (templates/components/)
                                         ↓
                         Pages implemented (templates/pages/) + HTMX routes
```

### Screen Index

| # | Screen | Route | Phase | Mockup | Impl |
|---|---|---|---|---|---|
| 1 | Login / OAuth | `/login` | 1 | [ ] | [ ] |
| 2 | Dashboard | `/` | 1 | [ ] | [~] (placeholder) |
| 3 | Onboarding — Resume Upload | `/onboarding` | 1 | [ ] | [ ] |
| 4 | Profile View | `/profile` | 1 | [ ] | [ ] |
| 5 | Profile Editor | `/profile/edit` | 1 | [ ] | [ ] |
| 6 | Bullet Editor (modal) | (component) | 1 | [ ] | [ ] |
| 7 | Resume Generator | `/generate/resume` | 1 | [ ] | [ ] |
| 8 | Cover Letter Generator | `/generate/cover-letter` | 1 | [ ] | [ ] |
| 9 | Settings | `/settings` | 1 | [ ] | [ ] |
| 10 | Jobs List | `/jobs` | 2 | [ ] | [ ] |
| 11 | Job Detail | `/jobs/:id` | 2 | [ ] | [ ] |
| 12 | Manual Job Entry | `/jobs/new` (modal) | 2 | [ ] | [ ] |
| 13 | Score Card / Match Explanation | (component) | 3 | [ ] | [ ] |
| 14 | Kanban Pipeline | `/jobs?view=kanban` | 4 | [ ] | [ ] |
| 15 | Analytics Dashboard | `/analytics` | 4 | [ ] | [ ] |
| 16 | Email Inbox | `/inbox` | 5 | [ ] | [ ] |
| 17 | Contacts List | `/contacts` | 5 | [ ] | [ ] |
| 18 | Outreach Composer | `/contacts/:id/compose` | 5 | [ ] | [ ] |
| 19 | Interview Pipeline | `/interviews` | 5 | [ ] | [ ] |

**Next design batch:** Screens 1–9 (Phase 1 MVP).

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

Full spec in `docs/design/DESIGN_SYSTEM.md`.
