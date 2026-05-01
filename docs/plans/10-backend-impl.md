---
Status: APPROVED
Type: implementation
Authored: 2026-05-01
Last updated: 2026-05-01
Approved: 2026-05-01
Depends on: 04-backend-architecture (graduated → docs/design/BACKEND.md), 05-data-model (graduated → docs/design/DATA_MODEL.md), 07-sample-data (graduated → docs/design/SAMPLE_DATA.md), 09-stage-3-impl (page templates + stub handlers — APPROVED 2026-05-01; this plan's Wave 4 part swaps plan 09's accessor bodies for DB queries, signatures preserved)
Wave order: this plan covers **Wave 4 (§ B — backend substrate + accessor swap)** and **Wave 5 (§ C — services + Typst + ATS)** in ROADMAP.md § Phase 1 (Scenario A — linear: 08 → 09 → 10 W3 → 10 W6).
---

# 10 · Backend implementation (multi-wave)

## Goal

Implement `docs/design/BACKEND.md` exhaustively, building the database, the auth layer, the LLM provider abstraction, the vault, the 14 services, the 7 ATS adapters, and the DB-backed handlers that replace plan 09's stubs. The work is **multi-wave** per ROADMAP.md § Phase 1 § Implementation waves: **Wave 3 (initial backend)** lands the data substrate + auth + LLM abstraction so plan 09's stubs swap to real handlers without UI churn; **Wave 6 (real backend)** completes the 14 services + Typst + DRAFT lifecycle + ATS adapters; **Phase 2–6 work** (scrapers, scoring, email, outreach, observability) graduates to follow-up plans (`11+`) when their time comes. Plan 10 details Waves 3 + 6 and outlines Phase 2–6 to ground their future plans.

## Context / why

Plan 08 ships components, plan 09 ships pages with sample-data accessors and stub endpoints, plan 10 makes everything real. After Wave 3 lands:

- Every fixture in `src/db/sample_data.py` is also seeded into Postgres via Alembic + `db/seed.py`.
- Every page handler that read from sample-data accessors continues to work (the accessor names are preserved; their bodies switch from `[a for a in APPLICATIONS if ...]` to `await session.exec(select(Application).where(...))`).
- Auth is real — `POST /api/v1/auth/login` validates against `User.password_hash` (bcrypt cost=12), issues a JWT cookie, and downstream handlers depend on the auth gate.
- LLM calls work end-to-end — `prompts/score_job.py` returns a real `JobScore` Pydantic model, with cost + token counts logged to `ApiUsage`.
- Settings persists per user; secrets live in the encrypted vault at `~/.naavik/secrets.enc`.

After Wave 6:

- The 14 services from BACKEND.md § H.1 are complete. `document_generator` produces real tailored resumes via Typst with bullet selection + trimming + page-count validation. `application_service` runs the full DRAFT lifecycle. `application_screener_answer` carries real auto-fill + AI-drafted rows. ATS adapters submit real applications to Greenhouse / Lever / Ashby (Workday / LinkedIn / Indeed are Phase 1.x).
- The auto-apply cron (`applications.auto_apply` every 5min per BACKEND.md § I.1) processes the DRAFT queue.
- Sample-data accessor bodies that still read from in-memory lists swap to DB queries.

Phase 2–6 work (scrapers, scoring nuance, email + auto-classification, LinkedIn DMs, Discord/Telegram, observability, semantic match, light mode, LaTeX template) gets its own kickoff prompt(s) — separate from Wave 6 because each phase is a coherent unit on its own and the team likely ships them across multiple weeks.

## Proposal

### A · Multi-wave structure

| Wave        | Scope                                                                                                                                                                   | Plan / prompt                                                                 | Status (after this plan approved)                                                             |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| **Wave 3**  | Models + auth + LLM abstraction + vault + initial services + db/seed                                                                                                    | This plan § B; kickoff prompt `docs/prompts/10-backend-impl.md` § Wave 3 part | Authored here, drives the next implementation session                                         |
| **Wave 6**  | Real services (all 14 from BACKEND.md § H.1) + Typst + DRAFT lifecycle + ATS adapters (Greenhouse / Lever / Ashby) + DB-backed handlers replacing sample-data accessors | This plan § C; kickoff prompt § Wave 6 part                                   | Authored here, drives the implementation session **after Wave 3 ships and is verified clean** |
| **Phase 2** | Scrapers + scraping cron + auto-apply scoring                                                                                                                           | Future plan `11-phase-2-scrapers.md`                                          | Outlined here § D.1                                                                           |
| **Phase 3** | Scoring + tag matching + visa filter end-to-end                                                                                                                         | Future plan `12-phase-3-scoring.md`                                           | Outlined here § D.2                                                                           |
| **Phase 4** | Email integration + auto-classification + recruiter-state derivation                                                                                                    | Future plan `13-phase-4-email.md`                                             | Outlined here § D.3                                                                           |
| **Phase 5** | LinkedIn DMs + Discord / Telegram / Calendar + outreach generator                                                                                                       | Future plan `14-phase-5-outreach.md`                                          | Outlined here § D.4                                                                           |
| **Phase 6** | Prometheus / Sentry / OTel + JobEmbedding semantic match + light mode + LaTeX template                                                                                  | Future plan `15-phase-6-polish.md`                                            | Outlined here § D.5                                                                           |

