`Status:` IN EXECUTION — 96a, 96b, 96c1–c3 landed 2026-07-08 (commits c7f8ebf, d50d829, 4acfa72, ac266ee, 9de68db; all gates green, live-QA'd); 96d/96e/96f + close-out continue in a follow-up session — see `docs/prompts/96-tracking-v3-execution-2-kickoff.md`
`Type:` design
`Authored:` 2026-07-08
`Last updated:` 2026-07-08 (rev 2 — owner review round 2: reconciler now event-driven per-application (#13), `/emails` confirmed (#14), job surface pulled forward to 96c (#15); slices renumbered, § 5 reordered to execution order)
`Depends on:` plan 95 (tracking v2, archived), `docs/design/TRACKING_PIPELINE.md`, hotfix 2b867f3 (`fix(tracking/96-pre)`)

# Plan 96 — Tracking v3: email intelligence, scheduling, and the job surface

## 1. Goal

Fix what a week of real use showed v2 got wrong (a dead kanban drag, invisible
rejection suggestions, a crash-looping classify tick, a stage picker that lies),
then build the next layer: **calendar-invite ground truth** (reschedule-aware
rounds), a **process reconciler** that re-derives state from all evidence, a
**scheduling assistant** (detect → suggest slots → draft in the owner's voice;
never sends), a **first-class email log**, and **one canonical job surface**
(modal + page, pre-apply / post-apply views) that replaces the tracking
slide-over and makes everything about a job reachable from the job.

## 2. Context / why

Plan 95 landed 2026-07-07 (12 commits, f9f60d2..6a5fccd). The owner used it
for a day and reported four bugs and five requirement clusters (R1–R5 below).
Per the owner's sequencing decision, bugs ship first as 96a — detection
quality (R2) cannot even be evaluated while classification is stalled — then
the design work in dependency order.

## 3. Diagnosis — B1–B4 root causes, with evidence

All four were reproduced against the live dev stack on 2026-07-08 (dev DB
5433, owner `user_id=2`, real Playwright gestures, live cron ticks).

### 3.1 B1 — kanban drag has NEVER worked (predates v2)

Shipped as incomplete scaffolding in plan 08 (commit 4543cf9, the component
library); v2's § 3.8 pin work never touched it. Three independent breaks,
each individually fatal:

1. **No shared Sortable group.** `base.js` § 2 initializes
   `Sortable.create(el, {handle: '.drag-handle', …})` with no `group` option
   — SortableJS rejects cross-list drops by design. Playwright repro:
   `sortable state: {"group":{"name":null}, …}`; after a real handle-drag
   from `col-applied` to `col-recruiter_screen`, the card landed back in
   `col-applied`.
2. **The POST carries no payload.** `stage_column.html` declares
   `hx-post="/api/v1/applications/move" hx-trigger="end"`, but nothing wires
   `application_id`/`target_status` — no `hx-vals`, no `onEnd` handler, no
   `htmx:configRequest` hook. Captured live: `POST /api/v1/applications/move`
   with `post_data=None` → **204** via the route's
   `if not payload: return Response(204)` branch (`api/applications.py:253`).
   The failure is perfectly silent — no toast, no error, no move.
3. **Content-type mismatch.** The route reads a JSON `Body()` dict; htmx
   sends form-encoded. Even with params wired, parsing would fail.

Also: Sortable's `end` event fires on the **source** column, which doesn't
know the destination — the fix must read `evt.to`.

### 3.2 B2 — rejection suggestions are created correctly; they are invisible

Dev-DB audit of every `classification='REJECTION'` message: the only two
rejections that hit **live** applications both created suggestions —
Inflection AI (msg 350 → app 19; the owner found and applied it from inside
the slide-over conversation on Jul 8 03:09, which is exactly the reported
friction) and Snorkel AI (msg 475 → app 22, **pending right now** with zero
board indication). The other nine rejections link to applications that were
_created already-CLOSED_ by Track-it (the rejection was folded into the
derived stage — no suggestion needed). So the classifier→suggestion path is
healthy; the only mounts for Apply/Dismiss live inside
`_conversation_section.html`. Nothing on `tracking_card.html`, nothing at
page level. **Surfacing gap, not a pipeline bug.**

### 3.3 B3 — sync fine; classification crash-looped for 37 hours

Chain audit: sync healthy (UID cursor 45194 advancing, newest mail minutes
old). But every message received after 2026-07-07 02:08 UTC sat
`classification=NULL, unclassified_reason=NULL` — 50+ messages including
three "Interview with Headway" calendar invites. Zero `classify_email`
ApiUsage rows after Jul 7 03:36 while other LLM tasks ran normally. Live
traceback captured from the 16:36 UTC tick:

1. **Poison receipt.** A receipt for Path AI (job 443, `source=MANUAL`)
   found no application via `_find_existing_application` — that matcher
   **excludes DRAFT** (`inference.py`), and app 63 sat at DRAFT — then
   `_find_library_job` found job 443 and `_create_inferred_application`
   inserted a duplicate → `UniqueViolation` on
   `ix_application_user_job_alive_unique (user_id, job_id)=(2, 443)`.
2. **The except handler crashed itself.** `inference.py`'s
   `log.warning(..., msg.id, ...)` touched an expired ORM attribute after
   the failed flush → `MissingGreenlet`-class secondary exception escaped
   the "one bad message never stalls the cron" guard.
3. **Tick-wide transaction.** `scheduler/jobs.py:classify_emails` committed
   once at the end, so every escape rolled back the whole tick —
   classifications, reason stamps, **and ApiUsage rows**. Each 10-minute
   retry re-billed ~50 classify calls invisibly (~$5–15/day; owner should
   glance at the OpenAI dashboard for Jul 7–8).

**Fixed during this planning session** (owner-approved hotfix, commit
`2b867f3`, full gates green, live-verified: backlog 0, Path AI message
linked to app 63, Headway invites classified INTERVIEW_REQUEST): link
receipts to an existing alive application on the resolved job; iterate ids +
re-fetch + rollback-first in `infer_unprocessed`; commit classification
before inference runs. 96a carries the follow-ups (§ 5.1).

The product-level half of B3 stands: **64 % of synced mail (377/589) has no
surface at all** — unlinked non-signal mail and any unclassified backlog
appear nowhere. Resolved: build the email log (§ 5.2).

### 3.4 B4 — Track-it picker: CLOSED unrepresentable

`tracking_ctx.track_stage_options` and `routes/tracking._TRACK_STATUS_OVERRIDES`
both enumerate only {APPLIED, RECRUITER_SCREEN, ONSITE_LOOP, OFFER}. When a
group derives CLOSED, no `<option>` matches `p.status`, so the browser
silently renders the first option — "Applied", the exact reported symptom.
Live case: the Google group (one real rejection, "Re: Google Interview prep
Information", plus Google Play receipts polluting the same canonical key —
noted for § 5.5 grouping quality). Additionally `track_process`'s override
path nulls `closed_reason`, so merely adding the option would crash
`create_tracked_application`'s CLOSED trail.

## 4. Decisions — resolved with the owner (2026-07-08)

| #   | Question                 | Decision                                                                                                                |
| --- | ------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| 1   | Live crash-loop handling | **Hotfix in the planning session** — landed as 2b867f3                                                                  |
| 2   | Sequencing               | **96a bug slice first**, then design slices                                                                             |
| 3   | Rejection posture (B2)   | **Keep human-confirm, make it visible** — suggestion chip on the card + pending-suggestions strip; auto-apply rejected  |
| 4   | Email visibility (B3)    | **Full email-log page** — all synced mail, classification, link state, correction affordances                           |
| 5   | R1 autonomy ladder       | **Detect → suggest slots → draft in owner's voice; owner sends.** No send capability in v3                              |
| 6   | Mail/calendar access     | **Stay read-only** (IMAP PEEK + ICS). No SMTP, no Gmail send scope, no OAuth app                                        |
| 7   | Invite parsing at rest   | **Yes — full structured invite rows** (times, organizer, attendees, sequence/status), cascade-deleted with the account  |
| 8   | Reconciler authority     | **Forward moves auto, § 3.8 pin-respecting** — the same contract email transitions already have                         |
| 9   | R4 shape                 | **One state-dependent body template, rendered as expandable modal AND `/jobs/{id}` page; tracking slide-over replaced** |
| 10  | R4 v1 deferrals          | Interview-prep section, outreach integration, scheduling panel all deferred (IA reserves their slots)                   |
| 11  | 2k excerpt opt-in        | **Enabled 2026-07-08** on the owner's account (no backfill)                                                             |
| 12  | R2 extra mechanisms      | **Thread-level LLM pass inside the reconciler**; embedding chain-linking stays deferred (like 95g)                      |
| 13  | Reconciler cadence       | **Event-driven, per-application** — triggered only by new evidence (classified mail, invite, correction, applied suggestion) and only for the affected job; no standing cron. Deterministic time-passage (past-due rounds) rides the existing calendar-sync cron |
| 14  | Email-log route          | **`/emails`** confirmed                                                                                                 |
| 15  | Job-surface ordering     | **Pulled forward** — lands as 96c, before invites/reconciler/scheduling                                                 |

## 5. Proposal

### 5.1 96a — bug slice (B1, B2, B4 + B3 residuals)

**B1 rewire — drag that works.** Keep SortableJS (already vendored, already
initialized) and fix the wiring in `base.js`:

- `Sortable.create(el, {group: 'tracking-board', handle: '.drag-handle', …})`.
- An `onEnd` handler replaces the dead `hx-trigger="end"` declaration:
  reads `evt.item.dataset.appId` + `evt.to.dataset.column`, no-ops when
  `evt.from === evt.to`, and issues the POST via `htmx.ajax`-equivalent
  `fetch` with `Content-Type: application/json` + `X-CSRF-Token` (double
  submit from the `naavik_csrf` cookie — same contract every htmx request
  already uses via the global config).
- Optimistic UX per INTERACTIONS.md § H.4: Sortable already moved the DOM
  node; on non-2xx/409 the handler moves the card back to `evt.from` at
  `evt.oldIndex` and toasts the server's detail (state-machine 409s must be
  legible — "backward moves need the card menu", not a silent snap-back).
- Server side (`api/applications.py:move`): unchanged contract, but the
  silent `204` no-op branches on malformed payloads become `422`s — a
  malformed drag must never look like success again. Dropping into the
  Closed column (visible when `show_closed=1`) prompts for `closed_reason`
  via the existing confirm-modal pattern before posting.
- Remove `hx-post`/`hx-trigger` from `stage_column.html` (dead wiring).

Options considered for the transport: keep the pseudo-declarative
`hx-trigger="end"` + hidden inputs (breaks on cross-column: `end` fires on
the source list; form-encoding still mismatches the JSON route) vs. explicit
`onEnd` + fetch (recommended — one place, reads `evt.to`, matches the JSON
route, testable). No matrix needed beyond this note; the declarative variant
is structurally unable to know the destination column.

**B2 surfacing — suggestions visible from the outside.**

- `tracking_ctx` board-card builder gains `suggestion_chip` (amber,
  "rejection?" / "→ Interview Stage?") when the application has a pending
  `EmailMessage.suggested_status`; renders on `tracking_card.html` beside
  the existing chip row.
- A **pending-suggestions strip** at the top of Tracking (same panel pattern
  as detected-processes / going-quiet): one row per pending suggestion —
  company, suggested transition, evidence subject, Apply / Apply-&-resume
  (when pinned) / Dismiss — posting to the existing
  `/api/v1/applications/{id}/email-suggestion/{mid}/…` routes (one component,
  three mounts: strip, card chip → opens the job surface, conversation).
- Receipt-on-DRAFT advance: a receipt that links to a DRAFT application now
  auto-applies DRAFT → APPLIED (forward move, decisive evidence, § 3.8
  pin-respecting, `trigger=AUTO_FROM_EMAIL`) — the Path AI case ends with
  the card honestly at Applied instead of linked-but-invisible.

**B4 — represent CLOSED.**

- `track_stage_options` + `_TRACK_STATUS_OVERRIDES` gain CLOSED; the
  override path passes `closed_reason` through (derived
  `rejected_by_them` when the timeline shows one, else default
  `rejected_by_them` for an explicit human CLOSED pick).
- Render test pinning the class: **for every status
  `status_for_email_timeline` can derive, the picker contains a matching
  `selected` option** — the bug class, not the instance.

**B3 residuals.** Hotfix already landed. 96a adds: a characterization test
on `classify_emails` commit boundaries (classification survives inference
failure — currently only pinned indirectly), and a `log.error` +
notification when a tick processes 0 rows while a backlog exists (the
37-hour silent stall must page next time).

**R5 riders in 96a:** round "Mark done" becomes the state icon/checkbox on
the round row itself in `_rounds_section.html` (POST unchanged; the side
button goes).

### 5.2 96b — the email log (owner decision #4)

New screen, domain-grouped per plan 93: `pages/email/email_log.html` +
`components/email/` partials, route `GET /emails` (+ `/_fragments/email/log`
for filter/pagination swaps), sidebar nav entry between Tracking and
Settings.

- **Row:** received (relative), sender (name + domain), subject,
  classification chip (existing vocabulary colors; "pending" for NULL),
  link state chip — `linked → <company>` (deep-link to the job surface),
  `detected`, `parked`, `dismissed`, `—` — and the round/stage extraction
  when present.
- **Row actions:** Reclassify (six labels — the 95b routes, third mount),
  Flag sender (95c), open-in-provider deep link, on-demand body expand
  (95l PEEK path).
- **Filters:** classification, link state, account, date range, sender
  search. Default view shows everything (owner explicitly chose the full
  log over signal-only); an "unclassified" badge in the header surfaces
  backlog size — the B3 stall would have been visible in a day.
- **Per-email signal detail (R5):** expanding a row (and the same component
  in the job-surface conversation) shows WHAT the email contributed:
  extracted company/role/stage/round/sender-type chips, and the transition
  it caused or suggested with its EMAIL_STATUS_SUGGESTED outcome
  (`applied` / `suppressed_by_pin` / pending) — the data already sits on
  `EmailMessage` + the event payloads; this is pure surfacing.
- Pagination keyset on `(received_at, id)`, 50/page. IDOR: all queries
  user-scoped; fragment-granularity guard tests.

### 5.3 96c — entity reachability + the job surface (R3, R4, owner #9, #10; pulled forward per owner review)

**R3 — the FK graph today** (audited): everything hangs off
`application_id` — `EmailThread`/`EmailMessage`, `InterviewRound`,
`AppEvent`, contacts (`Contact.application_id`), generated docs
(`submission_artifacts` + document rows), calendar matches. `Job` reaches
them only via its applications. Gaps: (a) detected-process mail links to
nothing until tracked (grouped by company key at read time); (b) email on a
job with no application yet is unreachable from the job; (c) multiple
applications per job are legal (re-applications) and must all surface.

**Resolution (option chosen: thread-level job link, not message-level):**
nullable `email_thread.job_id` (migration 0046) set whenever a thread links
to an application (denormalized from it) or when detected-process mail is
resolvable to a library job pre-application; messages reach the job via
their thread. Read-time company-key grouping stays for unresolved mail.
A message-level `job_id` was rejected (redundant with the thread's; two
writers for the same fact), as was a polymorphic evidence table (massive
churn for zero new capability).

**R4 — one body, two mounts, two views.**

- `src/ui/job_surface_ctx.py` builds one context: job, its applications
  (newest primary), threads+messages (+ per-email signal detail from 96b),
  rounds (invite chains join the same section when 96d lands), contacts,
  docs used at apply time (from `submission_artifacts`), score/tailoring
  state, timeline.
- `pages/jobs/_job_surface.html` renders `view=pre_apply|post_apply`
  (derived: no application or DRAFT → pre; APPLIED+ → post; CLOSED → post
  with closed banner) with a manual tab switch — composed from the
  existing partial catalog (`COMPONENTS.md` is closed by default; the
  componentization memo at execution time lists variants, per the
  designer conventions).
  - **Pre-apply:** JD + score/match analysis + tailoring workspace links +
    resume/cover-letter embeds — today's `/jobs/{id}` concerns, re-homed.
  - **Post-apply:** conversation (collapsible threads with
    expand/collapse-all — the R5 ask), rounds checklist, JD (collapsed),
    contacts, docs-used, status timeline. Reserved slots (rendered as
    muted "coming later" affordances, per owner #10): interview prep,
    outreach, scheduling panel.
- **Mount 1 — expandable modal** `GET /_modal/job/{id}` from board cards,
  Discover rows, email-log rows. **Mount 2 — full page** `GET /jobs/{id}`
  (same body, page chrome, deep-linkable; modal has an "expand" affordance
  to it). The tracking slide-over routes
  (`/_fragments/tracking/application/{id}`, `/tracking/{id}` push-URL)
  re-point to the job surface; `_application_detail.html` retires after a
  deprecation slice tick. Fragment-granularity guard extended to the new
  routes.
- **Board-card refresh (R5):** hierarchy pass on `tracking_card.html` —
  identity row (company/role), ONE metric row (match + salary), ONE status
  row where round-progress, quiet, pin, and suggestion chips collapse into
  at most two visible chips + a `+N` overflow that opens the modal.
  Design-token pass only; no new components.

### 5.4 96d — calendar-invite ground truth (owner decision #7)

**New table `email_invite`** (migration 0047):

```
EmailInvite
  id, user_id, email_message_id FK CASCADE, application_id FK?, interview_round_id FK?
  ics_uid          str      — VEVENT UID (stable across reschedules)
  recurrence_id    str?     — instance key for recurring events
  sequence         int      — RFC 5545 SEQUENCE (bumps on reschedule)
  method           str CHECK: request | cancel | reply | counter | publish
  status           str CHECK: confirmed | tentative | cancelled
  summary, location, organizer_email, attendee_emails JSONB
  starts_at, ends_at timestamptz, tz str
  created_at, updated_at
  UNIQUE (user_id, ics_uid, coalesce(recurrence_id,''), sequence, method)
```

- **Sync** parses `text/calendar` MIME parts + `.ics` attachments from the
  already-fetched RFC822 (no extra IMAP round-trips) via the `icalendar`
  library (new dependency — pyproject + flake). Parse failures degrade to a
  log line; sync never fails on a malformed invite.
- **Supersedence is derived, not stored:** the _final invite_ for an
  (ics_uid, recurrence_id) is the max-sequence non-cancelled REQUEST; a
  CANCEL at ≥ sequence kills the chain. One pure function
  (`invites.resolve_final`) with exhaustive unit tests — this is the
  reschedule/cancel state machine.
- **Rounds integration:** an invite on a linked application upserts the
  round by **ics_uid** (a new nullable `interview_round.invite_uid`
  evidence key, same migration) — reschedules MOVE the round's
  `scheduled_at` instead of spawning date-keyed siblings; cancellation
  without replacement flips the round back to `planned`; kind comes from
  the carrying message's `extracted_round_kind`, falling back to title
  heuristics (the calendar-producer regexes in `calendar_sync` today).
  Past-`ends_at` scheduled rounds complete automatically (outcome stays
  `pending`) — completion-by-time is the one evidence class with no email
  trigger, so it rides the existing 45-min `tracking.sync_calendars` cron
  as a deterministic rider (no LLM, no new cron; see § 5.5).
- Backfill task: parse invites for already-stored messages that have
  `imap_uid` (PEEK by UID, bounded, one-shot) so the Headway chain gets its
  ground truth without waiting for new mail.
- Privacy: `TRACKING_PIPELINE.md` body-posture section gains "structured
  invite metadata at rest (owner-approved 2026-07-08); body text posture
  unchanged".

### 5.5 96e — the process reconciler (owner decisions #8, #12, #13)

**Event-driven, per-application — no standing cron** (owner decision #13:
"trigger only when there is new information, and only for that job").
`services/email/reconcile.py` exposes `reconcile_application(session,
application_id)` (and a group variant for detected processes); it runs at
the end of any operation that produced new evidence, scoped to exactly the
applications/groups that evidence touched:

- the classify tick's `_post_classify_dispatch` collects the set of
  applications its messages linked/affected this tick and reconciles each
  once (batch-dedup — ten emails about one application still mean one
  reconcile);
- invite ingest (96d) reconciles the invite's application;
- a recorded correction (reclassify / unlink / merge / flag-sender)
  reconciles the affected application or group — corrections are new
  information too;
- applying a suggestion reconciles that application.

What a reconcile does: **re-derive rounds + stage from ALL evidence** —
classifications, extractions, invite chains (final invites only), calendar
matches, corrections, the pin — instead of trusting incremental dispatch
order alone.

- **Deterministic core first:** re-run grouping with current aliases +
  sender rules (heals the "rejection landed in a different group" class),
  re-fold the (classification, stage) timeline, re-resolve invite chains,
  and diff against current rounds/status.
- **Thread-level LLM pass** (owner #12): only for the triggering threads —
  the ones with new mail — one `tracked_call` per thread over the FULL
  conversation (subjects + excerpts, newest-first, capped) with schema
  `{process_stage, rounds: [{kind, date, state}], rejection: bool,
  needs_scheduling: bool}` — the conversation-coherent read that
  per-message snippets can't give. Prompt in `llm/prompts/`, eval-harness
  cases from day one, daily cost cap honored.
- **Writes ride existing seams only:** rounds through the 95d upsert
  producers; stage through `update_status` — forward-only,
  `trigger=AUTO_FROM_EMAIL`-class provenance (new
  `trigger=RECONCILED` for auditability), § 3.8 pin suppression to
  suggestions, CLOSED absolute, every suppressed move still emits
  `EMAIL_STATUS_SUGGESTED`. The reconciler can never do anything a
  well-ordered email stream couldn't.
- **Idempotence pinned by test:** reconciling twice with no new evidence
  produces zero writes; flapping is the failure mode to design against.
- **Time-passage rider:** past-due scheduled rounds completing (§ 5.4) is
  deterministic and rides the existing calendar-sync cron — the only
  reconciler-adjacent work not gated on an email arriving.

### 5.6 96f — scheduling assistant (owner decisions #5, #6)

Detect → suggest → draft; **Naavik never sends**. No new scopes.

- **Detect:** classifier schema gains `action_needed:
  none | send_availability | pick_slot | confirm_time` (deterministic
  keyword post-check like `end_client`); the thread pass (96e) sets
  `needs_scheduling` at conversation level. Either mounts a "Needs
  scheduling" strip row on Tracking (same panel pattern; urgency-ordered).
- **Suggest slots:** free-slot computation from the read-only calendar —
  synced events + final invites block; working hours + timezone from two
  new Settings fields (`scheduling_timezone`, `scheduling_window`,
  defaulted from the profile city); propose the next N conflict-free slots
  across 5 business days. Pure function, heavily unit-tested (DST edges).
- **Draft:** one `tracked_call` (`llm/prompts/draft_scheduling_reply.py`)
  — owner-voice reply embedding the chosen slots, grounded on the thread
  excerpt; renders in a panel with **Copy** and **Open in mail client**
  (Gmail compose deep-link `view=cm` with prefilled to/subject/body — a
  URL, not an API). Nothing persists except an AppEvent noting a draft was
  produced (auditability without storing prose).
- The send rung stays designed-but-unbuilt: this slice's seams (detection
  field, slot engine, draft prompt) are exactly what a later consented
  send step would reuse; the plan deliberately reserves
  `Settings.scheduling_autonomy` naming for it.

### 5.7 What this plan explicitly does NOT do

No mail sending, no SMTP/OAuth scopes, no calendar write, no embedding
cascade (95g stays deferred), no interview-prep/outreach/scheduling panels
inside the job surface v1, no CLI/vault anything, no auto-applied
rejections.

## 6. Risks

| Risk                                                                       | Mitigation                                                                                                                                                                              |
| -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Drag rewrite regresses the one thing that "worked" (within-column reorder) | It never persisted anything; Playwright gesture test in CI-surrogate QA per 96a acceptance                                                                                              |
| SortableJS group enables accidental cross-column drops                     | `handle:` stays (grip-only); 409 rollback restores; backward moves keep needing the card menu (state machine unchanged)                                                                 |
| ICS parsing variance (Outlook/Google METHOD, TZID, forwarded invites)      | `icalendar` lib + `zoneinfo`; parse failures degrade to log; supersedence is a pure function with vendor-fixture tests (Google, Outlook, Greenhouse samples from the owner's own inbox) |
| Invite dedup: same invite forwarded / re-delivered                         | UNIQUE key on (uid, recurrence, sequence, method); idempotent upsert                                                                                                                    |
| Reconciler flaps or fights the human                                       | Forward-only + pin + idempotence test (zero writes on unchanged evidence); every move carries `trigger=RECONCILED` provenance; suggestions for everything suppressed                    |
| Thread-pass LLM cost creep                                                 | Only threads with new mail since last pass; excerpt-capped prompt; daily cost cap already enforced by `llm_tracker`; ApiUsage now durable (2b867f3)                                     |
| Slide-over replacement breaks the UI test surface                          | Slide-over tests migrate slice-locally with the routes; push-URL contract (`/tracking/{id}`) redirects to `/jobs/{id}?application={id}` so bookmarks survive                            |
| Email-log page leaks another user's mail                                   | User-scoped queries + IDOR tests, same pattern as every tracking route                                                                                                                  |
| Free-slot suggestions cross DST/timezone edges wrong                       | Slot engine is a pure function on `zoneinfo`; DST-transition unit tests; suggested slots always render with explicit tz label                                                           |
| Gmail compose deep-link body length limits (~2k URL)                       | Draft panel's primary affordance is Copy; the deep-link truncates gracefully with a toast                                                                                               |
| One-template/two-mounts drifts into page-vs-modal divergence               | Single `_job_surface.html` body include pinned by a render-equivalence test (same ctx → same body HTML in both mounts)                                                                  |
| 0046/0047 migrations against live dev data                                 | Additive-only; tested upgrade+downgrade against a dev-DB snapshot before applying (never destructive fixtures at the dev DB)                                                            |
| Event-driven reconciler misses evidence with no email trigger (time passing) | Past-due-round completion is deterministic and rides the existing 45-min calendar-sync cron; staleness sweep (95e) already covers long silence — no evidence class is left uncovered   |

## 7. Suggested build sequence

| Slice | Contents                                                                                                                                   | Size                                                                     |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------ |
| 96a   | § 5.1 bug slice: drag rewire, suggestion chip + strip, CLOSED in picker, B3 residual guards, receipt-on-DRAFT advance, round-row mark-done | M                                                                        |
| 96b   | § 5.2 email log + per-email signal detail component                                                                                        | M                                                                        |
| 96c   | § 5.3 thread job-link (0046), job_surface ctx + template + both mounts, slide-over retirement, card refresh                                | XL — execute as c1 (data+ctx), c2 (surface+mounts), c3 (retirement+card) |
| 96d   | § 5.4 invite parsing (0047), supersedence, round integration, backfill                                                                     | L                                                                        |
| 96e   | § 5.5 event-driven reconciler + thread-level pass (`trigger=RECONCILED`)                                                                   | L                                                                        |
| 96f   | § 5.6 scheduling detect/slots/draft strip                                                                                                  | M–L                                                                      |

Ordering per owner review: the job surface lands before the email-
intelligence slices. Dependencies: 96b's signal-detail component is reused
by 96c's conversation; 96e consumes 96d's invite chains; 96f consumes 96d
(busy slots) and 96e's `needs_scheduling`. The job surface renders rounds
from the existing 95d producers on day one; invite chains and reconciler
output enrich it in place when 96d/96e land — no rework.

## 8. Implementation guide (per slice — files, tests, acceptance)

Cross-slice rules — carried over from plan 95 § 6 verbatim: gates per slice
(`ruff check . && ruff format --check .` + `uv run pytest` green + Playwright
QA for UI slices) before the slice's commit; commit locally on `main`, one
commit per slice, `feat(tracking-v3/96X):` / `fix(...)` prefixes; migrations
numbered as slices land, additive, reversible, never edited after applying
to the dev DB; service logic in domain packages (package `__init__` is the
patch surface); LLM calls only through `llm_tracker.tracked_call`; fragments
match their `hx-target` granularity; every state-changing control gets
loading + toast feedback; Lucide stroke 1.5; deviations logged the moment
implementation diverges and promoted into `## Deviations from plan` at
archive time.

| Slice    | Touch                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Tests                                                                                                                                                                                                                              | Acceptance                                                                                                                                                                              |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **96a**  | `base.js` (group + onEnd fetch + rollback), `stage_column.html` (drop dead hx attrs), `api/applications.py` (422 on malformed move; closed_reason), `tracking_ctx.py` + `tracking_card.html` (suggestion_chip), new `components/tracking/_suggestions_strip.html` + ctx + tracking.html mount, `tracking_ctx.track_stage_options` + `routes/tracking._TRACK_STATUS_OVERRIDES` + `processes.track_process` (closed_reason through override), `inference.py` (DRAFT→APPLIED advance), `_rounds_section.html` (mark-done on row) | Playwright drag gesture (cross-column persists after reload; 409 snaps back with toast); strip + chip render tests; picker render test over every derivable status; move-route 422/409/pin contract tests; DRAFT-advance unit test | Owner can drag a card and it sticks; the Snorkel suggestion is visible on the board and applies in one click; the Google group defaults to Closed and tracks as CLOSED/rejected_by_them |
| **96b**  | `pages/email/email_log.html`, `components/email/*` (row, signal-detail, filters), `src/ui/routes/email_log.py` (or extend `routes/email.py`), `email_log_ctx.py`, sidebar nav, keyset pagination                                                                                                                                                                                                                                                                                                                              | render + filter + pagination tests; IDOR; fragment guard; signal-detail component test (transition outcome renders from event payload)                                                                                             | Every synced email findable in ≤2 clicks with its classification, link state, and what it did; reclassify/flag work from the row                                                        |
| **96c1** | migration 0046 (`email_thread.job_id` + backfill from applications), `job_surface_ctx.py` | ctx aggregation tests (multi-application job; mail-no-application job; detected-only) | Every entity class about a job reachable from one ctx call |
| **96c2** | `pages/jobs/_job_surface.html` + view components, `/_modal/job/{id}` + `/jobs/{id}` mounts, expand affordance, reserved-slot placeholders | render-equivalence (modal vs page body); pre/post view derivation; fragment guard; Playwright visual QA both mounts | One surface answers "everything about this job", composition flips on state |
| **96c3** | slide-over route re-point + `_application_detail.html` retirement, `/tracking/{id}` redirect, `tracking_card.html` hierarchy pass, test migration | redirect contract; card render (chip collapse + overflow); full Playwright board pass | No orphaned routes/templates; the board card is legible at a glance |
| **96d**  | migration 0047 (`email_invite`, `interview_round.invite_uid`); `services/email/invites.py` (parse, `resolve_final`, round upsert wiring); sync MIME hook; `icalendar` dep (pyproject + flake); past-due-round rider on `tracking.sync_calendars`; one-shot backfill task; TRACKING_PIPELINE amendment | vendor-fixture parse tests; supersedence pure-fn matrix (reschedule, cancel, counter, recurring instance); round-moves-not-duplicates test; sync-degrades-on-malformed test; past-due completion test | The Headway chain shows ONE technical-screen round at the final invite's time; a reschedule email moves it; a cancellation reverts it to planned |
| **96e**  | `services/email/reconcile.py` (+ package export) with `reconcile_application` / group variant; trigger wiring in `_post_classify_dispatch` (batch-dedup per tick), invite ingest, corrections, suggestion-apply; `llm/prompts/classify_thread.py`, `StatusChangeTrigger.RECONCILED`, per-application reconcile stamp (JSONB slot), eval-harness cases | triggered only for evidence-touched applications (no global sweep); idempotence (no-new-evidence → zero writes); pin-suppression contract; forward-only; thread-pass only on triggering threads; cost-cap honored | ByteDance/Camber-class drift self-heals within minutes of the evidence classifying; nothing moves backward; every reconciler move is auditable on the timeline |
| **96f**  | classifier schema `action_needed` (+ post-check), `services/scheduling/` (slot engine, draft), `llm/prompts/draft_scheduling_reply.py`, Settings fields (tz/window), "Needs scheduling" strip + draft panel | slot-engine DST/tz unit matrix; detection post-check tests; strip render; draft prompt eval smoke; no-send static guard (no smtplib/send scope anywhere) | A "send your availability" email surfaces on the strip with 3 valid slots and a copyable owner-voice draft; Naavik demonstrably cannot send it |

**Done criteria for the whole plan:** all slices merged with green gates;
`docs/design/TRACKING_PIPELINE.md` updated (invites, reconciler, scheduling
posture, email log, job surface); this plan flipped to EXECUTED and archived
with a non-empty `## Deviations from plan`; kickoff prompt archived to
`docs/prompts/archive/`.

## 9. Open items — all resolved (owner review, 2026-07-08)

1. Reconciler cadence → **event-driven, per-application** (decision #13,
   § 5.5): triggered only by new information about a specific job — never a
   standing sweep. Deterministic time-passage (past-due rounds) rides the
   existing calendar-sync cron.
2. Email-log route name → **`/emails`** (decision #14).
3. Job-surface ordering → **pulled forward to 96c**, ahead of
   invites/reconciler/scheduling (decision #15, § 7).

No open items remain; the plan is ready to hand to an execution session.

## Deviations from plan (running — promoted to final form at archive time)

Logged during execution session 1 (2026-07-08, slices 96a → 96c3).

1. **96a — the Snorkel acceptance fixture was dead on arrival.** Msg 475's
   application (22) had been soft-deleted 2026-07-06;
   `list_pending_suggestions` deliberately excludes deleted applications
   (a strip row whose Apply targets a deleted app would 404). Live
   acceptance used the other real pending rejection: Anthuria
   (msg 546 → app 89). No design impact.
2. **96a — closed-reason picker is a client-built dialog, not
   `/_modal/confirm`.** The confirm modal has a fixed action URL and no
   input slot; the drop handler needs a `<select>` resolved back into its
   fetch. Same visual shell; the vocabulary is server-rendered on the
   CLOSED column via `data-closed-reasons` (pinned ⊆ `ClosedReason` by
   test).
3. **96a — post-drop board refresh added.** A successful move re-fetches
   `/_fragments/tracking/board` — pure optimistic UX left column counts
   and the card's own status pill stale.
4. **96a — stall-alert backlog is `classification IS NULL AND
   unclassified_reason IS NULL`.** Stamped degraded states
   (NO_PROVIDER_CONFIGURED / RATE_LIMITED / LLM_FAILED) must not page
   every tick; only never-stamped rows (the crash-loop signature) do.
5. **96a — DRAFT-advance stamps `applied_at = msg.received_at`** when the
   draft had none; `update_status`'s "now" default would misdate the
   funnel.
6. **96a/96c — app 63 (Path AI) advanced by a one-shot script.** Its
   receipt (msg 540) was linked by hotfix 2b867f3 BEFORE the 96a advance
   existed, and inference never revisits processed messages; the fix ran
   `_advance_draft_on_receipt` once via the production path
   (auditable AppEvent trail).
7. **96c — re-applications are soft-deleted history, not parallel alive
   rows.** `ix_application_user_job_alive_unique` allows one alive
   application per (user, job); "all must surface" (R3 gap c) is honored
   by listing deleted siblings with an `is_removed` flag; primary =
   newest alive.
8. **96c — pre-apply "resume/cover-letter embeds" shipped as document
   links + workspace deep-link,** not inline PDF iframes (off-viewport/
   headless-render bug class; the Discover review workspace already
   embeds them). Reserved-slot placeholders unaffected.
9. **96c — failure banner + DRAFT discover-jump render view-independently.**
   The plan's pre/post split would have hidden a stuck DRAFT's
   "Stuck in queue" banner (DRAFT derives pre_apply); plan-79/81
   contracts outrank the split.
10. **96c — bullet-overrides extracted to its own partial** as the PUT
    route's swap unit; the old route returned the whole slide-over into a
    section slot (pre-existing granularity quirk, fixed in passing).
    `sample_data_models.Job` gained the apply-resolver fields for parity.
11. **96c — surface ctx resolves the application through
    `services.applications.get_application`** (not `session.get`) so the
    sample-data shims intercept — same seam discipline as the routes.
