# Naavik

**Your intelligent career navigator.** An open-source, self-hosted platform that automates your entire job search — from profile to offer.

> _Naavik_ (Hindi: नाविक) means "navigator" or "helmsman" — the one who steers the ship.

---

## What is Naavik?

Naavik is an open-source career automation platform that handles the full job search lifecycle:

- **Profile Intake** — Upload your resume, AI extracts your profile, you refine it
- **Job Discovery** — Automated scraping from LinkedIn, Workday, Greenhouse, Lever, and more
- **Intelligent Matching** — AI scores every job against your profile with explainable reasoning
- **Resume Tailoring** — Generates a tailored 1-page resume for each job, selecting the most relevant bullets from your experience
- **Cover Letter Generation** — AI-powered personalized cover letters
- **Application Tracking** — Full pipeline from discovery to offer
- **Portfolio Integration** — Keeps your portfolio website's CV page in sync automatically
- **Auto-Apply** — Optional automated applications for high-match jobs (with human approval toggle)

### Self-hosted first, cloud available

The default path is self-hosted — any developer can deploy Naavik for free via Docker Compose or NixOS. Your data stays on your infrastructure. A managed cloud tier ($15/month, bring-your-own AI credits or local model) exists for those who prefer not to self-host, but it is functionally identical — never treated as "premium."

This positioning shapes the product: dark-mode developer aesthetic, no SaaS bloat, no upsell pressure, data-dense tool feel.

## Why Naavik?

No commercial platform is self-hostable. Naavik fills a real gap — and even open-source alternatives don't offer the full stack.

| What exists | Gap Naavik fills |
|---|---|
| **Sprout** ($20-100/mo) — closest to our vision. Swipe-to-apply, per-job resume tailoring, mobile-first | Not self-hosted, not open source, no visa filtering, no portfolio integration, no LLM choice, no outreach |
| **Teal** ($29/mo) — best job tracker + resume analyzer | No auto-apply, no generation, proprietary, no outreach |
| **Jobsolv** ($79-149/mo) — per-job tailoring + auto-apply via credits | Expensive, niche ($100K+ remote only), proprietary, no outreach |
| **LoopCV** (EUR 10-30/mo) — set-and-forget automation | No resume tailoring, generic form-filling, no outreach |
| **Sonara** ($6-24/mo) — background auto-apply | No resume tailoring, submits generic resume, no outreach |
| **AIHawk** (OSS, 29.7K stars) — LinkedIn auto-apply bot | Archived, LinkedIn-only, no profile system, no email monitoring, no outreach tracking |
| **JobSync** (OSS, 528 stars) — self-hosted tracker | No scraping, no auto-apply, no resume generation, no outreach |
| **JobNavigator** (OSS, new) — multi-source scraping + scoring | No cover letter gen, no auto-apply, no email monitoring, no outreach |

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

Four deployment paths — the codebase is identical across all of them. **Full deployment reference:** `docs/DEPLOYMENT.md`.

| Path | When | Cost | Setup |
|---|---|---|---|
| **NixOS module** (`nix/module.nix`) | Homelab / Lumino-pattern hosts | Free | ~15 min — see `docs/DEPLOYMENT.md` § 1 |
| **Docker Compose** | Any Linux / macOS host | Free | ~5 min — see below |
| **Managed cloud** at jobs.crypticsoul.dev | Don't want to self-host | $15/mo | ~2 min — bring your own LLM key |
| **Bare-metal dev** (`nix run .#dev`) | Local development | Free | ~3 min — see below |

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

The repo is **Nix-first**. One command boots Postgres (with pgvector), runs migrations, seeds the canonical fixture set, and starts FastAPI dev with auto-reload:

```bash
nix run .#dev
```

That's it. Per-project Postgres data lives in `./.naavik/db/` (gitignored). Ctrl-C tears down cleanly. Open <http://localhost:8000>.

For an interactive dev shell (uv, ruff, typst, postgresql-client on PATH):

```bash
nix develop          # or set up direnv to load automatically
```

`direnv` users: an `.envrc` is included; `direnv allow` once and the shell loads on `cd`.

