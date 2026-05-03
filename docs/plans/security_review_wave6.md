# Security review — Wave 6 checkpoint 3

> **Authored:** 2026-05-03 (during Wave 6 ship of plan 10).
> **Reviewer:** Wave 6 security checkpoint 3 (per `docs/plans/10-backend-impl.md` § F, checkpoint 3 = "before Wave 6 ships").
> **Status:** PASS — 0 CRITICAL, 0 HIGH. 1 MEDIUM, 3 LOW, 1 INFO documented for follow-up; none block Wave 6 per § F gating rule.
> **Scope:** four attack surfaces called out in the kickoff prompt — (1) Typst-template injection via `--input data=<json>`, (2) ATS adapter input sanitization, (3) `/api/portfolio/cv` info leak, (4) vault audit-trail completeness for Wave 6 callers.

Files audited:

- `src/services/document_generator.py`
- `src/typst/compiler.py`, `src/typst/templates/onepage.typ`, `src/typst/templates/cover_letter.typ`, `src/typst/validator.py`
- `src/services/application_service.py`
- `src/services/ats/{base,greenhouse,lever,ashby}.py`
- `src/services/portfolio_sync.py`, `src/api/portfolio.py`
- `src/services/notifications.py`
- `src/services/vault.py` (cross-checked for Wave 6 callers)

---

## 1. Typst-template injection (data → template)

**Concern:** `document_generator` builds an arbitrary Python dict (with embedded JD text + AI-generated trims + AI-drafted cover-letter paragraphs) and passes it to `typst compile --input data=<json>`. If user-controlled (or LLM-controlled) text were ever interpolated into the template at the *source* level (rather than read at runtime through `json.decode`), `#`-prefixed Typst directives could execute.

**What was checked:**

- `src/typst/compiler.py:84` — payload is serialized with `json.dumps(data, default=str)` and passed only as the value of the `--input data=...` CLI flag. The template is read from disk and never mutated.
- `src/typst/templates/onepage.typ:33` and `src/typst/templates/cover_letter.typ:14` — both call `json.decode(sys.inputs.data)` and bind the result to `#let data = ...`. Every downstream reference is field access (`data.profile.full_name`, `data.experiences[i].bullets[j]`, etc.) which Typst evaluates as *data*, not as code. There is no `eval(...)` / `parse(...)` / metaprogramming bridge that would re-interpret the value as Typst source.
- `--root` is pinned to the templates directory (`str(src.parent)`); no path injection vector via `data` keys.
- subprocess spawn uses `asyncio.create_subprocess_exec(*args, ...)` with an argv list — no shell, no `shell=True`, no f-string interpolation of `data_json` into a command string.
- timeout (`30s`) and stderr capture are bounded; LLM-generated strings cannot stall the worker indefinitely.

**Verdict:** **PASS** (severity: would have been HIGH if `data_json` were interpolated into a shell, or if templates concatenated user text into a `#` directive). No injection path exists. Field-access semantics in Typst keep arbitrary string contents inert.

**Notes (LOW, not a finding):**

- The header-footer block in `onepage.typ` (`#if data.profile.linkedin_handle != none [...]`) interpolates string fields verbatim. They render as text, *not* code, but a malicious string could include Typst-meaningful punctuation (`#`, `[`, `]`, `$`). Worst case is broken layout, not execution. Recommend adding a one-line comment near `bullet_line` documenting "all values from `data` render as text — never use `eval()`-style constructs against them."
- `--input` payload size is unbounded. A 50 MB JD could cause `argv` to exceed `ARG_MAX`. Mitigation already in place: `_render_select_prompt` and `_render_cover_letter_prompt` truncate to 1500 chars before sending to the LLM, and trimmed bullets are 120 chars. Worst-case payload is well under 1 MB. INFO only.

---

## 2. ATS adapter input sanitization

**Concern:** `application_service.submit_draft` builds `ApplicationBundle` and calls into Greenhouse / Lever / Ashby adapters. Each posts a multipart form with user-edited screener answers, AI-generated cover letter PDFs, resume PDFs, and identity strings. Risks include (a) HTTP header injection via answer text, (b) file-path traversal when reading the bundle's PDF off disk, (c) URL injection through `Application.external_url`, (d) leaking secrets into the multipart form.

