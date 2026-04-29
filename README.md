# Naavik

**Your intelligent career navigator.** An open-source, self-hosted platform that automates your entire job search — from profile to offer.

> _Naavik_ (Hindi: नाविक) means "navigator" or "helmsman" — the one who steers the ship.

---

## What is Naavik?

Naavik is a self-hosted career automation platform that handles the full job search lifecycle:

- **Profile Intake** — Upload your resume, AI extracts your profile, you refine it
- **Job Discovery** — Automated scraping from LinkedIn, Workday, Greenhouse, Lever, and more
- **Intelligent Matching** — AI scores every job against your profile with explainable reasoning
- **Resume Tailoring** — Generates a tailored 1-page resume for each job, selecting the most relevant bullets from your experience
- **Cover Letter Generation** — AI-powered personalized cover letters
- **Application Tracking** — Full pipeline from discovery to offer
- **Portfolio Integration** — Keeps your portfolio website's CV page in sync automatically
- **Auto-Apply** — Optional automated applications for high-match jobs (with human approval toggle)

All running on your own infrastructure. Free forever.

## Why Naavik?

Commercial tools like Sprout ($100/mo), Teal ($29/mo), or Jobsolv ($149/mo) charge significant monthly fees and lock your data in their cloud. Naavik gives you the same capabilities — and more — on your own hardware.

|                            | Naavik                      | Commercial Tools |
| -------------------------- | --------------------------- | ---------------- |
| Cost                       | Free                        | $20-150/mo       |
| Self-hosted                | Yes                         | No               |
| Open source                | Yes (AGPL-3.0)              | No               |
| LLM choice                 | Claude, GPT, Ollama (local) | Proprietary      |
| Per-job resume tailoring   | Yes                         | Some             |
| Portfolio integration      | Yes                         | No               |
| Visa/sponsorship filtering | Yes                         | Rare             |
| Multi-user                 | Yes                         | N/A              |
| Your data                  | Yours                       | Theirs           |

## Features

### Profile Management

- Upload a PDF resume — AI extracts structured profile data automatically
- Edit experience, skills, projects, certifications in a clean UI
- Each bullet is a **single long-form field**. AI trims it to fit one line at apply time, preserving numbers and verbs — you don't maintain two versions
- Auto-tagged with a fixed 9-tag vocabulary (`ai-ml · backend · frontend · devops · data-eng · genai · leadership · platform · product`); AI selects relevant bullets per job

### Resume Generation