#### First-time setup (live DB)

`nix run .#dev` is the happy path — orchestrator handles Postgres, migrations, seeding, and FastAPI in one terminal. On the **first** run the orchestrator's `seed` step prints a dev credential to stdout:

```
[seed] dev user: shyam.padia930@gmail.com
[seed] dev password: K7nQ2pXa4VtRm9zL  (set NAAVIK_DEV_PASSWORD env to override on next reseed)
```

Plan 10c (2026-05-12): the credential ALSO lands on disk at `~/.naavik/dev-credentials` (mode 0600, owner-readable only) AND is re-echoed by the `[app]` lifespan ~750 ms after `Application startup complete.`, so it's still visible at the bottom of the orchestrator's scrollback if the `[seed]` line interleaved past your eyes. If you missed it either way, read the file back:

```bash
cat ~/.naavik/dev-credentials                      # email + password, two lines
cat ~/.naavik/dev-credentials && rm ~/.naavik/dev-credentials  # shred-after-read
```

The file is only created when (a) `NAAVIK_DEV_PASSWORD` is unset (so we generated a fresh value), (b) `NAAVIK_DEBUG` is truthy (the orchestrator sets it; production stacks don't), and (c) the seeded `Settings.deployment_mode` is `SELF_HOSTED` (cloud-tier installs never persist plaintext creds). Production self-hosters with `NAAVIK_DEBUG` unset never see this file.

To pin the credential up-front so future reseeds don't surprise you, export the env var **before** the orchestrator boots:

```bash
export NAAVIK_DEV_PASSWORD='your-stable-password'
nix run .#dev
```

With `NAAVIK_DEV_PASSWORD` set, the `dev-credentials` file is NOT written — operator-supplied creds are the operator's to track.

Then:

1. Visit <http://localhost:8000/login>, sign in with the seeded email + password — JWT cookie is set, you land on Overview.
2. Set `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY` / `OLLAMA_BASE_URL`) in your `.env` file (`chmod 0600 .env`), restart the server.
3. Visit `/settings/llm-provider`, confirm the green env-presence indicator next to your chosen provider, pick it as Active, hit **Save**. Test the connection. Cost cards begin populating once real generations run.
4. Edit your profile via `/profile/edit`. Per-field autosave persists changes to Postgres immediately — verify with `psql -h 127.0.0.1 -p 5433 -U naavik -d naavik -c "SELECT headline FROM profile WHERE user_id=1"`.

#### Signup (multi-user / fresh-install)

Plan 10b adds a real `POST /api/v1/auth/signup` so a self-hoster on a fresh DB (no seed) can bootstrap an account from the UI:

1. On a fresh DB, hit `/login`, click **Create account**, enter your email + password (≥ 8 characters).
2. The first user lands as `is_admin=True`. Their default Settings has `allow_multiple_users=False`, which gates subsequent signups.
3. Once one user exists, additional `POST /api/v1/auth/signup` returns **403** unless an admin flips `Settings.allow_multiple_users=True` (multi-user proper is Phase 2+).

Same brute-force rate limit as `/login` (5 attempts / 15 min / IP).

### Manual local development setup

The long-form path: Postgres + migrations + FastAPI dev with no Nix orchestrator and no Docker. Use this when you want fine-grained control over each step, or when `nix run .#dev` errors out and you need to bisect what failed.

> **As of plan 26 (0.2.0.01, 2026-05-19)**, the backend substrate is live (20+ SQLModel entities, four Alembic migrations, bcrypt+JWT auth + signup endpoint, env-loaded secrets via `.env` + pydantic-settings, LLM provider abstraction with form-driven Settings UI, Typst document generator + ATS adapters + APScheduler crons). Steps **4–6** below are required for any DB-backed route. Steps **1–3** still work for the static / template-only routes. (The AES-256-GCM vault was deleted in plan 26 — secrets now live in env.)

