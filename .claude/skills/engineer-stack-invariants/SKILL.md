---
description: Quick-reference for Naavik's stack invariants — FastAPI + SQLModel + AsyncSession patterns, HTMX + Jinja + Tailwind + DaisyUI rules, Lucide stroke 1.5, LLM tracker wrapping, no raw SQL in routes, no CLI/vault extension. Use before editing ANY file in `src/`, when reviewing your own diff before commit, when implementing a new route/service/component. Triggers on phrases like "stack invariants", "naavik conventions", "before I edit", "before commit", "is this idiomatic", "fastapi pattern", "sqlmodel pattern", "htmx pattern".
---

# engineer-stack-invariants

Stack is opinionated. Engineer matches existing patterns rather than refactoring. Quick reference; canonical source = `AGENTS.md § Key Conventions` + post-Phase-1 learnings codified in plan 10a/10b/10c deviations.

## When to invoke

- Before editing any file under `src/` (especially first edit in fresh dispatch).
- Reviewing own diff pre-commit — confirm every change matches invariants.
- Implementing new route handler, service method, SQLModel entity, HTMX page, or component.
- When you catch yourself: "should I use `requests` or `httpx`?" — invariants answer.

## Backend invariants

| Layer | Rule |
|---|---|
| Python | 3.12+ |
| Web | FastAPI |
| ORM | SQLModel (Pydantic + SQLAlchemy) |
| DB | PostgreSQL + pgvector via `asyncpg` driver |
| Sessions | `AsyncSession` everywhere I/O happens. **Never** sync session in route. |
| Engine config | NullPool engine + `expire_on_commit=False` per plan 10b deviation — fixes greenlet bridge under lifespan shutdown |
| Migrations | Alembic — `migrations/env.py` uses SYNC psycopg (not asyncpg) to avoid plan 10a's async wedge |
| Lint/format | `ruff check` + `ruff format` — no black, no isort, no flake8 |
| Type hints | Every function signature. No `Any` unless boundary justifies. |
| API contracts | Pydantic models for every request body + response. |
| Routes | `/api/v1/` for REST. `/api/portfolio/` no-auth, allowlist-filtered. HTMX views under `/`. |
| Raw SQL | **Forbidden** in route handlers. Pull into service method using SQLModel's `select(Model).where(...)`. |
| Async boundary | Anything doing I/O (DB, HTTP, LLM, file) is `async def`. Sync boundary = pure CPU only. |

## Frontend invariants

| Layer | Rule |
|---|---|
| Server-render | Jinja2 templates (`src/ui/templates/`). |
| Interactivity | HTMX. `hx-get`, `hx-post`, `hx-swap`. No SPA framework. No client-side router. |
| Styling | Tailwind CSS + DaisyUI. **No inline styles.** No custom CSS unless absolutely required (then `base.html` `<style>` block per `COMPONENTS.md § F.2`). |
| Theme | Dark mode primary. Light mode is Phase 6. |
| Icons | Lucide ONLY. Stroke width 1.5. `<i data-lucide="<name>"></i>` + `lucide.createIcons()` post-`htmx:afterSwap`. |
| Fonts | Inter (sans, 400/500/600/700) + JetBrains Mono (data). No third font. |
| Components | Live at `src/ui/templates/components/` — 85 partials cataloged in `docs/design/COMPONENTS.md`. **Never invent a component that exists.** Extend via macro args. |
| Pages | One file per route under `src/ui/templates/pages/`. Page composes from components; pages don't define components. |
| Custom JS | Forbidden in page templates. All client behavior in `src/ui/static/base.js` or `src/ui/static/keys.js`. |
| Alpine.js | Only if HTMX can't express interaction (drag-drop, complex client-state). Default: no Alpine. |
| Forms | Every POST route gets CSRF double-submit token via `hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'`. |
| Visual QA | Playwright at desktop 1440×900 + mobile 375×812. Baselines at `tests/visual/baseline/`. 1% pixel-delta threshold. |

## LLM integration invariants

