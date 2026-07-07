# Tracking Pipeline — email-driven application tracking (2026-07 redesign)

Canonical design for how Naavik turns inbox signal into pipeline state. It
supersedes plan 90's "human-confirm-all" posture for forward transitions and
documents the single status pipeline every tracking source feeds.

## Design principles

- **Single write path.** Every status change — manual drag, bulk move, email
  signal, tracked process — goes through `services.applications.update_status`,
  which enforces the forward-transition state machine and emits the
  `STATUS_CHANGE` AppEvent. No side-door writes; the timeline is the audit log.
- **Separate extraction from action.** The LLM classifies and extracts
  entities (`classification`, `company`, `role`, `stage`, `urgency`) into
  `EmailMessage` columns. Deterministic code decides what to DO with them
  (linking, transitions, grouping). The LLM never mutates pipeline state.
- **Asymmetric autonomy.** Forward transitions (screen / interview / offer)
  auto-apply with `trigger=AUTO_FROM_EMAIL` — missing an update is the common
  failure and cheap to undo. Terminal transitions (REJECTION → CLOSED) stay
  human-confirm — killing a live application on a misclassification is the
  expensive failure.
- **Idempotent stage mapping.** The mapper is forward-only against a stage
  rank (`DRAFT < APPLIED < RECRUITER_SCREEN < ONSITE_LOOP < OFFER`); five
  reminders about the same interview produce zero extra transitions.
- **Everything observable.** Every LLM call rides `llm_tracker.tracked_call`
  (ApiUsage rows); every classification emits `EMAIL_RECEIVED`; every
  suggestion/auto-apply emits `EMAIL_STATUS_SUGGESTED` with `applied` flag.

## Stage vocabulary

DB enum values are stable contracts (`ONSITE_LOOP` stays); display goes
through `models.enums.APPLICATION_STATUS_LABELS` (Jinja global
`STATUS_LABELS`), where `ONSITE_LOOP` renders as **"Interview Stage"**.

## Pipeline stages

```
┌─────────┐   ┌──────────┐   ┌─────────┐   ┌──────────────┐   ┌────────────┐
│ 1 SYNC  │ → │ 2 CLASSIFY│ → │ 3 LINK  │ → │ 4 TRANSITION │ → │ 5 SURFACE  │
│ (IMAP)  │   │ + EXTRACT │   │         │   │              │   │            │
└─────────┘   └──────────┘   └─────────┘   └──────────────┘   └────────────┘
```

**1. Sync** (`services/email/sync.py`, cron `tracking.sync_emails`, 10 min).
UID-cursor incremental fetch per `EmailAccount`; RFC 2047 headers decoded at
ingest; snippet capped 240 chars (privacy: full bodies are never stored).
The cursor advances over every fetched UID (dedup'd included).

**2. Classify + extract** (`services/email/classifier.py`, cron
`tracking.classify_emails`, 10 min, offset +2). One structured LLM call per
message → `{classification, urgency, company, role, stage}`. The result dict
is validated through the Pydantic schema (`_parse_result`) — never `getattr`
on `StructuredResult.value`; it is a dict, and the silent-default bug there
is what killed tracking for 537/537 messages pre-redesign. Thread
classification is promoted from its messages (threads no longer stick at the
OTHER default).

**3. Link** — map the message to an Application, in precedence order:
1. thread already linked (inherited at sync),
2. deterministic receipt inference (`inference.py` — "thanks for applying"
   regexes; creates proposed applications for receipts),
3. fuzzy company match: `extracted_company` vs live applications
   (`find_application_for_company`). Linking backfills the thread so the rest
   of the conversation auto-links.

**4. Transition** (`services/email/status_mapper.py` → `update_status`).
Stage-aware mapping: `stage=screen → RECRUITER_SCREEN`,
`stage=interview → ONSITE_LOOP`, `OFFER → OFFER` (auto-applied, forward-only);
`REJECTION → CLOSED(rejected_by_them)` (suggestion only, banner confirm via
`applications.email_suggestions`).

**5. Surface** — messages that classified as interview signal but matched no
application group per-company into **detected processes**
(`services/email/processes.py`; Tracking page panel):

- `status_for_email_timeline` folds the group's (classification, stage)
  timeline into the stage the process has reached (offer > interview >
  screen; trailing rejection closes).
- **Track it** → Job (`source=email`) + Application created at the inferred
  stage, `applied_at` = first email, STATUS_CHANGE trail written, all
  messages/threads linked — the process joins the same pipeline as
  everything else.
- **Not mine** → `process_dismissed_at` stamps the group's messages; new
  mail from that company starts a fresh group.

## Failure modes

| Failure | Behavior |
|---|---|
| No LLM configured | `unclassified_reason=NO_PROVIDER_CONFIGURED`, retried after config |
| Rate limit / provider error | row stays `classification=NULL`, next tick retries |
| Schema mismatch from provider | loud `LLM_FAILED`, never a silent OTHER |
| Misclassified rejection | suggestion only — application survives |
| Company extraction noise | shows in detected panel; one-click dismiss; never auto-creates state |

## Data model deltas (migration 0041)

`email_message` + `extracted_company`, `extracted_role`, `extracted_stage`,
`process_dismissed_at`; one-way data repair (decode stored RFC 2047 headers,
reset pre-redesign OTHER classifications for re-run).