**What was checked:**

- **No header injection.** All adapters use `httpx.AsyncClient.post(url, data=..., files=...)`. `httpx` URL-encodes form fields and base64-encodes file contents — newlines in answers cannot break out of a header. No adapter sets `headers=` from user input.
- **Path traversal.** All three adapters do `Path(bundle.resume.path).read_bytes()` / `.exists()`. `bundle.resume.path` originates from `GeneratedDocument.path`, which is set in `document_generator.generate_resume` to `str(out_pdf)` where `out_pdf = _app_documents_dir(application_id) / "resume.pdf"` — fully derived from the integer `Application.id`, never user-controlled. Same for cover letter. **Verdict on traversal: safe today.** See LOW finding below for hardening.
- **URL injection.** `_parse_url` in each adapter pins to a hard-coded regex anchored at the board's domain (`boards-api.greenhouse.io`, `jobs.lever.co`, `jobs.ashbyhq.com`) and only extracts `org / posting_id` segments. Even if `Application.external_url` were attacker-controlled, the adapter only calls a URL it constructs itself: `f"{_BOARDS_API}/{org}/jobs/{job_id}"`. Constants (`_BOARDS_API`, `_API`) are module-level literals, not configurable. **Safe.**
- **Multipart file metadata** — filename is hard-coded `"resume.pdf"` / `"cover-letter.pdf"`; user cannot influence the multipart `filename=` param.
- **Screener answer injection.** Lever puts `customQuestions[idx][text] = q.question_text` into the form. `q.question_text` was scraped from the board itself in Phase 2; for Wave 6 it round-trips back to the same board so no privilege boundary is crossed. **Safe.**

**Findings:**

- **LOW · MED-1 (MEDIUM): identity-fields are mis-mapped from `application.role`.** `greenhouse.py:94` derives `first_name / last_name` from `application.role.partition(" ")` — almost certainly a copy-paste bug from prototyping (should be `application.user.full_name` or `Profile.full_name`). Result: every Greenhouse submission uploads the *job role* as the candidate name. Not a security issue per se, but it blocks an end-to-end smoke and an attacker controlling `Job.role` text could impersonate a different name string. The existing test suite is mocked at the HTTP layer so this never triggered. **Severity: MEDIUM (functional correctness with an authentication-adjacent surface).** Marked here so checkpoint 3 leaves a paper trail; do not block the wave but file as Phase 1.x ATS-hardening backlog.
- **LOW · LOW-1: Path defense-in-depth.** `Path(bundle.resume.path).read_bytes()` will follow symlinks and resolves any path. If a future code path ever lets the user influence `GeneratedDocument.path` (e.g., a "re-link existing PDF" feature), traversal becomes possible. Recommend asserting `Path(bundle.resume.path).resolve().is_relative_to(_documents_dir().resolve())` before reading. Not a current vuln — mitigation is preventive.
- **LOW · LOW-2: `application_id` board-side echo not sanitized when written to `submission_artifacts`.** `_record_success` stores `result.board_application_id` which originates from `response.json().get("application_id")`. A malicious board response could embed control chars; the value lands in JSONB which is safe for storage, and the UI escapes via Jinja. Documented for completeness only.

