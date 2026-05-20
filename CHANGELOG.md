# Changelog

All notable changes to Naavik are documented here. Format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

(work in progress under `[Epic] 0.2.0` + `[Epic] 0.2.1`)

### Removed (0.2.1.05 — CLI sunset)

- `src/cli/` (`main.py` + `__init__.py`) — the CLI dispatcher is gone. Plan 26 (0.2.0.01) deleted the `init` + `vault` subcommands along with the encrypted vault; plan 50 (0.2.1.05) completes the sunset by collapsing `naavik` to a uvicorn launcher.
- `tests/test_cli.py` — argparse-dispatch + bare-invocation routing tests no longer exist with the dispatcher gone. Replaced by `tests/test_main_entry.py::test_main_invokes_uvicorn` (one-line behavioral smoke) + `tests/test_no_cli_imports.py` (regression lint mirroring `test_no_vault_imports.py`).

### Changed (0.2.1.05)

- `[project.scripts] naavik = "cli.main:main"` → `naavik = "main:main"`. `src/main.py:main()` now calls `uvicorn.run("main:app", host=settings.host, port=settings.port, reload=False)` inline. `python -m main` and `uvicorn src.main:app` are functionally identical. `naavik-alembic` is unaffected.
- `[tool.setuptools] packages` drops `"cli"`.
- `README.md` § "`naavik` script entry" — replaces the prior CLI sunset section with the new minimal surface description.
- `docs/DEPLOYMENT.md` § Operations — CLI bullet rewritten to note the uvicorn collapse.

### Added (0.2.1.04 — JWT denylist on password rotation)

- New `RevokedJwt` SQLModel (`jti` unique-indexed, `user_id` FK, `revoked_at`, `expires_at`). Alembic 0010 creates the table + 3 indexes (`jti`, `user_id`, `expires_at`).
- `issue_jwt` now carries a `jti` claim (`secrets.token_urlsafe(16)` per issue).
- `verify_jwt` returns `tuple[user_id, jti, expires_at] | None` so callers can drive the denylist check + persist `expires_at` at rotation time.
- `services/auth.py` gains `revoke_jwt`, `is_jwt_revoked`, `cleanup_expired_revoked_jwts`. `get_current_user` + `require_authed_session` consult the denylist between JWT-decode + user-lookup; revoked tokens raise 401 with `Session revoked`.
- `POST /api/v1/auth/change-password` revokes the current `jti` BEFORE issuing the new JWT — defense-in-depth fix for PR #50 hacker Finding 3 (DEF-26): a stolen pre-rotation cookie now fails immediately after rotation, restoring the operator-visible "rotate to lock out" intuition.
- New `admin.cleanup_revoked_jwts` cron at 03:30 UTC daily (`scheduler/jobs.py:cleanup_revoked_jwts`). Added to plan 48's `FUNC_REF_ALLOWLIST` in `src/scheduler/json_jobstore.py`.
- `tests/test_jwt_revocation.py` — 8 sqlite-backed tests covering jti issuance, denylist round-trip, end-to-end change-password rotation (old JWT 401s on next `/auth/me`), cleanup pruning, and multi-user isolation.

### Security (0.2.1)

- `DEF-26` closed: a successful password rotation now invalidates the pre-rotation JWT. The old token survives only as long as the next `/auth/me` (or any authed) request takes to round-trip; subsequent requests with that cookie receive 401.

### Operations (0.2.1)

- **New daily cron** `admin.cleanup_revoked_jwts` runs at 03:30 UTC (offset from `admin.cleanup_stale_docs` weekly Sun 03:00). Prunes `revoked_jwt` rows whose `expires_at` has passed. No operator action required.
- **No new env var, no new on-disk path, no new CLI surface.** Sole operational addition is the cron above (behaviorally identical to the existing 5 admin crons).
- **Operators on 0.1.x with leftover `naavik vault status` scripts**: the binary still exists (now boots the server), so cached operator scripts that call `naavik vault status` will receive `argparse: unrecognized argument` from the implicit uvicorn entry rather than the prior 0.2.0 deprecation hint. Update scripts to `cat .env`-style inspection — values live in `.env` now.



