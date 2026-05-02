# CLAUDE.md

> **For Claude Code sessions.**
> **Canonical guide:** `AGENTS.md` — always read that first.
> **Last updated:** 2026-05-02 (added § Deviations from plan workflow rule + § Operational artifacts from plan 10 § B)

This file provides Claude Code-specific guidance. For general project conventions, architecture, and the design workflow, see `AGENTS.md`.

## Claude Code Quickstart

```
1. Read AGENTS.md
2. Read ROADMAP.md
3. If doing UI work: read docs/design/WORKFLOW.md + DESIGN.md
4. Start work. Update ROADMAP.md as you go.
5. Before archiving any plan, write its `## Deviations from plan` section. (AGENTS.md § Workflow step 7.)
```

## Deviations workflow — non-negotiable before archive

Per `AGENTS.md` § Workflow step 7, every plan in `docs/plans/` MUST have a `## Deviations from plan` section before it moves to `archive/`. The implementing agent (you) writes this section based on what actually shipped vs what the plan promised. Bullets carry: **what** changed, **why**, **impact** on follow-up plans, and any **new operational surface** introduced (env var, CLI, on-disk path, etc.).

Anything new and operational ALSO propagates to user-facing docs in the same change:

- New env var → README § Configuration
- New CLI command → README § Operations or wherever the equivalent lives
- New on-disk path or secret-handling rule → CLAUDE.md + `docs/plans/POST_PHASE_1.md`
- New port, schedule, or runtime invariant → both, plus ROADMAP "Last updated"

If the deviation only matters to maintainers, document it in the plan's `## Deviations from plan` section and stop — no doc propagation needed.

**Plans without a Deviations section may not be archived.** Use "no material deviations" if the plan really shipped exactly as spec'd, but that's rare; reviewers should be skeptical when they see it.

## Claude Code Specific Notes

### Development Commands (Nix-first)

```bash
# One-command dev orchestrator (Postgres + alembic + FastAPI in one terminal)
nix run .#dev

# Interactive dev shell (uv, ruff, typst, postgresql-client on PATH)
nix develop          # or via direnv

# Inside `nix develop`:
uv sync
uv run fastapi dev src/main.py
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "message"
uv run ruff check .
uv run ruff format .
uv run pytest
typst compile src/typst/templates/onepage.typ output.pdf

# Build Nix package (result/bin/naavik + naavik-migrate)
nix build

# Self-host stack (auto-migrates before app starts)
docker compose up -d
```

Dev DB runs on `127.0.0.1:5433`. State at `./.naavik/db/` (gitignored). Wipe with `rm -rf .naavik/`.

### Visual QA with Playwright

When implementing UI, use Playwright to take screenshots and compare against mockups:

```python
# In a test or script
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto("http://localhost:8000/")
    page.screenshot(path="screenshot.png")
    browser.close()
```

### Design Workflow for Claude Code