The kickoff prompt at `docs/prompts/10-backend-impl.md` is **structured into two parts** — a Wave-3 section and a Wave-6 section — each self-contained for a fresh session. The Wave-6 section is pasted **only after Wave 3 ships and verifies clean**. Splitting into separate `10a` / `10b` plans is avoided; Wave 3 + Wave 6 are tightly coupled (Wave 6 reuses Wave 3's models, services, vault) and authoring them as one plan keeps the contract coherent.

### B · Wave 3 — initial backend

**Goal:** Land the data substrate + auth + LLM abstraction so plan 09's stub endpoints can swap to real backends without UI churn. After Wave 3, every page in plan 09 still renders identically; reads come from Postgres instead of in-memory lists; auth + Settings persist; LLM calls produce real responses (cost + tokens tracked).

**Acceptance for Wave 3 to ship:**

- `uv run alembic upgrade head` succeeds against a clean Postgres
- `db/seed.py` populates every fixture from `src/db/sample_data.py`; `tests/test_sample_data.py` round-trip via Pydantic still passes; new `tests/test_seed.py` round-trip via SQLModel passes
- `POST /api/v1/auth/login` round-trips real bcrypt + JWT
- LLM provider factory + cost tracking work; `prompts/score_job.py` returns real `JobScore` against the seeded Profile
- `security-review` skill passes on the auth + vault paths
- Plan 09's pages render unchanged with real backend swapped in (sample-data accessor bodies updated to DB queries)

#### B.1 SQLModel models (1:1 with DATA_MODEL.md § C)

Build `src/models/*.py` files for all 19 entities + 1 Settings singleton + enums:

| File                               | Models                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/models/__init__.py`           | re-exports for `from src.models import User, Profile, ApiUsage, ...`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `src/models/enums.py`              | every enum from DATA_MODEL.md § D — `ApplicationStatus`, `ClosedReason`, `DocsState`, `ReferralState`, `RecruiterState`, `JobQueueState`, `JobSource`, `BulletSelectionOverride`, `Tag`, `WorkAuthorization`, `VisaSponsorship`, `VeteranStatus`, `DisabilityStatus`, `Race`, `Gender`, `RelocateOpenness`, `ApplicationBoard`, `AppEventKind`, `StatusChangeTrigger`, `OutreachStatus`, `OutreachIntent`, `ContactType`, `EmailClassification`, `ScreenerQuestionType`, `ScreenerAnswerSource`, `AtsLoginStatus`, `GeneratedDocumentKind`, `LLMProvider`, `DeploymentMode` |
| `src/models/user.py`               | `User`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `src/models/profile.py`            | `Profile`, `Experience`, `Bullet`, `Skill`, `Education`, `Project`, `Certification`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `src/models/job.py`                | `Job`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `src/models/application.py`        | `Application`, `ApplicationScreenerAnswer`, `GeneratedDocument`, `ATSCredential`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `src/models/contact.py`            | `Contact`, `ContactApplicationLink`, `OutreachMessage`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `src/models/email.py`              | `EmailThread`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `src/models/event.py`              | `AppEvent`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `src/models/api_usage.py`          | `ApiUsage` (entity #19; powers Settings · LLM Provider cost cards from day one — promoted from Phase 2+ on 2026-05-01)                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `src/models/settings.py`           | `Settings` (incl. new `eager_review_generation: bool = True` + `daily_llm_cost_cap_usd: Optional[float]` fields per DATA_MODEL.md § C `Settings`)                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `src/models/app_event_payloads.py` | discriminated Pydantic union per DATA_MODEL.md § M (`StatusChangePayload`, `DocsGeneratedPayload`, `EmailReceivedPayload`, etc.) — used at the service layer for typed payload reads                                                                                                                                                                                                                                                                                                                                                                                        |

**Field shape exactly matches DATA_MODEL.md § C.** Every relationship back-populates explicitly. Every CHECK constraint from § E lands as a SQLAlchemy `CheckConstraint` in `__table_args__`:

- `closed_reason IS NOT NULL WHEN status = 'CLOSED'`
- `salary_min <= salary_max OR salary_min IS NULL`
- **`applied_at IS NOT NULL OR status = 'DRAFT' OR deleted_at IS NOT NULL`** — covers (a) DRAFT pre-submission, (b) any post-submission status with `applied_at` set, and (c) discarded DRAFTs that flip to `CLOSED` with `closed_reason=withdrawn_by_me` and `deleted_at` non-null but never had `applied_at`. The previous "applied_at NOT NULL when status != DRAFT" formulation rejected discarded DRAFTs and was corrected 2026-05-01.

Soft-delete via `deleted_at: Optional[datetime] = None` on user-authored entities per § C.

The Pydantic models in `src/db/sample_data_models.py` (built in plan 09) **become a deprecation alias** — `from src.models import Profile as Profile, ...`; plan 09's `sample_data.py` continues to work. Once Wave 6 lands and DB-backed handlers replace sample-data accessor bodies, `sample_data_models.py` deletes.

**Index coverage** matches DATA_MODEL.md § G — every listed index lands in the initial Alembic migration.

#### B.2 Alembic initial migration

`migrations/versions/0001_initial.py`:

- Enable `pgvector` extension at the top (`op.execute("CREATE EXTENSION IF NOT EXISTS vector")`) so future Phase 6 `JobEmbedding` migrations don't have to.
- Create every Postgres ENUM type via SQLAlchemy `sa_Enum.create()`.
- Create every table.
- Create every index from DATA_MODEL.md § G.
- Create every CHECK constraint.
- Single migration; no incremental Phase 1 splits.
- Reversible: `downgrade()` drops every table + ENUM in reverse order.

#### B.3 Auth (JWT cookie + bcrypt + CSRF)

Per BACKEND.md § D.1, § G:

- `services/auth.py`:
  - `hash_password(plain) -> str` — bcrypt, cost=12.
  - `verify_password(plain, hash) -> bool`.
  - `issue_jwt(user_id, *, keep_signed_in: bool) -> str` — HS256 over `SECRET_KEY`, exp=30d (kept) or 24h (default).
  - `verify_jwt(token) -> Optional[int]` — returns `user_id` on success, `None` on expired/invalid.
  - `get_current_user` FastAPI dependency — reads `naavik_session` cookie, verifies JWT, loads `User` + `Settings` from DB.
- Routes in `src/api/auth.py`:
  - `POST /api/v1/auth/login` — verify password, issue JWT, set `Set-Cookie: naavik_session=<jwt>; HttpOnly; Secure; SameSite=Strict; Path=/`. Return 204 + `HX-Redirect`.
  - `POST /api/v1/auth/logout` — clear cookie.
  - `GET /api/v1/auth/me` — return current `User`.
  - `GET /api/v1/auth/csrf` — issue + rotate the CSRF token (used on auth events only — login / logout / password change).
- CSRF: double-submit pattern. `<meta name="csrf-token">` on `base.html` (already wired in plan 08). Server validates `X-CSRF-Token` header against the cookie-side token on every state-changing request. Read-only requests (GET) don't validate CSRF.
- Cookie flags: `HttpOnly` (no JS access), `Secure` (HTTPS only — relax to `Secure=False` only when `DEBUG=true` for local dev), `SameSite=Strict`. Path `/`. No `Domain=` to keep it host-only.
- Brute-force guard: simple in-memory rate limiter (`fastapi-limiter` or hand-rolled) — 5 failed login attempts per IP per 15min returns 429.

#### B.4 LLM provider abstraction (`src/llm/`)

Per BACKEND.md § M:

- `src/llm/base.py`:
  - `LLMProvider` ABC — `complete(prompt, max_tokens) -> str`, `structured(prompt, schema) -> T`, `stream(prompt, max_tokens) -> AsyncIterator[str]`, `estimate_cost(input_tokens, output_tokens) -> float`, `model_name -> str` property.
  - `LLMProviderError` exception.
- `src/llm/anthropic.py` — wraps `anthropic.AsyncAnthropic`. Tool-use for structured output. Cost: anthropic.com pricing as of Phase 1 ($3/M input, $15/M output for sonnet).
- `src/llm/openai.py` — wraps `openai.AsyncOpenAI`. `response_format=json_schema` for structured. Cost per OpenAI pricing.
- `src/llm/ollama.py` — wraps Ollama HTTP API. JSON mode for structured. Cost = $0 (local).
- `src/llm/__init__.py` — `get_provider(settings: Settings) -> LLMProvider` factory; resolves API key via `vault.get(scope="llm", key=settings.llm_provider.value)`.
- `services/llm_tracker.py` — `tracked_call(provider, method, *args, **kwargs)` wrapper that times the call, logs `ApiUsage(provider, method, input_tokens, output_tokens, cost_usd, latency_ms)`. **`ApiUsage` table is added in Wave 3** even though SAMPLE_DATA.md says it's "Phase 2+" (the cost tracking is Phase 1 surface; Settings · LLM Provider's "THIS MONTH" cost card needs it).
- Retry policy per BACKEND.md § M.5: rate-limit → exponential backoff (max 3 retries); timeout → retry once with longer timeout; 500 → fallback provider if `Settings.llm_fallback_provider` set, else raise; schema validation failure → re-prompt once with stricter instructions.
- Initial prompts shipped (per BACKEND.md § M.3 Phase 1 list): `extract_resume`, `extract_job`, `score_job`, `select_bullets`, `trim_bullet`, `draft_cover_letter`, `answer_screener`, `classify_email`, `draft_outreach`, `auto_tag_bullets` — but **Wave 3 only ships their module skeletons + Pydantic schemas + a working `score_job`**; the full set wires in Wave 6.

#### B.5 Vault service (`services/vault.py`)

Per BACKEND.md § H.1, § L.1, § N + DATA_MODEL.md § H:

- File at `~/.naavik/secrets.enc` (path from `Settings.DATA_DIR / "secrets.enc"` env override; default `.naavik/secrets.enc` per `CLAUDE.md`).
- Format: AES-256-GCM-encrypted JSON `{scope: {key: value}}`. The file header carries a 32-byte `key_fingerprint = sha256(master_key)[:32]` (plaintext) so the server can detect a `SECRET_KEY` mismatch before attempting decrypt and surface a clear error instead of silent corruption.
- Master key: derived from `SECRET_KEY` env var via PBKDF2 (100k iterations, salt is the file's bytes 32–48).
- API:
  - `vault.get(scope: str, key: str) -> Optional[str]`
  - `vault.set(scope: str, key: str, value: str) -> None`
  - `vault.delete(scope: str, key: str) -> None`
  - `vault.list(scope: str) -> list[str]` — returns key names only (not values)
  - `vault.fingerprint() -> str` — returns the stored `key_fingerprint`; used by Settings · Deployment to detect mismatches.
- Audit log per BACKEND.md § N: every `get` / `set` / `delete` writes a line to `~/.naavik/logs/vault-audit.log` with `{timestamp, op, scope, key, caller_service}`. **Secret value never logged.**
- File-locking via `fcntl.LOCK_EX` so concurrent writes don't corrupt.
- `naavik init` CLI (one-time setup) prompts for a passphrase if `SECRET_KEY` not in env; stores derived key in env or in `~/.naavik/key.bin` (mode 0600).

**Vault key rotation — Day-1 CLI** (`naavik vault rotate-key`). Self-hosters need this; rotating `SECRET_KEY` without a migration path bricks the vault.

```
$ naavik vault rotate-key --old-secret-key=$OLD_KEY --new-secret-key=$NEW_KEY
[vault] reading ~/.naavik/secrets.enc (current fingerprint: 9f3ab8...)
[vault] decrypting 12 entries across 5 scopes ...
[vault] re-encrypting with new key (new fingerprint: 4c2def...)
[vault] writing ~/.naavik/secrets.enc.new (atomic rename when done)
[vault] backup at ~/.naavik/secrets.enc.bak.2026-05-01-12-04
[vault] done. update SECRET_KEY env to the new value before next start.
```

Implementation: read with `--old`, decrypt all entries to memory, re-derive master key from `--new`, re-encrypt + atomic rename + leave a `.bak.YYYY-MM-DD-HH-MM` for safety. `--no-backup` flag for CI.

**Settings · Deployment UI mismatch warning.** On startup, `services/vault.py` reads `vault.fingerprint()` and compares to `sha256(PBKDF2(SECRET_KEY))[:32]`. If they differ, the app starts in "vault-locked" mode: writes are rejected (no new secrets accepted), reads fail (existing secret-dependent paths return 503). Settings · Deployment surfaces a rose-tinted banner: **"Vault locked — `SECRET_KEY` mismatch. Run `naavik vault rotate-key` or restore the original key."** This catches the most common self-hoster footgun (rotating `SECRET_KEY` in `.env` without realizing it bricks the vault).

**Backup procedure.** Document in README + Settings · Deployment "On disk" card: when restoring from backup, restore both `~/.naavik/secrets.enc` AND the `SECRET_KEY` env var that encrypted it — they're a matched pair. The `key_fingerprint` header lets the server detect when only one was restored.

Scopes used in Phase 1: `"llm"` (API keys), `"integrations"` (OAuth refresh tokens, IMAP passwords), `"notifications"` (Discord webhook, Telegram bot), `"ats"` (per-board cookies), `"misc"` (Netlify webhook URL).

#### B.6 ATS credentials metadata service (`services/ats_credentials.py`)

Per BACKEND.md § H.1, § K.5:

- `get_credential_metadata(user_id, board) -> Optional[ATSCredential]` — reads DB row.
- `set_credential_metadata(user_id, board, *, has_credential, login_status, last_login_at) -> ATSCredential` — upserts DB row.
- `resolve_secret(user_id, board) -> Optional[dict]` — reads from `vault.get(scope="ats", key=board.value)`. Returns the secret material (cookies, tokens, 2FA backup codes) for ATS adapters.

DB row carries metadata only; secret material is in vault. UI surfaces "Connect / Reconnect" via `has_credential` + `login_status`.

#### B.7 Profile service partial (`services/profile_service.py`)

Per BACKEND.md § H.1:

- `get_profile(user_id) -> Profile` — DB-backed read.
- `update_field(user_id, field: str, value)` — per-field PUT (used by Profile editor autosave). Returns OOB autosave indicator partial via service-side helper.
- `update_application_questions(user_id, payload: ApplicationQuestionsPayload)` — bulk update for the 10 EEO/visa fields.
- `add_bullet(experience_id, text, tags=[])` / `update_bullet(bullet_id, ...)` / `delete_bullet(bullet_id)` (soft).
- `reorder_bullets(experience_id, bullet_ids: list[int])`.
- `rewrite_bullet(bullet_id, tone) -> Bullet` — calls `prompts/auto_tag_bullets` + a rewrite prompt; sets `edited_at`.

Wave 6 expands this with `extract_resume_to_profile(pdf_path) -> Profile` and bullet-tag inference from new text. Wave 3 has a stub for those that returns the existing sample-data profile.

#### B.8 Settings persistence

Per BACKEND.md § D.7:

- DB-backed CRUD for `Settings` (one row per user). Schema includes `eager_review_generation: bool = True` + `daily_llm_cost_cap_usd: Optional[float]` per DATA_MODEL.md § C `Settings` (added 2026-05-01 for cost-aware DRAFT generation).
- `PUT /api/v1/settings/llm` — update `llm_provider`, `llm_model`, `llm_fallback_provider`. API key flows through `vault.set(scope="llm", key=provider, value=key)`; `llm_api_key_fingerprint` updated on `Settings`.
- `POST /api/v1/settings/llm/test` — calls `provider.complete("ping")` with a tiny prompt; returns `{ok, latency_ms, model}` or `{ok: false, error}`.
- `PUT /api/v1/settings/auto-apply` — `auto_apply_enabled`, `auto_apply_score_threshold`, `auto_apply_daily_cap`, `eager_review_generation`, `daily_llm_cost_cap_usd`. Saves trigger immediate enforcement (cost cap recalc; eager flag flips on next `/discover/{id}` GET).
- `PUT /api/v1/settings/sources` — `sources_enabled`, `source_schedules`. Reschedules APScheduler jobs on save.
- `PUT /api/v1/settings/notifications` — `notifications_enabled`; `discord_webhook_url` and `telegram_bot_token` flow through `vault.set(scope="notifications", ...)`.
- `GET /api/v1/settings/deployment` — returns `DeploymentInfo` (mode, version, uptime, paths, scheduler status, **vault fingerprint match status**). Version from package metadata.

**`/_design/components` gate swap.** Plan 08 ships the fixture page gated on the `NAAVIK_DEBUG=1` env var. Wave 4 swaps to the persisted `Settings.debug` field (per DATA_MODEL.md § C `Settings.debug`). The route handler in `src/ui/routes/design.py` changes from:

```python
if not os.environ.get("NAAVIK_DEBUG"):
    raise HTTPException(404)
```

to:

```python
settings = await get_settings_for(current_user)
if not settings.debug:
    raise HTTPException(404)
```

This is a one-line change in plan 08's handler but counts as a Wave 4 deliverable so the env-var → DB-flag transition isn't lost. Settings · Account tab gains a hidden "Developer mode" toggle flipping `Settings.debug`.

#### B.9 `db/seed.py`

Per SAMPLE_DATA.md § A:

- Imports every list + singleton from `src/db/sample_data.py`.
- INSERTs into Postgres in dependency order: User → Settings → Profile → Experience → Bullet → Skill → Education → Project → Certification → Job → Application (incl. 2 DRAFT) → Contact → ContactApplicationLink → OutreachMessage → EmailThread → AppEvent → GeneratedDocument → ApplicationScreenerAnswer.
- Idempotent: `ON CONFLICT DO NOTHING` via SQLAlchemy `insert(...).on_conflict_do_nothing()`.
- CLI: `uv run python -m src.db.seed` — populates the dev DB. Called automatically by `nix run .#dev` after `alembic upgrade head` succeeds.

#### B.10 Page-handler swap (sample-data → DB)

The Phase 1 plan-09 sample-data accessors (`get_profile()`, `applications_visible_in_tracking()`, etc.) get **rewritten in place** to DB queries. **Crucially, plan 09 ships every accessor as `async def` from day one** (per plan 09 § B), so Wave 4's swap is **purely a function-body change** — signatures stay identical:

```python
# Plan 09 (signatures already async; body returns from in-memory list)
async def applications_visible_in_tracking(session: AsyncSession, user_id: int) -> list[Application]:
    return [a for a in APPLICATIONS if a.user_id == user_id and a.status in {
        APPLIED, RECRUITER_SCREEN, ONSITE_LOOP, OFFER,
    }]

# Plan 10 Wave 3 (same signature; body issues a DB query)
async def applications_visible_in_tracking(session: AsyncSession, user_id: int) -> list[Application]:
    stmt = select(Application).where(
        Application.user_id == user_id,
        Application.status.in_([APPLIED, RECRUITER_SCREEN, ONSITE_LOOP, OFFER]),
        Application.deleted_at.is_(None),
    )
    return (await session.exec(stmt)).all()
```

Page handlers in `src/ui/routes/` already thread `session: AsyncSession = Depends(get_session)` + `current_user: User = Depends(get_current_user)` from plan 09; in plan 09 the `session` arg is unused (sample_data accessors ignore it). Wave 4 lights it up without touching call sites.

The plan-09 in-memory mutation shim (`_apply_status_override`, etc.) deletes — replaced by service-layer functions that issue real `INSERT` / `UPDATE` / `UPDATE` with `submission_artifacts.last_failure` writes for stuck DRAFTs.

After this swap: plan 09's stubs for `POST /api/v1/applications/move`, `POST /api/v1/discover/{id}/skip`, `PUT /api/v1/profile/{field}`, etc. all replace with real handlers that go through the service layer. The HTMX-side contract is unchanged.

**Side-by-side smoke test before declaring Wave 4 shipped:** spin up the dev server with `NAAVIK_PERSISTENCE=memory` (legacy plan-09 mode) on port 8000 and `NAAVIK_PERSISTENCE=db` (Wave 4 default) on port 8001 against the seeded DB. Visit each of the 11 screens on both. Diff Playwright snapshots — they should be pixel-identical (same sample data, same templates, same partials). The `NAAVIK_PERSISTENCE` env var is removed in a follow-up cleanup once the swap is verified.

### C · Wave 6 — real backend

**Goal:** Complete the remaining 14 services from BACKEND.md § H.1, ship Typst document generation, fully implement DRAFT lifecycle, and dispatch ATS submissions to Greenhouse / Lever / Ashby (the 3 boards with public APIs). Workday / LinkedIn / Indeed / Generic adapters are Phase 1.x — they need credentials + Playwright + manual review queue, deferred to a follow-up sub-prompt.

**Acceptance for Wave 6 to ship:**

- All 14 services from BACKEND.md § H.1 implemented + tested.
- `document_generator` produces real PDFs (resume + cover letter) via Typst with bullet selection + AI trim + page-count validation.
- `application_service` runs the full DRAFT lifecycle (auto-create, submit, discard) with `submission_artifacts` populated by ATS adapter return.
- 3 ATS adapters (Greenhouse / Lever / Ashby) submit real applications end-to-end.
- The `applications.auto_apply` cron (every 5min) processes the DRAFT queue.
- `document_generator.answer_screeners` populates `ApplicationScreenerAnswer` rows with `auto` (Profile-derived) + `drafted` (LLM-drafted) sources.
- `security-review` skill passes on the doc-generation + portfolio-public-API + vault audit paths.

#### C.1 Service catalog (per BACKEND.md § H.1)

| Service               | Wave 3 status                            | Wave 6 work                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| --------------------- | ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `auth`                | ✅ shipped                               | refresh-token rotation; OIDC scaffolding (Phase 2+)                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `profile_service`     | partial (CRUD + bullet ops)              | extract_resume_to_profile, AI tag inference on new text                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `extraction`          | stub                                     | full PDF → AI extraction pipeline; SSE event emission for Onboarding                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `scraper_service`     | n/a                                      | (Phase 2 — outline § D.1)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `scorer`              | naive LLM `score_job` skeleton           | **Wave 6 ships the deterministic visa filter** (zero-out when `Profile.visa_sponsorship_needed=NEEDED_NOW × Job.visa_restrictions ∈ {us_citizen_only, green_card_required}`); full tag-matching + gap analysis lives in plan 12 (Phase 3). The visa filter is required in Wave 6 because auto-apply runs in Wave 6 and would otherwise auto-submit visa-incompatible jobs at non-zero scores — embarrassing failure mode. The filter is deterministic + has zero LLM dep, so it doesn't wait for Phase 3. |
| `document_generator`  | not started                              | full pipeline § C.2                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| `application_service` | partial (DRAFT row create + submit stub) | full DRAFT lifecycle § C.3 + state-transition enforcement                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `email_monitor`       | n/a                                      | (Phase 4 — outline § D.3)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `email_classifier`    | n/a                                      | (Phase 4)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `contact_tracker`     | partial (CRUD)                           | dedup + state inference from outreach messages                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `outreach_generator`  | n/a                                      | (Phase 5 — outline § D.4)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| `notifications`       | stub (sends to no-op)                    | Discord webhook + Telegram bot + in-app toast routing                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `portfolio_sync`      | not started                              | `/api/portfolio/cv` + `/api/portfolio/resume.pdf` + Netlify rebuild webhook                                                                                                                                                                                                                                                                                                                                                                                                                               |
| `llm_tracker`         | ✅ shipped                               | per-month aggregation cron `admin.aggregate_costs`                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `vault`               | ✅ shipped                               | passphrase rotation flow                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `ats_credentials`     | ✅ shipped                               | login flows for Workday/LinkedIn (Phase 1.x — separate sub-prompt)                                                                                                                                                                                                                                                                                                                                                                                                                                        |

#### C.2 Document generator pipeline (per BACKEND.md § K.4)

`services/document_generator.py`:

- **`generate_resume(application: Application) -> GeneratedDocument`:**
  1. **Bullet selection** via `prompts.select_bullets(profile, job, max=12)` — returns selected `bullet_ids` respecting `Bullet.selection_override` (`always_include` pinned, `never_include` skipped).
  2. **Bullet trimming** via `prompts.trim_bullet(text, target_chars=120)` per selected bullet — preserves numbers + verbs.
  3. **Typst compilation** via `typst/compiler.py` → `~/.naavik/data/documents/<app_id>/resume.pdf`.
  4. **Page-count validation** via `typst/validator.py` — if page count > 1, drop the lowest-priority bullet and retry. Max 3 retries.
  5. **Persist** `GeneratedDocument` with `kind=resume`, `bullet_selection={"selected_ids": [...], "trimmed_lines": {...}}`, `cost_usd`, `token_count`, `model`.
- **`generate_cover_letter(application, tone="enthusiastic") -> GeneratedDocument`:**
  1. `prompts.draft_cover_letter(profile, job, tone)` → 4-section letter (intro / body / why_company / close).
  2. Typst compile → `~/.naavik/data/documents/<app_id>/cover-letter.pdf`.
  3. Persist as `GeneratedDocument(kind=cover_letter)`.
- **`answer_screeners(application) -> list[ApplicationScreenerAnswer]`:**
  1. For each screener question on the application form (extracted from JD or known per-board taxonomy):
     - **Auto-fill candidates** — questions matching a canonical Profile field (start date, salary expectation, work auth, visa sponsorship, race, gender, veteran, disability): create `ApplicationScreenerAnswer(source=AUTO, answer=<profile.field>, reviewed_at=utcnow())`.
     - **AI-drafted** — all other questions: `prompts.answer_screener(profile, job, question)` → drafted answer. Create `ApplicationScreenerAnswer(source=DRAFTED, answer=<drafted>, drafted_by_model=provider.model_name, reviewed_at=None)`.
  2. Each row carries `question_text`, `question_fingerprint` (lowercase + strip punctuation + remove company name + stem), `question_type`, `choices` (for select types), `required`, `order_index`.
- **`pre_generate(application)`:** runs all three above (resume + cover letter + screeners) — invoked from `application_service.get_or_create_draft` (manual review path, gated on `Settings.eager_review_generation`) or `application_service.queue_auto_apply` (auto-apply path, always eager).

  **DRAFT reuse heuristic** (formalized 2026-05-01): `pre_generate` is a **no-op** when ALL three hold:
  1. `application.docs_state == READY`
  2. for every `bullet_id` in the latest `GeneratedDocument(kind=resume).bullet_selection.selected_ids`, the bullet's `Bullet.edited_at <= GeneratedDocument.compiled_at` (no stale edits)
  3. `application.job.description_html` hash matches the JD hash recorded on the latest `GeneratedDocument` (catches re-scraped JD drift)

  Otherwise re-runs full generation. This means revisits to `/discover/{id}` that don't trigger generation are free (~0 LLM cost), satisfying the "Discover · review feels live" UX without the visit-tax. When (1)–(3) drift, `docs_state` flips to `STALE` and `pre_generate` re-runs.

  **Cost cap enforcement.** When `Settings.daily_llm_cost_cap_usd` is set and today's `sum(ApiUsage.cost_usd)` ≥ cap, `pre_generate` aborts and the route handler renders the lazy "Tailor for this job" CTA with a banner: "Daily cost cap of $N reached — manual tailor available." The DRAFT row is created but `docs_state=NONE` until user clicks. Cap resets at midnight UTC.

#### C.2.1 Typst templates + compiler

- `src/typst/templates/onepage.typ` — NEU-style 1-page resume (Helvetica, 0.3in margins, compact). Consumes JSON data: profile + selected_bullets + trimmed_lines.
- `src/typst/templates/cover_letter.typ` — letter template with 4 sections + signature block.
- `src/typst/compiler.py` — `compile(template_name, data: dict, output_path: Path) -> CompileResult`. Wraps `typst compile` CLI. Async via `asyncio.create_subprocess_exec`. **Captures `--emit metadata` JSON output** which includes `pages` count — no external `pdfinfo` / poppler dependency. `CompileResult = {output_path, page_count, byte_size, compiled_at}`.
- `src/typst/validator.py` — `validate_page_count(result: CompileResult, expected: int) -> bool` reads `result.page_count` (from `typst --emit metadata` above). Drops the dependency on `pdfinfo` / poppler / `nix/devshell.nix`'s `poppler-utils` add — Typst is already in the dev shell, so no new deps needed.

LaTeX template support is Phase 6 per ROADMAP.md.

#### C.3 Application service — full DRAFT lifecycle (per BACKEND.md § K)

`services/application_service.py`:

- `get_or_create_draft(user_id, job_id) -> Application` — used by `/discover/{job_id}` GET. Creates DRAFT if none exists, then **gated on `Settings.eager_review_generation`**: eager → kicks off `document_generator.pre_generate(draft)` (DRAFT-reuse heuristic in § C.2 may make this a no-op); lazy → leaves `docs_state=NONE` so the page renders the empty workspace + "Tailor for this job" CTA.
- `queue_auto_apply(user_id, job_id) -> Application` — used by `POST /api/v1/discover/{job_id}/auto-submit`. Always eager (intent is unambiguous). Sets `Job.queue_state = QUEUED_FOR_AUTO_APPLY`.
- `submit_draft(application_id) -> Application` — DRAFT → APPLIED transition. Validates `validate_submittable(application)` first (all required `DRAFTED` screener answers reviewed; `docs_state=READY`). Dispatches via `services/ats/__init__.py:dispatch(board)`. On success, sets `applied_at = utcnow()`, `Job.queue_state = APPLIED`, emits `AppEvent(STATUS_CHANGE: DRAFT → APPLIED)`, calls `notifications.notify_application_submitted`. On failure (CAPTCHA / auth_required / field_mismatch / unknown), keeps DRAFT, writes `submission_artifacts.last_failure = {kind, message, captured_at}`, increments `submission_artifacts.retry_count`, emits `DOCS_FAILED` or `AUTO_APPLY_FAILED`. **The DRAFT row now surfaces in Discover's "Stuck in queue · {N}" right rail card** (`up_next_card` `state="stuck"`, COMPONENTS.md `up_next_card`).
- `discard_draft(application_id) -> Application` — DRAFT → CLOSED `withdrawn_by_me`, soft-delete (`deleted_at`). Removes from "Stuck in queue" surface.
- `process_auto_apply_queue()` — invoked by the `applications.auto_apply` cron every 5min. Iterates DRAFTs where `Job.queue_state=QUEUED_FOR_AUTO_APPLY`, runs `submit_draft` per row, respects `Settings.auto_apply_daily_cap`. Failed DRAFTs stay queued visually (in "Stuck in queue") but `Job.queue_state` reverts to `SAVED` so the cron doesn't keep retrying without user intervention.
- `validate_submittable(application) -> Optional[ValidationError]` — all required `DRAFTED` screener answers reviewed (`reviewed_at IS NOT NULL`), `docs_state=READY`. Returns 409 + remediation hint if not.
- `update_status(application_id, new_status, *, closed_reason=None)` — manual-override transitions. Enforces forward-only transitions per DATA_MODEL.md § E (backwards transitions logged as `MANUAL_OVERRIDE` AppEvent with notes). Validates `closed_reason` set when `new_status=CLOSED`.
- `derive_recruiter_states()` — invoked by the `tracking.derive_recruiter_states` cron every 30min (Phase 4). Wave 6 ships the function but the cron is wired in Phase 4. Auto-derives `recruiter_state` per DATA_MODEL.md § E from `EmailThread` activity.

**Service-layer ownership of computed state** (locked here so plan 09's stub endpoints + plan 10's real handlers agree on where state derivation lives):

- **`Application.referral_state` rollup** lives in `application_service._roll_up_referral_state(application_id)`, called whenever a `ContactApplicationLink.referral_state` mutates. Roll-up rule per DATA_MODEL.md § E: `provided` if any link is provided, else `in_flight` if any is, else `requested` if any is, else `declined` if any is, else `none`.
- **`outreach_engagement` (computed)** lives in `application_service.compute_outreach_engagement(application_id)`. Pure function over `OutreachMessage[]` + `ContactApplicationLink[]`: `referred` if any link's `referral_state == provided`; `awaiting_reply` if any sent message in last 14d has no reply; `cold` if no contacts/messages; `active` otherwise. Phase 1 computed on demand (per DATA_MODEL.md § F); Phase 4+ may cache to a `Settings`-side denormal.
- **`Job.queue_state = APPLIED` flip** is enforced by `application_service.submit_draft`'s last step (after status → APPLIED, before commit) — single write transaction so `Job.queue_state` and `Application.status` never disagree.
- **`Application.docs_state` transitions** (NONE → GENERATING → READY → STALE → FAILED) are owned by `document_generator` (Wave 6 § C.2); `application_service` reads but never sets `docs_state` directly.

#### C.4 ATS adapter dispatcher (`src/services/ats/`)

Per BACKEND.md § K.5:

- `services/ats/__init__.py:dispatch(board: ApplicationBoard) -> ATSAdapter` — factory.
- `services/ats/base.py:ATSAdapter` ABC — `submit(application, bundle) -> SubmissionResult`, `can_submit(job) -> bool`, `requires_credential() -> bool`.
- **Wave 6 ships** (the 3 with public APIs):
  - `services/ats/greenhouse.py` — Greenhouse Public Boards API + Embedded API. POSTs `application` + uploads resume PDF + cover letter PDF + answers per `Job Form Field`. No credential needed for boards.greenhouse.io; per-company API key for direct submission.
  - `services/ats/lever.py` — Lever public API. POSTs `application` + attaches resume.
  - `services/ats/ashby.py` — Ashby public API. Same pattern.
- **Phase 1.x sub-prompt** ships (the 4 needing credentials + Playwright):
  - `services/ats/workday.py` — Playwright form-fill, per-tenant session (login + 2FA). Resume-parsing override per BACKEND.md § K.5: post canonical Profile fields explicitly via the structured form-field API; never rely on the board's PDF parser.
  - `services/ats/linkedin_apply.py` — Playwright Easy Apply with user session cookie.
  - `services/ats/indeed.py` — Playwright with Indeed account session.
  - `services/ats/generic.py` — Playwright generic form-fill.
- Manual fallback (no module): UI-side "Open ATS · {board}" button + clipboard paste of bundle.

`SubmissionResult = {ok, board_application_id, error?, retry_after?}`. Failures classified into `captcha`, `rate_limit`, `auth_required`, `field_mismatch`, `unknown` — drives `submission_artifacts.last_failure.kind`.

#### C.5 Notifications service (`services/notifications.py`)

Per BACKEND.md § H.1, § L.3, § L.4:

- Discord webhook — outbound only. Webhook URL in vault. Posts on:
  - new high-score job (≥ `Settings.notify_threshold`)
  - application submitted
  - interview invitation received (auto-classified)
  - offer received
  - rejection received (configurable, default OFF)
- Telegram bot — outbound only in Wave 6 (inbound `/status`, `/today`, `/silent` is Phase 5).
- In-app toasts — emit via SSE on `/_fragments/toast` (consumed by `#toast-region` OOB swap).
- Per-event toggles via `Settings.notifications_enabled`.

#### C.6 Portfolio sync (`services/portfolio_sync.py`)

Per BACKEND.md § L (Portfolio):

- `GET /api/portfolio/cv` — returns Profile JSON, public-fields-only filter (no email / phone / EEO / visa / salary). CORS configured via `Settings.portfolio_cors_allowed_origins` (default `["https://crypticsoul.dev"]`; self-hosters can edit). Phase 2+ adds `?version=v1` query param for consumer pinning per ROADMAP § Phase 1 deferred.
- `GET /api/portfolio/resume.pdf` — serves the latest **generic** 1-page PDF (compiled against Profile with no JD-specific tailoring).
- **Generic resume regeneration trigger**: on every `profile_service.update_*` call (Profile field PUT, bullet add/edit/delete, experience add/edit, etc.) the service emits a `profile_updated` AppEvent. A debounced (60s) listener regenerates the generic PDF via `document_generator.generate_generic_resume(profile)` and writes to `~/.naavik/data/documents/portfolio/resume.pdf`. The 60s debounce coalesces rapid edits (autosave can fire many PUTs in a session) into a single compile + Netlify rebuild. Same debounce timer also triggers `trigger_netlify_rebuild`.
- **Cache shape**: single fixed path `~/.naavik/data/documents/portfolio/resume.pdf` (not versioned per-edit; the generic resume always reflects the latest Profile state). On request, serve from disk; if missing (fresh install), generate on-demand and cache.
- `generate_generic_resume(profile)` — like `document_generator.generate_resume(application)` but with no JD context: bullets selected by `selection_override=ALWAYS_INCLUDE` first, then by `tags` count (proxy for "general-purpose" relevance), trimmed against a generic-line target (≤140 chars). One LLM call max per regen; cached aggressively.
- `trigger_netlify_rebuild()` — POSTs to `Settings.portfolio_webhook_url` (resolved via vault). Same 60s debounce as the PDF regen.

#### C.7 Cron registration (Wave 6 subset)

`scheduler/jobs.py` registers per BACKEND.md § I.1. Wave 6 wires only those Phase 1 needs:

- `applications.auto_apply` — every 5min — `application_service.process_auto_apply_queue()`
- `admin.aggregate_costs` — daily 00:30 — `llm_tracker.aggregate()`
- `admin.cleanup_stale_docs` — weekly Sun 03:00 — `document_generator.cleanup_stale()`
- `admin.daily_db_snapshot` — daily 02:00 — snapshot service
- `admin.refresh_oauth_tokens` — every 6h — each integration's refresh method (OAuth endpoints exist Phase 4 but Wave 6 ships the cron skeleton)

Phase 2-5 crons are added by their respective phase plans.

APScheduler with `PostgresJobStore` so jobs survive restarts. Idempotency keys per BACKEND.md § I.2.

### D · Phase 2–6 outline (future plans)

Each phase becomes its own plan + kickoff prompt when its time comes. Plan 10 doesn't author them; it just outlines them so the implementing team has a clear forward path.

#### D.1 Phase 2 — Scrapers + scraping cron (future plan `11-phase-2-scrapers.md`)

Scope (per BACKEND.md § J + ROADMAP.md § Phase 2):

- `BaseScraper` interface + dispatcher
- 7 site scrapers: LinkedIn (RSShub-fed), Workday, Greenhouse, Lever, Ashby, Indeed, Generic (Playwright fallback)
- Scraping cron per source (every 30–90min)
- AI job extraction (`prompts/extract_job`)
- Job dedup (URL + fuzzy title/company)
- `notifications.notify_new_high_score` gate at score ≥ `Settings.notify_threshold`
- n8n migration: one-time CSV import via `services/legacy_import.py`

Acceptance: jobs scraped on schedule, AI-extracted, deduped, scored, surfaced on Discover. Discord notification fires on high-score. n8n Main Workflow disabled after 1 week of clean run.

#### D.2 Phase 3 — Scoring (future plan `12-phase-3-scoring.md`)

Scope (per BACKEND.md § H.1 `scorer`, § M.3 `score_job`):

- Tag-based matching: JD → identify tags → match against Profile bullets
- AI scoring (`prompts/score_job`) returning `{score, explanation, matched_tags, gaps, visa_concern}`
- Visa filter: auto-zero score for `us_citizen_only` / `green_card_required` jobs when `Profile.visa_sponsorship_needed=NEEDED_NOW`
- Tailored resume preview on Discover · review showing which bullets selected/excluded
- One-click generation from Discover · review (already wired in plan 09 stub; Phase 3 makes it real end-to-end)
- Score history + analytics surfaces on Overview

Acceptance: every Job has a real score with explanation; visa filter zeros out incompatible jobs; bullet-selection preview reflects real `prompts/select_bullets` output.

#### D.3 Phase 4 — Email integration + auto-classification (future plan `13-phase-4-email.md`)

Scope (per BACKEND.md § L.1, § H.1, § I.1):

- Gmail OAuth + sync cron (every 10min)
- Outlook OAuth + sync (same shape)
- IMAP fallback for non-Gmail/Outlook
- `email_classifier`: LLM classifies into INTERVIEW_REQUEST / REJECTION / OFFER / ASSESSMENT / FOLLOW_UP / OTHER
- `application_service.derive_recruiter_states` cron (every 30min) — auto-sets `Application.recruiter_state` per DATA_MODEL.md § E rules
- Priority notifications gate (HIGH for INTERVIEW_REQUEST + OFFER)
- Email thread tracking on Tracking + Overview email-signal feed

Acceptance: emails sync automatically; each new email auto-classifies; recruiter-state on each Application reflects email activity; needs-followup banner on Tracking auto-surfaces silent applications.

#### D.4 Phase 5 — Outreach + LinkedIn + Discord/Telegram/Calendar (future plan `14-phase-5-outreach.md`)

Scope (per BACKEND.md § L.2–L.5, § H.1, § I.1):

- `integrations/linkedin_browser.py` — Playwright with user session cookie. DM send + employee search + reply check. Rate-limited: 50 DMs/day, 100 profile views/day.
- `services/contact_tracker.py` complete — dedup, state inference from outreach messages.
- `services/outreach_generator.py` — AI draft via `prompts/draft_outreach` for INTRO / REFERRAL_REQUEST / FOLLOW_UP / THANK_YOU / CHECK_IN. Tone-appropriate, not spammy.
- Outreach cron: `outreach.send_linkedin_dms` (every 5min batch), `outreach.check_dm_replies` (every 60min), `outreach.suggest_next_moves` (every 24h).
- Telegram inbound long-poll worker (`/status`, `/today`, `/silent` commands) — separate worker task per BACKEND.md § I.3.
- Google Calendar OAuth + auto-create events on `INTERVIEW_REQUEST` classification.

Acceptance: LinkedIn DMs sent on schedule; recruiter/employee contacts auto-tracked; warm intros surface on Discover · review; Telegram bot answers `/status` queries; calendar events auto-create on interview emails.

#### D.5 Phase 6 — Polish + observability + semantic match + light mode + LaTeX template (future plan `15-phase-6-polish.md`)

Scope (per BACKEND.md § N + ROADMAP.md Phase 6):

- Prometheus metrics endpoint `/metrics`
- Sentry via `SENTRY_DSN`
- OpenTelemetry tracing for LLM / scraper / ATS submission paths
- `JobEmbedding` (pgvector) for semantic match
- Light mode (DESIGN.md tokens + Tailwind `dark:` flips)
- LaTeX template alongside Typst (`latexmk` / `tectonic`)
- Resume A/B testing + ML scoring calibration from outcomes
- Weekly summary report (`admin.weekly_summary` cron)

Acceptance: metrics scraped by Prometheus; Sentry receives errors; pgvector search works on Discover; light mode renders correctly; LaTeX template compiles a valid 1-page resume from Profile data.

### E · Tests

Cross-wave test surface:

| File                                | Wave | Scope                                                                                                                                                          |
| ----------------------------------- | ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/test_models.py`              | 3    | Every SQLModel instantiates from sample data; relationships back-populate; CHECK constraints fire on invalid state                                             |
| `tests/test_seed.py`                | 3    | `db/seed.py` populates a clean DB; counts match SAMPLE_DATA.md inventory; round-trip via SQLModel matches sample-data fixtures                                 |
| `tests/test_auth.py`                | 3    | `bcrypt` hash + verify; JWT issue + verify; cookie flags; CSRF double-submit; brute-force rate-limit at 5 fails / 15min                                        |
| `tests/test_llm_provider.py`        | 3    | Each provider's `complete` / `structured` / `stream` / `estimate_cost` / `model_name`; tracker logs to `ApiUsage`; retry policy on 429/timeout/500/schema-fail |
| `tests/test_vault.py`               | 3    | AES-256-GCM round-trip; PBKDF2 key derivation; concurrent read/write safety (file lock); audit log line per op                                                 |
| `tests/test_application_service.py` | 6    | DRAFT lifecycle: get_or_create_draft, submit_draft (success + failure), discard_draft, process_auto_apply_queue, validate_submittable                          |
| `tests/test_document_generator.py`  | 6    | resume + cover letter pipelines; bullet selection respects `selection_override`; page-count validation retry; ScreenerAnswer auto + drafted creation           |
| `tests/test_typst.py`               | 6    | `compiler.compile` returns valid PDF; `validator.validate_page_count` correct                                                                                  |
| `tests/test_ats_adapters.py`        | 6    | Greenhouse / Lever / Ashby `submit` against mocked HTTP; `SubmissionResult` shape; failure classification                                                      |
| `tests/test_notifications.py`       | 6    | Discord embed format; Telegram bot send; per-event toggle from `Settings.notifications_enabled`                                                                |
| `tests/test_portfolio_sync.py`      | 6    | `/api/portfolio/cv` filters EEO/visa/salary; CORS allows crypticsoul.dev; Netlify webhook fires on Profile update                                              |

All tests run in `uv run pytest`. Wave-3 + Wave-6 tests live alongside the source (`src/...` + `tests/`).

### F · Security review checkpoints

`security-review` skill runs at three checkpoints:

1. **After Wave 3 auth lands** — review `services/auth.py`, JWT cookie flags, CSRF double-submit pattern, bcrypt cost, brute-force rate limit.
2. **After Wave 3 vault lands** — review AES-256-GCM key derivation, file lock concurrency, audit log completeness, secret-value never logged in any path.
3. **Before Wave 6 ships** — review `document_generator` (untrusted JD input → Typst template injection), `application_service.submit_draft` (input sanitization for ATS POST bodies), `portfolio_sync` public API (no info leak), full vault audit trail.

Each checkpoint produces a written report; any HIGH or CRITICAL findings block the wave.

### G · Build order calendar

Multi-week:

- **Wave 3 (~2 weeks)**:
  - Week 1: models + Alembic + seed + auth + LLM abstraction + vault
  - Week 2: `ats_credentials` + Settings persistence + profile_service partial + sample-data accessor swap; security review checkpoint 1 + 2
- **Wave 6 (~3 weeks)**:
  - Week 1: `document_generator` + Typst templates + `application_service` DRAFT lifecycle
  - Week 2: ATS adapters (Greenhouse + Lever + Ashby) + cron registration + `portfolio_sync` + `notifications`
  - Week 3: handler swap (sample-data accessors → DB), end-to-end smoke, security review checkpoint 3

Phase 2-6 ship across the following weeks per their own plans.

### H · Out-of-scope items explicitly forbidden in this plan

- ❌ Workday / LinkedIn / Indeed / Generic ATS adapters (Phase 1.x sub-prompt; needs credentials + Playwright + manual review queue)
- ❌ Job scrapers (Phase 2)
- ❌ AI job scoring full pipeline (Phase 3 — Wave 3 ships LLM abstraction; Phase 3 ships `prompts/score_job` end-to-end)
- ❌ Email integration (Phase 4)
- ❌ LinkedIn DMs / Discord inbound / Telegram inbound (Phase 5)
- ❌ Prometheus / Sentry / OTel / pgvector / light mode / LaTeX (Phase 6)
- ❌ Re-introducing oneline/detailed bullet split, `/generate/*` routes, flat status enum
- ❌ Storing secret material in DB rows — vault is the only path
- ❌ Storing the vault master key in DB — derived from `SECRET_KEY` env / passphrase only
- ❌ Logging secret values in any audit / request / error path
- ❌ DaisyUI / light-mode in this plan (already removed in plan 08; doesn't get reintroduced)
- ❌ Bypassing bcrypt for "fast tests" — tests use bcrypt cost=4 via env override, not plain hashing

## Open questions

1. **Wave 3 + Wave 6 in one plan vs. split into 10a / 10b.** Recommendation: **one plan, two-part kickoff prompt**. Single approval cycle for the user; tightly-coupled scope (Wave 6 reuses Wave 3's models, services, vault). The kickoff prompt is structured so Wave 3 ships first, then a fresh session pastes the Wave 6 part once Wave 3 verifies clean. If the implementer flags scope blowup mid-Wave-6, escalate to `10b-wave-6-revised.md` then.

2. **`ApiUsage` table — Wave 3 or Phase 2+?** DATA_MODEL.md § B says Phase 2+ but Settings · LLM Provider's "THIS MONTH" cost card needs it. Recommendation: **Wave 3**. Adding it later means a migration + cost-card-broken interim. Cost is low: one table, one index, used on every LLM call.

3. **Manual review queue for ATS auto-apply failures.** When Greenhouse / Lever / Ashby return CAPTCHA / auth_required, the DRAFT stays in DRAFT and surfaces in `/discover/{id}` for manual fix-up. Where does the surface live? Recommendation: **a banner card on Discover · review & apply** when `Application.submission_artifacts.last_failure` is populated. Plan 09 stubs this; Wave 6 wires it real.

4. **`db/seed.py` idempotency.** ON CONFLICT DO NOTHING per row, or wipe-and-reload on every run? Recommendation: **ON CONFLICT DO NOTHING**. Wipe-and-reload is destructive; users may add their own data on top of seed during dev. The dev orchestrator (`nix run .#dev`) seeds once on first run; subsequent runs are no-op.

5. **Bcrypt cost for tests.** Cost=12 is too slow for tests (~250ms per hash). Recommendation: **env override** `NAAVIK_BCRYPT_COST=4` in tests; production stays cost=12. Documented in test fixture.

6. **Vault master key derivation.** PBKDF2 (100k iterations) vs. Argon2id? Recommendation: **PBKDF2** for Phase 1 (Python stdlib `hashlib.pbkdf2_hmac`); Argon2id requires `argon2-cffi` dep. Argon2 migration is a Phase 6 polish item if security review flags it.

7. **JWT secret rotation.** When `SECRET_KEY` env changes, all JWTs invalidate. Should Naavik support multiple active signing keys (key-id in JWT header)? Recommendation: **single key, no rotation**. Self-hosted instances rarely rotate; cloud tier rotates by version-pinning. Phase 6+ if needed.

8. **`prompts/score_job` Wave 3 vs Wave 6 vs Phase 3.** It depends on the LLM abstraction (Wave 3) but the full scoring pipeline (visa filter, tag matching, gap analysis) is Phase 3. Recommendation: **ship `prompts/score_job` skeleton in Wave 3** (returns a real but naive score from the LLM), make it real-pipeline in Phase 3.

9. **Document generator's Typst template re-use.** Should Wave 6 ship one `onepage.typ` (NEU style) only, or multiple templates from the start? Recommendation: **one template (`onepage.typ`) Wave 6**; additional templates (`modern`, `academic`, `creative`) are Phase 6.

10. **CORS for `/api/portfolio/*`.** Currently strict to `https://crypticsoul.dev`. Should it be configurable via `Settings.portfolio_cors_allowed_origins`? Recommendation: **configurable — list field in Settings**. Default = `["https://crypticsoul.dev"]`. Lets self-hosters point at their own portfolio domain without code changes.

11. **`security-review` skill scope.** Three checkpoints listed (auth + vault + Wave 6 final). Should we add a fourth at "after model definitions land" to catch CHECK constraint omissions? Recommendation: **yes, add a fourth** — after Wave 3.B.1 + B.2 land, before B.3 starts. Catches schema-side issues early.

## Approval checklist

User ticks each item before plan moves to APPROVED. Agent does NOT author the kickoff prompt until all are ticked.

### Multi-wave structure (§ A)

- [x] Wave 3 + Wave 6 detailed in this plan; Phase 2-6 outlined as future sub-plans
- [x] Single plan, two-part kickoff prompt — agree?
- [x] Wave 3 ships before Wave 6's part of the kickoff prompt is pasted

### Wave 3 — initial backend (§ B)

- [x] § B.1 SQLModel models — 18 entities + Settings, file split per `src/models/{user,profile,job,application,contact,email,event,settings,enums,app_event_payloads}.py`
- [x] § B.2 Alembic initial migration — single file; pgvector extension enabled; every table + index + CHECK
- [x] § B.3 Auth — bcrypt cost=12, JWT cookie (HttpOnly + Secure + SameSite=Strict), CSRF double-submit, brute-force rate limit
- [x] § B.4 LLM abstraction — `LLMProvider` ABC + 3 implementations + tracker; `ApiUsage` table in Wave 3 (NOT Phase 2+)
- [x] § B.5 Vault — `~/.naavik/secrets.enc` AES-256-GCM, PBKDF2 key derivation, audit log
- [x] § B.6 ATS credentials — DB row metadata + vault-backed secret resolution
- [x] § B.7 Profile service partial — CRUD + bullet ops + per-field PUT
- [x] § B.8 Settings persistence — per-user singleton, vault-routed secrets, scheduler reschedule on save
- [x] § B.9 `db/seed.py` — idempotent (ON CONFLICT DO NOTHING), CLI invocable
- [x] § B.10 Page handler swap — sample-data accessor bodies become DB queries; plan 09 pages render unchanged

### Wave 6 — real backend (§ C)

- [x] § C.1 Service catalog — 14 services map to BACKEND.md § H.1
- [x] § C.2 Document generator — bullet selection + trim + Typst compile + page-count validation; `answer_screeners` auto + drafted
- [x] § C.3 Application service — full DRAFT lifecycle; `validate_submittable`; `process_auto_apply_queue`
- [x] § C.4 ATS adapters — Greenhouse + Lever + Ashby in Wave 6; Workday/LinkedIn/Indeed/Generic deferred to Phase 1.x sub-prompt
- [x] § C.5 Notifications — Discord webhook + Telegram outbound + in-app toast routing; per-event toggle
- [x] § C.6 Portfolio sync — `/api/portfolio/cv` filtered + `/api/portfolio/resume.pdf` + Netlify webhook
- [x] § C.7 Cron registration — auto_apply (5min) + admin crons; Phase 2-5 crons deferred

### Phase 2-6 outline (§ D)

- [x] Each phase has a one-paragraph scope + acceptance summary
- [x] Each phase will graduate to its own plan + kickoff prompt (numbered 11+) when its time comes
- [x] No Phase 2-6 code authored in this plan

### Tests (§ E)

- [x] `tests/test_models.py` (Wave 3)
- [x] `tests/test_seed.py` (Wave 3)
- [x] `tests/test_auth.py` (Wave 3)
- [x] `tests/test_llm_provider.py` (Wave 3)
- [x] `tests/test_vault.py` (Wave 3)
- [x] `tests/test_application_service.py` (Wave 6)
- [x] `tests/test_document_generator.py` (Wave 6)
- [x] `tests/test_typst.py` (Wave 6)
- [x] `tests/test_ats_adapters.py` (Wave 6)
- [x] `tests/test_notifications.py` (Wave 6)
- [x] `tests/test_portfolio_sync.py` (Wave 6)

### Security review (§ F)

- [x] Checkpoint 1 — after auth lands (Wave 3)
- [x] Checkpoint 2 — after vault lands (Wave 3)
- [x] Checkpoint 3 — before Wave 6 ships
- [x] Checkpoint 4 (optional) — after model definitions land — recommend add
- [x] HIGH or CRITICAL findings block the wave

### Build order (§ G)

- [x] Wave 3 ~2 weeks; Wave 6 ~3 weeks; Phase 2-6 across following weeks
- [x] Calendar is informational, not enforced

### Out-of-scope (§ H)

- [x] No Workday / LinkedIn / Indeed / Generic ATS adapters (Phase 1.x)
- [x] No scrapers / scoring / email / outreach / observability (Phase 2-6)
- [x] No re-introducing oneline/detailed split, `/generate/*` routes, flat status enum
- [x] No secrets in DB rows
- [x] No vault master key in DB
- [x] No logging secret values
- [x] No bcrypt bypass in production tests
- [x] No DaisyUI / light mode reintroduction

### Open questions (§ Open questions)

- [x] Q1 One plan, two-part kickoff prompt — agree?
- [x] Q2 `ApiUsage` table in Wave 3 (not Phase 2+) — agree?
- [x] Q3 Manual review queue surface = Discover · review banner — agree?
- [x] Q4 `db/seed.py` ON CONFLICT DO NOTHING — agree?
- [x] Q5 Test bcrypt cost=4 via env override — agree?
- [x] Q6 PBKDF2 (not Argon2id) for vault — agree?
- [x] Q7 Single JWT signing key (no rotation) — agree?
- [x] Q8 `prompts/score_job` Wave 3 skeleton + Phase 3 full — agree?
- [x] Q9 One Typst template (`onepage.typ`) Wave 6 — agree?
- [x] Q10 `Settings.portfolio_cors_allowed_origins` configurable list — agree?
- [x] Q11 Add 4th security checkpoint after model definitions — agree?

Once every box is ticked, plan moves to APPROVED. Agent then authors `docs/prompts/10-backend-impl.md` (two-part: Wave 3 + Wave 6) — to be pasted into separate fresh sessions with the Wave 6 part deferred until Wave 3 verifies clean.