**Prerequisites:**

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) — install via `curl -LsSf https://astral.sh/uv/install.sh | sh`
- (Optional, plan 10+) PostgreSQL 16+ with the [pgvector](https://github.com/pgvector/pgvector) extension
- Run all commands from the repo root (`cd /path/to/naavik`). Jinja2 resolves `src/ui/templates` relative to the process cwd, so launching from elsewhere will 500.

**1 · Install Python deps**

```bash
uv sync
```

This reads `uv.lock` and creates `.venv/` with Python 3.12 and every pinned dep.

**2 · Run the dev server**

```bash
uv run fastapi dev
```

Open <http://localhost:8000>. Auto-reload is on — edits to `src/ui/templates/**/*.html`, `src/ui/static/**`, and `src/**/*.py` reload automatically. (The repo-root `app.py` is a two-line re-export of `src/main:app` so `fastapi dev` auto-discovers the app object — see plan 10a / PC.2.)

To enable `/_design/components` (the component fixture page):

```bash
# Plan 10 § B Wave 4: gate is now persisted Settings.debug. The legacy env-var
# fallback below still works for the no-DB / static path.
NAAVIK_DEBUG=1 uv run fastapi dev
```

With the DB live, set `Settings.debug = True` for `user_id=1` instead — the env var is the legacy path.

**3 · (Optional) Lint, format, test**

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run pytest tests/ -v
```

---

Steps **4–6** are needed only once **plan 10 (Wave 4)** lands DB-backed handlers. Skip them on plan 08/09.

**4 · Start a local Postgres with pgvector**

Easiest: a one-shot Docker container (matches what `docker compose up` provisions):

```bash
docker run -d --name naavik-pg \
  -e POSTGRES_USER=naavik \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=naavik \
  -p 5432:5432 \
  pgvector/pgvector:pg17
psql -U naavik -d naavik -h localhost -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Or use a system Postgres — create the role, the database, and the extension:

```bash
sudo -u postgres createuser -s naavik
sudo -u postgres psql -c "ALTER USER naavik WITH PASSWORD 'password';"
sudo -u postgres createdb -O naavik naavik
psql -U naavik -d naavik -h localhost -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

To wipe and start over: `docker rm -f naavik-pg` (Docker path), or `sudo -u postgres dropdb naavik && sudo -u postgres dropuser naavik` (system Postgres path).

**5 · Set `DATABASE_URL`**

```bash
export DATABASE_URL="postgresql+asyncpg://naavik:password@localhost:5432/naavik"
```

`config.py`'s default already points here, so you only need to export when connecting somewhere else. Alternatively, copy `.env.example` → `.env` and edit — `pydantic-settings` picks it up automatically.

**6 · Run migrations + seed**

```bash
uv run alembic upgrade head     # creates all tables + pgvector extension
uv run python -m db.seed         # populates the seeded fixture set (372 rows; idempotent)
```

`db.seed` reads `src/db/sample_data.py` and INSERTs with `ON CONFLICT (id) DO NOTHING`, then bumps each table's autoincrement sequence past the seeded max so subsequent inserts don't collide. Safe to re-run.

The seed prints the dev-user credential — capture it on first run (or pin it via `NAAVIK_DEV_PASSWORD`). On re-runs against an existing DB, the credential stays unchanged and the seed prints a hint about how to reset.

**7 · Configure secrets via `.env`**

Plan 26 (0.2.0.01) replaced the encrypted vault with standard env-loading. Copy `.env.example` to `.env`, fill in values, and `chmod 0600 .env`:

```bash
cp .env.example .env
chmod 0600 .env
# Edit .env: set SECRET_KEY (>= 32 bytes), ANTHROPIC_API_KEY (or OPENAI_API_KEY / OLLAMA_BASE_URL),
# DISCORD_WEBHOOK_URL / TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID / PORTFOLIO_WEBHOOK_URL as needed.
```

Filesystem permissions on `.env` (`chmod 0600`) are the operative defense; the Settings UI surfaces presence indicators (green ✓ / gray dash) without exposing values.

After model changes, generate a new revision:

```bash
uv run alembic revision --autogenerate -m "describe the change"
```

Then re-launch step 2 with `DATABASE_URL` exported.

---

If this is too granular, prefer `nix run .#dev` (above) — it does steps 1, 4, and 6 for you in one command, and tears down cleanly on Ctrl-C.

## Configuration

All env vars are **optional**. `src/config.py` provides working defaults; override only what differs.

```bash
# Database (Compose / NixOS provision their own; only override if connecting elsewhere)
DATABASE_URL=postgresql+asyncpg://naavik:password@localhost:5432/naavik

# Override in production! Must be >= 32 bytes — JWT (HS256) signs cookies
# with this. PyJWT warns on shorter keys. Plan 26 (0.2.0.01) removed the
# AES-256-GCM vault that previously also derived from SECRET_KEY; rotating
# SECRET_KEY now just invalidates active sessions.
SECRET_KEY=<long-random-string-32-bytes-or-more>

# LLM providers (at least one for AI features). Plan 26 (0.2.0.01): these
# are now env-only. Settings UI shows configured-via-env indicators (no
# values rendered). Edit .env + restart to rotate.
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
OLLAMA_BASE_URL=http://localhost:11434

# Optional integrations — env-only post-vault.
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
PORTFOLIO_WEBHOOK_URL=...    # Netlify/Vercel rebuild trigger

# Data dir (mirrors production /app/.naavik in Docker, ~/.naavik on NixOS)
# Holds:
# data/documents/<app_id>/{resume,cover-letter}.pdf — per-application bundle PDFs (Wave 6)
# data/documents/portfolio/resume.pdf — cached generic resume served by /api/portfolio/resume.pdf
# data/snapshots/snapshot-YYYY-MM-DD.marker — daily DB snapshot markers (Phase 6 will replace)
# dev-credentials — plaintext dev login (mode 0600, debug + SELF_HOSTED + generated-password only — plan 10c)
# (~/.naavik/secrets.enc, secrets.enc.lock, secrets.enc.bak.*, logs/vault-audit.log
#  were deleted in plan 26 / 0.2.0.01; if upgrading from 0.1.x, see § Upgrading from 0.1.x.)
DATA_DIR=.naavik

# Scraper config (plan 33 / 0.2.0.07). Per-source company slugs as CSV.
# Cron skips a source silently when its list is unset.
GREENHOUSE_COMPANIES=anthropic,scale,databricks
LEVER_COMPANIES=netflix,figma
ASHBY_COMPANIES=ramp,vercel
WORKDAY_COMPANIES=salesforce/External,adobe/Adobe_Careers
SCRAPER_RSSHUB_URL=                        # optional LinkedIn RSShub fallback base URL
```

### Scraper sources (plan 33 / 0.2.0.07, plan 35 / 0.2.0.10, plan 38 / 0.2.0.13, plan 49 / 0.2.0.16)

Each scraper is configured through a mix of env vars (company watchlists, RSShub fallback URL) and per-user `Settings` rows (LinkedIn / Indeed keywords, per-source enable toggle, rate-limit overrides). Split: env vars hold deployment-wide config (the company list a Workday tenant follows is a deployment concern); the Settings row holds per-user search intent (which keywords this user wants LinkedIn searched for).

**Per-source config matrix:**

| Source | Companies (env) | Keywords (DB) | Location (DB) | Schedule (DB) | Rate limit (DB) |
|---|---|---|---|---|---|
| LinkedIn | — | `Settings.linkedin_keywords` | `Settings.linkedin_location` | `Settings.source_schedules["linkedin"]` (cron) | `Settings.scraper_rate_limits["linkedin"]` |
| Workday | `Settings.workday_companies` (per-user) | — | — | `Settings.source_schedules["workday"]` (cron) | `Settings.scraper_rate_limits["workday"]` |
| Greenhouse | `GREENHOUSE_COMPANIES` | — | — | `Settings.source_schedules["greenhouse"]` (cron) | `Settings.scraper_rate_limits["greenhouse"]` |
| Lever | `LEVER_COMPANIES` | — | — | `Settings.source_schedules["lever"]` (cron) | `Settings.scraper_rate_limits["lever"]` |
| Ashby | `ASHBY_COMPANIES` | — | — | `Settings.source_schedules["ashby"]` (cron) | `Settings.scraper_rate_limits["ashby"]` |
| Indeed | — | `Settings.indeed_keywords` | `Settings.indeed_location` | (IntervalTrigger 90 min, fixed) | `Settings.scraper_rate_limits["indeed"]` |
| LinkedIn (RSShub fallback) | — | (reuses `linkedin_keywords`) | (reuses `linkedin_location`) | (same cron as LinkedIn) | (no rate limit; RSShub server) |

**Operator workflow:**

1. **Pick which sources to enable.** All 6 default to enabled; toggle off on the Settings · Sources sub-tab in the UI for any source you don't want to scrape.
2. **For Workday:** edit the per-tenant watchlist via the Settings · Sources UI (currently surfaces existing `workday_companies` read-only; writable editor lands as a follow-up).
3. **For Greenhouse / Lever / Ashby:** set the company watchlist in `.env` (CSV, e.g. `GREENHOUSE_COMPANIES=anthropic,scale,databricks`). Cron skips a source silently when its watchlist is unset. **Restart the app** after editing `.env` — `pydantic-settings` loads env once at boot.
4. **For LinkedIn / Indeed:** set keywords + location via `PUT /api/v1/settings/sources` (writable UI editor lands as a follow-up row). Example payload:
   ```bash
   curl -b cookies.txt -H "X-CSRF-Token: $(jq -r .csrf cookies.txt)" \
        -X PUT http://localhost:8000/api/v1/settings/sources \
        -H "Content-Type: application/json" \
        -d '{"linkedin_keywords":["staff engineer"],"linkedin_location":"Remote"}'
   ```
5. **For LinkedIn RSShub fallback:** set `SCRAPER_RSSHUB_URL` in `.env` to your RSShub instance base URL (e.g. `https://rsshub.luminolab.net`). This is a fallback path used by `LinkedinRSScraper`; the primary `LinkedinScraper` does not use it.

**Verifying a source is configured:**

The Settings · Sources sub-tab in the UI (`/settings/sources`) is the canonical surface — each row shows configured/unconfigured indicator + last-scrape-run timestamp + last-run status. Anti-detection / rate limiting is documented in `docs/design/SCRAPER_BASE.md § G`. Per-source overrides live in `Settings.scraper_rate_limits` (JSONB shape: `{"linkedin": {"rpm": 0.4, "delay_lo": 3.0, "delay_hi": 7.0}, ...}`). The Sources panel surfaces the resolved value read-only; the writable editor lands at `/settings/rate-limits` per a deferred follow-up row.

### Dev / test env vars (not user-facing)

These exist for development and CI; production should leave them unset.

| Var | Purpose | Default |
|---|---|---|
| `NAAVIK_BCRYPT_COST` | bcrypt rounds for password hashing. Set to `4` in tests for ~10× speedup; production uses `12`. Out-of-range values fall back to `12`. | `12` |
| `NAAVIK_DEV_PASSWORD` | Dev-user password for the seeded `User` row. Set this **before** the first `nix run .#dev` (or `python -m db.seed`) to pin a stable credential; otherwise `db.seed` generates a 16-char alphanumeric value and prints it once. Reseeds against an existing User row never change the hash. | unset → generated |
| `NAAVIK_PERSISTENCE` | Sample-data accessor mode. `memory` (default for ad-hoc Python invocations) reads in-memory fixture lists; `db` reads from Postgres via SQLModel. **Plan 10b** flipped the orchestrator default to `db`; **plan 10c** added the same default to `nix develop` (and direnv-on-`cd`) so the interactive shell stays in parity. **Wave 4 partial swap** — only the high-traffic read accessors honor `db`; the rest fall back to memory in DB env. Removed in a follow-up cleanup once full DB-mode coverage lands. | `db` (orchestrator + `nix develop` + direnv) · `memory` (bare Python outside the dev shell) |
| `NAAVIK_LIVE_DB` | Opt-in to the live-DB-gated test suite (`tests/test_seed.py`, the DB-mode tests in `tests/test_persistence_swap.py`, the integration tests in `tests/test_stub_endpoints.py`). Set to `1` together with `DATABASE_URL` to run them. | unset |
| `NAAVIK_DEBUG` | Boot-time debug flag. Wave 4 introduced this as the legacy gate for `/_design/components` (the canonical path is now the persisted `Settings.debug` flag; the env var stays as a no-DB fallback). **Plan 10c** also wires this to `app_settings.debug`, gating the seed-time `dev-credentials` file write + the FastAPI lifespan credential echo. **Plan 17 (PC.5)** uses the same flag as the bypass for SECRET_KEY boot-time enforcement. The orchestrator (`nix run .#dev`) exports `NAAVIK_DEBUG=1` automatically; production stacks (`docker compose up`, NixOS module) leave it unset. (The generic `DEBUG` alias was dropped per PR #49 hacker review — `DEBUG=1` is shared by Flask/Django and would silently disable the PC.5 validator.) | unset (orchestrator: `1`) |

Auth is form-based (email + password) in v1. OIDC support for self-hosted (Authentik / Keycloak / Okta) is on the Phase 2+ roadmap.

## Operations

Self-hoster checklist for the things plan 10 § B introduced.

### Secrets via `.env` (plan 26 / 0.2.0.01)

Plan 26 deleted the encrypted vault. Every API key, webhook URL, and bot token is now configured via env vars consumed by pydantic-settings in `src/config.py`. The Settings UI surfaces presence indicators (configured / not set) sourced from `services/env_secrets.py`; values never appear in the response or template context.

```bash
cp .env.example .env
chmod 0600 .env       # filesystem permissions are the operative defense
# Edit .env with your values; restart the server.
```

Rotating a secret is `edit .env + restart`. No automated rotation; standard self-hosted-app pattern.

**Backup discipline:** back up `.env` alongside your `DATABASE_URL` / DB dump. `SECRET_KEY` is required to validate JWTs issued before the backup; preserve it.

### Rotating `SECRET_KEY`

Rotating `SECRET_KEY` invalidates active sessions (JWTs signed with the old key fail validation). It does NOT brick any on-disk state — the vault is gone. Steps:

```bash
# 1. Generate a new key
python -c 'import secrets; print(secrets.token_urlsafe(48))'
# 2. Edit .env to update SECRET_KEY; chmod 0600 .env
# 3. Restart
nix run .#dev    # or `docker compose up -d --force-recreate naavik`
# 4. Re-authenticate from the UI (existing cookies will be rejected with 401)
```

### Verify scrapers run (plan 35 / 0.2.0.10, plan 49 / 0.2.0.16)

After configuring `.env` + per-user keywords (§ Configuration · Scraper sources above), verify the chain end-to-end:

1. **Check the Settings · Sources sub-tab** at `/settings/sources`. Each row shows:
   - **Configured / not configured** — env-based for company-list sources (Workday / Greenhouse / Lever / Ashby); DB-based for LinkedIn / Indeed keywords.
   - **Last-scrape-run timestamp** + status chip.
   - **"Configure →" `<details>` popover** with env-var name + CSV example (for ATS sources) or current keywords + Edit-via-API hint (for LinkedIn / Indeed).
   A source row marked "Not configured" means the watchlist (Workday / Greenhouse / Lever / Ashby) or keywords (LinkedIn / Indeed) is empty — cron will skip that source silently.
2. **Trigger a one-off run** via the operator scheduler endpoint (`0.2.0.10a`):
   ```bash
   curl -b cookies.txt \
        -H "X-CSRF-Token: $(jq -r .csrf cookies.txt)" \
        -X POST \
        http://localhost:8000/api/v1/scheduler/jobs/scraping.linkedin/run
   ```
3. **Check `/discover`** for new jobs. Empty queue with sources marked "configured" + last-run `SUCCESS` means the source returned zero matching listings — try broader keywords or add more companies.
4. **Check the Sources panel** for last-run state. Status chips: `SUCCESS` (emerald), `PARTIAL` (amber — some listings failed extraction), `FAILED` (rose — top-level scrape error; the consecutive-failure counter is incrementing, Discord admin alert fires at 3), `TIMED_OUT` (rose), `running…` (indigo). The Discover queue surfaces jobs across all sources; the per-source counter lives only on the Sources panel.

### Scheduler endpoints (operator surface)

Four authenticated endpoints under `/api/v1/scheduler/` give read + control over the lifespan-registered APScheduler crons (`src/api/scheduler.py`): `GET /jobs` lists every registered job with its `next_run_time` + trigger summary + paused flag; `POST /jobs/{job_id}/run` triggers a one-off NOW run as a transient job (original cron's `next_run_time` is untouched); `POST /jobs/{job_id}/pause` and `/resume` toggle the paused state. Mutations require the `X-CSRF-Token` double-submit header (see `naavik_csrf` cookie). Returns 503 + `scheduler not started` when the scheduler hasn't booted (cold-start race / boot edge cases — operator usually sees this when DB was unreachable on startup).

### Upgrading from 0.1.x with a populated vault

If you previously used Settings UI to save an LLM API key or webhook URL, those values lived encrypted in `~/.naavik/secrets.enc`. Plan 26 deleted the vault module + CLI subcommands; there is no automated migration. Capture the scope list before upgrading:

```bash
# BEFORE upgrading (on 0.1.x):
naavik vault status      # capture your scope list / key names
# AFTER upgrading (on 0.2.0):
cp .env.example .env && chmod 0600 .env
# Edit .env with the values from the captured scope list. Then:
rm -f ~/.naavik/secrets.enc ~/.naavik/key.bin
rm -f ~/.naavik/secrets.enc.lock ~/.naavik/secrets.enc.bak.*
rm -rf ~/.naavik/logs/vault-audit.log
# Restart your deployment.
```

The app boots fine if you skip the migration — LLM calls fail with provider 401 until you set the env var. See `CHANGELOG.md` ## [0.2.0] § Operations.

### Reset the dev DB

```bash
rm -rf .naavik/db                 # nuke postgres data dir; nix run .#dev re-initializes
# or, with the orchestrator running:
uv run alembic downgrade base && uv run alembic upgrade head && uv run python -m db.seed
```

### `naavik` CLI

> **Sunset track — do not extend.** Plan 26 (0.2.0.01, 2026-05-19) deleted `naavik init` + `naavik vault <...>` along with the encrypted vault. The remaining surface is `naavik` (bare) and `naavik serve`; plan `0.2.0.02` (queued) removes those too. New operator capabilities ship as Settings UI surfaces or `.env`-based config per AGENTS.md § Key Conventions § CLI.

```bash
naavik                              # default: serve (back-compat)
naavik serve                        # explicit alias for default
naavik init                         # DEPRECATED in 0.2.0 — prints migration hint + exits 2
naavik vault status                 # DEPRECATED in 0.2.0 — prints migration hint + exits 2
naavik vault rotate-key --old=...   # DEPRECATED in 0.2.0 — prints migration hint + exits 2
```

The deprecated subcommands surface a hint pointing at `.env` config + `CHANGELOG.md ## [0.2.0]`. `naavik-alembic` (alembic's own CLI) is unaffected.

### Agent memory + learning (Phase A row A.15)

`.claude/memory/` holds decisions, discussions, lessons, knowledge entries, recurring patterns, and per-run analytics — owned by a single writer (`.claude/naavik_ops/memory.py`) mirroring the GitHub state pattern. Slash commands for daily use:

```bash
claude /memory list knowledge                    # see the captured corpus
claude /memory query decisions '.state == "active"'
claude /memory knowledge linkedin-scraping       # read a specific entry
claude /learn 10                                  # retrospective on last 10 runs
```

Manager auto-invokes `Skill: naavik-discussion-capture` at every PR_REVIEW_GATE + MILESTONE_GATE to surface deferred items the system noticed during the run. Architecture + extension guide: `docs/design/AGENT_MEMORY.md`. Daily-workflow integration: `docs/AGENT_OPS.md § 14`.

### Troubleshooting

#### `greenlet_spawn` / `libstdc++` errors under `nix run .#dev`

If you see `the greenlet library is required to use this function` or `libstdc++.so.6: cannot open shared object file` on the first DB write, your `flake.nix` is older than plan 10b. SQLAlchemy's greenlet bridge dlopens `libstdc++.so.6` and NixOS' Python venv doesn't ship it on the loader path. Pull the latest `flake.nix` (the orchestrator now exports `LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib`) — same fix `nix/devshell.nix` has had since plan 09.

#### `SECRET_KEY` rotation invalidates active sessions

Plan 26 (0.2.0.01) deleted the encrypted vault that previously tied `SECRET_KEY` to AES master-key derivation. Rotating `SECRET_KEY` now invalidates only active JWT cookies — there is no "vault locked" state to recover from. After rotation, re-authenticate from the UI. The cookie is HTTP-only; client-side state is unaffected.

#### UI shows mock-looking data after `nix run .#dev`

Plan 10b sets `NAAVIK_PERSISTENCE=db` in the orchestrator so the high-traffic page handlers read from Postgres. If you're running `uv run fastapi dev` directly (bypassing the orchestrator) and notice that profile edits don't persist, export `NAAVIK_PERSISTENCE=db` in your shell. The `memory` mode is intentional for ad-hoc Python invocations that don't have a live DB on hand.

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

## Agent System

Naavik ships with 6 specialized Claude Code subagents and 13 slash commands at `.claude/`. They deliver milestones end-to-end against a GitHub Project v2 board mirrored from `ROADMAP.md`.

**Read `docs/AGENT_OPS.md` first — it's the single operational guide** (setup, daily workflow, GitHub Mirror conventions, troubleshooting, extension). It links to the four canonical guides each agent loads on demand:

- **`ROADMAP.md`** — one-page roadmap digest
- **`docs/ARCHITECTURE.md`** — layer responsibilities + cross-cutting concerns + pattern catalog
- **`DESIGN.md`** (root, the visual contract) + **`docs/design/WORKFLOW.md`** (UI sub-process — skill routing, per-screen checklist, accessibility, common patterns)
- **`docs/RUNBOOK.md`** — devops runbook with known failure modes + diagnostic recipes + recovery procedures

### First-time setup (once per fork)

```bash
gh auth login                                # authenticate gh CLI
# Create a GitHub Project v2 with Status + Priority fields (see AGENT_OPS.md § 2.2)
.claude/naavik-ops gh init                   # cache project IDs at .claude/github-project.json
.claude/naavik-ops gh bootstrap --apply      # create Milestones + Issues from ROADMAP.md
claude /standup                              # confirm system is live
```

### Daily

```bash
claude /build "next"                         # deliver next milestone (halts at gates)
claude /plan <scope>                         # architect drafts a plan + opens GH Issue
claude /triage-bug <bug>                     # devops repros, engineer fixes
claude /review-pr <PR#>                      # engineer + hacker review
claude /standup                              # current state + drift + budget
```

Commands: `/build`, `/plan`, `/discuss`, `/triage-bug`, `/review-pr`, `/threat-model`, `/design-screen`, `/groom`, `/standup`, `/bootstrap`, `/sync-roadmap`, `/budget`, `/runs`.

- **Tracing:** `./traces/<run-id>/` per agent + `traces/watch.sh` for tmux pane view + `/runs` for history.
- **Budget:** `.claude/budget.json` caps daily token spend; manager updates `.claude/budget-ledger.json` per run; `/budget` to inspect.
- **GitHub Projects v2 helper:** `.claude/naavik_ops/gh.py` with `init`, `bootstrap`, `sync`, `create-issue`, `milestone-status`, `add-item`, `set-status`, `next-unblocked`, `runs`.
- **ROADMAP is authoritative;** the Project board is a one-way operational mirror.

See `docs/AGENT_OPS.md` for the full reference, `AGENTS.md` § Agent System for the workflow integration, `.claude/agents/` for full agent prompts.

## License

AGPL-3.0 — See [LICENSE](LICENSE) for details.

If you modify Naavik and deploy it as a service, you must open-source your modifications.