## [0.2.6] - 2026-05-20

Release bundle for 0.2.6. Detailed entries reconstructed from closed Issues post-merge.
## [0.2.0] - 2026-XX-XX

(in flight — partial; release ceremony lands once all `0.2.0.NN` rows ship)

### Removed

- `src/services/vault.py` (436 LOC) — AES-256-GCM + PBKDF2 + audit-log + flock encrypted vault deleted. Migration: secrets move to env vars in `.env` (gitignored, `chmod 0600`). See README § Configuration + § Upgrading from 0.1.x with a populated vault.
- CLI subcommands `naavik init`, `naavik vault status`, `naavik vault rotate-key`. Bare `naavik` still runs `serve`; `naavik-alembic` unchanged. Deprecated subcommands surface a migration hint with exit code 2.
- Files `src/cli/init.py` (103 LOC), `src/cli/vault.py` (155 LOC), `tests/test_vault.py` (entire file, 300+ LOC), vault sections of `tests/test_cli.py` (~150 LOC). Net deletion: ~1000+ LOC.
- `Settings` columns `llm_api_key_fingerprint` (str), `discord_webhook_configured`, `telegram_bot_configured`, `portfolio_webhook_configured`, `scraper_proxy_configured` (4 bool). Schema migration `0004_drop_vault_cols.py`. Downgrade restores empty cols; values are NOT restored (vault is gone).
- On-disk operational surfaces: `~/.naavik/secrets.enc{,.lock,.bak.*}`, `~/.naavik/key.bin`, `~/.naavik/logs/vault-audit.log` are no longer written or read. Self-hosters should delete after upgrade (see § Operations below).
- `services/ats_credentials.store_secret/resolve_secret/delete_secret` deleted. ATS adapters in Phase 2.X re-introduce a DB-side storage model when needed; Phase 1 adapters (Greenhouse / Lever / Ashby) ship vault-free.

### Changed

- `PUT /api/v1/settings/llm` rejects (`422`) any payload carrying `api_key` or `ollama_base_url`. Body now configures only `llm_provider` / `llm_model` / `llm_fallback_provider`.
- `PUT /api/v1/settings/notifications` rejects (`422`) any payload carrying `discord_webhook_url`, `telegram_bot_token`, or `telegram_chat_id`. Body now configures only `notify_threshold` / `notify_on_errors` / `notifications_enabled`.
- `GET /api/v1/settings/llm` returns `env_indicators` (per-provider bools); no `llm_api_key_fingerprint` field.
- `GET /api/v1/settings/notifications` similarly returns `env_indicators`; no `*_configured` fields.
- Settings · LLM Provider tab — drops the API-key input field + per-provider Ollama base URL field. New "API key (configured via environment)" indicator section shows configured / not-set per provider, sourced from env presence via `services/env_secrets.py`.
- Settings · Deployment tab — drops the rose vault-locked banner. The `vault_locked` / `vault_fingerprint_stored` / `vault_fingerprint_expected` template fields are removed. On-disk panel shows `.env` (env-loaded · gitignored) instead of `~/.naavik/secrets.enc`.
- Settings · Notifications tab — webhook + bot token are env-configured. The "(configured)" placeholder values are replaced with indicator cards reading from env.
- `.env.example` — full inventory of secret slots with documentation of `NAAVIK_DEBUG` interaction, `chmod 0600 .env` guidance, and the post-vault security model. 14 slot rows: `DATABASE_URL`, `SECRET_KEY`, 3 LLM (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `OLLAMA_BASE_URL`), 4 integrations (`DISCORD_WEBHOOK_URL` / `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` / `PORTFOLIO_WEBHOOK_URL`), `DATA_DIR`, 2 server (`HOST` / `PORT`), 3 dev/debug (`NAAVIK_DEBUG` / `NAAVIK_DEV_PASSWORD` / `NAAVIK_PERSISTENCE`).

### Added

