# Naavik Development Roadmap

> **Single source of truth for project progress.** Phases describe the long arc; per-phase wave/task tables are checked off as work lands. Tracking-only (per `AGENTS.md` § Single-doc-tracking).
>
> **Last updated:** 2026-05-19. (Historical "Earlier line:" entries removed — they're recoverable via `git log ROADMAP.md` if needed. We evolve as we go.)

---

## Index

| Section | Purpose |
|---|---|
| [Maintenance](#maintenance) | Rules for editing this doc; cross-refs to material that USED to live here |
| [Priority Queue](#priority-queue-derived-view--post-a29) | Sorting recipe; how `naavik-ops task next-unblocked` derives "what's next" |
| [Phases](#phases) | The 7 release-version sections (0.1.0 → 0.7.0), each with a task table |
| [Backlog (unprioritized)](#backlog-unprioritized) | Future-eligible work not on any release; parking lot |
| [Agent System (mirror conventions)](#agent-system-mirror-conventions) | How ROADMAP maps to the GitHub Project v2 board |

### Phase status (one-glance)

| Phase | Goal | Status | Shipped |
|---|---|---|---|
| **0.1.0** | Foundation + MVP (11 screens + backend + 6-subagent system + A.29 numbering migration) | ✅ Complete | 2026-05-18 |
| **0.1.1** | Legacy bash → Python rewrite + CHANGELOG sanitization | ✅ Complete | 2026-05-19 |
| **0.2.0** | Job Scraping & Discovery (vault sunset + 6 site scrapers + AI extraction + dedup + scheduler + UI + notifications + rate-limiting + n8n migration) | 🟢 Active | 13/15 shipped 2026-05-19 |
| 0.2.1 | Security cleanup (DEF) | 🟡 Queued | — |
| 0.2.2 | UI cleanup (DEF) | 🟡 Queued | — |
| 0.2.3 | ATS / scraper cleanup (DEF) | 🟡 Queued | — |
| 0.2.4 | Tracking cleanup (DEF) | 🟡 Queued | — |
| 0.2.5 | Observability cleanup (DEF) | 🟡 Queued | — |
| 0.2.6 | Tooling cleanup (DEF + A.28a) | 🟡 Queued | — |
| 0.3.0 | Intelligent Scoring & Matching | ⚪ Future | — |
| 0.4.0 | Application Tracking & Auto-Apply | ⚪ Future | — |
| 0.5.0 | Email Monitoring & Outreach | ⚪ Future | — |
| 0.6.0 | Optimization & Polish (light mode, observability, LaTeX, semantic match) | ⚪ Future | — |
| 0.7.0 | Agent-system follow-ups (formerly Phase 2.5) | 🟢 Active (pickup queue) | rolling |

### Active conventions

- **CLI sunset:** do NOT extend `src/cli/` or vault. Phase 2 tasks 0.2.0.01 + 0.2.0.02 delete them. (AGENTS.md § Key Conventions § CLI.)
- **Single-doc-tracking:** all task ledger lives in `ROADMAP.md` only. Plans describe the work; ROADMAP records completion.
- **Deviations gate:** every plan in `docs/plans/` MUST have a `## Deviations from plan` section before archive. Enforced by `naavik-ops plan archive` (post-0.7.0.21).
- **GitHub Mirror:** ROADMAP → Project v2 is one-way. Manager syncs FROM ROADMAP TO Project, never reverse. (`docs/AGENT_OPS.md § 6`.)
- **Parallel reviewer invariant:** PR_REVIEW_GATE reviewer dispatches (hacker + architect) MUST land in a single assistant tool-use response. (`.claude/agents/manager.md § Parallel reviewer invariant`.)
- **Backlog vs Todo:** `## Backlog (unprioritized)` section holds deferred work; release-section rows are active cycle (see `## Backlog` below).
- **Visual contract frozen:** Inter + JetBrains Mono + Lucide (stroke 1.5) + indigo/cyan + dark mode primary. (`DESIGN.md`.)

---


## Maintenance

This doc is **tracking-only** (per AGENTS.md § Single-doc-tracking). The maintenance rules live in **`AGENTS.md` § Roadmap Maintenance Rules** — read once, follow always. Quick summary:

- `[ ]` → `[~]` on start. `[~]` → `[x]` + deliverable note on completion.
- Edit the table directly when scope changes — don't bury in commits.
- Bump "Last updated" on every meaningful edit.
- **GitHub Project mirror:** the agent system mirrors this onto GitHub Project #4. See § Agent System (mirror conventions) below. Sync via `.claude/naavik-ops gh sync --apply` after ROADMAP edits.

Pointers for content that USED to be in this doc (carved 2026-05-16 to keep ROADMAP tracking-only):

| Was here | Now lives in |
|---|---|
| Vision + Competitive Context | `README.md` § What is Naavik? + § Why Naavik? |
| Architecture diagram + Tech Stack table + Design decisions | `docs/ARCHITECTURE.md` |
| Data Model sketches | `docs/design/DATA_MODEL.md` (canonical) |
| Repository Structure tree | `docs/ARCHITECTURE.md` § 3 layer responsibilities |
| Deployment (4 paths) | `docs/DEPLOYMENT.md` |
| n8n Migration Strategy | `docs/ARCHITECTURE.md` § 4.7 External integrations |
| Portfolio Integration | `docs/ARCHITECTURE.md` § 4.7 External integrations |
| UI Screens & Design narrative | `docs/design/SCREENS.md` + `DESIGN.md` + `docs/design/WORKFLOW.md` |


---

## Priority Queue (derived view — post-A.29)

**Replaced by `.claude/naavik-ops task next-unblocked 0.2.0` derived view** per A.29 D.13 caller-rewrite scope. The canonical "what should I work on next" surface is now release-version-grouped (`0.2.0` is the active release; `0.1.0` shipped; `0.1.1` queued; `0.2.X` thematic patches interleave with `0.2.0`).

Sort key per `docs/design/PHASE_NUMBERING.md` § 1: **release-version ASC → priority DESC (HIGH > MED > LOW > unset) → position ASC**, gated by deps. The two HIGH markers under `0.2.0` are `0.2.0.01` (vault deprecation, Tier-2 wave 1) and `0.2.0.05` (SQLModel Job models, hard dep for every scraper). All other `0.2.0.NN` tasks are equally required for the `0.2.0` cut.

**Maintenance:** drift-free by construction — `naavik-ops task next-unblocked <version>` reads `.claude/github-issue-map.json:issues` + `:priorities` + `:deps` and emits the sorted view on demand. Manager invokes it at every gate transition; `/standup` consumes it. The canonical source remains the per-release tables below.

---

## Phases

### 0.1.0 — Foundation + MVP + Pre-Phase-2 paper cuts + Phase A bootstrap (legacy Phase 0 + Phase 1 + PC + A.1–A.29)
> **Goal:** First full Naavik bundle — reproducible dev environment + 11-screen MVP UI + backend substrate + 6-subagent system + this A.29 phase-numbering migration.
> **Status:** ✅ Complete (cut as `0.1.0` tag during Wave 5 of A.29 PR).
> **Shipped:** 2026-05-18 (A.29 migration apply; legacy phases shipped 2026-04-25 through 2026-05-18).
> **Plan archive:** `docs/plans/archive/01-…` through `docs/plans/archive/24-…`.
> **Position cap rule:** D.1 Option B collapse — Phase 1's 5 Waves fold to 14 deliverable-level positions; sub-task detail preserved in `docs/plans/archive/10-backend-impl.md` and Notes-column prose. 48 of 99 slots used; 2 reserved (0.1.0.48–0.1.0.49) for future micro-fixes before tag cut.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.1.0.01 | Nix flake: devShell with Python 3.12, uv, typst, postgresql, ruff, pre-commit hooks | [x] | — | 0.1 | `nix/devshell.nix` — verified all tools available in `nix develop` |
| 0.1.0.02 | pyproject.toml + uv lockfile with all Python deps | [x] | — | 0.2 | 56 packages installed via `uv sync` |
| 0.1.0.03 | Dockerfile (multi-stage, uv-based, Python 3.12 slim) | [x] | — | 0.3 | Builder + runtime stages, typst in runtime |
| 0.1.0.04 | Docker Compose: FastAPI app + PostgreSQL (pgvector/pgvector:pg17) | [x] | — | 0.4 | Health check on db, app depends on healthy db |
| 0.1.0.05 | NixOS service module (`nix/module.nix`) — Lumino-compatible | [x] | — | 0.5 | Reads `settings.servicesConfig.apps.tools.naavik`, full systemd hardening, SOPS, Traefik, PostgreSQL ensure |
| 0.1.0.06 | Nix package derivation (`nix/package.nix`) | [x] | — | 0.6 | `nix build` produces `result/bin/naavik`, typst wrapped in PATH |
| 0.1.0.07 | FastAPI app skeleton — main.py + config.py + db/session.py + static files + Jinja2 templates | [x] | — | 0.7 | Sidebar drawer layout (Tailwind + DaisyUI + HTMX), dashboard placeholder, 5 nav stubs |
| 0.1.0.08 | Alembic setup (async, reads DATABASE_URL from settings) | [x] | — | 0.8 | `migrations/env.py` uses async_engine_from_config |
| 0.1.0.09 | .env.example with all env vars documented | [x] | — | 0.9 | DATABASE_URL, SECRET_KEY, all LLM keys, OAuth, integrations |
| 0.1.0.10 | Phase 1 Wave 1 — 5 design docs graduated (COMPONENTS + BACKEND + DATA_MODEL + INTERACTIONS + SAMPLE_DATA) | [x] | — | Phase 1 Wave 1 | Plans 03–07 GRADUATED + archived; ~5300 lines of canonical contract; DESIGN.md bumped v1.3 (DRAFT row added) |
| 0.1.0.11 | Phase 1 Wave 2 — 85-component partial library + base.html + macros + base.js + `/_design/components` fixture page | [x] | — | Phase 1 Wave 2 | All 100 tests pass; `docs/plans/archive/08-stage-2-impl.md` |
| 0.1.0.12 | Phase 1 Wave 3 — 11 page templates + sample_data accessors + stub fragment/JSON endpoints + Discover keyboard map + Playwright snapshots | [x] | — | Phase 1 Wave 3 | All screens render at desktop + mobile; `docs/plans/archive/09-stage-3-impl.md` |
| 0.1.0.13 | Phase 1 Wave 3a — Stage 3 bugfix + Discover redesign triage (Lucide diagnostics, sidebar mobile drawer, typed application questions, scroll-spy, native dialog backdrop, touch swipe) | [x] | — | Phase 1 Wave 3a | `docs/plans/archive/09a-stage-3-bugfix.md` |
| 0.1.0.14 | Phase 1 Wave 4 — 20 SQLModel entities + Alembic 0001_initial + pgvector extension + 25 model tests | [x] | — | Phase 1 Wave 4 (substrate) | `docs/plans/archive/10-backend-impl.md` § B |
| 0.1.0.15 | Phase 1 Wave 4 — Auth (bcrypt + JWT + CSRF + rate limit) + AES-256-GCM vault + key rotation CLI + Settings · Deployment vault-locked banner | [x] | — | Phase 1 Wave 4 (auth+vault) | 18 auth tests + 22 vault tests; cost=12 prod / cost=4 tests; HS256 JWT; HttpOnly+Secure+SameSite=Strict cookies |
| 0.1.0.16 | Phase 1 Wave 4 — LLM provider abstraction (Anthropic + OpenAI + Ollama) + structured-output retry policy + 10 prompt skeletons + `ApiUsage` cost tracker | [x] | — | Phase 1 Wave 4 (LLM) | Anthropic tool-use / OpenAI json_schema / Ollama JSON mode; `tracked_call` wraps every provider call; 15 tests |
| 0.1.0.17 | Phase 1 Wave 4 — Profile + Settings services + per-field autosave + `NAAVIK_PERSISTENCE=db` DB-backed accessor swap (12 high-traffic accessors) | [x] | — | Phase 1 Wave 4 (services+swap) | DB-backed CRUD per tab; PUT /api/v1/settings/llm flows API key through vault |
| 0.1.0.18 | Phase 1 Wave 4 — `db/seed.py` consuming `db/sample_data.py` (idempotent ON CONFLICT DO NOTHING) + `ats_credentials` service | [x] | — | Phase 1 Wave 4 (seed) | 372 rows seeded across 20 entities; bumps every PK sequence after seed; CLI `uv run python -m db.seed` |
| 0.1.0.19 | Phase 1 Wave 5 — `extraction` service (PDF → AI → Profile + SSE event emission) | [x] | — | Phase 1 Wave 5 (extraction) | `services/extraction.py` — PDF parse via pypdf + LLM `extract_resume` + SSE generator |
| 0.1.0.20 | Phase 1 Wave 5 — `document_generator` (bullet selection + AI trim + Typst compile + native page-count validation + DRAFT reuse heuristic) + Typst templates (`onepage.typ`, `cover_letter.typ`) + native page-count validator | [x] | — | Phase 1 Wave 5 (doc-gen) | NEU-style 1-page resume + 4-section letter; both with `<naavik-meta>` page-count label; `typst query <input.typ>` (the spec'd `--emit metadata` flag doesn't exist in 0.14) |
| 0.1.0.21 | Phase 1 Wave 5 — `application_service` (DRAFT lifecycle + submit/discard + ATS dispatch + `validate_submittable` + `process_auto_apply_queue`) + multi-axis state derivation | [x] | — | Phase 1 Wave 5 (application) | Full DRAFT lifecycle + computed-state ownership + 25 unit tests |
| 0.1.0.22 | Phase 1 Wave 5 — `notifications` (Discord webhook + Telegram outbound + in-app toast routing) + `portfolio_sync` (public CV API + filtered + debounced regen + Netlify webhook) | [x] | — | Phase 1 Wave 5 (notif+portfolio) | Discord embed + Telegram + toast queue; Allowlist-based portfolio filter + post-condition assert + 30 tests |
| 0.1.0.23 | Phase 1 Wave 5 — ATS adapters (Greenhouse + Lever + Ashby; Workday / LinkedIn / Indeed / Generic deferred to 0.2.3) + APScheduler cron registration (auto_apply / aggregate_costs / cleanup_stale_docs / daily_db_snapshot / refresh_oauth_tokens) | [x] | — | Phase 1 Wave 5 (ATS+cron) | All 3 adapters with public APIs + factory + 18 mock-HTTP tests; APScheduler with PostgresJobStore lifespan-managed |
| 0.1.0.24 | Pre-Phase-2 paper cut — Process-compose: confirm app logs + cold-start reliability | [x] | — | PC.1 | **Plan 10a (2026-05-02 + orphan-fix 2026-05-03):** `setsid -w` + `coreutils` + `pkill` cleanup; root cause was TTY/SIGTTIN not alembic async wedge |
| 0.1.0.25 | Pre-Phase-2 paper cut — `uv run fastapi dev` (no path) should just work | [x] | — | PC.2 | **Plan 10a:** 2-line `app.py` shim at repo root re-exports `src.main:app` |
| 0.1.0.26 | Pre-Phase-2 paper cut — Playwright local capture on NixOS | [x] | — | PC.3 | **Plan 10a:** `nodejs_22` + `PLAYWRIGHT_NODEJS_PATH`; Playwright pinned `>=1.58.0,<1.59`; 20 baseline PNGs committed |
| 0.1.0.27 | Pre-Phase-2 paper cut — Phase-1 finalization (orchestrator greenlet/libstdc++ + NAAVIK_PERSISTENCE=db default + working dev credential + signup endpoint + `naavik` CLI subcommands + Settings · LLM Provider form-wiring + README rewrite) | [x] | — | PC.4 | **Plan 10b EXECUTED 2026-05-03** — 9 paper cuts shipped; 475 tests pass (~12 new); ruff clean |
| 0.1.0.28 | Pre-Phase-2 paper cut — `SECRET_KEY` boot-time enforcement | [x] | — | PC.5 | **Plan 17 EXECUTED 2026-05-16 via PR #49** — `Settings._enforce_secret_key` validator at `src/config.py:45-66` refuses module import when `SECRET_KEY` is shipped default or <32 bytes unless `NAAVIK_DEBUG=1` |
| 0.1.0.29 | Pre-Phase-2 paper cut — Password complexity (min 12 chars, digit + letter) + must-change-on-first-login flag | [x] | — | PC.6 | **Plan 18 EXECUTED 2026-05-17 via PR #50** — `validate_password_complexity` + `User.must_change_password` (alembic `0003`) + `require_password_complete` dep + `POST /api/v1/auth/change-password` + cookie/CSRF rotation + dev-credential file cleanup on rotation |
| 0.1.0.30 | Pre-Phase-2 paper cut — First-time setup ergonomics (`NAAVIK_PERSISTENCE=db` parity + login signup-link promotion + signup-disabled banner + persisted `~/.naavik/dev-credentials` + lifespan credential echo) | [x] | — | PC.7 | **Plan 10c EXECUTED 2026-05-12** — three sub-items shipped; 478 tests pass (3 new pages tests + 2 new live-DB seed tests); new config field `Settings.debug` |
| 0.1.0.31 | Phase A — 6 subagent prompts (`.claude/agents/`) | [x] | — | A.1 | Frontmatter (name/description/tools/model/color) + body (principles, operating loop, tracing format, escalation); models: manager+architect+hacker on opus-4-7; engineer+devops+designer on sonnet-4-6 |
| 0.1.0.32 | Phase A — 13 slash commands (`.claude/commands/`) | [x] | — | A.2 | `/build`, `/plan`, `/discuss`, `/triage-bug`, `/review-pr`, `/threat-model`, `/design-screen`, `/groom`, `/standup`, `/bootstrap`, `/sync-roadmap`, `/budget`, `/runs` |
| 0.1.0.33 | Phase A — `.claude/naavik_ops/gh.py` Projects v2 helper | [x] | — | A.3 | `init` / `bootstrap` / `sync` / `milestone-status` / `add-item` / `create-issue` / `set-status` / `next-unblocked` / `runs`; idempotent; user-or-org auto-detected |
| 0.1.0.34 | Phase A — Token budget config + ledger | [x] | — | A.4 | `.claude/budget.json` (caps) + `.claude/budget-ledger.json` (manager-managed); halt at projected-spend-exceeds-cap; `/budget` to inspect |
| 0.1.0.35 | Phase A — Trace system + `watch.sh` (tmux) + `runs.log` index + `MANIFEST.json` per run | [x] | — | A.5 | Run-id format `YYYY-MM-DDTHH-MM-SS_<6hash>`; per-agent log format frozen in each agent's prompt; `/runs` to list history |
| 0.1.0.36 | Phase A — `docs/AGENT_OPS.md` — single operational guide | [x] | — | A.6 | Bootstrap → daily workflow → commands reference → agent reference → GitHub Mirror conventions → tracing → budget → troubleshooting → extending |
| 0.1.0.37 | Phase A — `.github/` templates (3 Issue forms + PR template) | [x] | — | A.7 | PR template aligns with AGENTS.md § Workflow step 7 (deviations summary required) |
| 0.1.0.38 | Phase A — First end-to-end `/build` shipping a real paper cut (satisfied via PC.5 PR #49) | [x] | — | A.8 | 5 skills invoked; git `prepare-commit-msg` hook auto-appended `Closes #7`; deviations promoted into plan 17; plan archived. Manager → architect → engineer → hacker → devops → ROADMAP update → Issue close → Project advance loop exercised |
| 0.1.0.39 | Phase A — Agent system v2 (cold-start hook + per-agent skill suite + git commit automation) | [x] | — | A.11 | **Plan 16 EXECUTED 2026-05-17** — `.claude/hooks/cold-start.sh` SessionStart + `.claude/skills/naavik-cold-start/SKILL.md` + Skill tool on all 6 agents + `.claude/hooks/git/prepare-commit-msg` auto-`Closes #N` + 29-skill per-agent suite |
| 0.1.0.40 | Phase A — Map cache + single-writer governance (gh-project.sh hardening) | [x] | — | A.12 | `find_issue_by_prefix` + `ensure_milestone` consult `.claude/github-issue-map.json` first; new `refresh-map` subcommand reconciles from authoritative GitHub state; duplicate epics #46/#47 closed; "GitHub state — single writer" rule codified |
| 0.1.0.41 | Phase A — Tracing contract ERROR + BUILT/REVIEWED event family + MANIFEST schema extensions | [x] | — | A.13 | `ERROR step=<what> kind=<retry\|skip\|halt\|pivot> reason='<line>' attempt=<n>/<max>` + `BUILT` / `REVIEWED` last-line summaries; MANIFEST gains `outcome` / `halt_reason` / `what_built` / `errors_encountered` |
| 0.1.0.42 | Phase A — Task Playbook (`docs/PLAYBOOK.md`) — strict 9-category if-then classification | [x] | — | A.14 | **Shipped 2026-05-17 via PR #51 squash `ab9f2589`** — STATUS / INSPECT / 3 gate responses / PRODUCT_WORK / BUG_TRIAGE / CONTRACT_CHANGE / BOOKKEEPING; default-deny allow-list-only for BOOKKEEPING |
| 0.1.0.43 | Phase A — Agent memory + learning system | [x] | — | A.15 | **Plan 19 EXECUTED 2026-05-17 via PR #53** — `.claude/memory/` substrate (6 stores) + single-writer `.claude/naavik_ops/memory.py` + 4 memory-aware skills + 2 slash commands (`/memory`, `/learn`); 50/50 smoke pass |
| 0.1.0.44 | Phase A — Machine-readable wording rewrite of agent-system files | [x] | — | A.16 | **Plan 22 EXECUTED 2026-05-18 via PR #68** — 57 files rewritten; -9.7% / ~-8.5k tokens per ingest cycle |
| 0.1.0.45 | Phase A — `agent-memory.sh` hardening (flock + jq sandbox + alias regex + manifest escape) | [x] | — | A.17 | **Plan 21 EXECUTED 2026-05-18 via PR #66** — 5 hacker findings closed; 30/30 concurrent writes persist (was 13/30 pre-fix); 14 new test assertions |
| 0.1.0.46 | Phase A — `agent-memory.sh` alias regex widening to include uppercase tokens | [x] | — | A.17a | **EXECUTED 2026-05-18 via PR #68 (A.16 fold-in)** — `ALIASES_RE` widened at `.claude/naavik-ops memory:119`; uppercase + `#` accepted; newline + `---` injection still blocked |
| 0.1.0.47 | Phase A — Board restructure (Backlog status + Phase 2.5 milestone + Priority Queue section) | [x] | — | A.28 | **Plan 20 EXECUTED 2026-05-17 via PR #63** — 5 waves; `Backlog` status added to Project v2; `Phase 2.5` milestone + epic created; ROADMAP surgery; `manager-backlog-promote` skill |
| 0.1.0.48 | (reserved buffer slot) | — | — | — | Reserved for post-A.29 micro-fixes before 0.1.0 tag cut |
| 0.1.0.49 | (reserved buffer slot) | — | — | — | Reserved for post-A.29 micro-fixes before 0.1.0 tag cut |
| 0.1.0.50 | Phase numbering system + `.claude/naavik-ops` Python dispatcher — 4-level semver task IDs replace Project Priority field; full retroactive renumber + release ceremony tooling | [x] | HIGH | A.29 | **Plan 24 EXECUTED 2026-05-18 via PR #73 squash `c5ac58f`** — Waves 1-4 shipped; Wave 5 (migration `--apply` + `0.1.0` release cut) runs post-merge per this diff patch + `step_7_rewrite_roadmap()` in `.claude/migrations/A.29-phase-renumber.py`. **This row is the closer for 0.1.0** — running `.claude/naavik-ops release cut 0.1.0` after Wave 5 cuts the first `0.1.0` tag |

**Deliverable (0.1.0):** Reproducible dev environment + 11-screen MVP + 20-SQLModel-entity backend substrate + 3 ATS adapters + Typst PDF generation + 6-subagent system + agent memory substrate + machine-readable rewrite + board restructure + this A.29 phase-numbering migration. Tag cuts in Wave 5 via `.claude/naavik-ops release cut 0.1.0`. Closes `Phase A` + `Pre-Phase-2 paper cuts` + `Phase 1 deferred items` (whose rows distribute into `0.2.X` thematic patches) + `Phase 2.5` (whose rows defer to `0.7.0`) GitHub Milestones.

**Verification log (Wave 5 post-merge):**
- Migration script applies cleanly: `python .claude/migrations/A.29-phase-renumber.py --apply` exits 0.
- `.claude/naavik-ops task check` exits 0 (no ROADMAP-vs-Issue-title drift; pyproject.toml + nix/package.nix at `0.1.0`; latest tag `0.1.0`).
- `git tag --list 0.1.0` returns `0.1.0` (cut via `.claude/naavik-ops release cut 0.1.0`).
- All 50 ROADMAP-rows-becoming-`0.1.0.NN` have Issue titles rewritten from `[A.X]` / `[PC.X]` to `[0.1.0.NN]` per the migration runbook step 6.
- `.claude/github-issue-map.json:redirects` populated with every legacy ID → new ID mapping.

---

### 0.1.1 — Legacy bash → Python rewrite + CHANGELOG sanitization (legacy A.30 + A.31)
> **Goal:** Replace legacy bash (`scripts/gh-project.sh` 1469 LOC + `scripts/agent-memory.sh` 843 LOC + `scripts/roadmap_parser.py` 304 LOC) with native Python under `.claude/naavik_ops/`; harden CHANGELOG.md markdown escaping before future closed-Issue ingestion lands.
> **Status:** ✅ Complete (2026-05-19). Shipped via PR #91 squash `494ffae`; tag `0.1.1` + GH release published at https://github.com/crizzy9/naavik/releases/tag/0.1.1.
> **Plan:** `docs/plans/archive/25-0.1.1-bash-to-python.md`.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.1.1.01 | Python rewrite of legacy bash scripts (`gh-project.sh` 1469 LOC + `agent-memory.sh` 843 LOC + `roadmap_parser.py`) into `.claude/naavik_ops/` Python modules + full `scripts/` → `.claude/` migration | [x] | MEDIUM | A.30 | **EXECUTED 2026-05-19 via PR #91 squash `494ffae`** (closed Issue #72). 7 commits W0-W6: W0 `.gitignore` + plan 25 + fixture dir; W1 `lib/changelog.py` sanitize + `lib/roadmap.py` writer-half inline; W2 native `gh.py` rewrite (20 callable subcommands + 1 helper `get_issue()`); W3 native `memory.py` (A.17 jq sandbox byte-for-byte) + 5 mutating `task` ops (atomic 3-store mutation + rollback under `~/.naavik/naavik-ops.lock`); W4 ~34 caller rewrites + skill frontmatter cleanup; W5 delete `scripts/{gh-project.sh,agent-memory.sh,roadmap_parser.py}` + `tests/test_agent_memory.sh` + `tests/test_naavik_ops/test_{gh,memory}_wrapper.py` (-2616 LOC); W6 PR_REVIEW_GATE reviewer pairing `hacker + devops` → `hacker + architect` (folded-in contract refactor; new § PR review mode in `.claude/agents/architect.md`). Hacker: APPROVE_WITH_NOTES (2 LOW + 1 INFO, none exploitable; R11 jq sandbox + R12 close-issue argv validated). Devops: PASS 12/12 gates (zero regressions; 210 tests passing in `tests/test_naavik_ops/`). 2 engineer deviations promoted into archived plan (W3 column-order swap + W3 collision guard). Closes A.29 Deviation 1 (mutating subcommands stubbed). |
| 0.1.1.02 | CHANGELOG.md markdown sanitization — escape commit-msg bodies before `.claude/naavik_ops/lib/changelog.py:62` renders to released artifact | [x] | LOW | A.31 | **EXECUTED 2026-05-19 via PR #91 W1 commit `8657655`** (closed Issue #74). `ReleaseEntry.__post_init__` escapes CommonMark special chars + collapses whitespace + rejects CR; `parse_changelog` round-trip avoids double-escape via `ReleaseEntry.from_rendered`. 7 sanitize tests in `tests/test_naavik_ops/test_changelog.py`. Hacker LOW finding from PR #75 review: CommonMark escape regex covers 19/30 spec chars (missing `~`/`=`/`&`); setext-h2 (`---`/`===`) gap defused by whitespace collapse — documented as design intent, no fix needed. |
| 0.1.1.03 | Close stale pre-A.29 epic Issues using new `close-issue` helper | [x] | LOW | — | **EXECUTED 2026-05-19 post-merge bookkeeping** (closed Issue #90). 8 stale epics closed via `naavik-ops gh close-issue <N> --reason completed`: `#1 [Epic] Phase A`, `#6 [Epic] Pre-Phase-2 paper cuts`, `#9 [Epic] Phase 2`, `#22 [Epic] Phase 1 deferred items`, `#65 [Epic] Phase 2.5`, `#76 [Epic] 0.1.0` (release shipped 2026-05-18), `#77 [Epic] 0.1.1` (release shipped 2026-05-19). Permission system blocked raw `gh issue close` at PR #75 (single-writer rule); the new dispatcher subcommand from 0.1.1.01 W2 closes the architectural gap. |

**Deliverable (0.1.1):** Legacy bash scripts deleted; `.claude/naavik_ops/` becomes the sole agent-system tooling surface; `scripts/` reserved for project-wide use only; CHANGELOG.md safe against markdown injection.

---

### 0.2.0 — Job Scraping & Discovery (legacy Phase 2)
> **Goal:** Automated multi-source job discovery with AI extraction; vault deprecation + CLI sunset.
> **Status:** 🟡 Queued (post-0.1.0 tag cut).
> **Plan:** `docs/plans/11-phase-2-scrapers.md` (to be authored after Phase 1 ships). Splits cleanly into 11a (LinkedIn + Greenhouse + Lever + Ashby) and 11b (Workday + Indeed + Generic + n8n migration).
> **Implementation contract:** `docs/design/BACKEND.md` § J (scraping architecture), § I (cron catalog), § K (auto-apply pipeline). Wave 6 services + Phase 2 sub-prompts of plan 10.
> **Estimated effort:** 2–3 weeks.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.2.0.01 | **Vault deprecation → env-only secrets.** Delete `src/services/vault.py` (AES-256-GCM + PBKDF2 + lockfile + audit log) and the encrypted vault entirely. Switch to standard self-hosted-app pattern: secrets via env vars sourced from a gitignored `.env` (loaded by `nix develop:shellHook`, `flake.nix:devEnv`, and Docker Compose `env_file:`). Ship `.env.example` with all secret slots commented. **DB migration:** alembic 0003 drops `Settings.*_configured` booleans + `Settings.*_fingerprint` columns; secret presence becomes runtime-derived from env. **API surface:** `PUT /api/v1/settings/llm` becomes read-only — exposes "Anthropic configured via env: ✓ / ✗" without an input field. **UI:** drop the API-key input from `_settings_llm.html`; drop the vault-locked banner from `_settings_deployment.html`. **Files removed:** `src/services/vault.py`, `src/cli/vault.py`, `src/cli/init.py`, `tests/test_vault.py`, vault sections of `tests/test_cli.py`. **Operational surface gone:** `~/.naavik/secrets.enc{,.lock,.bak.*}`, `~/.naavik/key.bin`, `~/.naavik/logs/vault-audit.log`. **UX regression to flag in changelog:** rotating an LLM API key is now "edit `.env` + restart". | [x] | HIGH | 2.12 | **Plan 26 EXECUTED 2026-05-19 via PR #92 squash `b91f50b` (closes #20).** Shipped Alembic 0004 instead of 0003 (numbering aligned w/ existing migrations). Migration story: Option A (pure docs path — no shim, no script). Per locked decision recorded in `.claude/memory/decisions.jsonl` (`0.2.0.01-migration-story`). 8 commits W0-W5 + W6/W7/W8 delta. Reviewers cleared at APPROVE (hacker round-1 1 LOW + 2 INFO defer-recommendations; architect FULL spec match post-delta). 7 substantive deviations promoted into archived plan. **Blocks `0.2.0.02`** unlocked — CLI now collapses to `naavik serve` only. **`0.2.1.03` (Argon2id) auto-closes as moot.** |
| 0.2.0.03 | Broader `require_password_complete` gate — extend to `src/api/profile.py` + `src/api/settings.py` + `src/ui/routes/*` | [x] | — | PC.6a | **Plan 23 EXECUTED 2026-05-18 via PR #69 — FROZEN done position.** New `require_authed_session` wrapper in `src/services/auth.py:297-371` applied to **41 mutation routes** across `src/api/profile.py` (7) + `src/api/settings.py` (5) + `src/ui/routes/{settings 9, discover 9, outreach 8, tracking 1, email 1, integrations 2}`. 2 onboarding routes skipped. 13 new tests. Hacker APPROVE_WITH_NOTES (1 MEDIUM onboarding bypass → PC.6b → 0.2.0.04). |
| 0.2.0.04 | Onboarding bypass — `/api/v1/profile/from-extraction` lets flagged user replace real-JWT with fake-session (close hacker MEDIUM from PR #69) | [ ] | — | PC.6b | **Filed 2026-05-18 via PR #69 hacker review** (Issue #70). Fix = add no-existing-user precondition to `post_profile_from_extraction` (`src/ui/routes/auth.py:223`). Also addresses 3 hacker LOW non-blocking notes. ~20-30 min engineer. Must ship before any multi-user expansion. |
| 0.2.0.05 | SQLModel: Job, StatusHistory models + migration | [x] | HIGH | 2.6 | **Plan 27 EXECUTED 2026-05-19 via PR #95 squash `693bb1e` (closes #15).** Reframed from "StatusHistory" → `JobScrapeRun` (scrape-side observability; AppEvent already audits Application.status). Job hardened: 6 new cols + partial-unique constraint + 5 new enums (JobSource 10v / VisaRestriction 4v / RemotePolicy 4v / SeniorityLevel 7v / JobScrapeRunStatus 5v). New `src/services/job_service.py` (8 fns) + Alembic 0005. Graduated to `docs/design/JOB_MODEL.md` (470 LOC × 11 sections). 53 plan-27 tests + 731 full suite passing. Reviewers: architect APPROVE FULL spec match; hacker APPROVE_WITH_NOTES (1 MED + 2 LOW + 2 INFO — all forward-looking, filed as 0.7.0.15-0.7.0.19). 4 engineer deviations promoted to archived plan. **Unblocks `0.2.0.06`–`0.2.0.14`** (scraper chain). |
| 0.2.0.06 | Crawl4AI setup + generic scraper base class | [x] | — | 2.1 | **Plan 29 EXECUTED 2026-05-19 via PR #96 squash `90e2928` (closes #10).** Shipped substrate-only: `ScraperBase` ABC + `RawJob` Pydantic DTO (17 fields, extra=forbid) + `Crawl4AIClient` wrapper (stealth + streaming) + `SampleScraper` test fixture + `scraper_service.run_scraper` lifecycle orchestrator. `crawl4ai==0.8.6` exact pin (litellm hotfix floor); `playwright` promoted to base deps. Graduated to `docs/design/SCRAPER_BASE.md` (~330 LOC × 11 sections). 7 commits W0-W6 (W6 delta for architect HIGH on RawJob→Job adapter). 785 tests passing (+49 new across 5 test files). 6-field rename adapter `RawJob.to_upsert_payload()` with `set(payload).issubset(_JOB_CREATE_FIELDS)` contract assertion. Reviewers: architect APPROVE post-delta (R1 HIGH+LOW resolved); hacker APPROVE_WITH_NOTES (2 MED + 2 LOW filed as `0.2.0.06a` #97 — must ship BEFORE 0.2.0.07). 4 engineer + 1 delta deviation promoted to archived plan. **Unblocks `0.2.0.07`–`0.2.0.14`.** Replaces Browserless. |
| 0.2.0.06a | Scraper hardening — SSRF/LFI scheme allowlist + errors[] redaction + max_listings cap + asyncio fix | [x] | MEDIUM | A.37 (hacker PR #96) | **Plan 31 EXECUTED 2026-05-19 via PR #98 squash `8657bcb` (closes #97).** All 4 hacker findings closed: (1) `pydantic.HttpUrl` + `TypeAdapter` validation in `Crawl4AIClient.fetch_html` rejects `file:`/`ftp:`/`gopher:`/`data:`/`javascript:` while preserving `http://localhost` dev; (2) new `src/scraper/redaction.py` with `safe_url`/`safe_exc` helpers wired into `scraper_service.run_scraper` errors[] composition + `crawl4ai_client.py` `log.warning` callsites; (3) `ScrapeQuery.max_listings: Field(default=200, ge=1, le=10_000)`; (4) `asyncio.get_running_loop()` swap at 2 callsites. Graduated cross-refs added to `docs/design/SCRAPER_BASE.md § E.1` + new `§ H.4`. 8 net-new tests across 3 files. Reviewers: architect APPROVE (full spec match); hacker APPROVE_WITH_NOTES (3 LOW residual — `stream_many` SSRF + log-redaction at 2 callsites + `safe_exc` control-char strip — filed as `0.2.0.06b` HIGH priority follow-up gating `0.2.0.07`). 2 engineer deviations promoted to archived plan. |
| 0.2.0.06b | Scraper hardening round 2 — `stream_many` SSRF allowlist + `safe_msg` log redaction + `safe_exc` control-char strip | [x] | HIGH | (hacker PR #98) | **Plan 32 EXECUTED 2026-05-19 via PR #101 squash `1df4fd4` (closes #100).** All 3 LOW residuals from PR #98 closed: (1) `Crawl4AIClient.stream_many` per-URL `HttpUrl` validation via existing `_HTTP_URL_ADAPTER`; rejected URLs log + skip; (2) new `safe_msg(s: str \| None) -> str` helper in `src/scraper/redaction.py`; both `crawl4ai_client.py` `log.warning` callsites swapped; (3) `_strip_control_chars` extracted from `safe_exc`; strips ANSI CSI + C0 (preserves `\t` + `\n`) + DEL; runs BEFORE 200-char cap (length-truncation-injection-safe). SCRAPER_BASE.md § H.4 updated. 3 net-new tests. Both reviewers APPROVE (state=COMMENTED self-approval pivot per knowledge entry). Forward refs for 0.2.0.07: userinfo URL reject + RFC1918/IMDS/link-local IP denylist captured in plan 32 § Forward refs. |
| 0.2.0.07 | Site scrapers: LinkedIn + Workday + Greenhouse + Lever + Ashby + Indeed + URL guard | [x] | — | 2.2 | **Plan 33 EXECUTED 2026-05-19 via PR #102 squash `998a735` (closes #11).** 6 per-source `ScraperBase` subclasses at `src/scraper/sites/{linkedin,workday,greenhouse,lever,ashby,indeed}.py`; LinkedIn uses guest-API + Crawl4AI stealth primary + RSShub fallback. New `src/scraper/url_guard.py:is_safe_destination` closes 0.2.0.06b forward refs (userinfo URL reject + RFC1918/IMDS/link-local IP denylist); wired into `Crawl4AIClient.fetch_html` + `stream_many`. New `_BaseSiteScraper._maybe_enrich` lazy-imports `services.job_extractor` (no-op until 0.2.0.08 wires extraction). `ScraperBase.__init__` extended to accept `session/user_id/provider` (all optional). Registry populated for 6 sources keyed by `JobSource.value`. Lint regression guard `tests/test_no_direct_http_imports.py`. 5 new env-var slots added to `Settings` + `.env.example` + README. Graduated to `docs/design/SCRAPER_SITES.md`. 89 net-new tests across 9 files + 13 HTML fixtures. Reviewers: architect APPROVE_WITH_NOTES (2 LOW — rate_limit_per_minute int vs float + CLAUDE.md slot propagation); hacker APPROVE_WITH_NOTES (2 MEDIUM filed as 0.2.0.07a — slug-validate URL components in Workday tenant + Greenhouse/Lever/Ashby company template substitution; 2 LOW filed as 0.2.0.07b + 0.2.0.13a + 1 INFO debug-mode loopback port). 5 engineer deviations promoted. **Unblocks 0.2.0.08 (extraction)**, 0.2.0.09 (dedup), 0.2.0.10 (scheduler), 0.2.0.11 (UI), 0.2.0.12 (notifications). |
| 0.2.0.07a | Slug-validate URL components in 6 site scrapers + lift to `scraper.url_guard._make_url(template, **slugs)` helper | [ ] | MEDIUM | (hacker PR #102) | **Filed 2026-05-19 via PR #102 hacker review (#103).** Hacker MEDIUM × 2: (1) Workday `_parse_tenant_spec` accepts `tenant="evil.com#"` → URL becomes `https://evil.com#.wd1.myworkdayjobs.com/External` → `urlsplit.hostname == "evil.com"` → url_guard PASSES → confused-deputy outbound HTTP. (2) Greenhouse/Lever/Ashby substitute `{company}` raw into URL template; Lever path-position substitution most dangerous (slash injection → vendor API path traversal). **Fix**: slug-validate (`^[a-zA-Z0-9][a-zA-Z0-9_-]*$`) BEFORE template substitution; lift to shared helper in `url_guard.py`. Non-exploitable in current single-tenant self-host (attacker is the user); MUST fix BEFORE multi-tenant cloud flip. |
| 0.2.0.07b | Expand `test_no_direct_http_imports.py` — prefix match + sibling libs + AST attribute walk | [ ] | LOW | (hacker PR #102) | **Filed 2026-05-19 via PR #102 hacker review (#104).** Lint guard bypasses confirmed: `from urllib import request`, `import http.client`, `import urllib3`, `import httpcore`, `import niquests`, `import aiohttp.client` all pass current regex. Fix: prefix-match + add siblings + AST attribute walk. |
| 0.2.0.13a | Replace `url_guard._resolve_host` LRU cache with TTLCache(ttl=60) to bound DNS rebinding TOCTOU window | [ ] | LOW | (hacker PR #102) | **Filed 2026-05-19 via PR #102 hacker review (#105).** `@lru_cache(maxsize=256)` with no TTL extends DNS rebinding TOCTOU window to process lifetime. Fix: `TTLCache(ttl=60)` or drop cache (DNS load is trivial). May fold into 0.2.0.13 rate-limiting work. |
| 0.2.0.08 | AI job extraction: HTML → JobInfo (company, position, location, visa, salary, skills) | [x] | — | 2.3 | **Plan 30 EXECUTED 2026-05-19 via PR #106 squash `2c30367` (closes #12).** New `src/services/job_extractor.py:enrich_raw_job(session, *, user_id, provider, raw_job, settings=None) -> RawJob` — bs4 boilerplate strip (conservative `_DROP_TAGS` preserves `<aside>`/`<main>`/`<article>` for LinkedIn JD right-rail) + 30k-char cap + `services.llm_tracker.tracked_call` wrap (closes the cost-cap blind spot the deleted skeleton bypassed) + structured output via new `JobExtraction` Pydantic v2 model (15 fields, `extra="forbid"`). Old `src/llm/prompts/extract_job.py:ExtractedJob` skeleton + bypassing `extract_job()` function DELETED. Source-agnostic prompt with 9-tag vocabulary enum-string canonical-lowercase guidance. Merge semantics: OVERWRITES `description_text` / `*_hint` enum trio / `location_raw` / `posted_at`; PRESERVES scraper identity quad (`source` / `external_id` / `source_url` / `board`); MERGES scorer arrays (`skills_required` / `criteria` / `tags` / `salary_min/max`) into `raw_meta`. 7-row failure-mode table: `extraction_skipped` marker on empty-html / schema-invalid / provider-failure. Integration with `_BaseSiteScraper._maybe_enrich` (shipped 0.2.0.07) verified — lazy-import resolves cleanly; 6 production scrapers now AI-enrich enabled when `session/user_id/provider` are passed to `__init__`. 15 net-new tests + 5 HTML fixtures + `_FakeLLMProvider` duck-type. Reviewers: architect APPROVE (full spec match; 3 deviations accepted — 14→15 field plan-prose off-by-one + 15>12 tests + `EXTRACT_JOB_PROMPT` alias); hacker APPROVE_WITH_NOTES (1 LOW — `JobExtraction.tags` Literal constraint deferred per OQ.5; filed as `0.2.0.08a` #107). 3 engineer deviations promoted. Doc graduation to `docs/design/JOB_EXTRACTION.md` deferred to bookkeeping. **Unblocks 0.2.0.09 dedup + 0.2.0.10 scheduler.** |
| 0.2.0.08a | Harden `JobExtraction.tags` to `Literal[...]` constraint (9-tag vocabulary enforcement at schema layer) | [ ] | LOW | (hacker PR #106) | **Filed 2026-05-19 via PR #106 hacker review (#107).** Plan OQ.5 deferred runtime filter; this row tightens schema to `tags: list[Literal["ai-ml","backend","frontend","devops","data-eng","genai","leadership","platform","product"]]` so LLM hallucinations fail-fast at Pydantic boundary. Trivial ~5 LOC + 1 test. Defer until tag-hallucination rate measured post-0.2.0.10 cron firings. |
| 0.2.0.09 | Job deduplication (URL-based + fuzzy title/company) | [x] | — | 2.4 | **Plan 34 EXECUTED 2026-05-19 via PR #108 squash `929f234` (closes #13).** Tier-3 fuzzy cross-source dedup wedge in `upsert_job` pre-INSERT: pg_trgm GIN candidate filter (`lower(company) % :norm_company` similarity > 0.3) + rapidfuzz `token_set_ratio` precision-score @ 88.0 threshold (weighted 0.6 × company + 0.4 × role). New `src/services/dedup.py:find_duplicate(session, *, user_id, raw_job) -> Job | None` (145 LOC) mirrors `contact_tracker` shape. New `Job.duplicate_of_id` FK column (ON DELETE SET NULL); both rows survive (no soft-delete); `list_jobs` default filters via `JobFilter.include_duplicates: bool = False`. Alembic 0006: `CREATE EXTENSION IF NOT EXISTS pg_trgm` + FK + GIN trigram index `ix_job_company_trgm`; sqlite test fallback uses LIKE matching. New base dep `rapidfuzz>=3.10.0,<4` (3.14.5; MIT; nixpkgs `python312Packages.rapidfuzz`). 14 new tests + 3 alembic round-trip tests. Reviewers: architect APPROVE FULL spec match; hacker APPROVE 0 findings (`DEDUP_CANDIDATE_LIMIT=20` caps trigram-bomb, parameterized text() bindings, multi-user isolation verified). 6 engineer deviations (all benign — `_FakeSession.bind` substrate + sqlite FK skip + LIKE fallback + scraper-test cold-cache +1 + lockfile note + docstring refresh). **Unblocks 0.2.0.10 scheduler.** |
| 0.2.0.10 | APScheduler: periodic scraping per source | [x] | — | 2.5 | **Plan 35 EXECUTED 2026-05-19 via PR #109 squash `a6c441c` (closes #14).** New `src/scheduler/scraping.py:register_scraping_jobs` registers 6 per-source crons (5 CronTrigger LinkedIn/Workday/Greenhouse/Lever/Ashby + 1 IntervalTrigger(minutes=90) for Indeed — `*/90` invalid cron). All 6 carry `jitter=30` + `max_instances=1` + `misfire_grace_time=300`. Per-user dispatch iterates Settings rows; LLM provider resolved per-firing per-user; `provider=None` graceful degrade on LLMProviderError. Alembic 0007 adds 5 nullable Settings cols (`linkedin_keywords`, `linkedin_location`, `indeed_keywords`, `indeed_location`, `consecutive_scrape_failures: dict[str, int]`). Failure handling: counter increments on FAILED; scrape ALWAYS runs (no skip-on-counter — closes hacker HIGH); notify_admin_error fires ONCE on threshold-cross (counter 2→3), silent thereafter until SUCCESS resets. Top-level broad-except emits admin signal. Initial round APPROVE_WITH_NOTES (architect) + REQUEST_CHANGES (hacker HIGH auto-skip deadlock + 2 MEDIUM + 1 LOW); delta commit `c89ab2d` closed all 3 in-scope findings; pickle-RCE deferred to `0.2.0.10b`. Final reviewers APPROVE clean. 5 deviations (JSON counter on Settings vs JobScrapeRun history scan; single commit vs 4-wave; SCHEDULER.md graduation deferred; D.5 contract reshape; alembic 0007 = 5 cols not 4). 32 net-new tests. |
| 0.2.0.10a | Add `/api/v1/scheduler/*` endpoints (list / run / pause / resume) — plan 35 § D.7 stub never implemented | [ ] | LOW | (architect PR #109) | **Filed 2026-05-19 via PR #109 architect review (#110).** Plan 35 § D.7 referenced these endpoints as pre-existing; they don't. Engineer correctly skipped smoke test. Fold into 0.2.0.11 Settings · Sources UI or ship standalone. |
| 0.2.0.10b | Replace `SQLAlchemyJobStore` pickle deser with safer alternative (MemoryJobStore or JSON serializer) | [ ] | LOW | (hacker PR #109) | **Filed 2026-05-19 via PR #109 hacker review (#111).** Pre-existing pickle-RCE-on-DB-compromise vector; +6 pickled job entries from 0.2.0.10. Worth evaluating: MemoryJobStore (lose persistence across restarts) vs custom JSON serializer (preserve persistence). Not exploitable in current single-tenant self-host. |
| 0.2.0.11 | HTMX UI: job list with filters, job detail view | [x] | — | 2.7 | **Plan 36 EXECUTED 2026-05-19 via PR #112 squash `47d78ec` (closes #16).** Wired `job_service.list_jobs` into existing `/discover` swipe queue (replaces `db.sample_data` shim). New 6-axis filter chip-row toolbar (sticky top): `source` / `remote_only` / `visa` / `seniority` / `score_min` / `include_duplicates`. HTMX fragment-swap into `#discover-main` with `hx-push-url=true` for bookmarkable URLs. New `/jobs/{job_id}` read-only Job-detail route (separate from `/discover/{id}` application workspace). Offset+limit pagination. **Folded in 0.7.0.15** — `archive_job` + `restore_job` now carry `user_id` boundary check (raise `PermissionError` on cross-user mutation). 8 new templates/macros (`filter_toolbar.html`, `filter_chip` macro, `_filter_hidden_inputs.html`, `job_topbar.html`, `_job_detail_body.html`, `job_detail.html`, etc.) + new `src/ui/routes/jobs.py` + `src/ui/jobs_ctx.py`. 20 net-new tests (16 route + 2 IDOR + 2 lint). Manual QA: Playwright captured `/discover`, filtered Discover, `/jobs/101` at 1440×900 + 375×812. Reviewers: architect APPROVE_WITH_NOTES (1 MEDIUM Wave 5 doc graduation deferred → `0.2.0.11a`; D.1-D.5 + IDOR all PASS); hacker APPROVE_WITH_NOTES (1 MEDIUM pre-existing CSRF gap on `/api/v1/discover/save/skip` PR widens but doesn't introduce → `0.2.0.11b`; 1 LOW `raw_meta` exposure → `0.2.0.11c`). 8 engineer deviations promoted. **0.7.0.15 closed via fold-in.** |
| 0.2.0.11a | Doc graduation for plan 36 — `docs/design/JOB_UI.md` + SCREENS.md screen #12 + COMPONENTS.md registry entries | [ ] | MEDIUM | (architect PR #112) | **Filed 2026-05-19 via PR #112 architect review (#113).** Plan 36 § Approval row 8 + Wave 5 promised graduation + COMPONENTS.md entries for 4 new components (`filter_toolbar`, `filter_chip` macro, `job_topbar.html`, `_filter_hidden_inputs.html`). Engineer punted to housekeeping commit; manager files this row instead. Run `architect-design-doc-graduation` skill next. |
| 0.2.0.11b | CSRF + IDOR on `/api/v1/discover/save/skip` — `Depends(require_csrf)` + migrate sample_data → job_service with user_id boundary | [ ] | MEDIUM | (hacker PR #112) | **Filed 2026-05-19 via PR #112 hacker review (#114).** Pre-existing fake-session bug widened by 0.2.0.11 wiring `_job_detail_body.html` Save/Skip POSTs to existing endpoints. Two fixes: (a) add `Depends(require_csrf)` to `post_skip` / `post_save` / `post_auto_submit`; (b) migrate to `job_service` with user_id boundary when fake-session retires. |
| 0.2.0.11c | Switch GET `/api/v1/jobs/{id}` to `JobRead` projection — drop `raw_meta` JSONB exposure | [ ] | LOW | (hacker PR #112) | **Filed 2026-05-19 via PR #112 hacker review (#115).** Defence-in-depth: PR #112 returns `Job.model_dump(mode="json")` which exposes `raw_meta`. Owner-only via IDOR but switch to `JobRead` projection for layered defense. Trivial fix. |
| 0.2.0.12 | Discord + Telegram notifications for new jobs | [x] | — | 2.8 | **Plan 37 EXECUTED 2026-05-19 via PR #116 squash `81b9a77` (closes #17).** Post-scrape `notify_scrape_run_summary` fan-out to Discord embeds + Telegram plain-text + Toast. Reuses Phase 1 `Settings.notifications_enabled` JSONB. Top-5 newly-inserted jobs per scrape run; duplicates excluded; URL list with company/role. Score-blind (n8n parity; scoring is 0.3.0). `notify_telegram` helper added. `_settings_notifications.html` swapped `.items()` for explicit 7-event catalog (closes pre-existing rendering hole for new users). BACKEND.md § L.3 + § L.4 + § H.3 updated. 17 net-new tests. Hacker MEDIUM (Telegram Markdown injection via scraper-controlled `role`/`company`) closed via delta commit `c4d4154`: dropped `parse_mode=Markdown` from `_send_telegram_scrape_run` + dropped header `*...*` bolding. Symmetric pre-existing path in `_telegram_text_for_event` deferred as `0.2.0.12a`. 3 deviations (BACKEND.md section + notifications catalog rewrite + D.5 Markdown→plaintext) promoted to archived plan. |
| 0.2.0.12a | Apply symmetric Telegram parse_mode/escape fix to `_telegram_text_for_event` + `send_telegram` (wave-6 high-score path) | [ ] | LOW | (hacker PR #116) | **Filed 2026-05-19 via PR #116 hacker review (#117).** Pre-existing wave-6 high-score notification has the same Markdown injection surface as `_send_telegram_scrape_run` had pre-fix. Apply identical mitigation: drop `parse_mode=Markdown` + drop `*...*` bolding. ~2 LOC + 1 test. |
| 0.2.0.13 | Rate limiting + anti-detection (random delays, throttling) | [x] | — | 2.9 | **Plan 38 EXECUTED 2026-05-19 via PR #118 squash `19a3dbf` (closes #18 + #105 / 0.2.0.13a).** New `Settings.scraper_rate_limits` JSONB col (alembic 0008; per-source `rpm`/`delay_lo`/`delay_hi` Pydantic v2 `RateLimitConfig` validates) lets operators tune without code edits; `scraper.rate_limit.resolve_rate_limit(settings, source)` returns override > class-attr fallback (with `isinstance(dict)` guard for hostile JSONB). `Crawl4AIClient` adopts `crawl4ai.RateLimiter` for 429/503 exponential backoff in `stream_many`'s `MemoryAdaptiveDispatcher` (`arun()` doesn't accept rate_limiter kwarg in 0.8.6 so `_enforce_min_interval` floor stays for `fetch_html`). New constructor kwargs `user_agent` + `use_undetected_adapter`; telemetry counters surface in `JobScrapeRun.raw_meta["rate_limit"]` + `["adapter_used"]`. `ScraperBase.rate_limit_per_minute: int → float` (LinkedIn 1 → 0.4 effective). New `src/scraper/user_agents.py` curated 8-UA round-robin. New base dep `cachetools>=5.0,<6` — `url_guard._DNS_CACHE` swap to `TTLCache(maxsize=256, ttl=60)` closes 0.2.0.13a DNS-rebind TOCTOU. `ScraperBase.use_undetected_adapter: bool = False` wiring + telemetry; engagement deferred to `0.2.0.13c`. Robots.txt explicit no-honor in SCRAPER_BASE.md § G.10. Initial round REQUEST_CHANGES (hacker HIGH HTTP endpoint silently drops `scraper_rate_limits` + 4 plan-35 kwargs + MEDIUM resolver AttributeError + LOW thread-safety); delta commit `6b96e89` wires 8 kwargs + 422 conversion + isinstance guard + TODO comment. **Carries forward a plan-35 fix** (the LinkedIn/Indeed `*_keywords`/`*_location` route kwargs were also silently dropped). 41 + 7 new tests. Graduated to `docs/design/SCRAPER_BASE.md § G`. 7 deviations promoted (alembic id length cap, RateLimiter dispatcher-only, AsyncPlaywright import path, backoff_total_s wall-clock proxy + 3 delta-round). |
**Deliverable (0.2.0):** Jobs scraped on schedule, AI-extracted, deduplicated, shown in dashboard with notifications. Vault deprecated; secrets via `.env`; CLI removed.

---

### 0.2.1 — Security cleanup (legacy DEF security rows)
> **Goal:** Defer-bucket cleanup for security-themed paper cuts from Phase 1 (JWT signing-key rotation, OIDC stub, Argon2id, JWT denylist).
> **Status:** 🟡 Queued (post-0.2.0; can interleave).
> **Plan:** Per-row plans authored when scheduled.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.2.1.01 | JWT signing-key rotation (multi-tenant cloud tier) | [ ] | — | DEF-13 | Phase 2+; single-key fine for self-hosted. From plan 10 Q7. |
| 0.2.1.02 | OIDC for self-hosted (Authentik / Keycloak / Okta) | [ ] | — | DEF-06 | Phase 2+. From SCREENS.md § Phase mapping > Deferred. |
| 0.2.1.03 | Argon2id vault upgrade (vs PBKDF2) | [x] | — | DEF-17 | **Auto-closed 2026-05-19 as moot — vault deleted in `0.2.0.01` (PR #92 squash `b91f50b`).** No PBKDF2 to upgrade to Argon2id; secrets now read from `.env` via pydantic-settings. Locked decision at PLAN_GATE for plan 26. From plan 10 Q6. |
| 0.2.1.04 | JWT denylist on password rotation (defense-in-depth for stolen pre-rotation JWTs) | [ ] | — | DEF-26 (was unfiled in Phase 1 deferred items table; gets DEF# here) | After successful `POST /api/v1/auth/change-password`, the OLD JWT remains valid for its natural TTL. A stolen pre-rotation JWT survives the rotation. Defense-in-depth fix: maintain a server-side denylist of invalidated `jti`s (or rotate the signing-key prefix per user). Lives in `services/auth.py` + a small DB table. **Filed 2026-05-17 (PR #50 hacker Finding 3).** Distinct from `0.2.1.01` (signing-key rotation, broader scope). |
| 0.2.1.05 | **CLI sunset** — depends on `0.2.0.01`. After vault deprecation ships, the only `naavik` subcommand left is `serve`; `init` / `vault status` / `vault rotate-key` are gone with the vault. Final cleanup: delete `src/cli/`, drop `[project.scripts] naavik = "cli.main:main"` from `pyproject.toml`, collapse the server entrypoint to `python -m main` or the Nix flake's `apps.default` output. Keep `naavik-alembic` (alembic's own CLI surface, not a Naavik feature). | [ ] |  | < 1 day after 0.2.0.01. Independent of scrapers (`0.2.0.06`–`0.2.0.14`). **Policy in AGENTS.md § Key Conventions § CLI:** do NOT extend the CLI in interim plans; new operator features ship in the UI. |
**Deliverable (0.2.1):** Self-hosted OIDC option + post-vault-sunset auth-hardening cleanup.

---

### 0.2.2 — UI cleanup (legacy DEF UI rows)
> **Goal:** UI polish + light mode + icon/sidebar stability paper cuts from Phase 1.
> **Status:** 🟡 Queued.
> **Plan:** Per-row plans authored when scheduled.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.2.2.01 | Light mode | [ ] | — | DEF-18 | Phase 6. From DESIGN.md. |
| 0.2.2.02 | Restore Lucide via CDN | [ ] | — | DEF-19 | Self-hosted at `/static/lucide.min.js` for now to fix "no icons render" issue. Production should serve from a CDN — investigate why unpkg failed (content-blocker / CSP / rate-limit), pick a stable URL or fallback chain, drop the local file. From plan 09a follow-up 2026-05-02. |
| 0.2.2.03 | Sidebar mobile-toggle reliability after navigation | [ ] | — | DEF-20 | Idempotent script guards fixed the most common failure mode; user reports it's "still kind of wonky" after navigating away. Repro on real device, isolate the remaining timing issue (likely Tailwind JIT vs HTMX swap order). Not a blocker. From plan 09a follow-up 2026-05-02. |
| 0.2.2.04 | Discover card max-w cap on ultra-wide screens | [ ] | — | DEF-21 | 09a-follow-up dropped the `max-w-7xl` page cap on Discover so the card fills available space. On 4K+ monitors the card may stretch >1500px and feel sparse — add a `2xl:max-w-[1400px]` cap if user feedback comes in. From plan 09a follow-up 2026-05-02. |

**Deliverable (0.2.2):** Light mode shipped; sidebar stable; Lucide CDN-served; Discover card width-capped.

---

### 0.2.3 — ATS / scraper cleanup (legacy DEF scraper rows)
> **Goal:** Long-tail ATS adapters (Workday/LinkedIn/Indeed/Generic) + scraping diagnostics that didn't make 0.2.0.07.
> **Status:** 🟡 Queued.
> **Plan:** Per-row plans authored when scheduled.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.2.3.01 | Workday / LinkedIn / Indeed / Generic ATS adapters (Greenhouse / Lever / Ashby shipped in 0.1.0.23) | [ ] | — | DEF-01 | Need credentials + Playwright + manual review queue. Greenhouse / Lever / Ashby ship in 0.1.0.23. From plan 10 § C.4. |
| 0.2.3.02 | Postmortem-on-failure: Playwright screenshot + AI summary on ATS failure | [ ] | — | DEF-03 | Surfaces in stuck-queue card; helps diagnose recurring CAPTCHA / field_mismatch. From this triage 2026-05-01. |
| 0.2.3.03 | LinkedIn proxy support | [ ] | — | DEF-15 | Phase 6+. From BACKEND.md § J.4. |

**Deliverable (0.2.3):** Full ATS coverage + scraper diagnostics + LinkedIn proxy hardening.

---

### 0.2.4 — Tracking cleanup (legacy DEF tracking rows)
> **Goal:** Tracking UI gap-fills + DRAFT-lifecycle hardening + manual-entry modal.
> **Status:** 🟡 Queued.
> **Plan:** Per-row plans authored when scheduled.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.2.4.01 | Stale-DRAFT cleanup cron (`admin.cleanup_stale_drafts`) | [ ] | — | DEF-02 | Auto-discard or auto-archive DRAFTs idle >30 days; otherwise queue accumulates. From this triage 2026-05-01. |
| 0.2.4.02 | Manual job entry modal (full) | [ ] | — | DEF-04 | `+ Add by URL` is the partial Phase 1 path. From SCREENS.md § Phase mapping > Deferred. |
| 0.2.4.03 | Application detail slide-over | [ ] | — | DEF-05 | Phase 2 introduces `/tracking/:id` route. From SCREENS.md § Phase mapping > Deferred. |
| 0.2.4.04 | `Show drafts` filter UI on Tracking | [ ] | — | DEF-08 | Endpoint stubbed in Wave 3; UI toggle Phase 1.x. From SCREENS.md § Tracking visibility rule. |
| 0.2.4.05 | Auto-apply immediate dispatch on right-swipe (vs current 5-min cron) | [ ] | — | DEF-10 | Refinement; user expectation may grow once auto-apply ships. From this triage 2026-05-01. |

**Deliverable (0.2.4):** Tracking UI feature-complete vs SCREENS.md spec; stale-DRAFTs auto-cleaned.

---

### 0.2.5 — Observability cleanup (legacy DEF observability rows)
> **Goal:** Cost-cap dashboard + submission-result analytics + rate-limit dial.
> **Status:** 🟡 Queued.
> **Plan:** Per-row plans authored when scheduled.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.2.5.01 | `Settings.scraper_aggressiveness` (rate-limit dial) | [ ] | — | DEF-11 | Phase 2+; default conservative. From this triage 2026-05-01. |
| 0.2.5.02 | Submission-result observability dashboard (failure-kind aggregates) | [ ] | — | DEF-16 | Phase 6 — helps user spot recurring board-side failures. From this triage 2026-05-01. |
| 0.2.5.03 | `Settings.daily_llm_cost_cap_usd` dashboard widget | [ ] | — | DEF-22 | Wave 6 ships the enforcement; visible cap-progress UI is a Settings polish item. From POST_PHASE_1 § Tier 3 (consolidated 2026-05-02). |

**Deliverable (0.2.5):** Operator-facing scrape + LLM cost + ATS-failure analytics dashboards.

---

### 0.2.6 — Tooling / paper-cut cleanup (legacy DEF tooling rows + A.28a)
> **Goal:** Pre-existing dev-experience papercuts (ruff cleanup, DB-test gating, NAAVIK_PERSISTENCE removal) + post-A.28 script hardening.
> **Status:** 🟡 Queued.
> **Plan:** Per-row plans authored when scheduled.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.2.6.01 | Onboarding offline retry buffer for autosave | [ ] | — | DEF-07 | Optional, not blocking MVP. From INTERACTIONS.md § H.3. |
| 0.2.6.02 | `ProfileAnswer` reuse cache (screener answer memory) | [ ] | — | DEF-09 | Phase 2+ entity. From DATA_MODEL.md § J. |
| 0.2.6.03 | Portfolio API versioning (`/api/portfolio/cv?version=v1`) | [ ] | — | DEF-12 | Lets crypticsoul.dev pin its consumer; Phase 2+. From this triage 2026-05-01. |
| 0.2.6.04 | `JobEmbedding` semantic match (pgvector) | [ ] | — | DEF-14 | Phase 6. From DATA_MODEL.md § H. |
| 0.2.6.05 | Full `NAAVIK_PERSISTENCE` env-var removal — migrate remaining ~20 lower-traffic accessors + page handlers to service-layer DB reads | [ ] | — | DEF-23 | Wave 4 partial-swap + Wave 5 partial-swap left ~20 accessors falling back to memory. Plan 10b sets `NAAVIK_PERSISTENCE=db` as orchestrator default, but the env var still gates the swap. Cleanup deserves its own plan once Phase 1 is fully verified. From this triage 2026-05-03 (post-Wave-5). |
| 0.2.6.06 | Pre-existing ruff errors in `migrations/` + `.claude/naavik_ops/lib/roadmap.py` (UP007 / UP035 / I001) | [ ] | — | DEF-24 | 10 ruff violations confirmed pre-existing via stash technique during A.15 PR review. Files: `migrations/versions/0001_initial.py` (4), `migrations/versions/0002_settings_multi_users.py` (4), `.claude/naavik_ops/lib/roadmap.py` (2). All fixable via `ruff check --fix`. ~30 min. From PR #53 devops review 2026-05-17 (Issue #55). |
| 0.2.6.07 | DB-test gating gap — 11 test files lack `_skip_if_no_db()` (asyncpg `InvalidPasswordError` on `localhost:5432`) | [ ] | — | DEF-25 | 65 pytest failures across 11 test files confirmed pre-existing via stash. Canonical pattern at `tests/test_settings_llm_form.py:17-25`. ~1h to propagate the helper. From PR #53 devops review 2026-05-17 (Issue #56). |
| 0.2.6.08 | `scripts/A.28-board-restructure.sh` hardening — eval pattern + rollback doc + apply default + ROADMAP § Agent System mirror-conventions 4-status refresh | [ ] | — | A.28a | **Filed 2026-05-17 via PR #63 hacker + devops review** (Issue #64). 3 LOW defense-in-depth findings in the migration runbook: (1) `run()` helper uses `eval` against composed string (line 54) — zero exploit today (all callers pass validated numeric Issue#s + node IDs), invites future bug if anyone interpolates Issue titles; fix = arg-array pass-through; (2) no rollback contract documented in header — script IS idempotent but recovery contract not stated; fix = 4-line comment; (3) `--apply` is silent default (lines 23-43) — bare invocation runs APPLY; fix = `DRY_RUN=true` default, require explicit `--apply`. Plus devops informational note. ~30 min engineer paper cut. **Folded to 0.2.6 (tooling/paper-cut) per theme match with rest of this patch's rows.** |

**Deliverable (0.2.6):** Repository-wide tooling cleanup; pre-existing CI/test gaps closed; script hardening complete.

---

### 0.3.0 — Intelligent Scoring & Matching (legacy Phase 3)
> **Goal:** AI compatibility scoring with tag-based profile matching and explainable results.
> **Status:** ⚪ Future.
> **Plan:** `docs/plans/12-phase-3-scoring.md` (to be authored after plan 11 ships).
> **Implementation contract:** `docs/design/BACKEND.md` § H.1 (`scorer` service), § M.3 (`score_job` prompt). DATA_MODEL.md § C (`Job.score`, `Job.score_explanation`, `Job.match_breakdown`).
> **Estimated effort:** 1–2 weeks.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.3.0.01 | Tag-based matching: job desc → identify tags → match against profile bullets | [ ] | — | 3.1 | |
| 0.3.0.02 | AI scoring: structured output (score 0-1, explanation, gap analysis) | [ ] | — | 3.2 | Cloud + local model support |
| 0.3.0.03 | Visa/sponsorship auto-filter (score 0 for citizenship-required / no-sponsorship) | [ ] | — | 3.3 | |
| 0.3.0.04 | Tailored resume preview: show which bullets selected/excluded for a job | [ ] | — | 3.4 | |
| 0.3.0.05 | One-click generation: from job detail → tailored resume + cover letter | [ ] | — | 3.5 | |
| 0.3.0.06 | Score history + analytics | [ ] | — | 3.6 | |
| 0.3.0.07 | HTMX UI: score card, match explanation, bullet selection preview | [ ] | — | 3.7 | |

**Deliverable (0.3.0):** Every job scored with explanation. User sees bullet selection preview and generates tailored docs in one click.

---

### 0.4.0 — Application Tracking & Auto-Apply (legacy Phase 4)
> **Goal:** Full application lifecycle with configurable automation level.
> **Status:** ⚪ Future.
> **Plan:** Most of Phase 4 ships inside plan 10 Wave 6 (DRAFT lifecycle, ATS submit, semi-auto + auto-apply paths). UI polish + analytics dashboard ship as a small follow-up `13a-tracking-polish.md` post-Phase-1.
> **Implementation contract:** `docs/design/BACKEND.md` § K (auto-apply + manual paths), § K.5 (ATS adapters per board), § L.1 (Gmail/Outlook OAuth). `docs/design/DATA_MODEL.md` § A multi-axis state, § E state transitions.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.4.0.01 | Application multi-axis state model: `status` (APPLIED → RECRUITER_SCREEN → ONSITE_LOOP → OFFER → CLOSED) + `closed_reason` + orthogonal sub-states `docs_state`, `referral_state`, `recruiter_state`, computed `outreach_engagement` | [ ] | — | 4.1 | State machine + transitions per axis. See `docs/design/DATA_MODEL.md` (plan 05) for authoritative definitions. |
| 0.4.0.02 | Manual application logger (form for external applications) | [ ] | — | 4.2 | |
| 0.4.0.03 | Semi-auto flow: generate docs → notification → human approves → submit → update status | [ ] | — | 4.3 | Default mode |
| 0.4.0.04 | Auto-apply flow: high-score jobs → generate → submit automatically (user setting, default OFF) | [ ] | — | 4.4 | Configurable threshold |
| 0.4.0.05 | Playwright form filling for supported boards (with optional review step) | [ ] | — | 4.5 | |
| 0.4.0.06 | Google Sheets sync (optional secondary view) | [ ] | — | 4.6 | Keep for shared tracking |
| 0.4.0.07 | Application analytics dashboard | [ ] | — | 4.7 | Response rate, interview rate, by company/role |

**Deliverable (0.4.0):** Full Kanban tracking. Semi-auto or auto-apply based on user preference. Analytics.

---

### 0.5.0 — Email Monitoring & Outreach (legacy Phase 5)
> **Goal:** Monitor emails, classify responses, manage interview prep, and track recruiter/employee outreach.
> **Status:** ⚪ Future.
> **Plans:** `docs/plans/13-phase-5-email.md` (Gmail/Outlook OAuth + classifier) → then `docs/plans/14-phase-5-outreach.md` (LinkedIn DM + Calendar + Discord/Telegram inbound). Both authored after plan 12 ships.
> **Implementation contract:** `docs/design/BACKEND.md` § L.1 (Gmail/Outlook), § L.2 (LinkedIn browser, account-ban risk), § L.3–L.5 (Discord/Telegram/Calendar), § H.1 (`email_classifier`, `outreach_generator`, `contact_tracker`).
> **Estimated effort:** Plan 13 1–2 weeks; plan 14 2–3 weeks (LinkedIn is the most fragile dep).

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.5.0.01 | Gmail API / IMAP email monitoring | [ ] | — | 5.1 | Connect to user's email inbox |
| 0.5.0.02 | AI email classification: INTERVIEW_REQUEST, REJECTION, OFFER, ASSESSMENT, FOLLOW_UP | [ ] | — | 5.2 | |
| 0.5.0.03 | Auto-update job status from email classification | [ ] | — | 5.3 | |
| 0.5.0.04 | Priority notifications (HIGH for interviews/offers) | [ ] | — | 5.4 | |
| 0.5.0.05 | Email thread tracking per application | [ ] | — | 5.5 | |
| 0.5.0.06 | AI draft response generation | [ ] | — | 5.6 | |
| 0.5.0.07 | Interview scheduling integration (Calendly/webhook) — surfaces on Tracking application detail and Overview priority actions | [ ] | — | 5.7 | |
| 0.5.0.08 | Interview prep: role-specific questions from job desc + profile gaps | [ ] | — | 5.8 | |
| 0.5.0.09 | LinkedIn connection tracker: store recruiter/employee contacts per company | [ ] | — | 5.9 | |
| 0.5.0.10 | Outreach template system: personalized messages for recruiters + employees | [ ] | — | 5.10 | Uses profile + job context |
| 0.5.0.11 | AI-generated outreach messages: referral requests, follow-ups, check-ins | [ ] | — | 5.11 | Tone-appropriate, not spammy |
| 0.5.0.12 | LinkedIn automation: send connection requests + messages via API | [ ] | — | 5.12 | Rate-limited, anti-detection. **Re-open `docs/design/research/LINKEDIN_SCRAPING.md` option matrix when authoring plan 14** — § 5 stack-rank flags stickerdaniel/linkedin-mcp-server (1.9k stars, Apache-2.0, Patchright-based) as the front-runner for the outreach surface because authenticated session is unavoidable here, unlike 0.2.0.07 where the guest API wins. |
| 0.5.0.13 | Outreach history tracking: sent messages, responses, acceptance rates | [ ] | — | 5.13 | |
| 0.5.0.14 | Warm intro finder: suggest mutual connections for warm outreach | [ ] | — | 5.14 | LinkedIn API |
| 0.5.0.15 | Interview process accelerator: auto-send thank-you notes, follow-up reminders | [ ] | — | 5.15 | |

**Deliverable (0.5.0):** Email inbox monitored → job statuses auto-updated. Recruiter/employee contacts tracked → AI-assisted outreach → referral requests sent at optimal timing.

---

### 0.6.0 — Optimization & Polish (legacy Phase 6)
> **Goal:** Performance, analytics, and advanced features.
> **Status:** ⚪ Future.
> **Plan:** `docs/plans/15-phase-6-polish.md` — splits cleanly into 15a (observability — Prometheus + Sentry + OTel), 15b (light mode), 15c (LaTeX template + ML scoring calibration). Author after plan 14 ships.
> **Implementation contract:** `docs/design/BACKEND.md` § N (observability — Prometheus, Sentry, OTel), `docs/design/DATA_MODEL.md` § H (`JobEmbedding` pgvector for semantic match), `DESIGN.md` (light mode tokens — Phase 6).
> **Estimated effort:** 3–4 weeks total (split across 15a/b/c).

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.6.0.01 | Resume A/B testing (track which variants get responses) | [ ] | — | 6.1 | |
| 0.6.0.02 | Semantic job matching with pgvector embeddings | [ ] | — | 6.2 | |
| 0.6.0.03 | Weekly summary reports | [ ] | — | 6.3 | |
| 0.6.0.04 | Performance: caching, batch AI calls, parallel scraping | [ ] | — | 6.4 | |
| 0.6.0.05 | ML scoring calibration from application outcomes | [ ] | — | 6.5 | |
| 0.6.0.06 | LaTeX template support alongside Typst (for users who prefer LaTeX) | [ ] | — | 6.6 | NEU template compat, latexmk/tectonic compilation |
| 0.6.0.07 | Additional Typst/LaTeX resume templates (modern, academic, creative) | [ ] | — | 6.7 | Template marketplace |

**Deliverable (0.6.0):** Observability stack live; light mode shipped; LaTeX template parity with Typst; ML-calibrated scoring.

---

### 0.7.0 — Agent-system follow-ups (legacy Phase 2.5)
> **Goal:** Quality-of-life improvements + nice-to-have agent-system features deferred until Phase 2 (job scrapers) clears. None blocks the product; all surfaced during Phase A bring-up.
> **Status:** ⚪ Future (deferred per user lock 2026-05-17; ships post-0.2.0 cycle clears).
> **Plan:** No single plan — each row gets its own plan when scheduled (post-Phase-2 user pickup).
> **Mirror milestone:** `0.7.0` (recreated by migration step 4; supersedes `Phase 2.5`).
> **Mirror epic:** `[Epic] 0.7.0`.
>
> User-locked scope decision 2026-05-17: A.22 carries HIGH priority within Phase 2.5 but still defers — Tier 1 / Tier 2 work clears first per pre-Phase-2 scope lock.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.7.0.01 | Cap retention on `traces/` (auto-delete runs > N days) | [ ] | — | A.9 | Today: manual delete. Add a `traces/.cleanup.sh` cron-style helper once accumulation gets noisy (>50 runs). |
| 0.7.0.02 | Visual run dashboard (web UI for `traces/runs.log`) | [ ] | — | A.10 | Nice-to-have. Current state: `claude /runs` + `./traces/watch.sh` cover the inspection use cases. |
| 0.7.0.03 | Architect-as-PR-reviewer (replaces devops in review role) | [ ] | — | A.18 | **Filed 2026-05-17 — deferred until after Phase 2.** User directive: *"moving forward i want the architect to review the PR and not the devops."* Rationale: architect's option-matrix lens fits PR reviews. Open: does devops stay for build-gate re-verify (ruff/pytest clean-shell) while architect does code-correctness + plan-fidelity, OR does devops fully exit PR-review duty? |
| 0.7.0.04 | Security review bar — Claude-Mythos-style depth | [ ] | — | A.19 | **Filed 2026-05-17 — deferred until after Phase 2.** User directive: *"there will be security review similar to the one that claude mythos provides."* Target: deeper STRIDE per-feature + supply-chain checks (dependency CVE scan, lockfile drift) + secret-rotation hygiene + auth-flow modeling + LLM prompt-injection vectors for scrapers. |
| 0.7.0.05 | PR review verdicts stored in repo (not only GitHub) | [ ] | — | A.20 | **Filed 2026-05-17 — deferred until after Phase 2.** User directive: *"the approved with notes is good but it should be stored in the repo not left on github."* Target: also persist to repo as `traces/<run-id>/pr-reviews/<pr-num>.md` AND/OR `docs/reviews/<pr-num>-<slug>.md`. Survives GitHub data loss; greppable history; works offline. Format: machine-readable per A.16 (now 0.1.0.44). |
| 0.7.0.06 | Progress indicator — flow visualizer like Jenkins pipeline | [ ] | — | A.21 | **Filed 2026-05-17 — deferred until after Phase 2.** User directive: *"somewhere in the PR or in claude code when im building it shows what step we are at."* Three candidate surfaces (architect picks): (a) PR body section auto-updated, (b) chat preamble line, (c) `.claude/current-step.json` file. ~1-2 engineer days. |
| 0.7.0.07 | Confusion-gate clause — ask user on ambiguity even in auto mode; technical decisions OK, business decisions always user | [ ] | HIGH | A.22 | **Filed 2026-05-17 — deferred until after Phase 2 (HIGH within 0.7.0 but cycle defer).** User directive: *"add a clause to always ask questions if the requirement is confusing or there are multiple paths forward."* Scope: extend `docs/PLAYBOOK.md` with explicit confusion-gate clause + decision-class taxonomy (technical vs business vs critical). |
| 0.7.0.08 | State-of-the-art security review tools (replace standard Claude Code hacker tooling) | [ ] | — | A.23 | **Filed 2026-05-17 — deferred until after Phase 2.** User directive: *"instead of using the standard claude code tools for security review."* Target: integrate SoTA SAST/DAST/SCA tools — Semgrep, CodeQL, Snyk/Trivy, gitleaks, pip-audit, OWASP ZAP, plus LLM-specific (prompt-injection detectors, jailbreak scanners). |
| 0.7.0.09 | State-of-the-art architect tools | [ ] | — | A.24 | **Filed 2026-05-17 — deferred until after Phase 2.** Target: add architecture-visualization + ADR tooling — Structurizr (C4 model), Mermaid (sequence + state diagrams, gh-native), PlantUML, diagrams.net, OpenAPI/AsyncAPI generators, dependency graph tools, ADR-tools. |
| 0.7.0.10 | State-of-the-art designer tools — wire huashu-design + similar | [ ] | — | A.25 | **Filed 2026-05-17 — deferred until after Phase 2.** User directive: *"for designer we are not using huashu design tooling. we need to use that."* Target: surface `huashu-design` as PRIMARY designer skill. |
| 0.7.0.11 | Trace analytics dashboard — simple metrics script | [ ] | — | A.26 | **Filed 2026-05-17 — deferred until after Phase 2.** Simple stdout script (`scripts/trace-analytics.py` or `scripts/agent-metrics.sh`) reads `traces/<run-id>/MANIFEST.json` × N + `traces/runs.log` and prints aggregate metrics. NOT a web UI (that's 0.7.0.02). Reads-only the trace logs. ~1 engineer day. |
| 0.7.0.19 | Tighten `JobCreate.source_url` type to `pydantic.HttpUrl` | [ ] | — | A.36 (hacker PR #95 INFO) | **Filed 2026-05-19** — hacker INFO on PR #95. URL validation at boundary catches malformed scraper output. Trivial fix; defer to 0.2.0.06+ when scrapers populate field. |
| 0.7.0.23c | Plan 41 D.7 — `tests/test_workflow_invariants/` commit-time lint suite (parallel-reviewer + deviations + fold-in) | [ ] | MEDIUM | (architect PR #127 HIGH) | **Filed 2026-05-19 via PR #127 architect HIGH partial-impl finding (#130).** Plan 41 D.7 not implemented in PR #127 (omnibus shipped PR-A only). 6 lint tests deferred per architect verdict that "engineer-manual-qa-gate would have caught mass-replace artifacts" — these tests automate that. Wire into CI gate. |
| 0.7.0.23b | Plan 41 D.5 — `MODEL_PICK` trace event in `manager.log` for dispatch-time model decisions | [ ] | LOW | (architect PR #127 HIGH) | **Filed 2026-05-19 via PR #127 architect HIGH partial-impl finding (#129).** Plan 41 D.5 not implemented. Per-dispatch trace event: `[ts] MODEL_PICK agent=<x> model=<opus-4-7\|opus-4-7[1m]> estimated_tokens=<n>` for retrospective analysis of model-selection accuracy. ~10 LOC + 1 test. |
| 0.7.0.23a | Plan 41 D.3 — twin agent variants `architect-1m.md` + `engineer-1m.md` for token-based model selection | [x] | MEDIUM | (architect PR #127 HIGH) | **Filed 2026-05-19 via PR #127 architect HIGH partial-impl finding (#128).** PR #127 shipped manager.md § Token-based model selection prose + flipped architect/engineer base from `[1m]` to non-`[1m]`, but did NOT ship the twin files. Task tool's `model` enum only accepts `sonnet\|opus\|haiku` per plan 41 OQ.1 research — twins are the workaround for fine-grained 1m selection. Ship `architect-1m.md` + `engineer-1m.md` as frontmatter-only copies with `model: claude-opus-4-7[1m]`; manager dispatches to twin variant when scope ≥60K. **CLOSED 2026-05-19 as RESOLVED-BY-DESIGN per user directive (no twin files; manager picks at dispatch via Task  enum override).** Frontmatter stays  default;  override drops  for small dispatches;  for tiny ones. Encoded in . |
| 0.7.0.24 | Requirement-slot feedback cadence — manager prefixes every user-directive response with a one-line `Slotted: <task-id> — <title> — <plan> — <PR>. Status: ...` ack | [~] | MEDIUM | (user directive 2026-05-19 — audit request) | **Filed 2026-05-19 via user audit "where did we log all the requirements i gave can you give me a rundown again and where they get slotted. and which ones did we already do? we need to make this a cadence you need to show me the version you added each one to when i give you requirements".** Codified in `manager.md` § Requirement-slot feedback (new section before § Dynamic resource allocation). Cadence rule: every new directive (not status query, not gate response) gets the slot ack as FIRST line of manager response. Includes the auto-log routing table (code/decision/discussion/run-event). Folded into PR #127 (omnibus). |
| 0.7.0.23 | Manager evolution + model selection + bookkeeping fold-in (plan 41 PR-A activated via PR #127 — D.3/D.5/D.7 deferred to 0.7.0.23a/b/c) | [~] | MEDIUM | (user directive) | **Plan 41 PR-A activated 2026-05-19 via PR #127 omnibus. PR-A shipped:** (a) manager staff-engineer coding lane (manager.md § Dynamic resource allocation); (c) timing-based bookkeeping fold-in (manager.md + PLAYBOOK.md § I revised); (b-partial) base model flip on architect/engineer to non-`[1m]` + § Token-based model selection prose. **D.3 twin agents → 0.7.0.23a (#128) deferred.** **D.5 MODEL_PICK trace → 0.7.0.23b (#129) deferred.** **D.7 lint suite → 0.7.0.23c (#130) deferred.** **D.8 two-PR sequencing → folded into followups.** Original plan body at Bundles 5 interrelated process changes: (a) manager staff-engineer coding lane (manager.md:9 + Anti-patterns revision); (b) twin agent variants (`architect-1m.md` + `engineer-1m.md`) for token-budget-based model selection (60K threshold; <60K → `opus-4-7`; ≥60K → `opus-4-7[1m]`); (c) timing-based bookkeeping fold-in (fold when PR open + related; exceptions: gitignored, security, personal); (d) `tests/test_workflow_invariants/` 6-lint suite shifting detection from PR-review-time → commit-time; (e) two-PR sequencing. Empirical evidence from run `2026-05-19T15-42-42_833f4a`: 14 direct-push bookkeeping commits since PR #91 (11 foldable); 22 architect dispatches range 38-260K (18% under 50K, 27% under 60K); parallel-reviewer invariant violated 2x; 5/8 plans archived w/o deviations section. |
| 0.7.0.22 | ROADMAP Backlog section + parser/task/sync recognition | [~] | MEDIUM | (plan 40) | **Plan 40 IN FLIGHT 2026-05-19 — DRAFT at `docs/plans/40-roadmap-backlog-section.md`.** Adds `## Backlog (unprioritized)` section to ROADMAP for future-eligible-but-unprioritized work. Teaches `.claude/naavik_ops/{lib/roadmap.py, task.py, gh.py}` to recognize as synthetic release-version `backlog`. First migrant: `0.2.0.14` n8n migration deferred (not closed-as-moot — historical-data import still possible). Engineer dispatch pending. |
| 0.7.0.21d | Partial-write rollback in `naavik_ops/plan.py` — `git mv` failure leaves plan mutated at source; capture pre-write text + restore on failure | [ ] | LOW | (hacker PR #120) | **Filed 2026-05-19 via PR #120 hacker review (#124).** Defense-in-depth: any `git mv` error (dirty tree, file outside repo) leaves plan file mutated at original path with section + Status: EXECUTED. Operational confusion, not exploitable. Fix: `try/except` around the file-write + git-mv pipeline; restore on failure. ~10 LOC + 2 tests. |
| 0.7.0.21c | `validate-deviations` should accept paragraph-style "No material deviations" as PASS, not just bullets | [x] | LOW | (dogfood discovery) | **Filed 2026-05-19 via dogfood scan.** Plan 32 retrofit uses paragraph form ("No material deviations.") — `validate-deviations` currently BLOCKs it. Either: tighten regex to detect non-empty content + sentinel phrase, OR convert plan 32 retrofit to bullet form. ~5 LOC + 1 test. **CLOSED 2026-05-19 via PR #127 squash 473d9b6 — anchored regex  multiline; 7 regression tests in test_plan.py::TestNoMaterialDeviationsSentinelAnchored.** |
| 0.7.0.21b | Bullet shape — `entry_to_bullet` should insert periods between `what`/`why`/`impact`/`surface` per plan 39 § C.7 | [ ] | LOW | (architect PR #120) | **Filed 2026-05-19 via PR #120 architect review (#122).** Cosmetic — current output reads `what: X why: Y impact: Z surface: S` without periods. ~1 LOC + 1 test. |
| 0.7.0.21a | Path-traversal hardening in `naavik_ops/plan.py:_resolve_plan_path` — constrain to `docs/plans/` via `relative_to` + reject if `ARCHIVE_DIR in parents` | [ ] | MEDIUM | (hacker PR #120) | **Filed 2026-05-19 via PR #120 hacker review (#121).** `_resolve_plan_path` accepts any `.md` path on disk — operator-only attack surface but allows mutation of arbitrary repo `.md` with Status: EXECUTED + forged Deviations. Fix: scope-check against `PLANS_DIR`; reject if path already in `ARCHIVE_DIR`. ~5 LOC + 2 tests. |
| 0.7.0.21 | `naavik-ops plan archive` subcommand — hard-stop deviation promotion at archive | [x] | HIGH | A.39 | **Plan 39 EXECUTED 2026-05-19 via PR #120 squash `b4346f4` (closes #119).** New `.claude/naavik_ops/plan.py` provides `plan archive <plan-path>` (canonical/only archive path) + `plan validate-deviations` (read-only PASS/BLOCK). Three UX paths: happy / empty-section-empty-log refusal exit 2 / `--no-material-deviations "<rationale>"` explicit / `--force` short-circuit. Replaces manual `git mv` per AGENTS step 7-8 + PLAYBOOK § I + CLAUDE.md + AGENT_OPS § 2.7a + manager.md step 11 + engineer.md hand-back. 22 net-new tests. **Dogfood**: plan 39 archived via the new command (5 bullets lifted from `engineer-deviations.log`). Reviewers: hacker APPROVE_WITH_NOTES (1 MEDIUM `0.7.0.21a` + 1 LOW `0.7.0.21d`); architect APPROVE (1 LOW `0.7.0.21b`). Plus 1 dogfood-discovery follow-up `0.7.0.21c`. 5 engineer deviations promoted via the new command's own pipeline. |
| 0.7.0.20 | Codify parallel reviewer invariant — manager.md hard-stop pre-flight + PLAYBOOK.md alignment | [x] | — | A.38 | **EXECUTED 2026-05-19 via PR #99 squash `08d2e3a`.** Added § Parallel reviewer invariant to `.claude/agents/manager.md` (top-level non-negotiable section between § Identity invariant and § GitHub state) with explicit pre-flight check: before submitting any reviewer-dispatch message, verify it contains TWO `Agent` tool calls (hacker + architect), not one. Strengthened `docs/PLAYBOOK.md` § D step 3 + § F step 9 + § H step 7 with identical single-message-two-Agent-calls language. Self-approval pivot symmetrized to existing `.claude/memory/knowledge/hacker-self-approval.md` (dispatch always, GitHub state pivots to COMMENTED). Captured after run `2026-05-19T15-42-42_833f4a` violated the invariant twice in one run despite existing language in 4 places. Architect REQUEST_CHANGES round-1 (HIGH scope leak from wrong branch base) resolved by rebase on main + force-push; both reviewers APPROVE round-2. |
| 0.7.0.18 | `JobUpdate` schema should `exclude` the `score` field (computed by scoring pipeline) | [ ] | — | A.35 (hacker PR #95 INFO) | **Filed 2026-05-19** — hacker INFO on PR #95. Prevents accidental score overwrite via API. Trivial fix; defer to 0.3.0 scoring sub-task. |
| 0.7.0.17 | `JobScrapeRun.errors[]` ARRAY needs schema guard against secret leakage | [ ] | — | A.34 (hacker PR #95 LOW) | **Filed 2026-05-19** — hacker LOW on PR #95. Forward-looking: Phase 2 scrapers may capture exception messages with tokens/cookies/URL params. Add `_redact_url` helper + cap entries at 200 chars. Fix BEFORE 0.2.0.07 (site scrapers wire exception capture). |
| 0.7.0.16 | Tighten visa_restrictions backfill: replace `LIKE '%sponsorship%'` with exact-match SQL CASE | [ ] | — | A.33 (hacker PR #95 LOW) | **Filed 2026-05-19** — hacker LOW on PR #95. Migration backfill over-broad; misclassifies hypothetical no_sponsorship strings as candidate-friendly. Trivial SQL CASE rewrite; defer to 0.2.5 cleanup cycle. |
| 0.7.0.15 | Add `user_id` boundary check to `archive_job` / `restore_job` (IDOR pattern propagation) | [x] | MEDIUM | A.32 (hacker PR #95 MEDIUM) | **CLOSED via fold-in to PR #112 (`0.2.0.11`) squash `47d78ec`.** `archive_job(session, *, user_id, job_id)` + `restore_job(...)` now require user_id; raise `PermissionError` on cross-user mutation. UI wiring in 0.2.0.11 routes uses scoped helpers + `_job_or_404` conflates `None/wrong_user/soft_deleted → 404` (no enumeration leak). 2 new IDOR tests in `tests/test_job_service.py`. |
| 0.7.0.14 | Fix 2 pre-existing pytest failures on main (`test_lazy_visit_shows_cta_no_draft` + `test_login_signup_mode_renders_signup_form`) | [ ] | — | A.31a (engineer deviation #4 from plan 27) | **Filed 2026-05-19** — discovered during plan 27 PR #95 dispatch. Both fail on a fresh `main` worktree, unrelated to job-models work. PR #95 deselects them for green-bar; this row tracks the proper fix. Likely flaky fixtures / state assumption. |
| 0.7.0.13 | Fix `task move` position-stability + add `gh clear-priority` + codify principle in 5 docs + restore 12 corrupted GH titles | [x] | MEDIUM | A.31 | **Plan 28 EXECUTED 2026-05-19 via PR #94 squash `70ee0d3` (closes #93).** Bug surfaced in run `2026-05-19T05-40-56_194aa5` when `task move 0.2.0.02 0.2.1.05` auto-renumbered ~10 sibling tasks. Shipped: (A) `cmd_move` gap-only on source + reject-on-collision on dest; (B) new `gh clear-priority` subcommand via `clearProjectV2ItemFieldValue` GraphQL mutation; (C) 5-doc codification of patch-position-stability principle; (D) 12 GH titles restored (`#62→[0.2.0.03]`, `#70→[0.2.0.04]`, `#15→[0.2.0.05]`, `#10→[0.2.0.06]`-`#19→[0.2.0.14]`; `#21` correctly at `[0.2.1.05]`). 4 commits W0-W3 + audit anchor; 217 tests passing (+8 new). Hacker APPROVE (2 INFO non-blocking); architect APPROVE FULL spec match (1 INFO naming). Memory knowledge entry at `.claude/memory/knowledge/patch-version-position-stability.md`. 3 deviations promoted to archived plan. |
| 0.7.0.12 | `develop` branch workflow — move PR target away from `main` | [ ] | — | A.27 | **Filed 2026-05-17 — deferred (user-flagged future move).** Action when scheduled: (1) create `develop` branch from `main`; (2) shift PR targets from `main` to `develop`; (3) keep `main` as release/stable + periodic `develop → main` promotion PR; (4) update PLAYBOOK + manager + repo settings. Open: BOOKKEEPING commits routing TBD. **Couples with A.29 release-tag implications** — release branches per MINOR? Release-branch promotion ceremony? A.27 owns the decision. |

**Deliverable (0.7.0):** Pickup queue for quality-of-life work after the scrapers ship. New rows added via `.claude/naavik-ops gh create-issue 0.7.0.NN "..." --milestone "0.7.0"`; rows graduate to active `0.2.X` or `0.3.0`+ release when scheduled.

---


## Backlog (unprioritized)

Tasks deferred from active cycles but not deleted. No priority within Backlog; pick by inspection or promote to a release section via `.claude/naavik-ops task move <id> <release>.NN` when ready. Project v2 board mirrors these to `Status=Backlog`.

| # | Task | Status | Priority | Legacy ID | Notes |
|---|---|---|---|---|---|
| 0.2.0.14 | Migrate existing n8n DataTable + Google Sheets data to PostgreSQL — historical-data import | [ ] | — | 2.10 | **Deferred 2026-05-19 per user directive.** Every n8n-functional-equivalent already shipped via 0.2.0 (scrapers / scheduler / notifications / dedup / Application table). Only remaining purpose is historical-data import. User to decide whether to ship (if meaningful n8n history) or close-as-moot (if starting fresh in Naavik). Service-layer importer skeleton was `services/legacy_import.py` per BACKEND.md § J.5; one-time CSV → DB. |

**Deliverable (Backlog):** none — this section is a parking lot. Items promoted to a release-version section trigger their own deliverable. Items closed-as-moot (`[x]`) document the reason inline.

---

## Agent System (mirror conventions)

> **Companion docs:** `docs/AGENT_OPS.md` (single operational guide), `AGENTS.md` § Agent System (workflow integration), `.claude/agents/` (full agent prompts), `.claude/commands/` (slash commands).
>
> **Reference guides loaded by agents on cold start:**
> - `ROADMAP.md` — one-page roadmap digest (faster than this 800-line doc)
> - `docs/ARCHITECTURE.md` — layer responsibilities + cross-cutting concerns + pattern catalog
> - `DESIGN.md` (root) — visual contract (tokens, type, icons, voice; frozen) + `docs/design/WORKFLOW.md` — UI sub-process (skill routing, per-screen checklist, accessibility, common patterns, anti-patterns)
> - `docs/DEPLOYMENT.md` — 4 deployment paths + config + ops checklist
> - `docs/RUNBOOK.md` — devops runbook (known failure modes + diagnostic recipes + recovery)
> - `docs/plans/POST_PHASE_1.md` — testing playbook + monitoring + "when something goes wrong"
> - `docs/design/PHASE_NUMBERING.md` — 4-level semver schema + release ceremony + Conventional Commits (post-A.29)

This ROADMAP is mirrored onto a GitHub Project v2 board for queryability and assignability. **ROADMAP is authoritative** (per AGENTS.md § Single-doc-tracking); the Project is a one-way operational mirror. The mapping is mechanical (post-A.29):

| ROADMAP element | GitHub Project equivalent |
|---|---|
| `### <X.Y.Z> — <Name>` release header | Milestone `<X.Y.Z>` (description = `**Goal:**` line) |
| Task row in a release table | Issue titled `[<X.Y.Z.NN>] <description>`, body links back to ROADMAP |
| `[ ]` / `[~]` / `[x]` status | Project Status field: `Backlog` (deferred) / `Todo` / `In Progress` / `Done` |
| Priority column (`HIGH` / `MEDIUM` / `LOW` / unset; TASK-level only) | Project Priority single-select (4-level IDs only; never on 3-level patches/releases) |
| Release header | Project Milestone single-select (`0.1.0`–`0.6.0`, `0.1.1`, `0.2.1`–`0.2.6`, `0.7.0`) |
| Notes column | Issue body |
| Plan reference (`docs/plans/NN-name.md`) | Label `plan:<NN>` on the Issue |

**Sync flow:** always ROADMAP → Project. Manager updates ROADMAP first (mark `[~]` on start, `[x]` on done), then runs `.claude/naavik-ops gh set-status` to push to Project. `/sync-roadmap --apply` is the bulk reconcile. If the Project drifts from ROADMAP, the Project is wrong — never edit ROADMAP to match a stale board.

**Bootstrap:** `.claude/naavik-ops gh bootstrap [--apply]` parses ROADMAP's task tables and creates Milestones + Issues + Project items for the active releases (defaults to `0.2.0` + `0.2.1`–`0.2.6` + `0.7.0` open releases; closed `0.1.0` is skipped). See `docs/AGENT_OPS.md` § 2 for the full setup walkthrough.

**What to do as a plan / task author:**
1. Write the task row in ROADMAP first (status `[ ]`, with optional Priority on 4-level IDs).
2. Run `/plan <task-id>` — architect drafts the plan, opens the GH Issue (via `.claude/naavik-ops gh create-issue`), adds to Project, links back to ROADMAP.
3. Run `/build <release>` (or `/build "next"`) when ready to implement.

**What to do as an implementer:**
1. Mark the ROADMAP row `[~]` when starting.
2. Reference the Issue in commits: `Closes #<N>` in the last commit triggers GH's auto-close on merge.
3. Mark the ROADMAP row `[x]` + add a one-line deliverable note when done.
4. `/build` handles steps 1 + 3 automatically; manual implementers do them by hand.
