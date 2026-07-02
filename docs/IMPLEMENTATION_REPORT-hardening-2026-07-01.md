# Naavik Production-Hardening Pass — Implementation Report

> **Date:** 2026-07-01
> **Scope:** Make the app self-hosted and production-capable — live persistence,
> no mock-dependent flows, no dead buttons, no fake success states, clean
> relational model. Audit → fix → verify.
> **Result:** All fixes implemented (not just audited). Full suite green
> (2353 passed, 14 skipped), ruff clean, fresh-install migration chain now
> reaches head from an empty Postgres, all changed surfaces smoke-tested live.

---

## 1. What Naavik is (inferred from code, not roadmap)

Naavik is a self-hosted-first career-automation platform: scrape jobs → score
them against a parsed résumé profile → generate tailored résumé + cover-letter
PDFs (Typst) via a user-selected LLM (Anthropic / OpenAI / Ollama) → track
applications through a pipeline → optional auto-apply + email monitoring +
outreach. Stack: FastAPI + SQLModel (async) + Alembic + Postgres/pgvector,
HTMX + Jinja + Tailwind/DaisyUI, APScheduler. "Fable 5" is not a product
concept in this repo — it is the model identity of the assistant that ran this
pass; the app's own LLM layer is provider-agnostic (`src/llm/`).

---

## 2. Commands run + results

| Check | Command | Result |
|---|---|---|
| Lint | `ruff check .` | **PASS** (clean) |
| Format | `ruff format --check .` | **PASS** (450 files) |
| Tests | `uv run pytest` | **2353 passed, 14 skipped** (was 2348; +5 new) |
| Migrations (incremental) | `alembic upgrade head` on dev DB | **PASS** → `0025` |
| Migrations (fresh install) | `alembic upgrade head` on empty Postgres | **PASS** → `0025`, 30 tables (was FAILING at `0021`) |
| Migration round-trip | `alembic downgrade -1 && upgrade head` | **PASS** |
| Startup | `nix run .#dev` + `/api/health` | **200 OK**, `/` → 307 → `/login` |
| Live CRUD/auth smoke | curl against `:8003` | **PASS** (see §6) |

---

## 3. Critical / High findings — fixed

### 3.1 CRITICAL — Authentication bypass via `naavik_session=fake-1`
`services/auth.py:require_authed_session` honored the plan-09 dev bootstrap
cookie in **all** environments, mapping any request carrying
`Cookie: naavik_session=fake-1` to the seeded owner (user 1) — a full auth
bypass on ~125 handlers. **Fix:** the fake session is now honored **only when
`settings.debug` (`NAAVIK_DEBUG=1`)** is set; outside dev it is rejected like
any invalid session. Verified live (dev honors it; unit test confirms
production rejects with 307/401). `.env.example` + `DEPLOYMENT.md` now flag
`NAAVIK_DEBUG` as a production auth-bypass switch.

### 3.2 CRITICAL — IDOR on bullet mutation endpoints
`POST/PUT/DELETE /api/v1/bullets/*` + `/reorder` + `/rewrite` accepted arbitrary
`bullet_id`/`experience_id` with **no ownership check** — any user could edit or
delete another user's résumé bullets by id. **Fix:** added
`profile_service.owns_bullet` / `owns_experience` (Bullet→Experience→Profile→user
join) and gated every bullet mutation; cross-user ids now 404. Covered by
`tests/test_hardening_pass.py`.

### 3.3 HIGH — Fake success: Settings account password change
`PUT /api/v1/settings/account/password` returned `"Password updated."` without
touching the DB. **Fix:** real change — re-verify current password, complexity
check, rotate bcrypt hash, revoke the presenting JWT, re-issue session/CSRF
cookies. Wrong current password → honest 422 (verified live). CSRF-gated.

### 3.4 HIGH — Fake success: Delete account
`POST /api/v1/settings/account/delete` returned 204 and deleted nothing.
**Fix:** new `services/account_service.delete_user_account` hard-deletes the user
and every owned row (child→parent order, DB-portable), clears cookies, redirects
to `/login`. Covered by a test proving user 1's data is removed while user 2's
survives.

### 3.5 HIGH — Fake success: Notification "Test" button
`POST /api/v1/settings/notifications/test` reported success without sending.
**Fix:** real send via `notifications.send_test_message` (new); honest 422 with
the missing-env-var name when the channel isn't configured (verified live).

### 3.6 HIGH — Fake AI: bullet rewrite
`POST /api/v1/bullets/{id}/rewrite` appended a literal `" (rewritten by AI)"`.
**Fix:** real LLM call via the existing `trim_bullet` prompt through
`llm_tracker.tracked_call` (records `ApiUsage`); 422 when no provider is
configured instead of pretending.

