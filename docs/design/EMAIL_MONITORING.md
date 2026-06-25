# Email Monitoring — canonical design

> **Status:** canonical (graduated from `docs/plans/90-0.5.0-email-monitoring.md`
> on owner approval, 2026-06-25).
> **Phase:** 0.5.0 (Email Monitoring & Outreach) — this doc covers the
> foundation (`0.5.0.01-06`: connection, storage, classification, status
> mapping, notifications, draft-response seam). Outreach (`0.5.0.09-15`,
> plan 91) and interview scheduling/prep (`0.5.0.07-08`, plan 92) build on
> this surface.
> **Owner-locked decisions (2026-06-25):** Q2 = Fernet column-level encryption
> (A.2.a). Q1/Q3–Q8 = the scaffold's recommended defaults (IMAP-only;
> EmailMessage metadata + snippet; LLM-graceful-degrade; human-confirm-all
> status flips; 10-min polling cadence; JSON draft-response seam; this doc as
> the graduation target).

Naavik watches a user's inbox over IMAP, persists application-related email
per Application, classifies each message
(`INTERVIEW_REQUEST` / `REJECTION` / `OFFER` / `ASSESSMENT` / `FOLLOW_UP` /
`OTHER`), surfaces high-priority signals on Discord + Telegram + the in-app
toast queue, and proposes (never auto-applies) Application status changes that
the owner confirms.

---

## A. Surface map

**REST routes (`src/api/integrations_email.py`):**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/integrations/email` | List the caller's `EmailAccount` rows (`EmailAccountRead` — password stripped). |
| POST | `/api/v1/integrations/email/imap` | Connect an IMAP inbox: validate creds, encrypt + persist. CSRF-guarded. |
| POST | `/api/v1/integrations/email/{id}/test` | Re-verify a stored account is still connectable. |
| DELETE | `/api/v1/integrations/email/{id}` | Soft-delete (`deleted_at`). |
| POST | `/api/v1/integrations/email/{id}/sync-now` | One-shot manual sync. |

**Email read + action routes (`src/ui/routes/email.py`):**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/email/threads` | List threads (read-side `email_service`). |
| GET | `/api/v1/email/threads/{id}` | Thread detail + message rollup. |
| POST | `/api/v1/email/threads/{id}/draft-reply` | LLM draft a reply (JSON; no auto-send). Graceful 503 when no LLM. |
| POST | `/api/v1/applications/{app_id}/email-suggestion/{message_id}/apply` | Human-confirm a suggested status flip. |
| POST | `/api/v1/applications/{app_id}/email-suggestion/{message_id}/dismiss` | Dismiss a suggestion. |

**UI page (`src/ui/routes/integrations.py`):** `GET /integrations/email` — lists
connected accounts (`_email_account_card.html`) + the Connect IMAP form, with a
trust-posture banner (§ D).

**Crons (`src/scheduler/jobs.py`):** `tracking.sync_emails` +
`tracking.classify_emails` (§ H).

**Every state-changing route is CSRF-guarded (`Depends(require_csrf)`) and
IDOR-guarded via `_effective_user_id`** — no hardcoded `user_id=1`. Mirrors the
0.7.0.48 fix-cycle pattern.

---

## B. Models

- **`EmailAccount`** (`src/models/email_account.py`) — per-user inbox
  connection. `(user_id, provider, account_email)` unique. Columns:
  `provider` (`EmailAccountProvider`), `account_email`, `imap_host`,
  `imap_port` (default 993), `imap_username`, `imap_password` (Fernet
  ciphertext token — § D), `imap_use_tls`, `status` (`EmailAccountStatus`),
  `last_sync_at`, `last_synced_uid`, `connection_failure_count`,
  `last_error_message`, `created_at`, `updated_at`, `deleted_at`.
- **`EmailMessage`** (`src/models/email_message.py`) — one row per fetched
  message; **metadata + a ≤240-char `snippet` only**, no full body (§ I).
  Carries `(user_id, thread_id, account_id?, application_id?, provider,
  message_id_external, sender_email, sender_name?, subject, snippet,
  received_at)` plus classification fields (`classification`,
  `auto_classified`, `classification_model`, `classification_at`,
  `unclassified_reason`, `urgency`) and suggestion fields (`suggested_status`,
  `suggested_at`, `suggestion_dismissed_at`, `suggestion_applied_at`).
  Indices on `(thread_id, received_at)` and `(user_id, classification,
  received_at)`; unique `(thread_id, message_id_external)`.
