# Changelog

All notable changes to Naavik are documented here. Format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

(work in progress under `[Epic] 0.2.0`)


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
- `PUT /api/v1/settings/notifications` rejects (`422`) any payload carrying `discord_webhook_url` or `telegram_bot_token`. Body now configures only `notify_threshold` / `notify_on_errors` / `notifications_enabled`.
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