### 3.7 HIGH — Mock data in production: Discover review cover letter
`ui/discover_review_ctx.py` rendered a hardcoded Intuit/Stripe cover letter into
**every** job's review workspace. **Fix:** cover section text is persisted on the
generated document (`document_generator`) and read back via
`application_service.get_latest_cover_sections`; the workspace shows the real
letter or an honest empty state. Section edits + the "Regen" button are now
real, DB-backed, and IDOR-checked (were a process-global dict + a fake SSE
chunk stream).

### 3.8 HIGH — Core feature never wired: résumé structured parse
Onboarding upload only stored raw text + regex-filled name/email/phone — the
`extract_to_profile` LLM pipeline (experiences + bullets) existed but was never
called ("résumé parse only fills the summary"). **Fix:** the upload now runs
`extract_to_profile` when an LLM provider is configured, with graceful fallback
to the regex path otherwise; the confirmation screen reports what was parsed.

### 3.9 HIGH (pre-existing) — Fresh-install migration blocker
A clean `alembic upgrade head` on an empty Postgres **failed at `0024`** and
halted at `0021` — a `docker compose up` blocker on any new host. Two root
causes, both introduced by plan 90 (0.5.0) and never caught (CI runs on SQLite
where enums are TEXT):
1. `0024` created its enums with `create_type=True`, double-creating
   `emailaccountprovider` → **fixed** with `create_type=False` +
   idempotent `.create(bind, checkfirst=True)`.
2. `0001_initial`'s `_TABLES_CREATED_LATER` set omitted `email_account` /
   `email_message`, so `0001` created them from live metadata and `0024`
   collided → **fixed** by adding them to the skip-set.
Fresh install now reaches `0025` with all 30 tables.

---

## 4. Medium findings — fixed

- **Tracking "Show closed" did nothing** — the toggle pointed at the full-page
  `/tracking` route and swapped it into a fragment slot. Rewired to
  `/_fragments/tracking/board` with `hx-push-url`. The list fragment also
  hardcoded `show_closed=True`; it now honors the query param.
- **Tracking list-row detail was a dead button** — the "⋮" control had no
  handler. Wired to the existing detail slide-over
  (`/_fragments/tracking/application/{id}`), matching the board card.
- **Apply action bar dead controls** — "Download bundle" (no handler) and
  "Open ATS" (`href="#"`) now hit the real bundle endpoint and the real job
  URL respectively.
- **Fake bundle download** — `/api/v1/applications/{id}/bundle` zipped
  `%PDF-1.4\n%placeholder` bytes. Now zips the real generated résumé/cover PDFs
  off disk + real screener answers; honest 409 when nothing is generated yet.
- **Deployment tab was almost entirely fake** — hardcoded uptime
  ("14d 6h"), a fabricated log-stream SSE, hardcoded on-disk stats
  ("412 MB · 27 jobs"), a fake "update available v0.4.3" prompt, and a dead
  Restart button. Replaced with real version, scheduler status, data-dir path,
  live job/application counts + real dir size, and honest "read logs via
  `docker compose logs` / `journalctl`" guidance. The fake restart + log SSE
  endpoints were removed (process lifecycle belongs to the supervisor).

---

## 5. Data model — ERD + integrity

- **Referential integrity (new migration `0025_fk_ondelete_rules`).** Every FK
  previously used Postgres default `NO ACTION`. Now explicit and principled:
  **non-null (owned) FK → `ON DELETE CASCADE`**, **nullable (reference) FK →
  `ON DELETE SET NULL`**. Declared at the model layer
  (`Field(..., ondelete=...)`, all 40 FKs) so fresh installs emit matching DDL,
  and applied to existing Postgres via a constraint-name-discovery migration
  (SQLite no-op). Verified on live Postgres (`settings.user_id`=CASCADE,
  `application.job_id`=SET NULL, etc.) and round-trips cleanly.
- **ERD docs.** `docs/design/ERD.md` (categorized) and
  `docs/design/ERD_v2.md` (single unified Mermaid diagram) were already valid
  (the owner-reported `PK_FK`/`FK_UK` parse errors had been fixed to `PK,FK`).
  `ERD_v2.md` gains a **Referential Integrity** section documenting the new
  ON DELETE rules.
- **Deferred (documented in ERD_v2 critique, not blocking):** no `Company`
  entity (free-text company on Job/Application/Contact); `Settings`
  junk-drawer (40+ columns); `EmailThread.messages` JSONB blob; inconsistent
  soft-delete across profile children; unchecked `Bullet.tags`/`Project.tags`
  arrays; vestigial `User.is_admin` / `Settings.allow_multiple_users`.

---

## 6. Live verification (curl against running server)