- Generates tailored 1-page resumes using [Typst](https://typst.app/) (blazing fast PDF compilation)
- AI analyzes job descriptions and selects the most relevant bullets from your profile, trimming each to a single line
- Multiple template support (NEU style included)

### Job Scraping & Discovery

- Multi-source scraping: LinkedIn (RSS + guest API), Workday, Greenhouse, Lever, Ashby, Indeed
- Configurable scraping schedules per source
- Smart deduplication (URL + fuzzy matching)
- Anti-detection: rate limiting, random delays

### AI-Powered Scoring

- Compatibility scoring (0-1) with detailed explanation
- Tag-based matching against your profile
- Automatic visa/sponsorship filtering
- Gap analysis: what skills you're missing for each role
- Supports Claude, GPT, and Ollama (run scoring locally with no API costs)

### Application Tracking

- Status pipeline: Applied → Recruiter Screen → Onsite / Loop → Offer → Closed (rejected/withdrawn/ghosted)
- Auto-classified from Gmail/Outlook integration; manual entries supported
- Outreach pipeline integrated (recruiter follow-ups, referral asks)
- Discord and Telegram notifications
- Analytics: response rate, onsite rate, offer rate (90-day windows)

### Portfolio Integration

- Public API endpoint serves your profile data as JSON
- Your portfolio website fetches this at build time — CV page always in sync
- Serves your latest 1-page resume PDF for download on your portfolio

## Tech Stack

| Component      | Technology                                         |
| -------------- | -------------------------------------------------- |
| Backend        | Python 3.12+ / FastAPI                             |
| Frontend       | HTMX + Jinja2 + Tailwind CSS + DaisyUI             |
| Database       | PostgreSQL + pgvector                              |
| Scraping       | Crawl4AI + Playwright                              |
| AI/LLM         | Anthropic (Claude) / OpenAI (GPT) / Ollama (local) |
| PDF Generation | Typst                                              |
| Scheduling     | APScheduler                                        |
| Auth           | JWT (forms) — OIDC for self-hosted in Phase 2+     |
| Deployment     | Docker Compose · NixOS module · Nix flake          |

## Quick Start

### Self-host with Docker Compose

```bash
git clone https://github.com/crizzy9/naavik.git
cd naavik

# Optional: provide API keys / overrides (defaults work out of the box)
cp .env.example .env

# One command — Postgres + auto-migrate + app, all wired
docker compose up -d

# Open http://localhost:8000
```

Migrations run automatically on first start. State persists in named volumes (`naavik-db-data`, `naavik-data`).

### Self-host on NixOS

Add Naavik to your flake inputs and enable the module — see `nix/module.nix`. Migrations run automatically as a systemd `ExecStartPre`. Postgres is provisioned via `services.postgresql.ensureDatabases`.

```nix
inputs.naavik.url = "github:crizzy9/naavik";

# In your host config (Lumino-compatible)
servicesConfig.apps.tools.naavik = {
  enable = true;
  subdomain = "jobs";   # → jobs.your.domain
};
```

### Development

The repo is **Nix-first**. One command boots Postgres (with pgvector), runs migrations, and starts FastAPI dev with auto-reload:

```bash
nix run .#dev
```

That's it. Per-project Postgres data lives in `./.naavik/db/` (gitignored). Ctrl-C tears down cleanly. Open http://localhost:8000.

For an interactive dev shell (uv, ruff, typst, postgresql-client on PATH):

```bash
nix develop          # or set up direnv to load automatically
```

`direnv` users: an `.envrc` is included; `direnv allow` once and the shell loads on `cd`.

## Configuration

All env vars are **optional**. `src/config.py` provides working defaults; override only what differs.

```bash
# Database (Compose / NixOS provision their own; only override if connecting elsewhere)
DATABASE_URL=postgresql+asyncpg://naavik:password@localhost:5432/naavik

# Override in production!
SECRET_KEY=<long-random-string>

# LLM providers (at least one for AI features)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
OLLAMA_BASE_URL=http://localhost:11434

# Optional integrations
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
TELEGRAM_BOT_TOKEN=...
PORTFOLIO_WEBHOOK_URL=...    # Netlify/Vercel rebuild trigger

# Data dir (mirrors production /app/.naavik in Docker, ~/.naavik on NixOS)
DATA_DIR=.naavik
```

Auth is form-based (email + password) in v1. OIDC support for self-hosted (Authentik / Keycloak / Okta) is on the Phase 2+ roadmap.

## Project Structure

```
naavik/
├── flake.nix                # Nix-first: devShell + package + NixOS module + `nix run .#dev`
├── nix/
│   ├── devshell.nix         # `nix develop` — interactive shell
│   ├── package.nix          # Nix package; bundles migrations + naavik-migrate wrapper
│   └── module.nix           # NixOS service module (auto-migrate ExecStartPre)
├── src/
│   ├── main.py              # FastAPI entrypoint
│   ├── config.py            # Settings (pydantic-settings)
│   ├── api/                 # REST API routes (/api/v1/)
│   ├── ui/                  # HTMX views (Jinja2 templates + components/)
│   ├── models/              # SQLModel DB models
│   ├── services/            # Business logic
│   ├── llm/                 # LLM provider abstraction (anthropic / openai / ollama)
│   ├── scraper/             # Site-specific scrapers
│   ├── typst/               # Templates + PDF compilation
│   ├── scheduler/           # APScheduler job definitions
│   └── db/                  # Session management
├── docs/design/             # SCREENS.md · WORKFLOW.md · HANDOFF_PROMPT.md · mockups/
├── migrations/              # Alembic DB migrations
├── tests/                   # Test suite
├── docker-compose.yml       # Self-host stack (db + migrate + app)
├── Dockerfile               # Multi-stage: uv builder + slim runtime
├── DESIGN.md                # Visual contract (tokens, components, voice)
├── AGENTS.md                # Canonical agent guide
├── ROADMAP.md               # Phase plan + progress
└── pyproject.toml
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full development plan.

**Current phase:** Phase 1 — Profile System & Resume Generation (Phase 0 foundation complete; MVP screens designed and queued for Claude Design handoff)

## Contributing

Contributions welcome! Please read the roadmap first to understand the current priorities.

This project uses:

- `uv` for dependency management
- `ruff` for linting and formatting
- `pytest` for testing

## License

AGPL-3.0 — See [LICENSE](LICENSE) for details.

If you modify Naavik and deploy it as a service, you must open-source your modifications.