- `src/services/env_secrets.py` — post-vault presence-indicator helpers. `is_configured(scope)` for generic lookups; `llm_provider_configured(provider)` / `discord_webhook_configured()` / `telegram_bot_configured()` / `portfolio_webhook_configured()` for typed callers; `env_indicators_for_{llm,notifications}_tab()` bundles for templates. Never returns secret values.
- `src/config.py` — new `telegram_chat_id` field (was previously vault scope `notifications.telegram_chat_id`).
- `tests/test_env_secrets.py` — 12 smoke tests covering env-presence indicators + scope dispatch + value-never-leaked invariant.
- `tests/test_no_vault_imports.py` — regression lint walks `src/` for `from services import vault` / `import vault` / `vault_svc` references + the on-disk vault module file. Fails loudly if anything reintroduces the vault.
- `tests/test_settings_llm_form.py` — env-indicator render checks + 422-on-secret-payload tests.
- `migrations/versions/0004_drop_vault_columns.py` — drops 5 `Settings` columns with reversible downgrade.
- **`Job` model hardening + `JobScrapeRun` scrape-side observability** (`0.2.0.05` / Issue #15) — plan 27 graduates to `docs/design/JOB_MODEL.md`.
  - 6 new `Job` columns: `external_id` (NOT NULL after sha1 backfill, partial-unique on `(user_id, source, external_id) WHERE deleted_at IS NULL` — primary dedup constraint), `remote_policy` (NOT NULL default `UNKNOWN`), `seniority_level` (nullable), `posted_at_text` (raw scraper string), `description_extracted_at`, `description_extraction_model`, `last_scrape_run_id` (FK → `job_scrape_run.id`).
  - `Job.visa_restrictions` promoted from free-form `str | None` to typed `VisaRestriction` enum via 4-step ALTER TABLE (add-col + UPDATE-CASE + drop-old + rename). Backfill maps lowercase string values + `LIKE '%sponsorship%'` onto enum members.
  - New `JobScrapeRun` table — 17 columns + 2 CHECK constraints + 3 composite indexes (`(source, started_at)`, `(user_id, status, started_at)`, `started_at`). One row per scraper invocation; carries `(status, started_at, finished_at, requests_made, listings_returned, new_jobs, updated_jobs, errors[], duration_ms, raw_meta)`.
  - 4 new Postgres ENUM types: `visarestriction` (4 values), `remotepolicy` (4 values), `senioritylevel` (7 values), `jobscrapestatus` (5 values).
  - `JobSource` enum: 9 per-source values added (`LINKEDIN` / `WORKDAY` / `GREENHOUSE` / `LEVER` / `ASHBY` / `INDEED` / `COMPANY_DIRECT` / `RSSHUB` / `N8N_LEGACY`); `AUTOMATED` deprecated (existing rows remapped to per-board values via `board::text::jobsource`; the dangling `automated` value stays in the type definition because Postgres has no `ALTER TYPE ... DROP VALUE` before PG16 — cosmetic only, follow-up `0.2.5.NN` cleanup row planned).
  - `migrations/versions/0005_job_hardening.py` (additive on Postgres; sqlite test-only fallback paths). Round-trip verified on Postgres + sqlite.
  - `src/services/job_service.py` — 8-function service surface: `upsert_job` (idempotent on `(user_id, source, external_id)`; merges raw_meta; field-level merge deferred to `0.2.0.09`), `get_job`, `list_jobs` (filtered, score DESC + found_at DESC, soft-delete honored), `archive_job`, `restore_job` (collision-aware), `create_manual_job` (synthetic `external_id = manual-<uuid4>[:12]`), `count_jobs_by_source`, `record_scrape_run`. AsyncSession everywhere; no raw SQL in routes.
  - Pydantic API schemas in `src/models/job.py` + `src/models/job_scrape_run.py`: `JobCreate` / `JobUpdate` / `JobFilter` / `JobRead` / `JobScrapeRunRead`. Co-located with the SQLModel of the same domain (matches existing `profile.py` convention).
  - `src/services/scorer.py` updated to match against `VisaRestriction` enum members (was free-form string set).
  - `src/llm/prompts/extract_job.py` — `ExtractedJob.visa_restrictions` is now the typed enum; AI extraction is structurally constrained via Pydantic `provider.structured(...)`.
  - `src/db/sample_data.py` — 27 Job fixtures backfilled with `external_id` (deterministic sha1 prefix) + fanned-out `source` per board; 5 `JobScrapeRun` fixtures (last 24h of scraping, mixed `SUCCESS` / `PARTIAL` / `FAILED` statuses); `Job.last_scrape_run_id` wired across 24 of the 27 jobs.
  - `tests/test_alembic_0005.py` (3 cases, sqlite round-trip), `tests/test_job_service.py` (15 cases, in-memory FakeSession); `tests/test_no_legacy_jobsource_imports.py` (regression lint — fails if any `src/` file imports `JobSource.AUTOMATED`).
  - `docs/design/JOB_MODEL.md` — new canonical reference, graduated from plan 27.
- **Crawl4AI scraper substrate** (`0.2.0.06` / Issue #10) — plan 29 graduates to `docs/design/SCRAPER_BASE.md`.
  - `crawl4ai==0.8.6` (exact pin, post-2026-03-24 litellm supply-chain hotfix release) added to base deps.
  - `playwright>=1.58.0,<1.59` PROMOTED from dev extras to base deps (Crawl4AI imports Playwright at module-import time; production runtime needs it).
  - `src/scraper/types.py` — `RawJob` Pydantic v2 boundary DTO (17 fields, `extra="forbid"`, `*_hint` enum fields preserve scraper-guess vs AI-ground-truth separability) + `ScrapeQuery` input DTO.
  - `src/scraper/base.py` — `ScraperBase(ABC)` with `async def scrape(query) -> AsyncIterator[RawJob]`. Class-level `rate_limit_per_minute=30` + `random_delay_seconds=(1.0, 3.0)` reserve the rate-limit interface (impl in `0.2.0.13`).
  - `src/scraper/crawl4ai_client.py` — `Crawl4AIClient` wraps `AsyncWebCrawler`. `enable_stealth=True` default. Two public methods: `fetch_html(url) -> str | None` + `stream_many(urls) -> AsyncIterator[tuple[str, str | None]]`. Per-process token-bucket rate limiter with jitter.
  - `src/scraper/sites/__init__.py` — `scrapers: dict[JobSource, type[ScraperBase]]` registry stub (populated by `0.2.0.07` site scrapers).
  - `src/scraper/sites/sample.py` — `SampleScraper` test fixture yielding 3 hard-coded RawJobs (NOT registered for production dispatch).
  - `src/services/scraper_service.py` — `run_scraper(session, *, scraper, user_id, query, triggered_by)` orchestrates the JobScrapeRun lifecycle (RUNNING → SUCCESS / PARTIAL / FAILED / TIMED_OUT). Streams `scraper.scrape(query)` → `job_service.upsert_job(...)` per yield; two-tier error model (per-listing recoverable / scraper-fatal raise / `asyncio.CancelledError` → TIMED_OUT re-raised).
  - `tests/test_scraper_{types,base,sample,service}.py` + `tests/test_crawl4ai_client.py` — 43 new tests (RawJob field-validation, ABC enforcement, Crawl4AIClient with `_FakeAsyncCrawler` mock, SampleScraper materialization, JobScrapeRun status derivation across 7 lifecycle outcomes).
  - `docs/design/SCRAPER_BASE.md` — new canonical reference (~330 LOC), graduated from plan 29; cross-refs into `BACKEND.md § J.1` + `JOB_MODEL.md § H` + `LINKEDIN_SCRAPING.md § 7` + `ARCHITECTURE.md § 3.8` updated to point at it.

### Changed

- `docs/design/BACKEND.md § J.1` — `BaseScraper(ABC)` sketch collapsed to single streaming `scrape() -> AsyncIterator[RawJob]` per plan 29 § D.5. Two-method `list_jobs + fetch_detail` + `matches()` shape DROPPED (RSShub / guest API / n8n migration imports have non-uniform shapes; subclasses orchestrate their own listing+detail chain internally). `matches()` routing logic moves to a future `scraper_service.dispatch_by_url(url)` reading the `sites/__init__.py:scrapers` registry.

### Operations

- **UX regression: rotating an LLM API key is now `edit .env + restart`.** No equivalent of `naavik vault rotate-key`. This matches the pattern of every other self-hosted app (n8n, Grafana, Authentik): secrets are env vars.
- **Migration for existing self-hosters with a populated vault**:
  ```
  # BEFORE upgrading (on 0.1.x):
  $ uv run naavik vault status     # capture your scope list (last time it works)
  # AFTER upgrading (on 0.2.0):
  $ cp .env.example .env && chmod 0600 .env
  # edit .env with the values from the captured scope list
  $ rm -f ~/.naavik/secrets.enc ~/.naavik/key.bin
  $ rm -f ~/.naavik/secrets.enc.lock ~/.naavik/secrets.enc.bak.*
  $ rm -rf ~/.naavik/logs/vault-audit.log
  $ # restart your deployment
  ```
  No automated migration tool ships; the operator runs ~5 commands and is done. See plan 26 § D.1 for the decision rationale.
- **Operators who skip migration**: the app boots fine; LLM calls fail with provider 401 until the relevant env var is set in `.env` and the app restarts.
- **`docker-compose.yml`**: env block adds `TELEGRAM_CHAT_ID`; banner comment updated to drop vault references.

### Security

- The vault was theater: the master key was derived from `SECRET_KEY` (the same env var the JWT signer reads). An attacker with `SECRET_KEY` could already decrypt the vault; an attacker without `SECRET_KEY` couldn't decrypt JWTs either. Moving to env-only flattens the trust model to "trust the env" (which is what every other self-hosted app does). Filesystem permissions (`chmod 0600 .env`) are the actual defense.
- Audit log (`~/.naavik/logs/vault-audit.log`) is gone. Operator visibility into "who accessed which secret" comes from the application access log + the request-tracing pipeline (Phase 2.5).
- `0.2.1.03` (Argon2id vault upgrade, DEF-17) auto-moots: the vault is gone, no PBKDF2 hash to upgrade. ROADMAP row closed at merge time.


## [0.1.1] - 2026-05-19

Legacy bash → Python rewrite + native mutating `task` subcommands + CHANGELOG markdown sanitization + PR_REVIEW_GATE reviewer pairing refactor. Shipped via PR #91 (squash `494ffae`). Plan: `docs/plans/archive/25-0.1.1-bash-to-python.md`. 210 tests passing in `tests/test_naavik_ops/`.

### Added
- **Native `.claude/naavik_ops/gh.py`** (0.1.1.01 / Issue #72) — full Python rewrite of `scripts/gh-project.sh` (1469 LOC bash); 20 callable CLI subcommands (18 legacy + 2 new: `update-issue-title` + `close-issue`) + 1 new Python helper function `get_issue()`.
- **Native `.claude/naavik_ops/memory.py`** (0.1.1.01 / Issue #72) — full Python rewrite of `scripts/agent-memory.sh` (843 LOC bash); 12 subcommands; A.17 jq sandbox char allowlist + identifier deny-list ported byte-for-byte (`env` / `getpath` / `path` / `paths` / `input` / `inputs` / `setpath` / `delpaths` / `debug` / `stderr` / `$ENV`).
- **5 mutating `task` subcommands** (0.1.1.01 / closes A.29 Deviation 1): `insert` / `defer` / `prioritize` / `move` / `renumber` — atomic 3-store mutation (ROADMAP rewrite + Issue title rewrite + map cache update) under `~/.naavik/naavik-ops.lock` flock with mid-loop rollback (R2 guard). Stub `exit 2 NOT_IMPLEMENTED_YET` from A.29 removed.
- **`.claude/naavik_ops/lib/roadmap.py`** — inlines the 304-line `scripts/roadmap_parser.py` legacy parser; adds the writer half (`ReleaseRow` / `ReleaseDiff` / `parse_release_section` / `write_release_section` / `rewrite_atomic`).
- **`# PR review mode` section in `.claude/agents/architect.md`** (W6) — architect joins hacker as parallel reviewer at PR_REVIEW_GATE; plan-adherence / design-coherence / sunset-guard / surface-propagation checks documented.
- **`.gitignore`** — `.claude/worktrees/` added (PR #75 hacker LOW finding folded in).

### Changed
- **PR_REVIEW_GATE reviewer pairing**: `hacker + devops` → `hacker + architect` (W6 contract refactor). Devops moves to on-demand dispatch for build-gate failures / runtime debugging via `/triage-bug` + direct manager invocation; engineer continues self-running `devops-build-gates` skill pre-PR for ruff + pytest + manual QA.
- `.claude/naavik-ops gh` + `.claude/naavik-ops memory` are now native Python entry points (no subprocess shim around legacy bash). Single-writer rule preserved by code path — same dispatcher, faster.

### Removed
- `scripts/gh-project.sh` (1469 LOC bash) — replaced by `.claude/naavik_ops/gh.py`.
- `scripts/agent-memory.sh` (843 LOC bash) — replaced by `.claude/naavik_ops/memory.py`.
- `scripts/roadmap_parser.py` (304 LOC) — inlined into `.claude/naavik_ops/lib/roadmap.py`.
- `tests/test_agent_memory.sh` — replaced by `tests/test_naavik_ops/test_memory.py` (38 cases).
- `tests/test_naavik_ops/test_{gh,memory}_wrapper.py` — replaced by direct-impl tests.
- `scripts/` folder reserved for project-wide user-runnable scripts only (currently only `scripts/README.md`).

### Security
- **CHANGELOG markdown sanitization** (0.1.1.02 / Issue #74) — `ReleaseEntry.__post_init__` escapes CommonMark special chars + collapses whitespace + rejects CR; `parse_changelog` round-trip avoids double-escape via `ReleaseEntry.from_rendered`. Defends header smuggling + link injection in commit-message bodies once future closed-Issue ingestion wires (PR #73 hacker Finding 3 closed).
- Single-writer rule still enforced by deletion-of-alternative (legacy bash entirely removed; only native Python in `.claude/naavik_ops/` writes to state stores).

### Operations
- **Post-merge bookkeeping** uses the new `naavik-ops gh close-issue <N>` subcommand to close 6 stale pre-A.29 epics (#1 Phase A, #6 Pre-Phase-2 paper cuts, #9 Phase 2, #22 Phase 1 deferred items, #65 Phase 2.5, #76 [Epic] 0.1.0) per Issue #90 (`0.1.1.03`).

## [0.1.0] - 2026-05-18

First full bundle: Phase 0 foundation + Phase 1 MVP + Pre-Phase-2 paper cuts + Phase A agent-system bootstrap + this A.29 phase-numbering migration. All work pre-Phase-2 ships as `0.1.0`.

### Added
- **Phase 0 foundation** (2026-04-25): Nix flake devShell, pyproject.toml + uv lockfile, Dockerfile, Docker Compose, PostgreSQL with pgvector.
- **Phase 1 MVP** (2026-05-03): user auth (bcrypt + JWT + CSRF), profile intake, settings UI, Typst PDF generation, LLM provider abstraction (Anthropic + OpenAI + Ollama), self-hosted single-user mode, Docker Compose deployment, `nix develop` orchestrator.
- **Pre-Phase-2 paper cuts** PC.1–PC.7.
- **Phase A agent system bootstrap** A.1–A.10 (2026-05-16).
- **Phase A v2** A.11–A.12 (2026-05-16).
- **Phase A tracing + memory** A.13–A.17 (2026-05-17).
- **Phase A board restructure** A.28 (2026-05-17).
- **Phase A machine-readable rewrite** A.16 (2026-05-18).
- **Phase A phase numbering** A.29 (2026-05-18, this release): `.claude/naavik-ops` Python dispatcher + `.claude/naavik_ops/` package.

### Changed
- Migrated all task IDs and ROADMAP rows to 4-level semver schema (`MAJOR.MINOR.PATCH[.POSITION]`). Legacy IDs preserved via `.claude/github-issue-map.json:redirects` map.
- GitHub Project Priority field role narrowed: optional intra-release impact signal at TASK level only.
- `scripts/` folder reserved for project-wide user-runnable scripts only.

### Security
- `SECRET_KEY` enforcement at module-import time (PC.5).
- Password complexity + must-change-on-first-login (PC.6).
- Broader `require_password_complete` gate (PC.6a).
- `scripts/agent-memory.sh` hardening (A.17 + A.17a).
