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
- Every bullet point has a **detailed** version (for full CV) and a **oneline** version (for 1-page resume)
- Tag-based system for intelligent bullet selection per job type

### Resume Generation

- Generates tailored 1-page resumes using [Typst](https://typst.app/) (blazing fast PDF compilation)
- AI analyzes job descriptions and selects the most relevant bullets from your profile
- Validates that every bullet fits on exactly one line — no overflow
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

- Status pipeline: Found → Scored → Approved → Docs Generated → Applied → Interviewing → Offer/Rejected
- Manual application logger for jobs applied outside Naavik
- Discord and Telegram notifications
- Analytics dashboard (response rates, interview conversion, by company/role)

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
| Auth           | JWT + Google OAuth                                 |
| Deployment     | Docker Compose                                     |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- An API key for at least one LLM provider (Anthropic, OpenAI) OR a running Ollama instance

### Deploy

```bash
git clone https://github.com/crizzy9/naavik.git
cd naavik

# Configure environment
cp .env.example .env
# Edit .env with your API keys and settings

# Start services
docker compose up -d

# Run migrations
docker compose exec naavik alembic upgrade head

# Open in browser
open http://localhost:8000
```

### Development Setup

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# Start PostgreSQL (via Docker)
docker compose up -d db

# Run migrations
uv run alembic upgrade head

# Start dev server
uv run fastapi dev src/main.py
```

## Configuration

Naavik is configured via environment variables or `.env` file:

```bash
# Required
DATABASE_URL=postgresql+asyncpg://naavik:password@localhost:5432/naavik
SECRET_KEY=your-secret-key

# LLM Providers (at least one required)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
OLLAMA_BASE_URL=http://localhost:11434

# Optional
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
TELEGRAM_BOT_TOKEN=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
PORTFOLIO_WEBHOOK_URL=...   # Netlify/Vercel rebuild trigger
```

## Project Structure

```
naavik/
├── src/
│   ├── main.py              # FastAPI entrypoint
│   ├── config.py            # Settings
│   ├── api/                 # REST API routes
│   ├── ui/                  # HTMX views (Jinja2 templates)
│   ├── models/              # SQLModel DB models
│   ├── services/            # Business logic
│   ├── llm/                 # LLM provider abstraction
│   ├── scraper/             # Site-specific scrapers
│   ├── typst/               # Templates + PDF compilation
│   ├── scheduler/           # Periodic job definitions
│   └── db/                  # Session management
├── migrations/              # Alembic DB migrations
├── tests/                   # Test suite
├── legacy/                  # n8n workflow exports (reference)
├── docker-compose.yml
├── pyproject.toml
└── Dockerfile
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full development plan.

**Current phase:** Phase 0 — Foundation & Profile System

## Contributing

Contributions welcome! Please read the roadmap first to understand the current priorities.

This project uses:

- `uv` for dependency management
- `ruff` for linting and formatting
- `pytest` for testing

## License

AGPL-3.0 — See [LICENSE](LICENSE) for details.

If you modify Naavik and deploy it as a service, you must open-source your modifications.
