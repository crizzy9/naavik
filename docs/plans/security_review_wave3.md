# Security review — Wave 3 checkpoints

> **Status:** advisory log written by the implementing agent during plan 10
> Wave 3 build. The full `security-review` skill should be run by an
> independent reviewer before Wave 6.

## Checkpoint 4 — post-models, pre-Alembic (2026-05-02)

Reviewed: `src/models/*.py`, `src/models/enums.py`, `src/models/app_event_payloads.py`.

### Findings

- **No secret material in models.** ✅
  - `User.password_hash` is a column for bcrypt hashes; never a plaintext password.
  - `Settings.llm_api_key_fingerprint` is a sha256 hash of the API key (set by `services/settings_service`); the actual key lives in vault.
  - `Settings.discord_webhook_configured`, `telegram_bot_configured`, `portfolio_webhook_configured` are booleans only; URLs/tokens live in vault.
  - `ATSCredential` is metadata-only (has_credential, login_status, last_login_at, last_failure_kind); cookies/tokens live in vault.
  - No raw `api_key` / `password` / `token` / `secret` columns on any model.
- **CHECK constraints land at the DB layer.** ✅
  - `Application` carries the corrected 2026-05-01 form: `applied_at IS NOT NULL OR status = 'DRAFT' OR deleted_at IS NOT NULL`. Covers the discarded-DRAFT corner case.
  - `Application.closed_reason IS NOT NULL WHEN status = 'CLOSED'`.
  - `Job.score` clamped to `[0.0, 1.0]`.
  - `Job.salary_min <= salary_max OR salary_min IS NULL`.
  - `Profile.salary_expectation_usd >= 0`, `notice_period_days >= 0`.
  - `Bullet.text` non-empty.
  - `Skill.category` non-empty.
  - `Experience` start_date < end_date (when end_date set).
- **Soft-delete on user-authored entities.** ✅
  - `deleted_at` nullable timestamp on User, Profile, Experience, Bullet, Project, Job, Application, Contact, OutreachMessage.
  - Partial unique indexes use `WHERE deleted_at IS NULL` so re-creating a user/job/contact after soft-delete works.
- **Per-user scoping.** ✅ Every operational table carries `user_id` FK with index. Phase 1 single-user MVP; multi-user safe.
- **Indexes match DATA_MODEL.md § G.** ✅ Spot-checked Application, Job, Contact, OutreachMessage, EmailThread, AppEvent, ApiUsage, GeneratedDocument.
- **GIN indexes on tag arrays.** ✅ `bullet`, `project`, `job` declare `postgresql_using="gin"`.

### Notes

- SQLModel `Relationship()` declarations stripped from Wave-3 models — services use explicit `select(...)` joins. This avoided a SQLModel 0.0.22 forward-ref resolution edge case (Job ↔ Application ↔ Contact circular graph). Wave 6 may revisit if relationship lazy-loading becomes ergonomic.
- `Settings.deployment_version` is runtime-populated via package metadata; not stored. ✅
- `cover_letter_base` JSONB on Profile carries placeholder paragraphs (no PII beyond what user enters).
- `submission_artifacts` JSONB on Application is opaque-to-DB — Naavik never queries by its contents. ATS adapter writes; UI reads.
- `messages` JSONB on EmailThread holds first-500-char body previews; full bodies fetched on-demand from Gmail per BACKEND.md § G.13. ✅ (no PII bloat in DB).

### Open follow-ups

- **Pgvector extension** is enabled in `0001_initial.py` even though no pgvector table ships in Phase 1. Cheap insurance for Phase 6 `JobEmbedding`.
- **`AppEvent.payload` shape** is enforced at the service layer via `models.app_event_payloads.parse_payload(kind, raw)`. Phase 1 doesn't add a postgres CHECK on the JSONB shape (would be brittle); the Pydantic discriminated union catches drift.

### Verdict

No HIGH or CRITICAL findings. Schema-side issues caught early; CHECK constraints
+ soft-delete partial uniques + secret-boundary discipline all in place. Ready
to proceed to `0001_initial.py`.

## Checkpoint 1 — post-auth (2026-05-02)

Reviewed: `src/services/auth.py`, `src/api/auth.py`, `tests/test_auth.py`.

### Findings

- **Password hashing.** ✅
  - `bcrypt` cost=12 in production; cost=4 in tests via `NAAVIK_BCRYPT_COST` env override.
  - `verify_password` runs over a dummy hash on user-not-found to keep timing constant — prevents email enumeration via login latency.
  - `verify_password` returns False on empty input + corrupt hashes (no exception leak).
  - Returned hash is bcrypt's `$2b$` format; never a different algorithm.
- **JWT.** ✅
  - HS256 over `Settings.secret_key`. Single signing key — deferred multi-key rotation per plan 10 Q7 (Phase 2+).
  - `iat` + `exp` claims set; `verify_jwt` returns None on expired/invalid (no swallowing of cryptographic errors that could mask attack).
  - `keep_signed_in=True` extends TTL to 30d; default 24h.
- **Cookie flags.** ✅
  - `naavik_session` (JWT): `HttpOnly` + `Secure` + `SameSite=Strict` + `Path=/`. No `Domain=` (host-only).
  - `naavik_csrf`: NOT HttpOnly (JS reads it for double-submit) + `Secure` + `SameSite=Strict`.
  - `Secure` flag relaxed only when `app.debug` is True (local dev).
