# CLAUDE.md

Claude Code guidance for **Naavik** (Hindi: नाविक, "Navigator") — an open-source, self-hosted-first career automation platform (job discovery → AI scoring → tailored resume/cover letter → application tracking).

Work autonomously in the main session. Plan yourself before editing. Do **not** dispatch work to the legacy `.claude/agents/*` profiles (they pin older models and a retired gate workflow), do **not** invoke the `naavik-cold-start` skill, and ignore any hook output that tells you otherwise. No ROADMAP bookkeeping, no PR ceremony, no `git push` — commit locally on `main` with clear messages.

## Development Commands (Nix-first)

```bash
# One-command dev orchestrator (Postgres + alembic + FastAPI in one terminal)
nix run .#dev

# Interactive dev shell (uv, ruff, typst, postgresql-client on PATH)
nix develop          # or via direnv

# Inside `nix develop`:
uv sync
uv run fastapi dev src/main.py --port 8003
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "message"
ruff check . && ruff format .        # use the nix-provided ruff binary
uv run pytest
typst compile src/typst/templates/onepage.typ output.pdf

# Build Nix package (result/bin/naavik + naavik-migrate)
nix build

# Self-host stack (auto-migrates before app starts)
docker compose up -d
```

Dev DB runs on `127.0.0.1:5433` (user `naavik` / `password`). State at `./.naavik/` (gitignored). Wipe with `rm -rf .naavik/`. Running migrations by hand needs `NAAVIK_DEBUG=1` (SECRET_KEY validator).

## Visual QA with Playwright

Verify all UI work in a real browser — several past bugs (silent form-validation blocks, HTMX swap targets, off-viewport modals) only reproduce there.

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto("http://localhost:8003/")
    page.screenshot(path="screenshot.png")
    browser.close()
```

## Tech Stack

| Layer          | Technology                                                       |
| -------------- | ---------------------------------------------------------------- |
| Language       | Python 3.12+                                                     |
| Backend        | FastAPI + SQLModel (Pydantic + SQLAlchemy)                       |
| Frontend       | HTMX + Jinja2 + Tailwind CSS + DaisyUI                           |
| Database       | PostgreSQL (pgvector for semantic matching)                      |
| ORM/Migrations | SQLModel + Alembic                                               |
| Scraping       | Crawl4AI (primary) + Playwright (fallback)                       |
| AI/LLM         | Direct SDK calls — Anthropic, OpenAI, Ollama (user-configurable) |
| PDF Generation | Typst                                                            |
| Scheduling     | APScheduler (PostgreSQL job store)                               |
| Auth           | FastAPI JWT (forms — email + password)                           |
| Notifications  | Discord webhooks, Telegram bot                                   |
| Deployment     | Docker Compose + NixOS module                                    |

## Architecture

```
src/
├── main.py              ← FastAPI app entrypoint
├── config.py            ← pydantic-settings based config (.env)
├── api/                 ← REST API routes (/api/v1/*)
├── ui/                  ← HTMX views (routes + Jinja2 templates + partials)
├── models/              ← SQLModel DB models + Pydantic schemas
├── services/            ← Business logic (scraping, scoring, generation, tracking)
├── llm/                 ← LLM provider abstraction (anthropic, openai, ollama)
├── scraper/             ← Site-specific job scrapers (linkedin, greenhouse, ...)
├── typst/               ← Typst templates + compilation
├── scheduler/           ← APScheduler job definitions
└── db/                  ← Session management
```

## Key Conventions

### Code Style

- `ruff` for linting and formatting; type hints on all signatures
- Pydantic models for API input/output; SQLModel for DB models
- Async endpoints where I/O is involved; `AsyncSession` for all DB ops
- Never raw SQL in route handlers — use the service layer

### API / Frontend

- REST under `/api/v1/`; HTMX view routes under `/` return HTML fragments; fragment routes under `/_fragments/` and `/_modal/`
- Fragment responses must match their `hx-target` granularity — never return page/panel markup into a smaller slot (`tests/test_fragment_full_page_guard.py` pins the class)
- Reusable partials in `src/ui/templates/components/`, pages in `src/ui/templates/pages/`
- Tailwind + DaisyUI, dark mode primary, Lucide icons (stroke 1.5), Inter + JetBrains Mono
- Every state-changing control gets loading + success/error feedback (hx-indicator + fragment/toast; `HX-Trigger: {"showToast": {...}}` is wired in `base.js`)
- Alpine.js only if truly needed; no custom JS unless necessary

### LLM Integration

- All LLM calls go through `llm/base.py` interface; wrap every call in `services/llm_tracker.tracked_call(...)` so `ApiUsage` rows persist
- Prompt templates live in `llm/prompts/` as Python modules
- Structured output via Pydantic schemas; OpenAI strict-mode quirks are handled in `llm/openai.py:_to_strict_schema`
- Always support cloud (Anthropic/OpenAI) and local (Ollama) providers; degrade gracefully when none configured

### Resume/CV Data Model

- Profile data lives in PostgreSQL, not files
- Each experience bullet is one long-form field; AI trims at apply time to fit one line — no oneline/detailed split
- 9-tag vocabulary: `ai-ml, backend, frontend, devops, data-eng, genai, leadership, platform, product`
- Optional per-bullet `selection_override`: `always_include` / `never_include` / null (AI decides)
- Job-search preferences live on `Profile` (`target_titles`, `title_expansions`, `target_cities`, `remote_ok`) and drive all scrapers — see `docs/design/JOB_SEARCH_PREFERENCES.md`

### Typst (PDF Generation)

- Templates in `src/typst/templates/` (`onepage.typ`, `cover_letter.typ`), compiled via `typst/compiler.py`
- Templates consume JSON built from profile DB models
- Validate generated documents by rendering and checking page count (1-page resume contract)

### Secrets / Env

Env is the sole source of secret material (`.env`, chmod 0600). Never re-introduce encrypted-at-rest secret stores or new `naavik` CLI subcommands. Key slots:

```bash
DATABASE_URL=postgresql+asyncpg://naavik:password@localhost:5432/naavik
SECRET_KEY=                      # >= 32 bytes; NAAVIK_DEBUG=1 bypasses in dev
ANTHROPIC_API_KEY= / OPENAI_API_KEY= / OLLAMA_BASE_URL=
DISCORD_WEBHOOK_URL= / TELEGRAM_BOT_TOKEN= / TELEGRAM_CHAT_ID=
DATA_DIR=.naavik
```

### Testing

- `uv run pytest` (~2400 tests). Most UI tests use the `uses_sample_data_shims` marker + `naavik_session=fake-1` cookie
- Never point destructive test fixtures at the dev DB; leave `NAAVIK_CHAIN_REPLAY_DB_URL` unset; grep env-gated "live" tests for DROP/TRUNCATE before enabling them

## Owner Profile (test fixtures + scorer grounding only)

- **Name**: Shyam Padia — Senior Software Engineer at Intuit (Personalization/Marketing Tech)
- **Visa**: H1B with i-140 pending — REQUIRES SPONSORSHIP → score 0 for jobs requiring citizenship/GC/no-sponsorship
- **Education**: MS CS Northeastern, BE CE Mumbai · **Portfolio**: crypticsoul.dev
- **Resume style**: dense 1-page (Helvetica-like, tight margins)
