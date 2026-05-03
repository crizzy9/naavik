---
Status: USED
Type: implementation kickoff (two-part)
Plan: docs/plans/10-backend-impl.md
Authored: 2026-05-01
Last updated: 2026-05-03 (PART 1 / Wave 3 + PART 2 / Wave 6 both USED — Phase 1 backend complete)
Prerequisite: Wave 3 (plan 09) shipped clean — every screen renders end-to-end with sample data, all 22 Playwright snapshots committed, all stub endpoints respond.
---

# Naavik · Backend implementation — implementation kickoff (two-part)

This file has **two parts**, each pasted into a separate fresh Claude Code session:

- **PART 1 (Wave 3 / plan 10 § B)** — backend substrate: 19 SQLModel entities + Alembic + auth + LLM abstraction + vault + initial services + accessor body swap. Pasted **after plan 09 ships and verifies clean**.
- **PART 2 (Wave 6 / plan 10 § C)** — real services + Typst document generator + DRAFT lifecycle + Greenhouse / Lever / Ashby ATS adapters + portfolio sync + auto-apply cron. Pasted **only after Part 1 ships, security review checkpoints 1+2+4 pass clean, and the side-by-side `NAAVIK_PERSISTENCE=memory|db` smoke matches**.

The repo is at `/home/nightwatcher/personal/dev/naavik`.

---

# PART 1 — Wave 3 (plan 10 § B)

> Paste THIS PART (everything from "PART 1" header above through "END OF PART 1" below) as the first message of a fresh Claude Code session.

## Goal

Land the data substrate + auth + LLM abstraction + vault + initial services so plan 09's stub endpoints + sample-data accessor bodies can swap to real DB-backed implementations **without UI churn**. After Part 1 ships: every page renders identically, reads come from Postgres, auth + Settings persist, LLM calls produce real responses with cost + token tracking, vault stores secrets at `~/.naavik/secrets.enc` with key-rotation CLI ready.

## Required reading (in order)