- **`EmailThread`** (`src/models/email.py`, pre-existing) — one row per thread;
  upserted by `email_sync` keyed on `References` / `In-Reply-To` / `Message-ID`.
  Its inline `messages` JSONB list stays as read-only legacy; `EmailMessage`
  rows are authoritative going forward (collapse tracked as `0.5.0.05b`).

**Enums (`src/models/enums.py`):** `EmailAccountProvider` (`IMAP`/`GMAIL`/
`OUTLOOK` — GMAIL/OUTLOOK reserved for follow-ups), `EmailAccountStatus`
(`OK`/`AUTH_REQUIRED`/`RATE_LIMITED`/`DISABLED`), `UnclassifiedReason`
(`NO_PROVIDER_CONFIGURED`/`LLM_FAILED`/`RATE_LIMITED`/`COST_CAP_EXHAUSTED`),
and `AppEventKind.EMAIL_STATUS_SUGGESTED`. Classification reuses the existing
`EmailClassification` StrEnum (no new members). Migration:
`migrations/versions/0024_email_account_message.py`.

---

## C. Connection layer

**IMAP-only foundation (Q1 = A.1.a).** Provider-agnostic — works for Gmail /
Outlook / Yahoo / Fastmail / iCloud / self-hosted Postfix. Onboarding is "paste
a provider app-password into Settings · Integrations → Email", the same
ergonomic shape as the Discord webhook / Telegram bot.

`src/services/email_sync.py` uses the Python **stdlib `imaplib.IMAP4_SSL`
wrapped in `asyncio.to_thread`** (engineer deviation D2 from the plan's
`aioimaplib` recommendation — no new dependency for the scaffold; stdlib
semantics match; an `aioimaplib` swap is a follow-up only if benchmarks call
for it). The IMAP client is injected via a `client_factory` seam so tests use a
fake client with canned RFC 5322 messages — no live network in CI.

- `sync_account(session, account, *, client_factory)` — fetch + persist new
  messages for one account; `sync_all_accounts(session)` — iterate live
  accounts.
- Fetch window: `UID SEARCH` since `last_synced_uid` (first sync backfills the
  last 50), capped at 500 messages/run to bound downstream LLM cost.
- Per message: parse RFC 5322 headers → write `EmailMessage`
  (classification left `None`; the classifier cron promotes it) → upsert
  `EmailThread`.
- Provider extensibility seam: `EmailAccountProvider.GMAIL`/`OUTLOOK` are
  reserved enum values; Gmail API + push webhooks are `0.5.0.01.1` (sub-minute
  classification) and IMAP IDLE-mode is `0.5.0.01.2` (Gmail connection-cap
  dodge).

---

## D. Credentials — Fernet column-level encryption (OWNER-APPROVED 2026-06-25)

**Q2 = A.2.a.** The IMAP app-password is stored as a **Fernet ciphertext token**
in the `email_account.imap_password` column, behind the
`src/services/email_credentials.py` seam:

- `store_imap_password(account, plaintext)` encrypts → stores the urlsafe-base64
  token. `load_imap_password(account)` decrypts.
- Key derivation: `Fernet(urlsafe_b64encode(sha256(SECRET_KEY).digest()))` —
  the key is `SHA-256(SECRET_KEY)`. `cryptography` is already a transitive dep
  (JWT signing); no new dependency.
- The column type is unchanged (`str`; the token is ASCII), so **no migration**
  is needed for the encryption.
- **Fail-closed:** `load_imap_password` returns `None` (never the raw column
  value) when the token can't be decrypted — empty column, or `SECRET_KEY`
  rotated since the password was saved. `email_sync` flips the account to
  `AUTH_REQUIRED` on `None`; the `test` route returns a clear "re-paste"
  error. The decrypted plaintext is never logged, never on a Read schema,
  never in a response body (`tests/test_no_email_password_leak.py` +
  `EmailAccountRead` enforce this).