- **CSRF.** ✅
  - Double-submit pattern: server cookie + `X-CSRF-Token` header.
  - `validate_csrf` uses `secrets.compare_digest` (constant-time).
  - Rotation on auth events (login/logout). `require_csrf` dependency exposed for state-changing routes.
- **Brute-force guard.** ✅
  - 5 failed attempts / 15min per IP returns 429.
  - `record_login_attempt(success=True)` clears the IP's bucket.
  - In-process state — single-instance MVP. Phase 2+ may move to Redis when horizontal scale becomes a concern.
- **Email lookup.** ✅
  - Lower-cased + `deleted_at IS NULL` filtered.
  - `is_active=False` users rejected at authenticate-time AND at `get_current_user` resolve time.
- **No secret material in errors / logs.** ✅
  - `_login_error_card` only ever returns "Invalid credentials" or rate-limit message — never echoes back the entered email/password.
  - JWT verification failures return None silently; no log of token contents.

### Open follow-ups

- The default `secret_key="change-me-in-production"` in `config.py` is 23 bytes — below SHA256's 32-byte recommended minimum. PyJWT emits an `InsecureKeyLengthWarning`. **Self-hosters and cloud deployments MUST set `SECRET_KEY` to a 32+ byte value.** Vault initialization (Wave-3 vault service) requires the same env var; mismatched keys brick the vault per the `key_fingerprint` mechanism.
- `_login_attempts` dict has no TTL eviction beyond the per-IP 15-min rolling window. For a long-running process with many distinct IPs this leaks memory. Phase 2+ migrate to Redis.

### Verdict

No HIGH or CRITICAL findings. Auth path is production-safe given the
documented `SECRET_KEY` length requirement. Ready to proceed to vault.

## Checkpoint 2 — post-vault (2026-05-02)

Reviewed: `src/services/vault.py`, `src/cli/vault.py`, `tests/test_vault.py`.

### Findings

- **AES-256-GCM round-trip.** ✅
  - `cryptography.hazmat.primitives.ciphers.aead.AESGCM` with 32-byte key + 12-byte nonce.
  - Fresh nonce per write (re-keying via `secrets.token_bytes(12)` on every encrypt).
  - Fresh salt only on first creation OR rotate-key — preserves key derivation deterministic across reads of the same vault.
- **PBKDF2 key derivation.** ✅
  - `hashlib.pbkdf2_hmac("sha256", SECRET_KEY, salt, iterations=100_000, dklen=32)`. Per plan 10 Q6 (locked: PBKDF2 over Argon2id for Phase 1).
  - Test confirms deterministic for same input + different per-secret + different per-salt.
- **`key_fingerprint` mismatch detection.** ✅
  - Stored as plaintext header (32 bytes) so the server can detect mismatch BEFORE attempting AES decrypt.
  - `secrets.compare_digest` for constant-time comparison.
  - On mismatch, `VaultLockedError` raised with clear remediation hint.
  - `is_locked()` exposes the boolean for Settings · Deployment banner.
- **File-locking concurrency.** ✅
  - Sibling `.lock` file (never replaced) holds `fcntl.LOCK_EX`; the main vault file gets atomic-replaced via `os.replace`.
  - Fixed a bug found during the test pass — the original implementation locked the vault fd directly, which got stale on `os.replace`. The lockfile pattern now serializes 10 concurrent writes correctly.
- **Audit log.** ✅
  - One line per `get` / `set` / `delete` / `list` / `rotate-key` to `~/.naavik/data/logs/vault-audit.log`.
  - JSON format: `{ts, op, scope, key, caller}`.
  - **Test confirms secret value never appears in audit log** (the value is set in the test, then audit log read back and asserted not to contain the value string).
- **No master key in DB.** ✅ Master key is derived on every operation from `SECRET_KEY` env. Never persisted.
- **No secret material returned by `list_keys`.** ✅ Returns names only.
- **Atomic write.** ✅ `tempfile + os.replace` pattern; `os.fsync` before swap. Mode 0o600 on tmp + final.
- **Rotate-key.** ✅
  - `--old` + `--new` required.
  - Fresh salt + nonce on rotation.
  - Backup at `secrets.enc.bak.YYYY-MM-DD-HH-MM` unless `--no-backup`.
  - End-to-end CLI demo: stored 3 secrets with old key → rotated → secrets readable with new key.
- **Defaults safe for new install.** ✅ When `secrets.enc` doesn't exist, the vault returns empty + initializes a fresh salt on first `set()`.
- **No path traversal.** ✅ Vault path resolved relative to `Settings.data_dir` only; scope/key strings never become file paths.

### Open follow-ups

- **Argon2id migration.** Plan 10 Q6 deferred this; revisit in Phase 6 if security review flags PBKDF2 strength as inadequate for the threat model.
- **Settings · Deployment UI banner** when `is_locked() is True` — wired in `services/settings_service.py` + the deployment tab template. Tested manually (deliberately set wrong SECRET_KEY → banner fires).
- **Periodic vault integrity audit** (cron) — Phase 2+; cheap insurance.

### Verdict

No HIGH or CRITICAL findings. Vault boundary is sound; secret material
never logged; concurrent writes safe; rotate-key end-to-end verified.
Ready to proceed to LLM abstraction.
