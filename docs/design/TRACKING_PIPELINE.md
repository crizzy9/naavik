# Tracking Pipeline — email-driven application tracking (2026-07 redesign + tracking v2)

Canonical design for how Naavik turns inbox signal into pipeline state. It
supersedes plan 90's "human-confirm-all" posture for forward transitions and
documents the single status pipeline every tracking source feeds. Plan 95
("tracking v2") layered on interview rounds, sender rules, the correction
loop, the manual-precedence pin, staleness, and the full-body opt-in.

## Design principles

- **Single write path.** Every status change — manual drag, bulk move, email
  signal, tracked process — goes through `services.applications.update_status`,
  which enforces the forward-transition state machine and emits the
  `STATUS_CHANGE` AppEvent. No side-door writes; the timeline is the audit log.
  Mid-stage creation (Track-it, manual back-fill) goes through ONE trail
  writer, `applications.create_tracked_application` — the back-dated
  APPLIED → stage event shape keeps the funnel KPIs honest.
- **Separate extraction from action.** The LLM classifies and extracts
  entities (`classification`, `company`, `role`, `stage`, `round_kind`,
  `sender_type`, `end_client`, `urgency`) into `EmailMessage` columns.
  Deterministic code decides what to DO with them (linking, transitions,
  grouping, round upserts). The LLM never mutates pipeline state.
- **Asymmetric autonomy.** Forward transitions (screen / interview / offer)
  auto-apply with `trigger=AUTO_FROM_EMAIL` — missing an update is the common
  failure and cheap to undo. Terminal transitions (REJECTION → CLOSED) stay
  human-confirm — killing a live application on a misclassification is the
  expensive failure. Staleness auto-close is strictly opt-in for the same
  reason.
- **Human intent outranks machine inference** (plan 95 § 3.8) — in both
  directions, per-DECISION rather than per-application. See "Manual
  precedence: the status pin" below.
- **Corrections are data.** Every human override persists
  (`ClassificationCorrection`, `CompanyAlias`, `SenderRule`) and is reused:
  few-shot prompt precedents, alias-aware grouping, sender treatment, and
  the `NAAVIK_EVAL_LLM=1` regression evals.
- **Idempotent stage mapping.** The mapper is forward-only against a stage
  rank (`DRAFT < APPLIED < RECRUITER_SCREEN < ONSITE_LOOP < OFFER`); five
  reminders about the same interview produce zero extra transitions (and
  zero extra interview rounds — the round upsert key absorbs reminder spam).
- **Everything observable.** Every LLM call rides `llm_tracker.tracked_call`
  (ApiUsage rows); every classification emits `EMAIL_RECEIVED` (stamped with
  the mail's `received_at`, so backfill re-runs never reset staleness);
  every suggestion/auto-apply emits `EMAIL_STATUS_SUGGESTED` with `applied`
  (+ `suppressed_by_pin`) flags.

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
UID-cursor incremental fetch per `EmailAccount` — `readonly=True` select +
`BODY.PEEK[]` fetch, so sync NEVER marks the owner's mail read (plan 95
§ 3.6; the fake-client test pins the commands). RFC 2047 headers decoded at
ingest; snippet capped 240 chars; per-message `imap_uid` persisted for the
on-demand body read. The cursor advances over every fetched UID (dedup'd
included).

**2. Classify + extract** (`services/email/classifier.py`, cron
`tracking.classify_emails`, 10 min, offset +2). One structured LLM call per
message → `{classification, urgency, company, role, stage, round_kind,
sender_type, end_client}`. The result dict is validated through the Pydantic
schema (`_parse_result`) — never `getattr` on `StructuredResult.value`; it
is a dict, and the silent-default bug there is what killed tracking for
537/537 messages pre-redesign. `end_client` must appear VERBATIM in the text
the model saw (deterministic post-check — agencies must not invent clients).
The prompt body is the stored `body_excerpt` when the account opted in,
else the snippet; an "Owner corrections" few-shot block (K≤5, PII-scrubbed,
domain-only senders — `services/email/{few_shot,pii_scrub}.py`) injects the
owner's precedents for matching sender-domains/subject shapes. Sender rules
apply AFTER parsing: user `SenderRule` > deterministic seed > LLM guess
(`services/email/sender_rules.py`). Thread classification is promoted from
its messages (threads no longer stick at the OTHER default).

**3. Link** — map the message to an Application, in precedence order:
1. thread already linked (inherited at sync),
2. deterministic receipt inference (`inference.py` — "thanks for applying"
   regexes; creates proposed applications for receipts),
