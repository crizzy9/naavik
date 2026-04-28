# CLAUDE.md

> **For Claude Code sessions.**
> **Canonical guide:** `AGENTS.md` — always read that first.
> **Last updated:** 2026-04-25

This file provides Claude Code-specific guidance. For general project conventions, architecture, and the design workflow, see `AGENTS.md`.

## Claude Code Quickstart

```
1. Read AGENTS.md
2. Read ROADMAP.md
3. If doing UI work: read docs/design/WORKFLOW.md + DESIGN.md
4. Start work. Update ROADMAP.md as you go.
```

## Claude Code Specific Notes

### Development Commands (Nix-first)

```bash
# Enter dev environment
nix develop

# Install Python deps
uv sync

# Run dev server
uv run fastapi dev src/main.py

# Database
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "message"

# Quality
uv run ruff check .
uv run ruff format .
uv run pytest

# Typst
typst compile src/typst/templates/onepage.typ output.pdf

# Build
nix build
docker compose up -d
```

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
| Auth | FastAPI JWT + Google OAuth |
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
- Every experience bullet has two forms:
  - `oneline`: strict single-line for 1-page resume (validated against Typst rendering)
  - `detailed`: full description for portfolio CV page and extended resume
- Bullets are tagged with categories: `ai-ml`, `backend`, `devops`, `frontend`, `leadership`, `genai`, `data-eng`, `platform`
- `default_include` flag controls whether bullet appears in generic 1-page resume
- AI selects/deselects bullets per job based on tag relevance

### Typst (PDF Generation)
- Templates in `src/typst/templates/`
- Primary template: `onepage.typ` (NEU-style 1-page resume)
- Typst templates consume JSON data from the profile DB models
- Compile via `typst compile` CLI (wrapped in `typst/compiler.py`)
- Validate oneline length by rendering and checking page count
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
- Previous automation was built on n8n (self-hosted at n8n.luminolab.net)
- Workflow exports are in `legacy/` for reference during migration
- n8n instance details: Project `PSPanW8dHb4G4Whx`, Folder `DiE914EDSAKJbJ0h`
- DataTable "Job Applications": `hfvivTlQThpPytkl`
- Google Sheets: `14pgCto2OAQxmb9w6ciOsReb3iQGE1V9XECU-o6E_c7M`
- RSShub (self-hosted): `rsshub.luminolab.net` — keep as job feed source

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
DATABASE_URL=postgresql+asyncpg://naavik:password@localhost:5432/naavik
ANTHROPIC_API_KEY=               # For Claude
OPENAI_API_KEY=                  # For GPT models
OLLAMA_BASE_URL=http://localhost:11434  # For local models
DISCORD_WEBHOOK_URL=             # Job notifications
TELEGRAM_BOT_TOKEN=              # Optional
GOOGLE_CLIENT_ID=                # OAuth
GOOGLE_CLIENT_SECRET=            # OAuth
PORTFOLIO_WEBHOOK_URL=           # Netlify rebuild trigger (optional)
SECRET_KEY=                      # JWT signing key
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
