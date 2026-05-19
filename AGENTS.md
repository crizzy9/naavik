# Naavik — Agent Guide

> **This is the canonical reference for AI agents working on Naavik.**
> **Last updated:** 2026-05-19 (Plan 29 / `0.2.0.06` EXECUTED — Crawl4AI scraper substrate. New `src/scraper/` layer: `types.py` (RawJob 17-field Pydantic v2 DTO w/ `extra="forbid"` + `*_hint` enum fields + ScrapeQuery), `base.py` (`ScraperBase(ABC)` matching `LLMProvider(ABC)` convention; `async def scrape(query) -> AsyncIterator[RawJob]`; class-level `rate_limit_per_minute=30` + `random_delay_seconds=(1.0, 3.0)` reserve `0.2.0.13` interface), `crawl4ai_client.py` (`Crawl4AIClient` wraps `AsyncWebCrawler` w/ `enable_stealth=True` default; `fetch_html(url)` + `stream_many(urls)`), `sites/__init__.py` (registry stub for `0.2.0.07`) + `sites/sample.py` (test fixture; NOT registered for production). New `src/services/scraper_service.py:run_scraper` orchestrates JobScrapeRun lifecycle (RUNNING → SUCCESS/PARTIAL/FAILED/TIMED_OUT) consuming plan 27's `job_service.upsert_job` + `record_scrape_run`. Deps: `crawl4ai==0.8.6` (post-litellm-hotfix exact pin) added; `playwright>=1.58.0,<1.59` PROMOTED from dev extras to base deps. 43 new tests (RawJob validation, ABC enforcement, Crawl4AIClient w/ `_FakeAsyncCrawler` mock, SampleScraper materialization, JobScrapeRun status derivation across 7 lifecycle outcomes). No new CLI / vault / env / on-disk surface. Nix flake / Docker Chromium binary install DEFERRED to `0.2.0.07` per OQ.5. Canonical ScraperBase + RawJob + Crawl4AIClient reference: `docs/design/SCRAPER_BASE.md` (graduated from plan 29). BACKEND.md § J.1 collapses `list_jobs + fetch_detail + matches` sketch to streaming `scrape()` per plan § D.5.)
> Earlier line: 2026-05-19 (Plan 27 / `0.2.0.05` EXECUTED — Job model hardening + `JobScrapeRun`. 6 new `Job` columns (`external_id` partial-unique on `(user_id, source, external_id) WHERE deleted_at IS NULL`; `remote_policy` / `seniority_level` / `posted_at_text` / `description_extracted_at` / `description_extraction_model` / `last_scrape_run_id` FK); `visa_restrictions` promoted from `str | None` to typed `VisaRestriction` enum. New `JobScrapeRun` SQLModel + table (per-scraper-invocation observability). 4 new Postgres ENUM types (`visarestriction` / `remotepolicy` / `senioritylevel` / `jobscrapestatus`); `JobSource` collapses from 2-value catch-all to 10 per-source values (LINKEDIN/WORKDAY/GREENHOUSE/LEVER/ASHBY/INDEED/COMPANY_DIRECT/RSSHUB/N8N_LEGACY/MANUAL; `AUTOMATED` deprecated). Alembic 0005 additive. New `src/services/job_service.py` (8 functions: `upsert_job` / `get_job` / `list_jobs` / `archive_job` / `restore_job` / `create_manual_job` / `count_jobs_by_source` / `record_scrape_run`). No new env / CLI / on-disk surface; sole on-disk addition is the `job_scrape_run` DB table. Canonical Job + JobScrapeRun reference: `docs/design/JOB_MODEL.md` (graduated from plan 27).)
> Earlier line: 2026-05-19 (Plan 26 / `0.2.0.01` EXECUTED — vault deprecation. `src/services/vault.py` (436 LOC AES-256-GCM + PBKDF2 + audit-log) DELETED. `src/cli/{vault,init}.py` (258 LOC) DELETED. Alembic 0004 drops 5 vault-derived `Settings` columns. Settings UI no longer accepts API-key / webhook input; env-presence indicators sourced from `services/env_secrets.py` instead. `.env.example` rewritten with 14 slot rows incl. new `TELEGRAM_CHAT_ID`. `naavik init` + `naavik vault <...>` print migration hints (exit 2). `~/.naavik/secrets.enc{,.lock,.bak.*}` + `~/.naavik/key.bin` + `~/.naavik/logs/vault-audit.log` are no longer written or read. Single survivor CLI: `naavik serve` (dies in `0.2.0.02`). 0.2.1.03 (Argon2id PBKDF2 upgrade) closed as moot.)
> Earlier line: 2026-05-19 (Plan 25 / `0.1.1` EXECUTED — legacy bash → Python rewrite + 5 mutating `task` subcommands (`insert` / `defer` / `prioritize` / `move` / `renumber`) + CHANGELOG markdown-escape hardening. `.claude/naavik-ops gh` + `memory` no longer subprocess-wrap legacy bash — native Python under `.claude/naavik_ops/{gh,memory}.py`. `scripts/gh-project.sh` + `scripts/agent-memory.sh` + `scripts/roadmap_parser.py` DELETED. Single-writer rule preserved. Design doc: `docs/design/PHASE_NUMBERING.md`.)
> Earlier line: 2026-05-17 (Plan 19 / A.15 EXECUTED — agent memory + learning system. § Agent System infrastructure table adds `.claude/memory/` + `.claude/naavik_ops/memory.py` (single-writer rule per A.15) + 4 memory-aware skills; slash commands table adds `/memory` + `/learn`. Design doc: `docs/design/AGENT_MEMORY.md`. Workflow integration: `docs/AGENT_OPS.md § 14`.)
> Earlier line: 2026-05-10 (§ Key Conventions § CLI — both the `naavik` script AND the encrypted vault are on a sunset track per ROADMAP § Phase 2 tasks 2.12 (vault → env-based secrets) and 2.11 (CLI deletion, sequenced after 2.12). Do NOT extend either; new operator features ship as Settings UI or `.env.example` slots.)
> **Always read this before starting work.**

---

## Quick Start

```
1. Read this file (AGENTS.md)
2. Read docs/PLAYBOOK.md — the strict task-classification + procedure tree the manager
   consults on EVERY user message (codified after the aa2f6a0 workflow miss; ROADMAP § Phase A row A.14).
   9 categories: STATUS / INSPECT / 3 gate responses / PRODUCT_WORK / BUG_TRIAGE / CONTRACT_CHANGE / BOOKKEEPING.
   CONTRACT_CHANGE = PR; BOOKKEEPING = direct push to main. Never mix.
3. Read ROADMAP.md — understand current phase and what's already done
4. Read DESIGN.md — if you're doing any UI work (root-level design system reference)
5. Read docs/design/WORKFLOW.md — for the full design → implementation pipeline
6. Start work. Update ROADMAP.md as you go.
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

## Documentation locations

A handful of canonical files have specific roles. Everything else is discovered by reading the relevant directory on demand — don't expect a maintained file index.

**Canonical anchors (always present, named):**

- `AGENTS.md` (this file) — agent guide + workflow
- `CLAUDE.md` — Claude Code conventions
- `ROADMAP.md` — phase plan + task tracking
- `DESIGN.md` (root) — visual contract (tokens, typography, components, voice)
- `docs/design/SCREENS.md` — screen catalog (functional contract per screen)
- `docs/design/WORKFLOW.md` — UI sub-process (mockup → component → page)
- `docs/plans/README.md` — plan-file conventions

**Directories — read on demand:**

- `docs/design/` — canonical design docs (SCREENS.md, WORKFLOW.md, plus any graduated docs like COMPONENTS.md, ROUTES.md, DATA_MODEL.md, INTERACTIONS.md, SAMPLE_DATA.md)
- `docs/design/mockups/` — visual reference (gitignored). PDF + Claude Design bundle JSX. See `docs/design/mockups/README.md` for what should be there and how to regenerate if missing.
- `docs/plans/` — active plans (numbered `NN-name.md`)
- `docs/plans/archive/` — executed plans (audit trail)
- `docs/prompts/` — active kickoff prompts (one per active implementation plan, numbered to match)
- `docs/prompts/archive/` — used prompts
- `docs/misc/` — reference material that doesn't fit elsewhere

When you need to know what's currently in any of these directories, **list them**. The state changes as plans are authored, executed, and archived; a maintained file table would drift.

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

### CLI (sunset track — do not extend)

Plan 26 (0.2.0.01, 2026-05-19) DELETED `naavik init` + `naavik vault <subcommand>` along with the encrypted vault. The remaining CLI surface is `naavik` (bare) + `naavik serve`, both running uvicorn. `0.2.0.02` (queued) deletes those too. `naavik-alembic` stays — alembic's own CLI surface.

- ROADMAP row **0.2.0.01** (legacy ID `2.12`) — vault deprecation. **EXECUTED 2026-05-19** in plan 26. `src/services/vault.py` deleted; secrets are env-loaded via `.env` consumed by `pydantic-settings` in `src/config.py`. Settings UI surfaces env-presence indicators sourced from `services/env_secrets.py`.
- ROADMAP row **0.2.0.02** (legacy ID `2.11`) — CLI sunset. Queued: `serve` is the last subcommand standing. After `0.2.0.02`, bare `naavik` becomes the uvicorn launcher; `naavik serve` goes away.

**Rule:** do **not** add new subcommands to `naavik`. Do **not** re-introduce vault-like encrypted-at-rest secret storage (`src/services/vault.py` deletion is permanent; AES-GCM / PBKDF2 / audit-log code is forbidden). New operator capability — secret rotation, dev-credential retrieval, anything that today might feel like "this should be a CLI command" — ships as a **Settings UI surface** (read-only "configured via env" indicator) or lands in `.env` per the post-vault pattern.

Why: every other self-hosted app uses env-based secrets, and filesystem permissions (`chmod 0600 .env`) are the actually-relevant defense. The vault was theater — the master key was derived from `SECRET_KEY` (the same env var that the JWT signer reads), so an attacker with `SECRET_KEY` could decrypt the vault; an attacker without `SECRET_KEY` couldn't decrypt JWTs either. Plan 26 collapsed that trust model to "trust the env" + filesystem perms.

If you find yourself wanting to add a `naavik <thing>` subcommand or any encrypted-at-rest secret store, stop and design the equivalent Settings UI flow OR add it to `.env.example`. `tests/test_no_vault_imports.py` lint guards against regressions.

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

## Workflow (canonical lifecycle for non-trivial change)

Every meaningful change — features, models, screens, refactors, doc surgery — follows the same lifecycle. The agent (Claude) authors the artifacts; the user (you) reviews, approves, and drives implementation by using the prompts.

```
ROADMAP.md       →  Plan         →  user review  →  Design doc       →  Prompt           →  Implementation  →  Document deviations  →  Archive + roadmap mark
(scope source)      docs/plans/      (approval)      docs/design/        docs/prompts/        (user runs it)      (in the plan, pre-      (agent files away)
                                                                                                                   archive)
```

### The nine steps

1. **Scope** — read `ROADMAP.md`, pick a coherent unit of work (one phase task, one feature, one refactor). Larger items get split.

2. **Plan** *(agent → `docs/plans/NN-name.md`)* — agent authors a plan with required front-matter (`Status`, `Type`, `Authored`, `Last updated`, `Depends on`) and an explicit approval checklist at the bottom. One plan per coherent unit. Conventions live in `docs/plans/README.md`.

3. **Review** *(user)* — user reads the plan, ticks the approval checklist, calls out any open questions inline. Agent revises until APPROVED.

4. **Design doc** *(agent → `docs/design/NAME.md`)* — for **design plans** (those that propose a new contract — components, routes, data model, interactions, etc.), the approved plan content graduates into a permanent design doc with a semantic name (e.g. `COMPONENTS.md`, `DATA_MODEL.md`). For **execution plans** (housekeeping, doc surgery, config), this step is skipped.

5. **Implementation prompt** *(agent → `docs/prompts/NN-name.md`)* — for plans whose execution actually writes code, agent authors a self-contained kickoff prompt. The prompt references the relevant design doc(s), the plan, any mockups, and lists concrete deliverables. This prompt is what the user pastes into a fresh Claude Code session (or runs in the current one). For plan-01-style doc-only execution, no prompt is needed — agent executes inline.

6. **Implement** *(user drives, agent or fresh agent executes)* — user uses the prompt to start implementation. Code, tests, migrations, templates, etc. land. Implementation can iterate; the design doc is the contract that survives.

7. **Document deviations** *(agent → in the plan, before archive)* — implementation never lands exactly as the plan describes. Before archiving the plan, the agent **MUST** add a `## Deviations from plan` section to `docs/plans/NN-name.md` capturing every place the shipped code diverged from the plan's spec. One bullet per deviation:
   - **What** changed (one-line)
   - **Why** (root cause / constraint that forced the change — e.g. "SQLModel 0.0.22 forward-ref resolution failed under circular FK graph")
   - **Impact** on dependent plans / phases (does this need to be backported into a future plan? Is a follow-up issue needed?)
   - **Surface** any new env var, CLI command, on-disk artifact, or operational requirement that the plan didn't anticipate but the implementation introduced. **Each of those MUST also propagate to user-facing docs** (`README.md`, `CLAUDE.md`, `docs/plans/POST_PHASE_1.md`) before archive — not "we'll do it later". Drift on operational surfaces is the source of self-hoster bugs we don't get to debug.

   This section is the contract for future-you (or future-them) — without it, plan archives become "what we hoped to ship" not "what we actually shipped", and reviewers chasing a regression have to read every commit instead of one section. Keep it terse and honest. **Plans without a Deviations section may not be archived** (use "no material deviations" if the plan really shipped exactly as spec'd, but that's rare).

8. **Archive** *(agent)* — once implementation is verified AND deviations are documented:
   - Plan → `docs/plans/archive/NN-name.md`, `Status: EXECUTED` (or `Status: GRADUATED → docs/design/NAME.md` if it produced a design doc)
   - Prompt → `docs/prompts/archive/NN-name.md`, `Status: USED`
   - Design doc stays at `docs/design/NAME.md` (canonical, permanent)

9. **Roadmap update** *(agent)* — mark the corresponding `ROADMAP.md` task(s) `[x]` with a one-line deliverable note. Bump "Last updated" if the change is meaningful. See § Roadmap Maintenance Rules below.

### Naming convention

`NN` is a two-digit ordinal shared across plan / prompt (and referenced from the design doc). The design doc itself uses a SEMANTIC name because it's permanent and gets cross-referenced widely.

| Artifact | Active path | Archived path | Naming |
|---|---|---|---|
| Plan | `docs/plans/03-component-catalog.md` | `docs/plans/archive/03-component-catalog.md` | `NN-kebab-name` |
| Design doc | `docs/design/COMPONENTS.md` | (stays canonical, never archived) | `SEMANTIC_NAME.md` |
| Prompt | `docs/prompts/03-component-catalog.md` | `docs/prompts/archive/03-component-catalog.md` | `NN-kebab-name` (matches plan) |

### When to skip parts of the lifecycle

- **Trivial typos / one-line clarifications** — just edit. No plan needed. Use a `TaskCreate` to track if it helps.
- **Bug fixes that don't change architecture** — `TaskCreate` for tracking; skip plan/prompt unless the fix is non-obvious or touches >2 files.
- **Doc realignments / config tweaks** — plan + execute inline; no design doc, no prompt.
- **Emergencies** — fix first, document the workflow cleanup after.

When unsure, default to authoring a plan. Plans are cheap to write and prevent rework.

### What goes in a prompt (`docs/prompts/NN-name.md`)

A kickoff prompt is self-contained for a fresh agent session. Required sections:

1. **Goal** — one sentence
2. **Required reading** — paths to the design doc, plan, AGENTS.md, DESIGN.md, SCREENS.md, etc. in the order they should be read
3. **Deliverables** — concrete files to write/modify with one-line descriptions
4. **Quality bar** — `uv run ruff check`, `uv run pytest`, Playwright screenshots, etc.
5. **Forbidden patterns** — copy from HANDOFF_PROMPT-style § 7 (no React/Vue, no inline styles, no non-Lucide icons, no `console.log`, etc.)
6. **Hand-back format** — what to report when done (file list, screenshot paths, follow-up notes, **deviations summary**)

The hand-back **MUST** include a deviations summary that the agent will then promote into the plan's `## Deviations from plan` section (see § Workflow step 7). Do not let the kickoff prompt's hand-back section omit deviations — that's how plans get archived as "this is what we shipped" when really it's "this is what we wished we shipped".

### Documenting deviations — what counts, what doesn't

Step 7 forces the implementer to land a `## Deviations from plan` section in `docs/plans/NN-name.md` before archive. Use this filter:

**Deviation (record it):**
- A spec field, file, or behavior the plan called for that didn't ship as written.
- An on-disk artifact, env var, CLI command, or operational invariant that exists now but wasn't in the plan.
- A test the plan promised that's now skipped, gated, or restructured.
- A library version, dependency, or runtime constraint discovered during implementation.
- A scope reduction (e.g. "Wave 4 implements 12 of 50 accessors; rest fall back to memory").
- An infrastructure decision (e.g. NullPool engine, sequence-bumping after seed) that future plans will care about.

**Not a deviation (don't clutter the section):**
- Routine commit-level cleanups (variable rename, comment fixes).
- Test fixtures added beyond the plan's count, when the plan said "≥ N".
- Lint fixes that don't change behavior.

**Anything that lands as a new operational surface (env var, CLI, on-disk path, secret-handling rule, port, schedule)** must ALSO be added to:
- `README.md` § Configuration (if user-facing) or § Development (if dev-facing)
- `CLAUDE.md` and/or `docs/plans/POST_PHASE_1.md` (whichever is the right home for the operational guidance)
- `ROADMAP.md` "Last updated" line if the deviation changes a phase deliverable

Operational drift is the leading source of self-hoster pain. The deviations section is your one-time chance to catch it before the plan archives.

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

### Single-doc-tracking principle (codified 2026-05-02)

**Project-wide task / backlog / phase tracking lives only in `ROADMAP.md`.** Plans, prompts, design docs, and operational guides reference ROADMAP but must not duplicate the same cross-plan tracking tables. Drift between two tracking surfaces is the most common source of plan/reality mismatch in this repo.

#### What "tracking" means here

The thing that's centralized in ROADMAP is the **`[ ]` / `[~]` / `[x]` task ledger that gates "is this phase done"**. That ledger has exactly one home — the per-phase tables in ROADMAP — so anyone glancing at the roadmap sees the real state of the project at a glance.

What "tracking" does **not** mean: it does not mean a plan can't have its own scope breakdown. Plans should still describe the work in whatever depth the plan needs to communicate intent.

#### What lives in `ROADMAP.md` only

- **Per-phase task ledgers** (Phase 0–6, including wave + sub-task lists) — the canonical `[ ]` / `[~]` / `[x]` checkboxes that gate phase completion.
- **Phase 1.x deferred backlog** (the post-Phase-1 deferred items table).
- **Pre-Phase-2 paper cuts** (immediate dev-experience fixes before plan 11).
- **Plan-to-phase mapping** (each phase header names its implementing plan via `**Plan:** docs/plans/NN-name.md`).
- **Phase deliverable specs** (the "Deliverable (end of Phase X)" lines).

#### What plans (`docs/plans/NN-name.md`) DO contain

Plans describe **how** to implement and gather the user's approval before code lands. A healthy plan has all of:

- **Goal + context / why** — why this work, why now, what motivates the scope.
- **Proposal** — the actual plan content. This is rich on purpose: scope items per sub-section, file-by-file edits, design sketches, code snippets, option matrices, build sequence, risk + mitigation tables, spec-impact summaries, test-plan-per-fix. **Plan-internal scope tables are fine and encouraged** — the plan is the only place this design-time detail lives.
- **Open questions** — things that need user input before approval.
- **Approval checklist** — `[ ]` boxes the user ticks to gate plan APPROVAL (one row per design decision the user must sign off on). This is plan-acceptance, not implementation-tracking.

Plan-internal scope tables, "build sequence" lists, and approval checklists are NOT cross-plan task tracking — they're plan-acceptance + plan-internal-coherence. They stay in the plan.

#### What plans DO NOT duplicate

- The phase-level `[ ]` / `[~]` / `[x]` ledger that says "is Phase 2 task 2.3 done?" — that single bit lives in ROADMAP. The plan describes 2.3 in detail; ROADMAP records its completion.
- A "Phase 1.x deferred backlog" mirror — there's exactly one of those, in ROADMAP.
- A "pre-Phase-2 paper cuts" mirror — there's exactly one of those too, in ROADMAP.

#### Operational guidance (separate from tracking)

Cross-cutting concerns, monitoring playbooks, testing playbooks, "when things go wrong" notes, success criteria — none of these are discrete trackable tasks. They live in `POST_PHASE_1.md` (or a new `docs/plans/<topic>_GUIDE.md` if a new operational topic appears).

If a supporting doc grows a backlog table or a `[ ]` / `[x]` ledger that mirrors ROADMAP, that's drift. Move the rows to ROADMAP and replace them with a one-line pointer.

#### Step-by-step: plan author / implementer responsibilities

When you author a plan:

1. Pull scope from `ROADMAP.md`'s phase header (or "Phase 1.x deferred" / "Pre-Phase-2 paper cuts" tables).
2. Write the plan with all the implementation detail it needs (scope, sub-tasks, file lists, design sketches, build sequence, risk table, approval checklist).
3. ROADMAP's phase header gets a `**Plan:** docs/plans/NN-name.md` line if it doesn't already (the canonical "this plan implements this phase / sub-task" link).

When you implement a plan:

1. Mark ROADMAP's tracking row `[~]` when starting.
2. Mark ROADMAP's tracking row `[x]` + add a one-line deliverable note when done.
3. Archive the plan + prompt per AGENTS.md § Workflow step 7.
4. Bump ROADMAP's "Last updated" line if the change is meaningful.

The plan stays rich; ROADMAP stays current.

### GitHub state — single writer rule (codified 2026-05-16; updated 2026-05-18 for A.29 dispatcher)

`ROADMAP.md` is the authoritative ledger; the GitHub Project v2 board mirrors it. To keep the mirror deterministic, **`.claude/naavik-ops gh`** (Python dispatcher; subprocess-wraps `.claude/naavik_ops/gh.py` during the A.29 transition, native Python in A.30) is the **sole writer entry point** to GitHub Issues, Milestones, Project items, and `.claude/github-issue-map.json` (the persistent `{phase → epic#, task_id → issue#, phase → milestone#}` association cache).

**Why this exists.** The GitHub search API is eventually consistent (~30s–2min indexing lag) and rate-limited. Pre-2026-05-16 the script's idempotency check (`find_issue_by_prefix`) queried that API and silently treated indexing-lag misses as "doesn't exist," producing duplicate issues (e.g. `#46` dup `#6` for `[Epic] Pre-Phase-2 paper cuts`, `#47` dup `#7` for `[PC.5]`). The map cache eliminates the race: every create writes to the map, every existence check reads it first.

**Operational rules:**

- All `gh issue create` / `gh issue close` / Project field writes go through `.claude/naavik-ops gh` subcommands (`create-issue`, `create-epic`, `set-status`, `set-priority`, `set-effort`, `add-subissue`). The dispatcher subprocess-wraps `.claude/naavik_ops/gh.py` during A.29; A.30 (0.1.1) inlines native Python. Never call `gh` or `gh api graphql` for those operations from agent prompts or scripts.
- Never hand-edit `.claude/github-issue-map.json`. It's machine-managed.
- If manual UI edits drift the map (someone renames/closes/deletes an issue in github.com), run `.claude/naavik-ops gh refresh-map` to reconcile from authoritative GitHub state. Collisions on title prefix resolve to (open, lowest-#).
- The `manager` agent is the sole entry point for delivery-loop state mutations. Other agents (architect, engineer, hacker, devops, designer) may invoke `.claude/naavik-ops gh create-issue` for plan-driven issue creation, but must not write the Project board's Status column directly — that's manager's job during step 9 (mirror) of the workflow.
- This rule supersedes the older AGENT_OPS.md § 9.5 "bootstrap created duplicates" guidance, which assumed dupes were a rename problem. They're almost always a search-API consistency problem; run `refresh-map`, close the duplicate by hand, document in the relevant plan's deviations section.
- **Post-A.29 sort key for `next-unblocked`:** release-version ASC → priority DESC (HIGH > MED > LOW > unset) → position ASC, gated by deps. Use `.claude/naavik-ops task next-unblocked <release-version>` (e.g. `0.2.0`) for the new schema; legacy `next-unblocked` (no version) sorts by Project Priority field for backward compat during A.29 transition.

**Patch-version positions are not stable identifiers.** Captured 2026-05-19 as `.claude/memory/knowledge/patch-version-position-stability.md`; enforced in code from 0.7.0.13 (plan 28). In the 4-level semver task-ID schema (`MAJOR.MINOR.PATCH[.POSITION]`), the **release-version (3-level)** is the canonical tree source. The **position (4th level)** is a sort key, not a primary key. Operational consequences:

- **Patch tasks are unprioritized + unordered by default.** HIGH/MED/LOW markers + position ASC are sort hints, not invariants.
- **Gaps in position numbering are intentional + acceptable.** Moving `0.2.0.02` out (e.g. via `naavik-ops task move 0.2.0.02 0.7.0.05`) leaves position `02` empty in `0.2.0`; remaining tasks (`0.2.0.03`, `0.2.0.04`, ...) do NOT shift to fill the gap. `naavik-ops task move` enforces this — source-section siblings are never renumbered on cross-release move.
- **Destination-section collisions reject.** Operator picks a free slot; `naavik-ops task list <dest-version>` shows occupancy.
- **Cosmetic compaction is opt-in.** Run `naavik-ops task renumber <version>` to compact gaps when you actually want renumbering — never as an automatic side-effect of `move`.
- **Within-section `defer` is different.** `naavik-ops task defer` shifts siblings by design (it's the "shove this task back N slots" operation). The non-shift rule applies to **cross-release** `move`, not intra-release `defer`.

---

## Design pipeline (sub-process within step 6 of the workflow)

UI work plugs into the broader workflow above. The design pipeline (`docs/design/WORKFLOW.md`) is the per-screen sub-process that runs inside step 6 (Implement) for screens:

**Phase A — Design System (Claude Design, one-time, ✅ done):** design system published in claude.ai/design with `DESIGN.md` as source material.

**Phase B — Screens (Claude Design, per batch, ✅ done for MVP):** create Prototype project, paste screen descriptions, iterate, export mockups to `docs/design/mockups/`.

**Phase C — Implementation (Claude Code):** read mockups + `DESIGN.md` + `SCREENS.md` → build component library → implement pages.

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

## Agent System

Naavik uses 6 specialized Claude Code subagents and 13 slash commands at project scope.

> **Operational guide:** `docs/AGENT_OPS.md` — single source for first-time setup, daily workflow, GitHub Mirror conventions, troubleshooting, extending the system. Read once; reference as needed.
> **Reference guides loaded by agents on cold start:**
> - `docs/ROADMAP_OVERVIEW.md` — phase state at a glance
> - `docs/ARCHITECTURE.md` — layer responsibilities + cross-cutting concerns + pattern catalog
> - `DESIGN.md` (root) — visual contract (tokens, type, icons, voice; frozen)
> - `docs/design/WORKFLOW.md` — UI sub-process (skill routing, per-screen checklist, accessibility, common patterns, anti-patterns)
> - `docs/DEPLOYMENT.md` — 4 deployment paths (NixOS / Docker / Cloud / Dev) + config + ops checklist
> - `docs/RUNBOOK.md` — known failure modes + diagnostic recipes + recovery procedures
> - `docs/plans/POST_PHASE_1.md` — testing playbook + monitoring + "when something goes wrong"
>
> **Mirror tracking:** `ROADMAP.md` § Phase A: Agent System (task ledger A.1–A.10) and § Agent System (mirror conventions).
> **Full prompts:** `.claude/agents/<name>.md`. Slash commands: `.claude/commands/<name>.md`.

| Agent | Color | Model | Role |
|---|---|---|---|
| manager | pink | opus-4-7 | Orchestrator, GitHub Projects + ROADMAP owner |
| architect | blue | opus-4-7 | Planner, design docs, technology research |
| engineer | green | sonnet-4-6 | Implementer (escalates to opus on tagged tasks) |
| devops | orange | sonnet-4-6 | Debugger, log diver, quality gates |
| hacker | red | opus-4-7 | Security reviews, threat modeling |
| designer | yellow | sonnet-4-6 | UI/UX, mockups, DESIGN.md guardian |

**Operational invariant** (codifies § Single-doc-tracking): `ROADMAP.md` is authoritative; the GitHub Project board is a one-way operational mirror. Manager syncs FROM ROADMAP TO Projects, never the reverse. If they drift, the Project board is wrong — run `/sync-roadmap --apply` to reconcile.

### Slash commands

| Command | Purpose |
|---|---|
| `/build` | Autonomous milestone delivery loop. |
| `/plan` | Architect drafts a plan + opens GH Issue. |
| `/discuss` | Multi-agent debate. |
| `/triage-bug` | Devops repros, engineer fixes. |
| `/review-pr` | Engineer + hacker review in parallel. |
| `/threat-model` | Hacker produces STRIDE for a feature / doc. |
| `/design-screen` | Designer mocks a screen. |
| `/groom` | Manager grooms the Project board. |
| `/standup` | Current state + drift + budget snapshot. |
| `/bootstrap` | First-time setup wrapper. |
| `/sync-roadmap` | Diff ROADMAP vs Project; --apply pushes ROADMAP → Project. |
| `/budget` | Token spend ledger vs caps. |
| `/runs` | Trace history. |
| `/memory` | Read-only inspection of `.claude/memory/` stores (decisions / discussions / lessons / patterns / knowledge / runs-analysis). |
| `/learn` | Manual retrospective. Analyzes last N runs, mines patterns, surfaces promotion + ROADMAP candidates. |

### Infrastructure

- `.claude/naavik_ops/gh.py` — GitHub Projects v2 helper (init / bootstrap / refresh-map / sync / create-issue / create-epic / milestone-status / add-item / set-status / set-priority / set-effort / next-unblocked / runs). **Sole writer for Issue / Milestone / Project state** per § GitHub state — single writer rule.
- `.claude/naavik_ops/memory.py` — agent memory single writer (init / record-decision / record-discussion / record-knowledge / record-lesson / list / query / analyze-run / mine-patterns / promote-lesson). **Sole writer for `.claude/memory/` stores** per Phase A row A.15 design (`docs/design/AGENT_MEMORY.md`).
- `.claude/naavik_ops/lib/roadmap.py` — parses ROADMAP.md task tables to JSONL (used by bootstrap + sync).
- `traces/<run-id>/` — per-run agent logs + MANIFEST.json. Run-id format: `YYYY-MM-DDTHH-MM-SS_<6hex>`.
- `traces/watch.sh` — tmux session, one pane per agent log.
- `traces/runs.log` — append-only run index.
- `.claude/agents/` — 6 subagent prompts (manager, architect, engineer, devops, hacker, designer).
- `.claude/commands/` — 15 slash command prompts (/build, /plan, /discuss, /triage-bug, /review-pr, /threat-model, /design-screen, /groom, /standup, /bootstrap, /sync-roadmap, /budget, /runs, /memory, /learn).
- `.claude/skills/` — project-level auto-trigger skills, one directory per skill (`<name>/SKILL.md`). **Shipped by Phase A.11 Phase 1** (`naavik-cold-start`) + Phase 2 (per-agent suites) + **A.15** (`naavik-memory-lookup`, `naavik-discussion-capture`, `naavik-learn`, `manager-promote-lesson`). One directory per skill (`<name>/SKILL.md`). Six agent prefixes (`manager-*`, `architect-*`, etc.) + shared `naavik-*` prefix for cross-agent skills.
- `.claude/memory/` — agent memory stores (decisions / discussions / lessons / knowledge / recurring-patterns / runs-analysis). Sole writer: `.claude/naavik_ops/memory.py`. Gitignored per-fork EXCEPT `.keep` + `knowledge/*.md` (committed as shared corpus). Design doc: `docs/design/AGENT_MEMORY.md`; daily workflow: `docs/AGENT_OPS.md § 14`.
- `.claude/hooks/` — Claude Code SessionStart hook + git hooks. **Shipped by Phase A.11 Phase 1.** Holds `cold-start.sh` (SessionStart, injects required-reading context) and `git/prepare-commit-msg` (auto-appends `Closes #N` from branch name using `.claude/github-issue-map.json`). Git hook installed via symlink (see `docs/AGENT_OPS.md` § 2.8).
- `.claude/settings.json` — Claude Code config (hooks registration, permissions, env vars).
- `.claude/budget.json` — daily ceiling + per-agent caps.
- `.claude/budget-ledger.json` — manager-managed daily spend ledger (gitignored).
- `.claude/github-project.json` — Project ID + field IDs cache (gitignored).
- `.claude/github-issue-map.json` — persistent {phase → epic#, task_id → issue#, phase → milestone#} association cache (gitignored, per-fork). Sole writer: `.claude/naavik_ops/gh.py`. Reconcile with `refresh-map`.
- `docs/prompts/` — session-kickoff prompts (`docs/prompts/README.md` for the convention). Architect-authored for plan-execution prompts; archives alongside plans.
- `docs/plans/` — implementation plans (archived to `docs/plans/archive/` when shipped + deviations section written).
- `docs/design/` — visual contract + design docs + mockups + componentization specs.
- `.github/ISSUE_TEMPLATE/` — bug / feature / plan-execution forms.
- `.github/pull_request_template.md` — PR template enforcing the deviations + security review checklists.

### Phase A vs product phases

Phase A (Agent System) is tracked separately from product phases 0–6 because it's the dev process, not the product. Phase A's task ledger lives in ROADMAP.md § Phase A; its milestone on the Project board is named `Phase A`. Plan / design-doc / prompt artifacts for Phase A live where everything else does (`docs/plans/`, `docs/design/`, `docs/prompts/`) but are typically small + inline-executed.

---

## Contact

- Repo: https://github.com/crizzy9/naavik
- Issues: Use GitHub issues for bugs and feature requests
- Design questions: Check `DESIGN.md` first
- Architecture questions: Check this file and `ROADMAP.md`