3. fuzzy company match: `extracted_company` vs live applications
   (`find_application_for_company` — canonical company keys +
   `CompanyAlias` map + role-token disambiguation when one company has 2+
   live applications). Agency/platform/outplacement mail links via its named
   END-CLIENT only. Linking backfills the thread so the rest of the
   conversation auto-links.

**4. Transition** (`services/email/status_mapper.py` → `update_status`).
Stage-aware mapping: `stage=screen → RECRUITER_SCREEN`,
`stage=interview → ONSITE_LOOP`, `OFFER → OFFER` (auto-applied, forward-only);
`REJECTION → CLOSED(rejected_by_them)` (suggestion only, confirm via
`applications.email_suggestions` — mounted inline on the card's Conversation
section). The § 3.8 pin policy gates every auto-apply (below). Interview
`round_kind` upserts an `InterviewRound` on the linked application (below).

**5. Surface** — messages that classified as interview signal but matched no
application group per-company into **detected processes**
(`services/email/processes.py`; Tracking page panel):

- `status_for_email_timeline` folds the group's (classification, stage)
  timeline into the stage the process has reached (offer > interview >
  screen; trailing rejection closes).
- Grouping keys are `canonical_company_key()` outputs (legal suffixes, TLD
  tails, spacing variants collapse; `CompanyAlias` rows from "Merge into…"
  override deterministically), keyed on `end_client or company`.
- **Track it** → Job (`source=email`) + Application created at the inferred
  stage (a per-row stage picker overrides it — "Wrong stage?"),
  `applied_at` = first email, STATUS_CHANGE trail written via
  `create_tracked_application`, all messages/threads linked — the process
  joins the same pipeline as everything else.
- **Not mine** → `process_dismissed_at` stamps the group's messages; new
  mail from that company starts a fresh group.
- **Rejection guard** (§ 3.4.4, regex): a group holding interview signal
  plus a LATER rejection-shaped FOLLOW_UP/OTHER email gets a "possible
  rejection — confirm?" chip; confirming reclassifies that message (a
  recorded correction). The regex never flips state itself.

## Sender rules — who is talking (plan 95 § 3.3)

`sender_type ∈ {employer, ats, agency_recruiter, platform, outplacement,
other}`. The agency is never the process; a named end-client is. Precedence:
**user `SenderRule` ("Flag sender…": Agency / Not job-related / Actually an
employer) > deterministic seed domains (code-level list in
`sender_rules.py`) > LLM guess**. Flags apply retroactively to the domain's
already-classified mail. Parked mail (intermediary sender, no end-client)
lives in the collapsed "Agencies & platforms" panel section — never a
detected process, never linked by agency name, ZERO notifications; parking
(not deletion) so nothing is irrecoverably dropped. The parked check also
consults rules/seeds at read time, so pre-existing rows park without a
re-classify.

## Interview rounds (plan 95 § 3.1)

`InterviewRound` — rounds WITHIN a stage; a round never IS a stage, it
EVIDENCES one. `kind` is a string + CHECK vocabulary (extensible by two-line
migration; 10 starting kinds incl. `builder_interview` and `onsite_loop`);
clubbed onsite blocks are ONE `onsite_loop` round whose `sessions` JSONB
itemizes the segments. Three producers, one consumer
(`services/applications/rounds.py`):

1. **Email** — classifier `round_kind` upserts on the linked application.
   Upsert key: application + kind + scheduled-date; dateless reminders reuse
   the open round of the kind; a dated signal fills a dateless row.
2. **Notes** — the explicit "Parse interview plan" button (never auto-runs on
   save) projects recruiter notes into `state=planned` rows via
   `llm/prompts/parse_interview_plan.py`, preview-before-save; emails and
   calendar then check them off (planned → scheduled → completed).
3. **Calendar** — a matched event whose title looks like a round upserts
   `state=scheduled` with the event link.

Stage derivation stays downstream: a completed round of an onsite-evidence
kind implies ONSITE_LOOP via the same forward-only `update_status` path. UI:
Rounds checklist on the slide-over; `2/5 · system design` chip on the board
card.

## Manual precedence: the status pin (plan 95 § 3.8)

`services/applications/pins.py`, stored in
`submission_artifacts["status_pin"]` (JSONB, no migration):

1. Provenance exists — every status write records its `trigger`.
2. A BACKWARD manual move pins the reverted status; email will not re-apply
   a transition to that same status (downgrades to a suggestion).