**Trust posture vs vault.** The trust model is identical to JWT signing: an
attacker with `SECRET_KEY` can decrypt both the token and forge sessions; a
`pg_dump` alone (no `SECRET_KEY`) yields only ciphertext. This is **column-level
encryption, NOT a vault revival** — there is no `~/.naavik/secrets.enc`, no
`key.bin`, no audit-log file, no Argon2id/PBKDF2 CLI ceremony, no new "vault
scope" string. It is therefore compliant with `AGENTS.md § Key Conventions §
CLI` (vault sunset, plan 26). The deleted vault derived its master key from the
same `SECRET_KEY`, so it added file + audit-log + CLI attack surface without
raising the trust floor; a single DB-column cipher keyed off `SECRET_KEY` keeps
the floor and drops the ceremony (the `pgcrypto` equivalent, done app-side for
sqlite-parity tests).

**SECRET_KEY rotation:** rotating `SECRET_KEY` invalidates every stored token.
Accounts flip to `AUTH_REQUIRED`; the operator re-pastes the same app-password
to re-encrypt under the new key. No mail data is lost. (RUNBOOK § 2.14.)

---

## E. Classification — LLM-only with graceful degrade

**Q4 = A.4.a.** `src/services/email_classifier.py` classifies unprocessed
`EmailMessage` rows via the existing `src/llm/prompts/classify_email.py` prompt,
wrapped in `services/llm_tracker.tracked_call(prompt_name="classify_email")`
(mandatory — `ApiUsage` rows persist for the cost cap).

- **No LLM configured** → `get_provider` raises `LLMProviderError(kind=
  "auth_required")`; the classifier persists `classification=OTHER` +
  `unclassified_reason=NO_PROVIDER_CONFIGURED` + `auto_classified=False` and
  moves on. When the operator later sets `ANTHROPIC_API_KEY` (or another
  provider) and restarts, the next `tracking.classify_emails` tick re-processes
  those rows. Mirrors the scorer (`BACKEND.md § H.4`) and the pdfplumber-only
  resume-extract degrade pattern the owner already accepted (0.7.0.48).
- **LLM call fails** → `unclassified_reason=LLM_FAILED`; retried next tick.
- **Cost-cap integration:** the classifier consults the cost-cap slot before
  each `tracked_call`; on exhaustion it persists
  `unclassified_reason=COST_CAP_EXHAUSTED` and retries next tick.
- On success: persists `classification` + `urgency` + model name, then runs the
  post-classify dispatch (emit `AppEvent(EMAIL_RECEIVED)`, propose a status
  change per § F, fire priority notifications per § G).

The classifier reads only the stored `snippet` (≤240 chars) — the prompt
truncates body anyway, and full bodies are not persisted (§ I).

---

## F. Status mapping — human-confirm-all

**Q5 = A.5.b.** A misclassified `REJECTION` auto-closing an Application is
destructive; the foundation therefore **never auto-flips** status. Instead:

1. `src/services/email_status_mapper.py:suggest_status(application,
   classification, urgency)` is a pure function returning a `SuggestedTransition
   | None` — never mutates anything.
2. The classifier persists `EmailMessage.suggested_status` and emits
   `AppEvent(kind=EMAIL_STATUS_SUGGESTED, payload=EmailStatusSuggestedPayload)`.
3. The UI shows a "Suggested action" banner
   (`_email_suggestion_banner.html`); the owner clicks Apply or Dismiss.
4. Apply → `application_service.apply_email_suggestion(...)` → invokes
   `update_status(..., trigger=StatusChangeTrigger.AUTO_FROM_EMAIL)` and stamps
   `suggestion_applied_at`. Dismiss → stamps `suggestion_dismissed_at`.

**Mapping table:**

| `EmailClassification` | Suggested `ApplicationStatus` | Closed reason | Skip when |
|---|---|---|---|
| INTERVIEW_REQUEST | RECRUITER_SCREEN (→ ONSITE_LOOP if already at RECRUITER_SCREEN) | — | already at/beyond suggested |
| ASSESSMENT | RECRUITER_SCREEN (informational) | — | `urgency == "low"` |
| OFFER | OFFER | — | already OFFER or CLOSED |
| REJECTION | CLOSED | `rejected_by_them` | already CLOSED or OFFER |
| FOLLOW_UP | (no suggestion) | — | always |
| OTHER | (no suggestion) | — | always |

`update_status` gained an optional `trigger: StatusChangeTrigger =
StatusChangeTrigger.MANUAL` kwarg (default preserves all existing behavior). An
auto-flip Settings toggle (positive classifications only; REJECTION/ASSESSMENT
stay gated) is the `0.5.0.03a` follow-up.

The banner only renders when `suggested_status != current_status AND
suggestion_applied_at IS NULL AND suggestion_dismissed_at IS NULL`.

---

## G. Notifications

`src/services/notifications.py:notify_priority_email(*, settings, application,
classification, ...)` dispatches by classification onto the **existing** Discord
+ Telegram + toast surfaces — no new embed/template code:

- INTERVIEW_REQUEST + ASSESSMENT → `EVENT_INTERVIEW_SCHEDULED`
- OFFER → `EVENT_OFFER_RECEIVED`
- REJECTION → `EVENT_REJECTION` (gated by `Settings.notifications_enabled`)

Every classified message also pushes a low-urgency in-app toast with a "View
thread" action.

---

## H. Cron registration

Two APScheduler jobs (`src/scheduler/jobs.py`), each
`IntervalTrigger(minutes=10)` + `max_instances=1` + `coalesce=True`, mirroring
`embed_pending_jobs`:

- **`tracking.sync_emails`** — `email_sync.sync_all_accounts`.
- **`tracking.classify_emails`** — `email_classifier.classify_unprocessed`,
  offset +2min so the DB has flushed the sync writes.

**Q6 = A.6.a + Sync-now.** 10-min cadence; a manual "Sync now" button on each
account card (rate-limited 1/min/user). The `EMAIL_SYNC_INTERVAL_MINUTES`
`.env` slot is a documented-but-not-yet-wired hook (RUNBOOK § 2.15); the
interval is currently hardcoded.

---

## I. Privacy posture

**Q3 = A.3.c.** `EmailMessage` persists **metadata + a ≤240-char snippet only**
— never the full body. A `pg_dump` of a Naavik DB already carries Profile +
Settings + Application notes; adding full inbox bodies would multiply the leak
blast-radius for negligible classification gain. IMAP remains the source of
truth for the body, so re-classification on a model upgrade refetches by
`message_id_external`. Full-body archival is an opt-in
`Settings.email_store_full_bodies` follow-up (`0.5.0.05a`, default off). The
Connect form discloses the inbox-read scope + the at-rest-encryption posture
before the operator pastes.

---

## J. Account-ban risk

Email is far less hostile than LinkedIn-DM scraping — IMAP is a documented
protocol with no anti-scraping defense. Mitigations the foundation respects:

- One IMAP connection per account (no parallel connections to the same inbox).
- Sync window scoped to "since `last_synced_uid`" — never a full-inbox refetch.
- 3rd consecutive auth failure → `EmailAccountStatus.AUTH_REQUIRED`; cron skips;
  UI surfaces "Reconnect IMAP".
- **Gmail's 15-IMAP-connections/IP/day cap** is below our 10-min cadence
  (≈144/day). Documented workaround: lengthen the interval (RUNBOOK § 2.15);
  permanent fix is IMAP IDLE-mode (`0.5.0.01.2`).

---

## K. Follow-ups

- `0.5.0.07-08` — interview scheduling (Calendly/webhook) + prep generator →
  **plan 92** (reads `AppEventKind.EMAIL_STATUS_SUGGESTED` payloads).
- `0.5.0.09-15` — LinkedIn outreach (contacts, templates, AI drafts,
  automation, history, warm-intro) → **plan 91** (reads `EmailMessage` signals
  for recipient engagement scoring).
- `0.5.0.01.1` Gmail API + push webhooks · `0.5.0.01.2` IMAP IDLE-mode ·
  `0.5.0.02a` sender-domain heuristic pre-filter · `0.5.0.03a` auto-flip
  toggle · `0.5.0.04a` email-driven Contact upsert · `0.5.0.05a` full-body
  opt-in · `0.5.0.05b` collapse `EmailThread.messages` JSONB ·
  `0.5.0.06a/06b` draft-response edit modal + SMTP send.

See `docs/plans/archive/90-0.5.0-email-monitoring.md` for the full option
matrices, risk table, and decision rationale.
