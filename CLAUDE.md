# CLAUDE.md

> **For Claude Code sessions.**
> **Canonical guide:** `AGENTS.md` — always read that first.
> **Last updated:** 2026-05-20 (Plan 52 / `0.2.3.02` EXECUTED — ATS postmortem-on-failure. New `src/services/ats_postmortem.py:capture_postmortem` runs from `application_service._record_failure` on every DRAFT submission failure (Greenhouse/Lever/Ashby HTTP adapters); writes `<DATA_DIR>/data/postmortems/<application_id>/<utc-ts>/{trace.json,analysis.md}` atomically. New Pydantic v2 schema `src/llm/prompts/ats_postmortem.PostmortemAnalysis` (`Literal[failure_kind]` + bounded summary/action lengths) drives LLM classification via `llm_tracker.tracked_call(prompt_name="ats_postmortem")`. LLM-unconfigured → trace-only postmortem with placeholder analysis (graceful degrade). Best-effort capture: any internal exception → log + return None; `_record_failure` itself never raises. New `submission_artifacts.last_failure.postmortem_path: str | null` JSONB sub-key (no migration — opaque blob) holds relative path stem. New `GET /api/v1/applications/{id}/postmortem/{ts}` returns `{trace, analysis_markdown}` envelope; IDOR via owner check returns 404 on cross-user, path-traversal blocked via `\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z` regex + `Path.resolve().relative_to(data_root)` containment. `up_next_card.html` restructured (outer wrapper `<div>` + absolute-positioned card link) so the new "postmortem" chip-link sibling renders without nested anchors. `discover_ctx.stuck_views` now threads `application_id` into the card-dict. 16 new tests in `tests/test_ats_postmortem.py` (capture + redaction + cap + LLM-unavailable + idor + path-traversal + ts-format + retrieve happy-path). No new env var / CLI subcommand / vault scope / port / scheduled job / alembic migration. Canonical sub-shape reference: `docs/design/DATA_MODEL.md § Application` (graduated inline from plan 52).)
>
> Earlier line: 2026-05-19 (Plan 38 / `0.2.0.13` EXECUTED — rate limiting + anti-detection. New `Settings.scraper_rate_limits` JSONB column (alembic 0008, nested per-source dict keyed by `JobSource.value`; Pydantic v2 `RateLimitConfig` validates) lets operators tune per-source `rpm` / `delay_lo` / `delay_hi` without code edits; `scraper.rate_limit.resolve_rate_limit(settings, source)` returns operator override > class-attr fallback. `Crawl4AIClient` adopts `crawl4ai.RateLimiter` for 429/503 exponential backoff (wired into `MemoryAdaptiveDispatcher.rate_limiter` in `stream_many`; `arun()` doesn't accept rate_limiter in 0.8.6 so `_enforce_min_interval` floor stays for `fetch_html`); new constructor kwargs `user_agent` + `use_undetected_adapter`; counters `rate_limit_hits` + `backoff_total_s` + `user_agent` property surface as telemetry in `JobScrapeRun.raw_meta["rate_limit"]` + `["adapter_used"]`. `ScraperBase.rate_limit_per_minute: int → float` (LinkedIn class attr `1 → 0.4`; effective ~24/hr). New `src/scraper/user_agents.py` curated 8-UA round-robin pool. New `src/scraper/rate_limit.py` resolver + Pydantic config model. `scraper.url_guard._DNS_CACHE` swapped from `@lru_cache` to `cachetools.TTLCache(maxsize=256, ttl=60)` — closes `0.2.0.13a` Issue #105 DNS-rebind TOCTOU. New base dep `cachetools>=5.0,<6`. `ScraperBase.use_undetected_adapter: bool = False` class attr ships wiring + telemetry; engagement deferred to `0.2.0.13c` follow-up gated on observed 403-rate (Indeed). Robots.txt explicit no-honor policy documented in `SCRAPER_BASE.md § G.10`. 41 new tests (UA pool composition + rotation + freshness, RateLimitConfig validator + resolver + Settings round-trip, alembic 0008 round-trip, RateLimiter wiring + 429/503 counter increment + UndetectedAdapter branch, TTL cache bounds, scheduler reads override, scraper_service writes telemetry). Canonical: `docs/design/SCRAPER_BASE.md § G` (graduated from plan 38 — replaces the prior "interface only" stub). No new CLI / vault / env / on-disk artifact surface — sole on-disk addition is the `scraper_rate_limits` JSONB column.)
>
> Earlier line: 2026-05-19 (Plan 29 / `0.2.0.06` EXECUTED — Crawl4AI scraper substrate. New `src/scraper/` layer: `types.py` (RawJob 17-field Pydantic v2 DTO w/ `extra="forbid"` + `*_hint` enum hints + ScrapeQuery), `base.py` (`ScraperBase(ABC)` matching `LLMProvider(ABC)` convention; `async def scrape(query) -> AsyncIterator[RawJob]`; class-level `rate_limit_per_minute=30` + `random_delay_seconds=(1.0, 3.0)`), `crawl4ai_client.py` (`Crawl4AIClient` wraps `AsyncWebCrawler` w/ `enable_stealth=True`; `fetch_html(url)` + `stream_many(urls)`), `sites/__init__.py` (registry stub) + `sites/sample.py` (test fixture; NOT registered for production). New `src/services/scraper_service.py:run_scraper` orchestrates JobScrapeRun lifecycle (RUNNING → SUCCESS/PARTIAL/FAILED/TIMED_OUT) consuming plan-27 `job_service.upsert_job` + `record_scrape_run`. Deps: `crawl4ai==0.8.6` exact pin (post-litellm-hotfix); `playwright>=1.58.0,<1.59` PROMOTED from dev extras to base deps (Crawl4AI imports Playwright at module-import time). 43 new tests (RawJob validation, ABC enforcement, Crawl4AIClient w/ `_FakeAsyncCrawler` mock, SampleScraper materialization, JobScrapeRun status derivation across 7 lifecycle outcomes). No new CLI / vault / env / on-disk artifact surface. Nix flake / Docker Chromium binary install DEFERRED to `0.2.0.07` per OQ.5 — tests mock Crawl4AI entirely. Canonical: `docs/design/SCRAPER_BASE.md` (graduated from plan 29). BACKEND.md § J.1 collapses `list_jobs + fetch_detail + matches` sketch to single streaming `scrape() -> AsyncIterator[RawJob]` per plan § D.5.)
>
> Earlier line: 2026-05-19 (Plan 27 / `0.2.0.05` EXECUTED — Job model hardening + `JobScrapeRun` scrape-side observability. 6 new `Job` columns: `external_id` (NOT NULL after sha1 backfill, partial-unique on `(user_id, source, external_id) WHERE deleted_at IS NULL` — primary dedup constraint), `remote_policy` (NOT NULL default `UNKNOWN`), `seniority_level` (nullable), `posted_at_text`, `description_extracted_at`, `description_extraction_model`, `last_scrape_run_id` (FK → `job_scrape_run.id`). `Job.visa_restrictions` promoted from `str | None` to typed `VisaRestriction` enum (4 values). New `JobScrapeRun` SQLModel + table (17 cols + 2 CHECK + 3 indexes) — one row per scraper-invocation; carries `(source, status, started_at, finished_at, requests_made, listings_returned, new_jobs, updated_jobs, errors[], duration_ms, raw_meta)`. 4 new Postgres ENUM types: `visarestriction` (4), `remotepolicy` (4), `senioritylevel` (7), `jobscrapestatus` (5). `JobSource` enum: 9 per-source values added (LINKEDIN / WORKDAY / GREENHOUSE / LEVER / ASHBY / INDEED / COMPANY_DIRECT / RSSHUB / N8N_LEGACY); `AUTOMATED` rows remapped to per-board values; the dangling `automated` member lingers in the Postgres ENUM type only (no clean `DROP VALUE` pre-PG16; follow-up `0.2.5.NN` cosmetic cleanup row planned). Alembic 0005 additive (autocommit_block for `ALTER TYPE ADD VALUE`, then `UPDATE ... USING board::text::jobsource`). New `src/services/job_service.py` (8 functions per plan § D.9): `upsert_job` (idempotent on `(user_id, source, external_id)`; merges `raw_meta`; field-level diff deferred to `0.2.0.09`), `get_job`, `list_jobs` (filtered + ordered + soft-delete-aware), `archive_job` / `restore_job` (collision-aware), `create_manual_job` (synthetic `external_id = manual-<uuid4>[:12]`), `count_jobs_by_source`, `record_scrape_run`. AsyncSession everywhere; no raw SQL in routes. Pydantic API schemas co-located: `JobCreate` / `JobUpdate` / `JobFilter` / `JobRead` / `JobScrapeRunRead`. Scorer + `extract_job` prompt updated to use the new enum. Sample data: 27 Jobs (backfilled `external_id` via deterministic sha1 prefix; fanned-out `source` per board) + 5 `JobScrapeRun` fixtures (mixed `SUCCESS` / `PARTIAL` / `FAILED`). New regression lint `tests/test_no_legacy_jobsource_imports.py`. Canonical Job + JobScrapeRun reference: `docs/design/JOB_MODEL.md` (graduated from plan 27 per AGENTS.md § Workflow step 4). **No new env / CLI / on-disk artifact surface** — sole on-disk addition is the `job_scrape_run` DB table.)
>
> Earlier line: 2026-05-19 (Plan 26 / `0.2.0.01` EXECUTED — vault deprecation. `src/services/vault.py` (436 LOC AES-256-GCM/PBKDF2/audit-log) DELETED. `src/cli/{vault,init}.py` (258 LOC) DELETED. Alembic 0004 drops 5 vault-derived `Settings` columns. New `src/services/env_secrets.py` exposes presence indicators sourced from `pydantic-settings`. `PUT /api/v1/settings/{llm,notifications}` reject `api_key` / `discord_webhook_url` / `telegram_bot_token` payloads with 422. Settings UI no longer accepts secret input — env-presence indicator cards instead. `.env.example` rewritten w/ 14 slot rows incl. new `TELEGRAM_CHAT_ID`. `naavik init` + `naavik vault <...>` exit 2 w/ migration hints. On-disk artifacts gone: `~/.naavik/secrets.enc{,.lock,.bak.*}`, `~/.naavik/key.bin`, `~/.naavik/logs/vault-audit.log`. New lint `tests/test_no_vault_imports.py` guards regression. Only surviving CLI subcommand: `naavik serve` (dies in `0.2.0.02`). 0.2.1.03 (Argon2id) closed as moot.)
>
> Earlier line: 2026-05-19 (Plan 25 / `0.1.1` EXECUTED — legacy bash → Python rewrite + 5 mutating `task` subcommands + CHANGELOG markdown-escape hardening. `.claude/naavik-ops gh` no longer subprocess-wraps `scripts/gh-project.sh`; native Python in `.claude/naavik_ops/gh.py` (18 legacy + 3 new helpers: `update-issue-title` / `close-issue` / `get-issue`). `.claude/naavik-ops memory` no longer subprocess-wraps `scripts/agent-memory.sh`; native Python in `.claude/naavik_ops/memory.py` (12 legacy subcommands; A.17 jq sandbox regex ported byte-for-byte). `.claude/naavik_ops/lib/roadmap.py` inlines the 304-line `scripts/roadmap_parser.py` + adds the writer-half. `.claude/naavik_ops/task.py` implements 5 mutating subcommands (`insert` / `defer` / `prioritize` / `move` / `renumber`) via atomic 3-store mutation under `~/.naavik/naavik-ops.lock` w/ rollback (A.29 deviation 1 closed). CHANGELOG `ReleaseEntry` sanitized per CommonMark spec (Issue #74). **Files deleted**: `scripts/gh-project.sh` + `scripts/agent-memory.sh` + `scripts/roadmap_parser.py` + `tests/test_agent_memory.sh`. Single-writer rule preserved by code path; `.claude/naavik-ops gh` / `memory` are still the sole entry points. Tests: 210 passing in `tests/test_naavik_ops/`.)
>
> Earlier line: 2026-05-18 (Plan 24 / A.29 Waves 1-4 IN FLIGHT — phase numbering system + `.claude/naavik-ops` Python dispatcher. New executable entry point `.claude/naavik-ops` routes `<group> <command>` to `.claude/naavik_ops/` package (5 groups: `task` / `release` / `deps` / `gh` / `memory`). `gh` + `memory` groups subprocess-wrap the legacy `.claude/naavik_ops/gh.py` + `.claude/naavik_ops/memory.py` during A.29; A.30 (0.1.1) inlines natively. 4-level semver task IDs (`MAJOR.MINOR.PATCH[.POSITION]`); regex `^\d+\.\d+\.\d+(\.\d{2})?$`. Migration runbook `.claude/migrations/A.29-phase-renumber.py` ships dry-run-only this PR; Wave 5 applies post-merge. Single-writer rule now routes through dispatcher entry; AGENTS.md § GitHub state — single writer rule updated accordingly. Design doc: `docs/design/PHASE_NUMBERING.md`. New on-disk paths: `~/.naavik/naavik-ops.lock` (flock), `~/.naavik/A.29-migration.lock` (migration apply, post-merge only), `CHANGELOG.md` (keepachangelog v1.1.0; bootstrap by migration apply).)
>
> Earlier line: 2026-05-17 (Plan 19 / A.15 EXECUTED — agent memory + learning system. `.claude/memory/` substrate (6 stores: decisions / discussions / lessons / knowledge / recurring-patterns / runs-analysis) + single-writer `.claude/naavik_ops/memory.py` + 4 memory-aware skills (`naavik-memory-lookup`, `naavik-discussion-capture`, `naavik-learn`, `manager-promote-lesson`) + 2 slash commands (`/memory`, `/learn`). Manager auto-invokes `Skill: naavik-discussion-capture` at PR_REVIEW_GATE + MILESTONE_GATE to surface deferred items. Design doc: `docs/design/AGENT_MEMORY.md`. Daily workflow: `docs/AGENT_OPS.md § 14`. New on-disk path: `.claude/memory/` (gitignored per-fork EXCEPT `.keep` + `knowledge/*.md`).)
>
> Earlier line: 2026-05-16 (Plan 16 Phase 1 EXECUTED — cold-start hook + naavik-cold-start skill + Skill tool added to all 6 agents + git prepare-commit-msg hook for auto-`Closes #N`. Remaining: Phase 2 per-agent skill suite, Phase 3+4 validation builds.)
>
> Earlier line: 2026-05-12 (Plan 10c EXECUTED — first-time-setup ergonomics paper cut. New operational surface: `~/.naavik/dev-credentials` (mode 0600, written only when `NAAVIK_DEBUG` is set AND `NAAVIK_DEV_PASSWORD` is unset AND the seeded `Settings.deployment_mode == SELF_HOSTED`). Plain `cat ~/.naavik/dev-credentials` is the canonical retrieval path — **NOT** a new CLI subcommand: `AGENTS.md` § Key Conventions § CLI codifies the "do not extend" rule (CLI sunset per ROADMAP § Phase 2 task 2.11; vault deprecation per task 2.12). `nix develop` shellHook also exports `NAAVIK_PERSISTENCE=db` for parity with the orchestrator, and `flake.nix:devEnv` exports `NAAVIK_DEBUG=1` so the lifespan credential echo + on-disk file fire under `nix run .#dev`. New config field `Settings.debug` (config.py) reads `NAAVIK_DEBUG` / `DEBUG` via pydantic-settings alias.)

This file provides Claude Code-specific guidance. For general project conventions, architecture, and the design workflow, see `AGENTS.md`.

## Claude Code Quickstart

```
1. Read AGENTS.md
2. Read ROADMAP.md
3. If using the agent system: read docs/AGENT_OPS.md (single operational guide)
4. If doing UI work: read docs/design/WORKFLOW.md + DESIGN.md
5. Start work. Update ROADMAP.md as you go.
6. Before archiving any plan, write its `## Deviations from plan` section. (AGENTS.md § Workflow step 7.)
```

**Cold-start invariant (post-A.11):** every agent's first action MUST be
`Skill: naavik-cold-start`. The `.claude/hooks/cold-start.sh` SessionStart hook
reminds the parent session of this; the agent prompts enforce it on subagent
dispatches. Do not read individual canonical files (AGENTS.md, ROADMAP, etc.)
before the skill has run — that path is what plan 16 fixed.

**Agent system entry points:**
- `docs/AGENT_OPS.md` — first-time bootstrap, daily workflow, troubleshooting. **This links to the four canonical guides:**
  - `ROADMAP.md` — phase state at a glance
  - `docs/ARCHITECTURE.md` — layer responsibilities + cross-cutting concerns + pattern catalog
  - `DESIGN.md` (root, visual contract) + `docs/design/WORKFLOW.md` (UI sub-process — skill routing, checklists, common patterns) — UI work
  - `docs/DEPLOYMENT.md` — 4 deployment paths + config + ops checklist (deployment / install work)
  - `docs/RUNBOOK.md` — known failure modes + diagnostic recipes (devops work)
- `ROADMAP.md` — full task ledger. Phase A: Agent System and § Agent System (mirror conventions) are the agent-system-specific rows.
- `.claude/agents/` — full agent prompts (manager, architect, engineer, devops, hacker, designer).
- `.claude/commands/` — slash commands (`/build`, `/plan`, `/discuss`, `/triage-bug`, `/review-pr`, `/threat-model`, `/design-screen`, `/groom`, `/standup`, `/bootstrap`, `/sync-roadmap`, `/budget`, `/runs`).
- `.claude/skills/` — project-level auto-trigger skills, one directory per skill (`<name>/SKILL.md`). **Planned by Phase A.11** (`docs/prompts/agent-system-v2.md`); currently empty. Per-agent suites (manager / architect / engineer / designer / hacker / devops) plus shared cross-agent skills (cold-start, roadmap-status, deviations-check, vault-sunset-guard).
- `.claude/hooks/` — Claude Code SessionStart hook + git hooks. **Planned by Phase A.11**; currently empty. Will hold `cold-start.sh` (SessionStart, injects required-reading context) and `git/prepare-commit-msg` (auto-appends `Closes #N` from branch name using `.claude/github-issue-map.json`).
- `.claude/settings.json` — Claude Code config (hooks registration, permissions, env vars). Edits managed via the `update-config` skill.
- `.claude/github-project.json` — Project ID + field option IDs cache (gitignored, per-fork; `.claude/naavik-ops gh init` writes; legacy `.claude/naavik-ops gh init` also works during A.29 transition).
- `.claude/github-issue-map.json` — Persistent {phase → epic#, task_id → issue#, phase → milestone#} association cache (gitignored, per-fork; `.claude/naavik-ops gh` is the sole writer entry point — during A.29 it subprocess-wraps `.claude/naavik_ops/gh.py`; `refresh-map` reconciles). See § GitHub state — single writer rule.
- `.claude/naavik-ops` — Executable Python dispatcher entry point (A.29). Routes `<group> <command>` to `.claude/naavik_ops/` package.
- `.claude/naavik_ops/` — Python package with module-per-group: `task` / `release` / `deps` / `gh` / `memory`. `gh` + `memory` subprocess-wrap legacy bash during A.29 transition; A.30 (0.1.1) inlines.
- `.claude/migrations/` — One-shot historical migration runbooks. `A.28-board-restructure.sh` (done), `A.29-phase-renumber.py` (DOES NOT RUN in PR; Wave 5 applies post-merge).
- `.claude/budget.json` — Daily token ceiling + per-agent caps.
- `.claude/budget-ledger.json` — Manager-managed running spend (gitignored).
- `docs/prompts/` — Session-kickoff prompts (the markdown briefings you paste into a fresh `claude --agent <name>` session). See `docs/prompts/README.md` for the convention. Archived alongside plans when the work ships.
- `docs/plans/` — Implementation plans (`NN-name.md`). Archived to `docs/plans/archive/` when shipped (with `## Deviations from plan` section).
- `docs/design/` — Visual contract + design docs + mockups + componentization specs.
- `.claude/naavik_ops/gh.py` — GitHub Projects v2 helper bash script. **Subprocess-wrapped by `.claude/naavik-ops gh` during A.29 transition.** Sole writer for Issue/Milestone/Project state (delegated through dispatcher). A.30 deletes this file + inlines native Python.
- `.claude/naavik_ops/memory.py` — `.claude/memory/` writer bash script. **Subprocess-wrapped by `.claude/naavik-ops memory` during A.29 transition.** Sole writer for memory stores. A.30 deletes this file + inlines native Python.
- `.claude/naavik_ops/lib/roadmap.py` — ROADMAP.md → JSONL parser (used by bootstrap + sync; wrapped by `.claude/naavik_ops/lib/roadmap.py`).
- `scripts/README.md` — Documents the `.claude/naavik_ops/` (agent-system tooling) vs `scripts/` (project-wide) convention.
- `traces/<run-id>/` — Per-run agent logs + `MANIFEST.json`. Run-id format `YYYY-MM-DDTHH-MM-SS_<6hex>`.
- `traces/runs.log` — Append-only index of all runs.

## Deviations workflow — non-negotiable before archive

Per `AGENTS.md` § Workflow step 7, every plan in `docs/plans/` MUST have a `## Deviations from plan` section before it moves to `archive/`. The implementing agent (you) writes this section based on what actually shipped vs what the plan promised. Bullets carry: **what** changed, **why**, **impact** on follow-up plans, and any **new operational surface** introduced (env var, CLI, on-disk path, etc.).

Anything new and operational ALSO propagates to user-facing docs in the same change:

- New env var → README § Configuration
- New CLI command → README § Operations or wherever the equivalent lives
- New on-disk path or secret-handling rule → CLAUDE.md + `docs/plans/POST_PHASE_1.md`
- New port, schedule, or runtime invariant → both, plus ROADMAP "Last updated"

If the deviation only matters to maintainers, document it in the plan's `## Deviations from plan` section and stop — no doc propagation needed.

**Plans without a Deviations section may not be archived.** Use "no material deviations" if the plan really shipped exactly as spec'd, but that's rare; reviewers should be skeptical when they see it.

**Archive via `naavik-ops plan archive`, never manual `git mv`** (codified plan 39 / `0.7.0.21`). The dispatcher subcommand `.claude/naavik-ops plan archive docs/plans/<NN-name>.md` is the canonical, single-writer entry point for moving any plan to `docs/plans/archive/`. It lifts entries from `traces/<run-id>/engineer-deviations.log`, writes them as canonical bullets in `## Deviations from plan`, flips frontmatter `Status: EXECUTED`, performs `git mv` (plan + matching prompt), and reports operational surfaces needing propagation. Refuses (exit 2) on empty sections unless `--no-material-deviations "<rationale>"` is passed. Read-only check: `.claude/naavik-ops plan validate-deviations docs/plans/<NN-name>.md`.

## GitHub state — single writer rule (codified 2026-05-16; updated 2026-05-18 for A.29)

**All mutations to GitHub Issues, Milestones, and the Project v2 board** (create, close, label change, status field, priority field, sub-issue link) MUST go through `.claude/naavik-ops gh` subcommands. The dispatcher subprocess-wraps `.claude/naavik_ops/gh.py` during the A.29 transition (A.30 inlines native Python). The script chain is the **sole writer** to `.claude/github-issue-map.json` — the persistent `{phase → epic#, task_id → issue#, phase → milestone#}` cache that gives bootstrap + plan-driven creates deterministic, instant idempotency.

Never bypass this:

- Don't run `gh issue create` / `gh issue close` / raw `gh api graphql` mutations against issues, milestones, or Project items from agent prompts. Use `.claude/naavik-ops gh create-issue` / `set-status` / `add-subissue` / `create-epic`.
- Don't hand-edit `.claude/github-issue-map.json`. It's machine-managed.
- If state drifts (someone renames/closes an issue in the GitHub web UI, or a stale process bypassed the helper), run `.claude/naavik-ops gh refresh-map` to reconcile from authoritative GitHub state. The reconciler prefers open + lowest issue number on title-prefix collisions.

**Why this exists.** Before 2026-05-16, the script's idempotency check (`find_issue_by_prefix`) relied on `gh api search/issues`, which is eventually consistent (~30s–2min indexing lag) and rate-limited. Re-running bootstrap shortly after the first apply caused the search API to miss freshly-created issues, producing duplicate issues (`#46` dup of `#6` for `[Epic] Pre-Phase-2 paper cuts`; `#47` dup of `#7` for `[PC.5]`). The map cache eliminates that race because every successful create writes to the map immediately, and every existence check reads the map first.

**Skill delegation.** `/bootstrap`, `/groom`, `/sync-roadmap`, `/standup`, and the `manager` agent all delegate state writes to `.claude/naavik-ops gh` (which during A.29 subprocess-wraps `.claude/naavik_ops/gh.py`). Other agents may READ the map (e.g. for a quick "what issue # is task `0.2.0.01`?") but must never write it directly. If a workflow needs new write semantics, extend the dispatcher modules under `.claude/naavik_ops/`, not the callers.

## Claude Code Specific Notes

**`naavik-ops` dispatcher** (Phase A row A.29, in flight 2026-05-18). The agent-system operations entry point lives at `.claude/naavik-ops` (executable Python). Routes `<group> <command> [args]` to module functions:

```bash
.claude/naavik-ops --help                                  # group surface
.claude/naavik-ops task list 0.2.0                         # ordered tasks for release-version
.claude/naavik-ops task next-unblocked 0.2.0               # priority DESC → position ASC
.claude/naavik-ops task check                              # version drift lint
.claude/naavik-ops release dry-run 0.1.0                   # preview release ceremony
.claude/naavik-ops deps add 0.2.0.06 0.2.0.05              # record dep edge
.claude/naavik-ops gh next-unblocked                       # legacy bash subprocess wrap
.claude/naavik-ops memory list discussions                 # legacy bash subprocess wrap
```

Schema: 4-level semver `MAJOR.MINOR.PATCH[.POSITION]` (regex `^\d+\.\d+\.\d+(\.\d{2})?$`). Position is 2-digit zero-padded; intra-release sort is `priority DESC → position ASC`. Single-writer rule: dispatcher is the sole entry point; underlying bash scripts during A.29, native Python in A.30.

Lock file: `~/.naavik/naavik-ops.lock` (flock; serializes concurrent mutations).

**Agent memory + learning** (Phase A row A.15, shipped 2026-05-17). `.claude/memory/` holds JSONL + markdown stores (decisions, discussions, lessons, knowledge, recurring-patterns, runs-analysis) owned by single-writer `.claude/naavik-ops memory` (subprocess-wraps `.claude/naavik_ops/memory.py` during A.29; A.30 inlines). Read via `/memory list <store>` / `/memory query <store> '<jq-expr>'` / `/memory knowledge <slug>`. Manual retrospective via `/learn [N]`. Manager auto-invokes `Skill: naavik-discussion-capture` at PR_REVIEW_GATE + MILESTONE_GATE. `~/.claude/projects/<...>/memory/MEMORY.md` is **read-only** from this system. Architecture: `docs/design/AGENT_MEMORY.md`. Daily workflow: `docs/AGENT_OPS.md § 14`.

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

Plan 26 (0.2.0.01) made env the sole source of secret material. Copy `.env.example` -> `.env`, chmod 0600, edit. Full slot inventory:

```bash
# All vars optional — config.py defaults are sane. Override only what differs.
DATABASE_URL=postgresql+asyncpg://naavik:password@localhost:5432/naavik
SECRET_KEY=                      # JWT signing key (>= 32 bytes; required outside nix run .#dev)
ANTHROPIC_API_KEY=               # For Claude
OPENAI_API_KEY=                  # For GPT models
OLLAMA_BASE_URL=http://localhost:11434  # For local models
DISCORD_WEBHOOK_URL=             # Job notifications
TELEGRAM_BOT_TOKEN=              # Optional
TELEGRAM_CHAT_ID=                # Required when TELEGRAM_BOT_TOKEN set
PORTFOLIO_WEBHOOK_URL=           # Netlify rebuild trigger (optional)
DATA_DIR=.naavik                 # State root (PDFs, snapshots, logs, dev-credentials)
NAAVIK_DEBUG=1                   # Local dev only: bypasses SECRET_KEY validators + writes dev-credentials
NAAVIK_DEV_PASSWORD=             # Optional: pin a stable dev login (mode 0600)
NAAVIK_PERSISTENCE=db            # Dev orchestrator forces; bare-shell override
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