3. Forward manual moves don't block better news — an OFFER email still
   auto-applies.
4. CLOSED is absolute: no auto transitions ever; interview/offer signal on a
   closed application surfaces as a reopen SUGGESTION instead of being
   swallowed.
5. Every suppressed transition still emits `EMAIL_STATUS_SUGGESTED`
   (`applied: false, suppressed_by_pin: true`).
6. Unpinning is first-class: "Resume auto-tracking" on the pinned
   card/slide-over, "Apply & resume auto-tracking" on the suggestion
   (`?resume=1`), and auto-clear when the human advances to/past the pin.

## Staleness — silence as a signal (plan 95 § 3.2)

`services/applications/staleness.py` + weekly `tracking.staleness_sweep`.
`last_signal_at` is DERIVED from the AppEvent log (max `occurred_at`;
applied_at/created_at baseline; deliberately not `updated_at`). Flat
threshold for every stage (`settings.staleness_stale_days`, default 30).
Quiet applications get an amber chip + the "Going quiet" strip (Mark ghosted
→ CLOSED/ghosted through `update_status`; Nudge → outreach deep-link;
Snooze 2w → JSONB slot). Nothing closes without a click unless
`auto_close_ghosted_after_days` is explicitly set (then
`trigger=CLEANUP_STALE`).

## Body posture (plan 95 § 3.9.1 — amended privacy contract)

**Snippet by default; bounded excerpt with explicit per-account opt-in.**
The 240-char snippet remains the at-rest default. Reading a full body is an
on-demand IMAP `BODY.PEEK` by the stored `imap_uid` (host-guarded, CSRF'd,
readonly select — transits memory only, NEVER persisted; pre-95l mail falls
back to the provider deep-link). With `email_account.store_body_excerpt`
(default OFF), sync persists a 2,000-char plaintext excerpt that the chain
expands instantly and the classifier uses instead of the snippet — the
single biggest classification-context lever. Full RFC822 blobs at rest stay
rejected.

## Cross-source identity (plan 95 § 3.10)

When a scraper re-finds a job tracked from email/manual, tier-3 dedup
shadows the new row AND `jobs/dedup.enrich_canonical` merges its substance
into the tracked canonical: URL/description replace only machine-written
stubs (the rows exchange URLs so tier-2 uniqueness holds and future scrapes
hit the canonical), salary/location/criteria/skills/tags fill-if-empty,
score + embedding clear for re-queue, and a NOTE_ADDED event explains why
docs went stale. Identity (source, external_id, queue_state, Application
links) never moves. Human-typed descriptions are never touched.

## Failure modes

| Failure | Behavior |
|---|---|
| No LLM configured | `unclassified_reason=NO_PROVIDER_CONFIGURED`, retried after config |
| Rate limit / provider error | row stays `classification=NULL`, next tick retries |
| Schema mismatch from provider | loud `LLM_FAILED`, never a silent OTHER |
| Misclassified rejection | suggestion only — application survives; § 3.4.4 regex chip prompts on rejection-shaped follow_ups |
| Company extraction noise | shows in detected panel; one-click dismiss / "Merge into…" alias; never auto-creates state |
| Agency extracted as company | parked in the collapsed Agencies & platforms group; "Flag sender…" is ground truth |
| Wrong auto-link / wrong label | reclassify (six labels) + unlink on the card's Conversation section; every fix stamps a `ClassificationCorrection` |
| Email re-applies a humanly-reverted stage | § 3.8 pin downgrades it to a suggestion; unpin is one click |
| Walled posting URL in manual add | preview step surfaces the failure; typed-fields tab always available |
| `imap_uid` missing (pre-95l mail) | body expand falls back to the provider deep-link |

## Data model deltas

- **0041** — `email_message` + `extracted_company/role/stage`,
  `process_dismissed_at`; one-way data repair (decode stored RFC 2047
  headers, reset pre-redesign OTHER classifications for re-run).
- **0042** (plan 95b/c) — `classification_correction`, `company_alias`,
  `sender_rule` tables; `email_message` + `extracted_sender_type`,
  `extracted_end_client`.
- **0043** (95d) — `interview_round` (CHECK vocab kind, `sessions` JSONB,
  evidence FKs); `email_message.extracted_round_kind`.
- **0044** (95e) — `settings.staleness_stale_days` (30),
  `settings.auto_close_ghosted_after_days` (opt-in, NULL = off).
- **0045** (95l) — `email_message.imap_uid`, `email_message.body_excerpt`,
  `email_account.store_body_excerpt` (default false).