1. `AGENTS.md` § Workflow.
2. `CLAUDE.md`.
3. `ROADMAP.md` § Phase 1 § Implementation waves → Wave 4 row + per-task checklist.
4. `docs/plans/10-backend-impl.md` — **THE PLAN.** Status: APPROVED. Read § A multi-wave structure + § B (Wave 3) end-to-end + § E tests + § F security review + § H out-of-scope.
5. `docs/design/BACKEND.md` § A file layout, § D JSON API, § G HTTP conventions, § H services, § L (vault, integrations, secrets boundary), § M LLM abstraction, § N observability.
6. `docs/design/DATA_MODEL.md` — full document, with care for § B inventory (19 entities incl. `ApiUsage`), § C model definitions (incl. corrected `Application` CHECK constraint, `Settings.eager_review_generation`, `daily_llm_cost_cap_usd`, `portfolio_cors_allowed_origins`), § D enums, § E state transitions, § G indexes, § H migration strategy + secrets boundary, § L Settings consumer mapping, § M AppEvent payload schemas.
7. `docs/design/SAMPLE_DATA.md` — for the seed pipeline.
8. `docs/design/INTERACTIONS.md` § A.4 persistent IDs (already wired in plan 08 base.html; Wave 3 doesn't touch them but understands them).
9. The archived plan 09 + plan 08 + their hand-back reports — context for what's already built.

Open question answers (locked by user 2026-05-01): one plan, two-part kickoff prompt; `ApiUsage` in Wave 3 (already promoted in DATA_MODEL.md § B); manual review queue surface = `up_next_card` `state="stuck"` on Discover right rail; `db/seed.py` `ON CONFLICT DO NOTHING`; test bcrypt cost=4 via env override; PBKDF2 (not Argon2id); single JWT signing key (no rotation); `prompts/score_job` Wave 3 skeleton + Phase 3 full pipeline; one Typst template (`onepage.typ`) Wave 6; `Settings.portfolio_cors_allowed_origins` configurable; 4th security checkpoint after model definitions.

## Deliverables

| Path | Description |
|---|---|
| `src/models/__init__.py` | Re-exports |
| `src/models/enums.py` | Every enum from DATA_MODEL.md § D |
| `src/models/user.py` | `User` |
| `src/models/profile.py` | `Profile`, `Experience`, `Bullet`, `Skill`, `Education`, `Project`, `Certification` |
| `src/models/job.py` | `Job` |
| `src/models/application.py` | `Application` (with the corrected CHECK constraint per DATA_MODEL.md § E), `ApplicationScreenerAnswer`, `GeneratedDocument`, `ATSCredential` |
| `src/models/contact.py` | `Contact`, `ContactApplicationLink`, `OutreachMessage` |
| `src/models/email.py` | `EmailThread` |
| `src/models/event.py` | `AppEvent` |
| `src/models/api_usage.py` | `ApiUsage` (entity #19) |
| `src/models/settings.py` | `Settings` (incl. `eager_review_generation`, `daily_llm_cost_cap_usd`, `portfolio_cors_allowed_origins`, `debug`) |
| `src/models/app_event_payloads.py` | Discriminated Pydantic union per DATA_MODEL.md § M |
| `migrations/versions/0001_initial.py` | Single Alembic migration: `CREATE EXTENSION vector` + every ENUM + every table + every index + every CHECK constraint. Reversible. |
| `src/services/auth.py` | bcrypt hash/verify; JWT issue/verify; `get_current_user` FastAPI dep; brute-force rate limit (5/15min) |
| `src/services/vault.py` | AES-256-GCM at `~/.naavik/secrets.enc`; PBKDF2 from `SECRET_KEY`; **`key_fingerprint` header for mismatch detection**; `get`, `set`, `delete`, `list`, `fingerprint`; audit log to `~/.naavik/logs/vault-audit.log`; `fcntl.LOCK_EX` |
| `src/cli/vault.py` | `naavik vault rotate-key --old=... --new=... [--no-backup]` CLI per plan 10 § B.5 |
| `src/services/ats_credentials.py` | DB row metadata + `vault.get(scope="ats", key=board)` resolution |
| `src/services/profile_service.py` | CRUD + per-field PUT + bullet ops + `update_application_questions`; profile-update emits `profile_updated` AppEvent (consumed by Wave 6 portfolio_sync debouncer) |
| `src/services/settings_service.py` | DB-backed CRUD; `PUT /api/v1/settings/llm` flows API key through vault; reschedule APScheduler jobs on sources save |
| `src/llm/__init__.py` | `get_provider(settings) -> LLMProvider` factory; vault-backed key resolution |
| `src/llm/base.py` | `LLMProvider` ABC |
| `src/llm/anthropic.py` | tool-use structured output |
| `src/llm/openai.py` | `response_format=json_schema` |
| `src/llm/ollama.py` | JSON mode |
| `src/llm/prompts/__init__.py` | Per-prompt module skeletons (`extract_resume`, `extract_job`, `score_job`, `select_bullets`, `trim_bullet`, `draft_cover_letter`, `answer_screener`, `classify_email`, `draft_outreach`, `auto_tag_bullets`) — each ships its Pydantic schema + a working callable; `score_job` returns a real-but-naive score (full pipeline is Phase 3 plan 12). |
| `src/services/llm_tracker.py` | `tracked_call` wrapper; logs to `ApiUsage`; retry policy per BACKEND.md § M.5 |
| `src/api/auth.py` | `/api/v1/auth/{login, logout, me, csrf}` real handlers (replacing plan 09 stubs) |
| `src/api/profile.py` | Profile + bullet endpoints (replacing plan 09 stubs) |
| `src/api/settings.py` | Settings endpoints (replacing plan 09 stubs); `Settings.debug` swap on `/_design/components` route |
| `src/db/seed.py` | Imports from `sample_data.py`; INSERTs in dependency order with `ON CONFLICT DO NOTHING`; CLI invocable via `uv run python -m src.db.seed` |
| `src/db/sample_data.py` | **Accessor bodies swapped from in-memory lists to DB queries** (signatures already async from plan 09). Module docstring + comment explaining the swap. |
| `src/ui/routes/*.py` | Page handlers updated to thread `session` + `current_user` into accessor calls (where they didn't already from plan 09) |
| `tests/test_models.py` | Every SQLModel instantiates from sample data; relationships back-populate; CHECK constraints fire on invalid state (incl. discarded-DRAFT corner case) |
| `tests/test_seed.py` | `db/seed.py` populates a clean DB; counts match SAMPLE_DATA.md inventory; round-trip via SQLModel matches sample-data fixtures |
| `tests/test_auth.py` | bcrypt + JWT + cookie flags (HttpOnly + Secure + SameSite=Strict) + CSRF double-submit + brute-force rate limit at 5 fails / 15min |
| `tests/test_llm_provider.py` | Each provider's methods + cost estimate; `tracked_call` logs to `ApiUsage`; retry policy on 429/timeout/500/schema-fail |
| `tests/test_vault.py` | AES-GCM round-trip; PBKDF2 key derivation; concurrent read/write safety (file lock); `key_fingerprint` mismatch detection; audit log line per op; rotate-key CLI dry-run |
| `tests/test_persistence_swap.py` | Side-by-side `NAAVIK_PERSISTENCE=memory|db` test — every page renders pixel-identically (or close) under both flags; this is the regression gate before deleting the env var |

## Build sequence (sub-week 1 then sub-week 2)

**Week 1:**
1. `src/models/*.py` (all 19 entities + Settings + enums) — ~1.5 days. **Stop and run security review checkpoint 4** (post-models, pre-Alembic) per plan 10 § F.
2. `migrations/versions/0001_initial.py` — half day.
3. `db/seed.py` + `tests/test_seed.py` — half day. Run `uv run alembic upgrade head` against a clean Postgres + `uv run python -m src.db.seed` — must populate cleanly.
4. `services/auth.py` + `api/auth.py` + `tests/test_auth.py` — 1 day. **Stop and run security review checkpoint 1** (auth) per plan 10 § F.
5. `services/vault.py` + `cli/vault.py` + `tests/test_vault.py` — 1 day. Includes `key_fingerprint` header + rotate-key CLI + Settings · Deployment mismatch warning. **Stop and run security review checkpoint 2** (vault) per plan 10 § F.

**Week 2:**
6. `src/llm/*` + `services/llm_tracker.py` + `tests/test_llm_provider.py` — 1.5 days.
7. `services/profile_service.py` + `services/settings_service.py` + `services/ats_credentials.py` — 1 day.
8. `src/api/profile.py` + `src/api/settings.py` real handlers — half day.
9. `db/sample_data.py` accessor body swap — 1 day. Every accessor's body becomes a DB query; signatures preserved.
10. `tests/test_persistence_swap.py` — half day.
11. Side-by-side smoke: spin up two dev servers (`NAAVIK_PERSISTENCE=memory` on :8000 + `NAAVIK_PERSISTENCE=db` on :8001 against the seeded DB). Visit each of the 11 screens on both. Diff Playwright snapshots — should be pixel-identical given same sample data. Document any deltas.
12. Once smoke passes, the `NAAVIK_PERSISTENCE` env var is removed (always `db` now).

## Quality bar

```bash
uv run alembic upgrade head            # clean
uv run python -m src.db.seed           # populates without conflict
uv run ruff check .                    # clean
uv run pytest tests/                   # all green
uv run fastapi dev src/main.py         # boots without warning
```

Functional checks:

- `POST /api/v1/auth/login` with the seeded user (Shyam, hashed via bcrypt cost=4 in tests, cost=12 prod) round-trips real bcrypt + sets JWT cookie with proper flags.
- `naavik vault rotate-key --old=... --new=...` CLI re-encrypts the vault and writes a `.bak` file.
- Settings · Deployment shows the vault `key_fingerprint` match status (matches by default; deliberately tamper `SECRET_KEY` in dev to verify the rose-tinted warning fires).
- `prompts/score_job` (real-but-naive) called against the seeded Stripe / Anthropic / Linear jobs returns plausible scores logged to `ApiUsage`.
- `Settings.debug = True` toggle in DB makes `/_design/components` accessible; `False` returns 404. Env var `NAAVIK_DEBUG` is no longer consulted.
- Every page from plan 09 renders identically against the DB-backed accessors. Visual diff on Playwright snapshots ≤ 1% pixel delta per screen (font rendering tolerance).
- `tests/test_persistence_swap.py` passes on the side-by-side smoke.

`grep` checks (must be empty):

```bash
rg --no-config 'def [a-z_]+\(.*session.*\).*->.*:' src/db/sample_data.py | rg -v 'async def'
# — every accessor still async after the swap
rg --no-config 'API_KEY|PASSWORD|TOKEN' src/models/   # no secret material in models
rg --no-config 'os.environ\[?["\']NAAVIK_DEBUG' src/ui/routes/   # env-var gate replaced by Settings.debug
rg --no-config 'SECRET_KEY' --type py | rg -v '(vault|tests|cli)' # SECRET_KEY only consulted by vault + CLI + tests
```

## Forbidden patterns

- ❌ Storing API keys / OAuth refresh tokens / IMAP passwords / ATS cookies / Discord webhook URL / Telegram bot token / Netlify webhook URL **anywhere except `~/.naavik/secrets.enc` via the vault**. DB rows store fingerprints + booleans only.
- ❌ Logging secret values in any audit / request / error path.
- ❌ Storing the vault master key in DB.
- ❌ Bypassing bcrypt for "fast tests" — tests use `NAAVIK_BCRYPT_COST=4` env override (production stays cost=12). No plain hashing.
- ❌ Reordering existing Postgres ENUM values (only append).
- ❌ Sync sample-data accessor signatures (must stay async — the swap is body-only).
- ❌ Workday / LinkedIn / Indeed / Generic ATS adapters in this part — Wave 6 ships Greenhouse / Lever / Ashby; the rest is Phase 1.x.
- ❌ Real scoring full pipeline — Phase 3 (plan 12). Wave 3 ships `score_job` skeleton; Wave 6 adds the deterministic visa filter (NOT here).
- ❌ Real document generation, real ATS submission — Wave 6.
- ❌ Real scrapers, cron schedules, email sync, outreach — Phase 2-5.
- ❌ Reverting any of plan 10's Wave-3 open-question decisions without explicit user instruction.

## Hand-back format

When complete:

1. **File list** grouped by directory.
2. **Test results** — `uv run pytest tests/ -v`, `uv run alembic upgrade head` output, `uv run python -m src.db.seed` output.
3. **Security review reports** — checkpoint 1 (auth), checkpoint 2 (vault), checkpoint 4 (post-models). Any HIGH/CRITICAL → fix before hand-back.
4. **Side-by-side smoke** — Playwright diff results between memory and DB modes. Per-screen pixel delta numbers.
5. **Vault key rotation CLI demo** — paste the output of a successful `naavik vault rotate-key` run on a test vault.
6. **Any deviations from the plan** with reason.
7. **Archive step done** — confirm:
   - `docs/plans/10-backend-impl.md` front-matter `Status: APPROVED` → `Status: WAVE 3 EXECUTED · Wave 6 awaiting`.
   - `docs/prompts/10-backend-impl.md` front-matter `Status: ACTIVE` → `Status: WAVE 3 USED · Wave 6 awaiting` (file stays in `docs/prompts/` because Part 2 is still active).
   - `ROADMAP.md` Wave 4 row + per-task checklist marked `[x]` with deliverable note.
8. **Next** — confirm Wave 5 (PART 2 below) is now unblocked. Send the user the green light to paste PART 2 in a fresh session.

# END OF PART 1

---

# PART 2 — Wave 6 (plan 10 § C)

> Paste THIS PART (everything from "PART 2" header above through end of file) as the first message of a **second** fresh Claude Code session, **only after PART 1 ships and security review checkpoints 1 + 2 + 4 pass clean**.

## Goal

Complete the remaining 14 services from BACKEND.md § H.1, ship Typst document generation with bullet selection + AI trim + native page-count validation, fully implement the DRAFT lifecycle (auto-create on `/discover/{id}` gated on `Settings.eager_review_generation`, submit, discard, auto-apply cron), dispatch ATS submissions to Greenhouse / Lever / Ashby (the 3 boards with public APIs), and surface failed auto-apply DRAFTs in the Discover stuck-queue card. Workday / LinkedIn / Indeed / Generic adapters are Phase 1.x — they need credentials + Playwright + manual review queue, deferred to a follow-up sub-prompt.

## Required reading (in order)

1. `AGENTS.md` § Workflow.
2. `docs/plans/10-backend-impl.md` § C end-to-end (the Wave 6 part), § D Phase 2-6 outline, § E tests, § F security review checkpoint 3, § G build order, § H out-of-scope.
3. `docs/design/BACKEND.md` § H services, § I crons (only Wave 6 subset wires here), § K full DRAFT lifecycle + auto-apply + ATS submission per board, § L portfolio sync.
4. `docs/design/DATA_MODEL.md` § A axes, § E state transitions (incl. corrected `applied_at` CHECK), § F KPI derivations, § J custom screener questions.
5. The archived Wave 3 hand-back report.

## Deliverables

| Path | Description |
|---|---|
| `src/services/document_generator.py` | `generate_resume`, `generate_cover_letter`, `answer_screeners`, `pre_generate` (with **DRAFT reuse heuristic** per plan 10 § C.2 — no-op when `docs_state=READY` AND no bullets edited since compile AND JD hash unchanged), **cost-cap enforcement** (skip generation when `daily_llm_cost_cap_usd` exceeded; render lazy CTA) |
| `src/typst/templates/onepage.typ` | NEU-style 1-page resume template — Helvetica, 0.3in margins, compact. Consumes JSON: profile + selected_bullets + trimmed_lines |
| `src/typst/templates/cover_letter.typ` | 4-section letter template + signature block |
| `src/typst/compiler.py` | Async `compile(template_name, data, output_path) -> CompileResult` wrapping `typst compile --emit metadata` (page count from metadata; **NO `pdfinfo`/poppler dep**) |
| `src/typst/validator.py` | `validate_page_count(result, expected)` reading from `CompileResult.page_count` |
| `src/services/application_service.py` | Full DRAFT lifecycle: `get_or_create_draft` (gated on `Settings.eager_review_generation`), `queue_auto_apply` (always eager), `submit_draft` (DRAFT → APPLIED, ATS dispatch, `submission_artifacts.last_failure` write on failure → surfaces in stuck queue), `discard_draft`, `process_auto_apply_queue`, `validate_submittable`, `update_status`, `derive_recruiter_states` (function lands here; cron is Phase 4). **Service-layer ownership of computed state** per plan 10 § C.3: `_roll_up_referral_state`, `compute_outreach_engagement`, `Job.queue_state=APPLIED` flip-on-submit |
| `src/services/scorer.py` | **Wave 6 visa filter** per plan 10 § C.1: deterministic zero-out when `Profile.visa_sponsorship_needed=NEEDED_NOW × Job.visa_restrictions ∈ {us_citizen_only, green_card_required}`. No LLM dep. Auto-apply consumes this; full tag-matching scoring is Phase 3 plan 12 |
| `src/services/extraction.py` | PDF → AI extraction → structured Profile; SSE event emission for Onboarding step 2 |
| `src/services/contact_tracker.py` complete | dedup + state inference; rolls up to `Application.referral_state` |
| `src/services/notifications.py` | Discord webhook + Telegram outbound + in-app toast routing; per-event toggle from `Settings.notifications_enabled` |
| `src/services/portfolio_sync.py` | `/api/portfolio/cv` filtered (no email/phone/EEO/visa/salary); CORS via `Settings.portfolio_cors_allowed_origins`; **portfolio resume PDF regen on Profile-update debounced 60s, cached at `~/.naavik/data/documents/portfolio/resume.pdf`**; Netlify webhook same debounce; `generate_generic_resume(profile)` |
| `src/services/ats/__init__.py` | `dispatch(board) -> ATSAdapter` factory |
| `src/services/ats/base.py` | `ATSAdapter` ABC + `SubmissionResult` shape |
| `src/services/ats/greenhouse.py` | Greenhouse Public Boards API + Embedded API |
| `src/services/ats/lever.py` | Lever public API |
| `src/services/ats/ashby.py` | Ashby public API |
| `src/scheduler/jobs.py` | Wave 6 cron registration: `applications.auto_apply` (5min), `admin.aggregate_costs` (daily 00:30), `admin.cleanup_stale_docs` (weekly Sun 03:00), `admin.daily_db_snapshot` (daily 02:00), `admin.refresh_oauth_tokens` (every 6h skeleton — Phase 4 lights it up) |
| `src/scheduler/__init__.py` | Lifespan-managed APScheduler with `PostgresJobStore` |
| `src/api/applications.py` real handlers | Replace plan 09 + Wave 3 stubs for `/api/v1/applications/*` (submit, discard, manual, bundle, cover-letter/generate SSE, sections, screeners, resume/regen, notes, move) |
| `src/api/discover.py` real handlers | Replace plan 09 stubs for `/api/v1/discover/*` and `/api/v1/jobs/*` |
| `src/api/portfolio.py` | `/api/portfolio/cv` + `/api/portfolio/resume.pdf` + Netlify webhook trigger |
| `src/ui/routes/*.py` | Page handlers updated to consume real services (most already done in Wave 3 accessor swap; this stage adds the doc-generation paths and stuck-queue surface wiring) |
| `tests/test_application_service.py` | DRAFT lifecycle (auto-create eager + lazy gates; submit success + failure with stuck-queue surface; discard; process_auto_apply_queue; validate_submittable; state-transition enforcement; service-layer computed state — referral rollup + outreach engagement + Job.queue_state flip) |
| `tests/test_document_generator.py` | resume + cover letter + screener pipelines; bullet selection respects `selection_override`; page-count validation retry; ScreenerAnswer `auto` + `drafted` + `user` source paths; **DRAFT reuse heuristic no-op when conditions hold**; **cost-cap aborts generation when exceeded** |
| `tests/test_typst.py` | `compiler.compile` produces a valid PDF; `--emit metadata` yields page count without poppler |
| `tests/test_ats_adapters.py` | Greenhouse / Lever / Ashby `submit` against mocked HTTP; `SubmissionResult` shape; failure classification (captcha / rate_limit / auth_required / field_mismatch / unknown); resume-parsing override (Workday-style boards' canonical-Profile-fields posting) |
| `tests/test_notifications.py` | Discord embed format; Telegram outbound; per-event toggle |
| `tests/test_portfolio_sync.py` | `/api/portfolio/cv` filters EEO/visa/salary; CORS allowlist works; Netlify webhook fires on Profile update (60s debounced); generic resume regen + cached path |
| `tests/test_scorer_visa_filter.py` | Deterministic visa filter zero-outs `us_citizen_only` / `green_card_required` jobs when `Profile.visa_sponsorship_needed=NEEDED_NOW`; `score_job` LLM call still runs but score multiplied by 0 |

## Build sequence

**Week 1:**
1. `services/document_generator.py` + Typst templates + compiler + validator + `tests/test_typst.py` + `tests/test_document_generator.py` — 2.5 days. **Includes DRAFT reuse heuristic + cost-cap enforcement.**
2. `services/application_service.py` full DRAFT lifecycle + state transitions + service-layer computed state + `tests/test_application_service.py` — 2 days.

**Week 2:**
3. `services/scorer.py` Wave 6 visa filter + `tests/test_scorer_visa_filter.py` — half day.
4. `services/ats/{__init__, base, greenhouse, lever, ashby}.py` + `tests/test_ats_adapters.py` — 2 days.
5. `services/extraction.py` (PDF → AI → Profile + SSE) — 1 day.
6. `services/contact_tracker.py` complete — half day.
7. `services/notifications.py` + `tests/test_notifications.py` — 1 day.

**Week 3:**
8. `services/portfolio_sync.py` + `tests/test_portfolio_sync.py` — 1 day.
9. `scheduler/jobs.py` Wave 6 cron registration + `scheduler/__init__.py` lifespan integration — 1 day.
10. Real `api/*` handlers replacing remaining stubs — 1 day.
11. UI handler swap for stuck-queue card on Discover (data flows from `Application.submission_artifacts.last_failure` filter → `up_next_card state="stuck"`) — half day.
12. **Security review checkpoint 3** (per plan 10 § F): doc-gen Typst-template injection, ATS POST input sanitization, portfolio public API info leak, vault audit trail completeness — 1 day to remediate any findings.
13. End-to-end smoke: real auto-apply queue, real Greenhouse submission against staging board (or mocked), real Discord notification, real portfolio CV API fetch from a curl. Document any prod-vs-staging deltas.

Total: ~3 weeks.

## Quality bar

```bash
uv run alembic upgrade head            # still clean (no Wave 6 migrations expected — Wave 6 doesn't add models)
uv run ruff check .
uv run pytest tests/                   # all green incl. new Wave 6 tests
uv run fastapi dev src/main.py         # boots; APScheduler logs the registered crons
```

End-to-end:

- **DRAFT lifecycle.** Visit `/discover/{job_id}` for a fresh job → DRAFT row created (eager) with bundle pre-generated (or lazy CTA shown if `Settings.eager_review_generation=False`). Click "Submit application" → ATS dispatched, status flips to APPLIED, `Job.queue_state=APPLIED`, AppEvent emitted, notification fired.
- **DRAFT reuse heuristic.** Revisit the same `/discover/{id}` 5 minutes later → no new LLM calls (verify zero new `ApiUsage` rows).
- **Cost cap.** Set `Settings.daily_llm_cost_cap_usd=0.05`. Visit a fresh `/discover/{id}` after the cap is exceeded → lazy CTA + banner ("Daily cost cap reached"), no `ApiUsage` row.
- **Stuck queue.** Force an ATS adapter to return `auth_required` (mock). Auto-apply queue processes; DRAFT stays DRAFT with `submission_artifacts.last_failure.kind="auth_required"`. Discover right rail "Stuck in queue · 1" card appears with amber border + "auth needed" chip.
- **Visa filter.** Score a fresh `us_citizen_only` job with `Profile.visa_sponsorship_needed=NEEDED_NOW` — score forced to 0.0; not surfaced in auto-apply queue even at high naive-score.
- **Portfolio.** Edit Profile → wait 60s → fresh `~/.naavik/data/documents/portfolio/resume.pdf` regenerated; Netlify webhook fired; `curl http://localhost:8000/api/portfolio/cv` returns Profile JSON with EEO/visa/salary/contact filtered out; CORS allows the configured origin.
- **Auto-apply cron.** Right-swipe a Greenhouse-board job; wait ≤5min; `applications.auto_apply` cron fires; DRAFT submits real to Greenhouse (or mocked); status flips to APPLIED.

`grep` checks (must be empty):

```bash
rg --no-config 'pdfinfo|poppler' src/typst/    # no poppler dep
rg --no-config '/generate/(cover-letter|resume)' src/   # no forbidden routes
rg --no-config 'NAAVIK_PERSISTENCE' src/      # env var removed in Wave 4 cleanup
```

## Forbidden patterns

- ❌ Workday / LinkedIn / Indeed / Generic ATS adapters in this part — they need credentials + Playwright + manual review queue, all Phase 1.x in a follow-up sub-prompt.
- ❌ Real LinkedIn DMs / email integration / outreach generation — Phase 4-5.
- ❌ Real scrapers, scoring tag-matching pipeline, observability dashboards — Phase 2-3-6.
- ❌ Re-introducing `pdfinfo` / poppler — Typst native page-count via `--emit metadata` is the only path.
- ❌ Eager DRAFT generation hardcoded — must check `Settings.eager_review_generation`.
- ❌ Bypassing the DRAFT reuse heuristic on revisits.
- ❌ Bypassing the cost-cap check before LLM calls.
- ❌ Returning `submission_artifacts.last_failure` from the stuck queue endpoint without filtering for the current user (vault boundary applies — never leak another user's failures).
- ❌ Real prompts/score_job tag-matching gap-analysis logic — Phase 3 (plan 12).
- ❌ Multiple Typst templates beyond `onepage.typ` + `cover_letter.typ` — Phase 6.
- ❌ Reverting any of plan 10's Wave-6 open-question decisions without explicit user instruction.

## Hand-back format

When complete:

1. **File list** grouped by directory.
2. **Test results** — `uv run pytest tests/ -v` output (must be all green).
3. **Security review checkpoint 3** report.
4. **End-to-end smoke** — DRAFT lifecycle, reuse heuristic, cost cap, stuck queue, visa filter, portfolio sync, auto-apply cron.
5. **Cost telemetry** — paste a 7-day window of aggregated `ApiUsage` numbers (model breakdown, total cost, avg per generation).
6. **Greenhouse / Lever / Ashby submission demo** — successful real or mocked submission against each board.
7. **Any deviations from the plan** with reason.
8. **Archive step done** — confirm:
   - `mv docs/plans/10-backend-impl.md docs/plans/archive/10-backend-impl.md` (Status: WAVE 3 EXECUTED · Wave 6 awaiting → EXECUTED).
   - `mv docs/prompts/10-backend-impl.md docs/prompts/archive/10-backend-impl.md` (Status: WAVE 3 USED · Wave 6 awaiting → USED).
   - `ROADMAP.md` Wave 5 row + per-task checklist marked `[x]` with deliverable note. Phase 1 status header → `✅ Complete (YYYY-MM-DD)`.
9. **Next** — Phase 1 is shipped. Read `docs/plans/POST_PHASE_1.md` for the post-MVP authoring sequence (plans 11-15+).

If you hit a blocker (a Greenhouse / Lever / Ashby API surface that BACKEND.md mis-described, an ATS field-mapping gap that requires schema work, a Typst template that doesn't fit the 1-page constraint), STOP and post a question. Phase 1 deliverable line is the contract — anything that endangers it gets escalated, not papered over.

Phase 1 ships when you complete this part.

# END OF PART 2