**Verdict:** **PASS** for the sanitization concern. MED-1 is a correctness bug that should be tracked as backlog (it's an obvious break of every submission flow), not a security gating issue.

---

## 3. `/api/portfolio/cv` public info leak

**Concern:** `/api/portfolio/cv` is unauthenticated and CORS-allowlisted via `Settings.portfolio_cors_allowed_origins`. Profile rows carry every sensitive field — email, phone, salary expectation, EEO (race / gender / veteran / disability), visa status. The endpoint must drop all of these AND not leak via error paths or unknown fields.

**What was checked:**

- `src/services/portfolio_sync.py:62` `public_cv_payload` uses an **explicit allowlist** of 14 keys (`id`, `user_id`, `full_name`, `headline`, `current_company`, `location`, `portfolio_url`, `github_handle`, `linkedin_handle`, `summary_full`, `summary_short`, `open_to_opportunities`, `created_at`, `updated_at`). Every other Profile column — including `email`, `phone`, `salary_expectation_usd`, `veteran_status`, `disability_status`, `race_ethnicity`, `gender_identity`, `work_authorization`, `visa_sponsorship_needed`, `willing_to_relocate`, `notice_period_days`, `earliest_start`, `cover_letter_base` — is dropped by virtue of not being in the allowlist. Allowlist semantics survive future Profile schema additions (new sensitive columns will not auto-leak).
- `_FILTERED_PROFILE_FIELDS` in the same module enumerates the *forbidden* set and is checked by `assert_no_pii(payload)` (called inline at `src/api/portfolio.py:101` after every CV response). This double-gate (allowlist build + denylist assertion) is exactly the belt-and-braces pattern. Test at `tests/services/test_portfolio_sync_*.py` (per Wave 6 hand-off) exercises both.
- Experience / Education / Project / Skill children are serialized through dedicated helpers that only emit company/title/location/dates/text fields. No `notes`, no `internal_metadata`, no per-row PII columns exist on those models (verified in `src/models/profile.py`).
- `GET /api/portfolio/cv` raises `HTTPException(404)` if profile missing — the error body is `{"detail": "profile not found"}`, no leakage.
- `GET /api/portfolio/resume.pdf` serves the generic-resume PDF from a path constructed entirely from `app_settings.data_dir` + literals (`"data/documents/portfolio/resume.pdf"`). Not user-controlled. The PDF itself is generated by `document_generator.generate_generic_resume`, which uses the same allowlist via `_build_resume_data`, so EEO/visa/salary do not bleed into the PDF either.
- CORS: `_cors_response` only emits `Access-Control-Allow-Origin: <origin>` if `is_cors_allowed(settings, origin)` returns True — exact-match against the configured list (`portfolio_cors_allowed_origins`). No wildcards, no scheme/host fuzz. `Vary: Origin` set so caches don't bleed responses across origins. `OPTIONS` handler emits the same headers; preflight is gated identically.

**Findings:**

- **LOW · LOW-3: `summary_full` is in the public allowlist, `summary_short` too.** If the user ever pastes secret-flavored text into `summary_full` (e.g., "managed an FAANG offer at $X comp, see attached"), it leaks. This is documented behavior — the portfolio site at `crypticsoul.dev` consumes `summary_full` for the "About" block — but worth documenting so the user knows the field is public-by-design. Not a code bug.
- **INFO: rate limiting.** `/api/portfolio/cv` has no rate limit. A malicious origin not in the allowlist still gets the JSON body (CORS only restricts browser access; the *server* response is not gated). Phase 2 adds CDN-level caching + origin filtering at Cloudflare; for Wave 6 this is acceptable because the data shipped is already public-by-design and bandwidth is bounded by the small payload size. INFO only.

**Verdict:** **PASS.** Allowlist + assert_no_pii is robust. Future Profile columns inherit the safe-by-default posture.

---

## 4. Vault audit-trail completeness (Wave 6 callers)

**Concern:** Per Wave 3 checkpoint 2, every secret read/write/delete must produce an audit-log line at `~/.naavik/logs/vault-audit.log`. Wave 6 introduced new callers (notifications, portfolio_sync). Verify each routes through `services/vault.{get,set,delete,list_keys}` and never logs secret values.

**What was checked:**

- `services/vault.py:230` — `get` calls `_audit("get", scope, key, caller)` *before* returning the value; the audit line carries `{ts, op, scope, key, caller}` only.
- `services/vault.py:258` — `set` writes the secret through `_with_exclusive_lock(op)` and then calls `_audit("set", ...)` inside the locked region. Value never reaches the audit logger.
- `services/vault.py:281` — `delete` likewise.
- `services/vault.py:307` — `list_keys` audits with `key="*"`.
- `_audit()` itself (`vault.py:204`) builds the JSON line from {ts, op, scope, key, caller} only. There is no path for the secret value to reach the logger; no `**kwargs` interpolation, no exception payload that would carry the value. If the audit log is unwritable, vault op continues (`OSError` swallowed with a warning to the standard logger — no secret in that warning either).

Wave 6 callers, traced:

| Caller | Scope | Op(s) | Through `vault_svc.*`? | Audit line emitted? |
|---|---|---|---|---|
| `services/notifications.py:84 _discord_url` | `notifications` | `get` | yes (`vault_svc.get`) | yes (caller="notifications") |
| `services/notifications.py:202 _telegram_token` | `notifications` | `get` | yes | yes |
| `services/notifications.py:206 _telegram_chat_id` | `notifications` | `get` | yes | yes |
| `services/portfolio_sync.py:213 trigger_netlify_rebuild` | `misc` | `get` | yes | yes (caller="portfolio_sync") |
| `services/settings_service.py:67/143/151/155/163` | `llm` / `notifications` | `set` / `delete` | yes | yes |
| `services/ats_credentials.py:88/104/108` | `ats` | `get` / `set` / `delete` | yes | yes |
| `llm/__init__.py:47/53` | `llm` | `get` | yes | yes |

`document_generator.py` and `application_service.py` were checked: neither imports `vault` directly. They obtain `Settings` from the route handler and read fingerprints / booleans only. ATS adapter base classes also do not touch the vault (per-board credentials live in `ats_credentials.py`, which always routes through `vault_svc`).

No `print(secret)` / `log.info(...secret...)` patterns found. `notifications._discord_url()` returns the URL; the URL is then passed to `client.post(url, json=body)`. Httpx will not log the URL by default. The `log.warning(...)` calls in `notifications.py` log status code + first 200 chars of response body — none of those carry the bot token (Discord/Telegram do not echo the token in their response bodies for these endpoints).

**Verdict:** **PASS.** All Wave 6 vault callers route through `vault_svc.{get,set,delete}`, every op produces an audit line with `caller=` set to the originating module, no secret-value paths into either the audit log or the application logger.

---

## Summary table

| # | Surface | Severity | Verdict | Action |
|---|---|---|---|---|
| 1 | Typst-template injection | INFO | PASS | None blocking; INFO note about argv size + comment hygiene |
| 2 | ATS adapter sanitization | MEDIUM (MED-1: name-field bug), LOW (LOW-1, LOW-2) | PASS | File MED-1 + LOW-1 as Phase 1.x ATS-hardening backlog |
| 3 | `/api/portfolio/cv` info leak | LOW (LOW-3), INFO | PASS | Document `summary_full` is public-by-design |
| 4 | Vault audit completeness | — | PASS | None |

**Gating decision:** No HIGH or CRITICAL findings. Wave 6 may ship per `docs/plans/10-backend-impl.md` § F. The MEDIUM-severity Greenhouse name-field bug should be filed as a tracked backlog item (functional, blocks end-to-end smoke against a real Greenhouse posting, but does not break security boundaries).

## Recommended follow-ups (non-blocking)

1. **MED-1 (Greenhouse adapter):** replace `application.role.partition(" ")`-derived `first_name`/`last_name` with `Profile.full_name` partitioning (or, better, surface `first_name` + `last_name` as separate Profile columns since Greenhouse asks for them explicitly per BACKEND.md § K.5). Track in ROADMAP under Phase 1.x ATS hardening.
2. **LOW-1 (Path defense-in-depth):** add `path.resolve().is_relative_to(_documents_dir().resolve())` guard before `read_bytes()` in each adapter's resume/cover-letter open. Prevents future regressions if `GeneratedDocument.path` ever takes user input.
3. **LOW-2 / INFO-rate-limit:** when Phase 2 wires CDN, ensure `/api/portfolio/cv` lands behind origin-filter + 60-rpm rate limit at the CDN edge.
4. **Wave 7 vault checkpoint:** once email-thread sync ships (`scope=email`) confirm audit lines fire on the new callers; the pattern is identical to Wave 6.