```
signup fresh user                                  → 204
settings LLM PUT then GET round-trip               → persisted (ollama/qwen3:8b)
auto-apply / notifications PUT                      → persisted (real payloads)
notification test (discord, unconfigured)          → 422 "DISCORD_WEBHOOK_URL not set"
account password change, wrong current             → 422 "incorrect"
deployment restart endpoint (removed)              → 404
deployment logs SSE (removed)                      → 404
tracking board fragment (show_closed)              → 200, fragment (no <html>)
deployment tab HTML                                → v0.2.6, "scheduler running", no fake data
fresh Postgres alembic upgrade head                → head 0025, 30 tables
```

---

## 7. Self-hosting

- **`docker compose up` fresh-install now works** (see §3.9). Compose already
  requires `SECRET_KEY` (`${SECRET_KEY:?...}`) and auto-runs migrations.
- **Docs corrected.** `DEPLOYMENT.md` Docker quick-start previously claimed
  "defaults work out of the box" — false, since `SECRET_KEY` is mandatory. Now
  shows key generation, a `POSTGRES_PASSWORD` production warning, the
  first-user signup step, and an explicit **never-set-`NAAVIK_DEBUG`-in-prod**
  warning (it re-enables the auth-bypass cookie). `.env.example` carries the
  same `NAAVIK_DEBUG` warning.
- **First run:** open the app → Create account (first signup owns the instance;
  no seeded credentials). Confirmed live.
- **Secrets hygiene:** no committed secrets; API keys/webhooks are env-only;
  IMAP creds Fernet-encrypted; bcrypt password hashing. (Unchanged — verified.)

---

## 8. Tests added

`tests/test_hardening_pass.py` (5 tests): fake-session gated by debug (reject in
prod / allow in dev), bullet ownership guard, account deletion removes owned
rows only, cover-section persistence + IDOR. Updated `test_stub_endpoints.py`
to assert the new real contracts (password validation, CSRF gate, removed
restart endpoint, honest notification/bundle responses).

---

## 9. Risks + prioritized limitations

**Low risk in this pass**
- `0024` and `0001` migrations were edited for the fresh-install fix. Existing
  DBs at `≥0024` never re-run them; the end state is identical. Verified via a
  full clean-DB replay to head.
- `account_service.delete_user_account` deletes explicitly (portable) rather
  than relying solely on the new cascade — intentional, so it works on the
  SQLite test backend too.

**Not addressed (documented, not blocking self-host)**
1. **Auto-apply submission is not built** — the Playwright ATS adapters
   (`services/ats/*`) raise `NotImplementedError` and no browser pool is wired;
   they fail closed with `FAILURE_AUTH_REQUIRED`, so there is no fake success,
   but auto-submit to Workday/LinkedIn/Indeed does not work. This is milestone
   0.8.0 territory. Recommend hiding the auto-apply "submit" affordance until
   an adapter ships, or clearly labeling it experimental.
2. **OAuth token refresh cron is a stub** (`scheduler/jobs.py`) — Phase 4.
3. **Public portfolio API is single-user** (`user_id=1` hardcoded) — correct
   for single-user self-host; multi-tenant dispatch is future work.
4. **Data-model normalization debt** — Company entity, Settings split,
   EmailMessage normalization (see §5 / ERD_v2 critique).
5. **Dead (but unreachable) code** — the `/_fragments/settings/test-connection`
   fake LLM-test fragment is not wired to any button; left in place to avoid
   churn, noted here.
6. `docker compose config` could not be validated in this environment (no
   docker binary); the compose file was not structurally changed.

---

## 10. Files changed (summary)

- **Security:** `services/auth.py` (fake-session gate), `api/profile.py` +
  `services/profile_service.py` (bullet IDOR + real rewrite).
- **Fake-success → real:** `ui/routes/settings.py` (password, notifications
  test, deployment info, on-disk, removed fake restart/log endpoints),
  `services/account_service.py` (new), `services/notifications.py`
  (`send_test_message`), `ui/routes/discover.py` + `ui/discover_review_ctx.py` +
  `services/document_generator.py` + `services/application_service.py` (real
  cover letter), `ui/routes/tracking.py` (real bundle, show_closed),
  `ui/routes/auth.py` (résumé parse wiring).
- **Data model:** all `src/models/*.py` (ondelete), `migrations/versions/0025_fk_ondelete_rules.py` (new).
- **Fresh install:** `migrations/versions/0024_email_account_message.py` +
  `0001_initial.py`.
- **Templates:** deployment, tracking board/list-row, apply action bar, cover
  letter partial, onboarding confirmation.
- **Docs:** `DEPLOYMENT.md`, `.env.example`, `docs/design/ERD_v2.md`,
  this report.
- **Tests:** `tests/test_hardening_pass.py` (new), `tests/test_stub_endpoints.py`.