| Layer | Rule |
|---|---|
| Abstraction | `src/llm/base.py` abstract interface. Three impls: `anthropic.py`, `openai.py`, `ollama.py`. |
| Tracking | **Every** LLM call wraps in `services/llm_tracker.tracked_call(...)` so `ApiUsage` rows persist. Bare `await client.messages.create(...)` is forbidden. |
| Prompts | Live in `src/llm/prompts/` as Python modules — not string files. |
| Structured output | Pydantic models on both Anthropic + OpenAI paths (both SDKs support native structured output). |
| Provider choice | Per-user in `Settings.llm_provider`. Never hardcode provider in service. |
| Local option | Ollama implementation always available; cloud is opt-in. |
| Cost cap | `Settings.daily_llm_cost_cap_usd` is HARD (not soft). Auto-apply cron checks before each call. |

## Data model invariants

- Bullets: single `text` field per bullet. AI trims at apply time. NO `oneline` / `detailed` / `default_include` / metric fields (removed pre-Phase-1).
- Tag vocab: fixed 9 — `ai-ml · backend · frontend · devops · data-eng · genai · leadership · platform · product`. Don't invent.
- Bullets have optional `selection_override`: `always_include | never_include | null` (default).
- Application status pipeline: 6 stages (`DRAFT | APPLIED | RECRUITER_SCREEN | ONSITE_LOOP | OFFER | CLOSED`). `DRAFT` + `CLOSED` hidden in Tracking by default.
- Document generation, referral, recruiter engagement = orthogonal sub-states, NOT pipeline stages.

## Sunset rules

- **No new `naavik` CLI subcommands.** CLI is on Phase 2 task 2.11 sunset.
- **No extensions to `src/services/vault.py`.** Vault is on Phase 2 task 2.12 sunset.
- New operator capability → Settings UI surface OR `.env.example` slot.
- See `naavik-vault-sunset-guard` + `architect-sunset-guard` for rejection template.

## Comments policy

- Default: **no comments.** Identifiers should self-document.
- Add ONE short line ONLY when WHY is non-obvious (hidden constraint, subtle invariant, workaround for specific bug).
- Don't reference current task / fix / callers in comments — belongs in PR descriptions, rots in code.
- No multi-paragraph docstrings or multi-line comment blocks.

## Common file references (quick navigation)

- `src/main.py` — FastAPI app + lifespan
- `src/config.py` — pydantic-settings
- `src/db/session.py` — AsyncSession factory + NullPool engine
- `src/llm/base.py` — LLM abstract interface
- `src/services/llm_tracker.py` — `tracked_call(...)` wrapper
- `src/services/auth.py` — bcrypt + JWT + CSRF + rate limit
- `src/services/vault.py` — **SUNSET. Don't touch unless deleting.**
- `src/ui/templates/base.html` — page shell + Lucide bootstrap + HTMX bootstrap
- `src/ui/templates/components/_macros.html` — `tag_chip`, `score_circle`, `status_dot`, `kbd`, `meta_item`, `chip`, `log_line` macros
- `src/scheduler/jobs.py` — APScheduler crons (auto_apply, daily_db_snapshot)
- `flake.nix` — Nix orchestrator + dev shell + LD_LIBRARY_PATH for libstdc++

## Canonical references

- `AGENTS.md` § Key Conventions (Code Style / API Design / Frontend / Database / LLM / Resume).
- `AGENTS.md` § Key Conventions § CLI (sunset rules).
- `docs/ARCHITECTURE.md` — layer responsibilities + cross-cutting concerns.
- `docs/design/COMPONENTS.md` — 85-partial catalog.
- `docs/design/INTERACTIONS.md` — HTMX patterns.
- `CLAUDE.md` § Tech Stack + § Architecture + § Key Conventions.

## When NOT to invoke

- Already read AGENTS.md § Key Conventions this turn — skip redundant load.
- 1-line typo fix — invariants don't change for trivial fixes.
- Compaction events.

## Forbidden during invocation

- Do NOT propose refactor of existing code already matching invariants. Match local style.
- Do NOT introduce third font / icon set / styling library. Stack is closed.
- Do NOT bypass `tracked_call` "just this once" for LLM. Cost cap depends on full tracking.
