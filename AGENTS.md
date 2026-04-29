# Naavik — Agent Guide

> **This is the canonical reference for AI agents working on Naavik.**
> **Last updated:** 2026-04-25
> **Always read this before starting work.**

---

## Quick Start

```
1. Read this file (AGENTS.md)
2. Read ROADMAP.md — understand current phase and what's already done
3. Read DESIGN.md — if you're doing any UI work (root-level design system reference)
4. Read docs/design/WORKFLOW.md — for the full design → implementation pipeline
5. Start work. Update ROADMAP.md as you go.
```

---

## Project

**Naavik** (Hindi: नाविक, "Navigator") is an open-source career automation platform that handles the full job search lifecycle: profile intake, job discovery, AI-powered matching and scoring, resume/cover letter tailoring, application tracking, and interview pipeline management.

**Self-hosted first, cloud available.** Deploy for free via Docker Compose or NixOS. A managed cloud tier ($15/month, bring-your-own AI credits or local model) exists for convenience — functionally identical, never treated as "premium."

**License:** AGPL-3.0 — all modifications must remain open source.

### Owner Profile (for seed data and design references)

- **Name:** Shyam Padia
- **Current Role:** Senior Software Engineer at Intuit (Personalization/Marketing Tech)
- **Visa:** H1B with i-140 pending — REQUIRES SPONSORSHIP
- **Scoring Rule:** Score 0 for jobs requiring US citizenship, Green Card, or no sponsorship
- **Experience:** 8+ years (5.5+ at Intuit US)
- **Education:** MS CS Northeastern, BE CE Mumbai
- **Portfolio:** crypticsoul.dev
- **Resume style:** NEU template (Helvetica, 0.3in margins, compact 1-page)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Backend | FastAPI + SQLModel (Pydantic + SQLAlchemy) |
| Frontend | HTMX + Jinja2 + Tailwind CSS + DaisyUI |
| Database | PostgreSQL + pgvector |
| ORM/Migrations | SQLModel + Alembic |
| Scraping | Crawl4AI (primary) + Playwright (fallback) |
| AI/LLM | Direct SDK calls — Anthropic, OpenAI, Ollama |
| PDF Generation | Typst (primary), LaTeX compatibility planned |
| Scheduling | APScheduler (PostgreSQL job store) |
| Auth | FastAPI JWT (forms — email + password) — OIDC for self-hosted (Authentik / Keycloak / Okta) is Phase 2+ |
| Notifications | Discord webhooks, Telegram bot |
| Deployment | Docker Compose + NixOS service module |
| Dev Environment | Nix flake + uv |

---

## Architecture

```
src/
├── main.py              ← FastAPI app entrypoint
├── config.py            ← pydantic-settings based config
├── api/                 ← REST API routes
├── ui/                  ← HTMX views (Jinja2 templates + partials)
│   ├── templates/
│   │   ├── base.html
│   │   ├── components/  ← Reusable Jinja partials
│   │   └── pages/       ← Composed screens (one per route)
│   └── static/
├── models/              ← SQLModel DB models + Pydantic schemas
├── services/            ← Business logic
├── llm/                 ← LLM provider abstraction
├── scraper/             ← Site-specific job scrapers
├── typst/               ← Typst templates + compilation
├── scheduler/           ← APScheduler job definitions
└── db/                  ← Session management, seeding
```

---

## Documentation Map

| Document | What it is | Read when |
|---|---|---|
| `AGENTS.md` (this file) | Canonical agent guide | Every session |
| `CLAUDE.md` | Claude Code-specific conventions | When using Claude Code |
| `ROADMAP.md` | Phase plan, task tracking, progress | Before any work |
| `DESIGN.md` | Root-level design system quick reference | Before any UI work |
| `DESIGN.md` | Root-level design system (canonical reference) | Before any UI work |
| `docs/design/SCREENS.md` | Complete screen catalog with specs | Before any UI work |
| `docs/design/CLAUDE_DESIGN_PROMPT.md` | Screen descriptions for Claude Design | When designing UI |
| `docs/design/WORKFLOW.md` | Design → implementation pipeline | When designing or implementing UI |
| `docs/design/mockups/` | Committed mockup PNGs | When implementing a screen |

---

## Key Conventions