**Prerequisite:** Mockups must already exist in `docs/design/mockups/` (generated via Claude Design's design system → prototype pipeline). See `AGENTS.md` for the full design workflow.

When implementing a screen:
1. Read `docs/design/SCREENS.md` for the screen spec
2. Open `docs/design/mockups/{n}-{slug}-desktop.png` (and `-mobile.png`)
3. Read `DESIGN.md` for tokens and components
4. Check `src/ui/templates/components/` for reusable partials
5. Build the page in `src/ui/templates/pages/{slug}.html`
6. Add route in the appropriate FastAPI router module
7. Run `uv run ruff check` before finishing

### Project Overview

**Naavik** (Hindi: नाविक, "Navigator") is an open-source career automation platform. **Self-hosted first, cloud available** ($15/mo, bring-your-own AI credits). See `AGENTS.md` for full details.

### Roadmap Maintenance (CRITICAL)

`ROADMAP.md` is the **single source of truth** for project progress. Rules:
1. Read relevant phase before starting work
2. Mark `[~]` when starting a task
3. Mark `[x]` + deliverable note when completing
4. Update phase `Status:` to `✅ Complete (YYYY-MM-DD)` when done
5. Edit directly when scope changes — don't bury in commits
6. Bump "Last updated: YYYY-MM-DD" on meaningful edits

Never let the roadmap drift. Fix it first, then continue work.

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Backend | FastAPI + SQLModel (Pydantic + SQLAlchemy) |
| Frontend | HTMX + Jinja2 + Tailwind CSS + DaisyUI |
| Database | PostgreSQL (pgvector for semantic matching) |
| ORM/Migrations | SQLModel + Alembic |
| Scraping | Crawl4AI (primary) + Playwright (fallback for interactive flows) |
| AI/LLM | Direct SDK calls — Anthropic, OpenAI, Ollama (user-configurable) |
| PDF Generation | Typst (primary), LaTeX compatibility planned for later |
| Scheduling | APScheduler (PostgreSQL job store) |
| Auth | FastAPI JWT (forms — email + password) — OIDC for self-hosted (Authentik / Keycloak / Okta) is Phase 2+ |
| Notifications | Discord webhooks, Telegram bot |
| Deployment | Docker Compose |

## Architecture

```
src/
├── main.py              ← FastAPI app entrypoint
├── config.py            ← pydantic-settings based config
├── api/                 ← REST API routes
├── ui/                  ← HTMX views (Jinja2 templates + partials)
├── models/              ← SQLModel DB models + Pydantic schemas
├── services/            ← Business logic (profile intake, scraping, scoring, generation)
├── llm/                 ← LLM provider abstraction (anthropic, openai, ollama)
├── scraper/             ← Site-specific job scrapers (linkedin, workday, greenhouse, etc.)
├── typst/               ← Typst templates + compilation
├── scheduler/           ← APScheduler job definitions
└── db/                  ← Session management, seeding
```

## Key Conventions

### Code Style
- Use `ruff` for linting and formatting
- Type hints on all function signatures
- Pydantic models for all API input/output
- SQLModel for database models (inherits from both Pydantic BaseModel and SQLAlchemy)
- Async endpoints where I/O is involved (DB, HTTP, LLM calls)

### API Design
- REST endpoints under `/api/v1/`
- HTMX view routes under `/` (return HTML fragments)
- Portfolio public API under `/api/portfolio/` (no auth required)
- All API responses use Pydantic response models
- Use FastAPI dependency injection for DB sessions, auth, LLM providers

### Frontend (HTMX)
- Templates in `src/ui/templates/`
- Reusable partials in `src/ui/templates/components/` (HTMX fragment swaps)
- Use `hx-get`, `hx-post`, `hx-swap` for interactivity — no custom JavaScript unless absolutely necessary
- Tailwind CSS + DaisyUI for styling (same stack as the portfolio site crypticsoul.dev)
- Alpine.js only if needed for complex client-side state (e.g., drag-and-drop)

### Database
- PostgreSQL with pgvector extension
- Alembic for migrations (`migrations/versions/`)
- SQLModel for models — define in `models/` directory
- Use `AsyncSession` for all DB operations
- Never raw SQL in route handlers — use service layer

### LLM Integration
- All LLM calls go through `llm/base.py` abstract interface
- Implementations: `llm/anthropic.py`, `llm/openai.py`, `llm/ollama.py`
- User selects provider in settings — stored per-user in DB
- Use Pydantic models for structured output (both Anthropic and OpenAI support this natively)
- Prompt templates live in `llm/prompts/` as Python modules (not string files)
- Always provide both cloud (Anthropic/OpenAI) and local (Ollama) options

### Resume/CV Data Model
- Profile data lives in PostgreSQL, NOT in YAML/JSON files
- Each experience bullet is a single field — the **long, full version**. AI trims it at apply time to fit one line on the tailored 1-page resume, preserving numbers and verbs. **No oneline / detailed split.**
- Bullets are tagged with the 9-tag vocabulary: `ai-ml`, `backend`, `frontend`, `devops`, `data-eng`, `genai`, `leadership`, `platform`, `product` (auto-generated by LLM during resume parse and on each new bullet; user can edit)
- Optional per-bullet `selection_override`: `always_include`, `never_include`, or `null` (default — AI auto-decides per JD)
- AI selects/deselects bullets per job based on tag relevance + JD signals; the override pins the result when the user wants manual control
- **Removed from earlier drafts:** `oneline`, `detailed`, `default_include`, metric fields (revenue / percentage / team_size). See `docs/design/SCREENS.md` § Section 6 for the canonical bullet editor spec.

### Typst (PDF Generation)
- Templates in `src/typst/templates/`
- Primary template: `onepage.typ` (NEU-style 1-page resume)
- Typst templates consume JSON data from the profile DB models
- Compile via `typst compile` CLI (wrapped in `typst/compiler.py`)
- Validate AI-trimmed bullet output by rendering and checking page count (the bullet's stored full text is unconstrained; the apply-time trim is what must fit)
- LaTeX compatibility is a future roadmap item — do not add LaTeX support now

### Auto-Apply
- Auto-apply is a user-configurable setting (default: off)
- When enabled, high-scoring jobs get documents generated and applications submitted automatically
- When disabled, semi-auto: docs generated, human approves before submission
- Always respect rate limits and anti-detection measures

## External Integrations

### Portfolio Website (crypticsoul.dev)
- Naavik exposes `GET /api/portfolio/cv` — returns full profile as JSON
- Naavik exposes `GET /api/portfolio/resume.pdf` — serves latest generic 1-page resume
- The portfolio's CV page (`cv.astro`) will fetch from this API at build time
- When profile is updated, optionally trigger Netlify rebuild webhook

### n8n (Legacy)
- Previous automation lives on n8n (`n8n.luminolab.net`); n8n stays as the source-of-truth until Phase 2 scrapers ship in Naavik
- n8n instance details: Project `PSPanW8dHb4G4Whx`, Folder `DiE914EDSAKJbJ0h`
- DataTable "Job Applications": `hfvivTlQThpPytkl`
- Google Sheets: `14pgCto2OAQxmb9w6ciOsReb3iQGE1V9XECU-o6E_c7M`
- RSShub (self-hosted): `rsshub.luminolab.net` — keep as job-feed source (Naavik consumes directly)

## Development Environment

**Nix-first.** All development uses the Nix flake devShell. Never install dependencies globally.

```bash
# Enter dev environment (provides python, uv, typst, postgresql, ruff, pre-commit)
nix develop

# Install Python deps (inside dev shell)
uv sync

# Run dev server
uv run fastapi dev src/main.py

# Database
uv run alembic upgrade head                   # Run migrations
uv run alembic revision --autogenerate -m ""  # Generate migration

# Quality
uv run ruff check .                           # Lint
uv run ruff format .                          # Format
uv run pytest                                 # Tests

# Typst
typst compile src/typst/templates/onepage.typ output.pdf

# Build
nix build                                     # Build Nix package
docker compose up -d                          # Docker deployment
```

## Nix Flake Structure

```
flake.nix                    # Main flake: inputs, outputs
nix/
├── devshell.nix             # Dev shell: python312, uv, typst, postgresql, ruff
├── package.nix              # Nix derivation for naavik
└── module.nix               # NixOS service module (Lumino-compatible)
```

### NixOS Module Pattern (Lumino-compatible)

The NixOS module in `nix/module.nix` follows the patterns from `~/lumino/services/`:
- Config from `settings.servicesConfig.apps.tools.naavik`
- `lib.mkIf enable { ... }` guard
- Systemd service with hardening (ProtectHome, CapabilityBoundingSet, etc.)
- SOPS secrets via `sops.secrets."naavik_env"` for API keys
- Traefik dynamic routing: `Host(\`${domain}\`)`
- PostgreSQL as dependency
- `services` group (GID 888) for shared storage
- Data directory via `systemd.tmpfiles.rules`

## Environment Variables

```bash
# All vars optional — config.py defaults are sane. Override only what differs.
DATABASE_URL=postgresql+asyncpg://naavik:password@localhost:5432/naavik
ANTHROPIC_API_KEY=               # For Claude
OPENAI_API_KEY=                  # For GPT models
OLLAMA_BASE_URL=http://localhost:11434  # For local models
DISCORD_WEBHOOK_URL=             # Job notifications
TELEGRAM_BOT_TOKEN=              # Optional
PORTFOLIO_WEBHOOK_URL=           # Netlify rebuild trigger (optional)
SECRET_KEY=                      # JWT signing key
DATA_DIR=.naavik                 # State root (PDFs, secrets.enc, snapshots, logs)
```

## Profile Data — Key Facts

Owner's current profile (for seed data / testing):
- **Name**: Shyam Padia
- **Current Role**: Senior Software Engineer at Intuit (Personalization/Marketing Tech)
- **Visa**: H1B with i-140 pending — REQUIRES SPONSORSHIP
- **Scoring Rule**: Score 0 for jobs requiring US citizenship, Green Card, or no sponsorship
- **Experience**: 8+ years (5.5+ at Intuit US)
- **Education**: MS CS Northeastern, BE CE Mumbai
- **Portfolio**: crypticsoul.dev
- **Resume style**: NEU template (Helvetica, 0.3in margins, compact 1-page)