### Code Style
- Use `ruff` for linting and formatting
- Type hints on all function signatures
- Pydantic models for all API input/output
- SQLModel for database models
- Async endpoints where I/O is involved (DB, HTTP, LLM calls)

### API Design
- REST endpoints under `/api/v1/`
- HTMX view routes under `/` (return HTML fragments)
- Portfolio public API under `/api/portfolio/` (no auth required)
- Use FastAPI dependency injection for DB sessions, auth, LLM providers

### Frontend (HTMX)
- Templates in `src/ui/templates/`
- Reusable partials in `src/ui/templates/components/`
- Page templates in `src/ui/templates/pages/`
- Use `hx-get`, `hx-post`, `hx-swap` for interactivity
- Tailwind CSS + DaisyUI for styling
- Alpine.js only if needed for complex client-side state (e.g., drag-and-drop)
- Lucide Icons exclusively — stroke width 1.5

### Database
- PostgreSQL with pgvector extension
- Alembic for migrations
- SQLModel for models
- Use `AsyncSession` for all DB operations
- Never raw SQL in route handlers — use service layer

### LLM Integration
- All LLM calls go through `llm/base.py` abstract interface
- Implementations: `llm/anthropic.py`, `llm/openai.py`, `llm/ollama.py`
- User selects provider in settings — stored per-user in DB
- Use Pydantic models for structured output
- Prompt templates live in `llm/prompts/` as Python modules (not string files)

### Resume/CV Data Model
- Profile data lives in PostgreSQL, NOT in YAML/JSON files
- Each experience bullet is a single field — the **long, full version**. AI trims it at apply time to fit one line on the tailored 1-page resume, preserving numbers and verbs. **No oneline / detailed split.**
- Bullets are tagged with the 9-tag vocabulary: `ai-ml`, `backend`, `frontend`, `devops`, `data-eng`, `genai`, `leadership`, `platform`, `product` (auto-generated by LLM during resume parse and on each new bullet; user can edit)
- Optional per-bullet `selection_override`: `always_include`, `never_include`, or `null` (default — AI auto-decides per JD)
- AI selects/deselects bullets per job based on tag relevance + JD signals; the override pins the result when the user wants manual control
- **Removed from earlier drafts:** `oneline`, `detailed`, `default_include`, metric fields (revenue / percentage / team_size). See `docs/design/SCREENS.md` § Section 6 for the canonical bullet editor spec.

---

## Development Environment

**Nix-first.** One command boots everything; the interactive shell is opt-in.

```bash
# One-command dev orchestrator: Postgres (with pgvector) + alembic + FastAPI dev,
# all multiplexed in one terminal. Per-project state at ./.naavik/db (gitignored).
# Ctrl-C tears down cleanly.
nix run .#dev

# Interactive dev shell (uv, ruff, typst, postgresql-client on PATH)
nix develop          # or set up direnv to load on cd

# Inside `nix develop`:
uv sync                                          # install deps from uv.lock
uv run fastapi dev src/main.py                   # dev server (without orchestrator)
uv run alembic upgrade head                      # migrations
uv run alembic revision --autogenerate -m "msg"  # generate migration
uv run ruff check .                              # lint
uv run ruff format .                             # format
uv run pytest                                    # tests

# Build the Nix package (produces result/bin/naavik + naavik-migrate)
nix build
```

**Dev DB:** runs on `127.0.0.1:5433` (the dev orchestrator avoids 5432 to dodge any system Postgres). The default `DATABASE_URL` is overridden by the orchestrator to match. Run `rm -rf .naavik/` to wipe and reset.

---

## Environment Variables

```bash
# All vars optional — config.py provides working defaults. Override only what differs.
DATABASE_URL=postgresql+asyncpg://naavik:password@localhost:5432/naavik
SECRET_KEY=change-me-in-production
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434
DISCORD_WEBHOOK_URL=
TELEGRAM_BOT_TOKEN=
PORTFOLIO_WEBHOOK_URL=
DATA_DIR=.naavik
```

---

## Roadmap Maintenance Rules

`ROADMAP.md` is the **single source of truth** for project progress. It must always be kept in sync with reality:

1. **Before starting work**: Read the relevant phase in `ROADMAP.md` to understand scope and priorities
2. **When starting a task**: Mark it `[~]` (in progress) in the task table
3. **When completing a task**: Mark it `[x]` and add a brief deliverable note in the same row
4. **When completing a phase**: Update the phase `Status:` header to `✅ Complete (YYYY-MM-DD)` and add a verification log
5. **When scope changes mid-phase**: Edit the table directly — add new rows for new tasks, remove rows for cancelled work
6. **When making architectural decisions**: Update the relevant section (Tech Stack, Key Design Decisions, Architecture diagram)
7. **Always bump** the "Last updated: YYYY-MM-DD" date at the top when making meaningful edits

Never let the roadmap drift from the actual state of the codebase. If you discover a discrepancy, fix the roadmap first, then continue work.

---

## Design Workflow (UI Work)

See `docs/design/WORKFLOW.md` for the full pipeline. Summary:

**Phase A — Design System (Claude Design, one-time):**
1. Point Claude Design's **"Set up design system"** at the GitHub repo (or upload `DESIGN.md`)
2. Claude extracts tokens, components, patterns
3. Validate with test prompts
4. **Publish** the design system

**Phase B — Screens (Claude Design, per batch):**
5. Create **Prototype** project (auto-inherits published design system)
6. Paste `docs/design/CLAUDE_DESIGN_PROMPT.md` screen descriptions
7. Iterate and export mockups to `docs/design/mockups/`

**Phase C — Implementation (Claude Code):**
8. Read mockups + `DESIGN.md`
9. Build component library → `src/ui/templates/components/`
10. Implement pages → `src/ui/templates/pages/`

**Critical rule:** Never implement a screen without a mockup. Never build a component without checking if it already exists.

**Design principle:** The UI should feel like a developer tool you self-host, not a SaaS product you're renting. Dark mode, data-dense, no upsell pressure. The cloud tier ($15/mo, bring-your-own AI credits) is mentioned in Settings as an option, never as a premium upsell.

---

## External Integrations

### Portfolio Website (crypticsoul.dev)
- `GET /api/portfolio/cv` — full profile as JSON
- `GET /api/portfolio/resume.pdf` — latest generic 1-page resume
- CV page fetches at build time; profile updates trigger Netlify rebuild webhook

### n8n (Legacy)
- Previous automation lived on n8n (`n8n.luminolab.net`); the n8n instance still runs as the source-of-truth until Phase 2 scrapers ship
- DataTable "Job Applications": `hfvivTlQThpPytkl`
- RSShub: `rsshub.luminolab.net` (kept as a job-feed source — Naavik consumes it directly)

---

## Agent-Specific Notes

### Claude Code
- Reads `CLAUDE.md` for additional conventions specific to Claude
- Uses Playwright for visual QA when implementing UI
- Can run `ruff check` and `uv run pytest` for validation

### OpenCode / Other Agents
- This file (`AGENTS.md`) is your canonical guide
- If something conflicts between AGENTS.md and another file, AGENTS.md wins
- When in doubt, check `ROADMAP.md` for current priorities

### Design Agents
- The visual contract is `DESIGN.md`
- When generating mockups, use realistic sample data from the Owner Profile section above
- Dark mode is primary; light mode is Phase 6
- Export mockups at 1440×900 (desktop) and 375×812 (mobile)
- Commit mockups to `docs/design/mockups/` with naming: `{number}-{slug}-{desktop|mobile}.png`

---

## Decision Log

| Date | Decision | Context |
|---|---|---|
| 2026-04-25 | UI Screens & Design workflow formalized | Added DESIGN.md, SCREENS.md, WORKFLOW.md, CLAUDE_DESIGN_PROMPT.md |
| 2026-04-25 | Phase 0 Complete | Foundation infrastructure shipped |
| 2026-04-25 | Dark mode primary | Light mode deferred to Phase 6 |
| 2026-04-25 | Lucide Icons exclusively | No mixing icon sets |
| 2026-04-25 | Inter + JetBrains Mono typography | Paired for readability and data density |
| 2026-04-25 | Indigo/cyan brand palette | AI sophistication + navigator water theme |

---

## Contact

- Repo: https://github.com/crizzy9/naavik
- Issues: Use GitHub issues for bugs and feature requests
- Design questions: Check `DESIGN.md` first
- Architecture questions: Check this file and `ROADMAP.md`
