---
Status: ACTIVE
Type: prompt (planning handoff — investigate + discuss + author plan 96; do NOT implement yet)
Authored: 2026-07-08
Predecessor: docs/prompts/archive/95-tracking-v2.md (executed), docs/plans/archive/95-tracking-v2-interview-rounds-and-signal-quality.md
---

# Handoff — Tracking v3: fix what v2 got wrong, then design the next layer

You are starting a PLANNING session in the Naavik repo. The previous session
executed plan 95 ("tracking v2") end to end; the owner has used it and found
real problems plus a set of new requirements. Your job, in order:

1. **Read the context** (below).
2. **Diagnose the reported bugs against the live dev stack** — reproduce
   before theorizing; several items may be data/plumbing bugs, not design
   gaps.
3. **Brainstorm the system-design questions WITH the owner** (the email
   intelligence redesign and the job-page redesign explicitly ask for
   discussion first — present how things work today, lay out options with
   trade-offs, and use AskUserQuestion to resolve every open decision).
4. **Author `docs/plans/96-tracking-v3-*.md`** to the repo's plan quality
   bar (frontmatter, option matrices for non-trivial decisions, risk table,
   per-slice implementation guide) — only after the owner has answered the
   open questions. Do NOT implement anything in that session beyond
   read-only diagnosis instrumentation.

## 1. What the previous session shipped (context you inherit)

Plan 95 landed as 12 commits on `main` (f9f60d2..6a5fccd, 2026-07-07), one
per slice, all gates green (~3,512 tests). Read, in order:

- `CLAUDE.md` — repo conventions (Nix-first, service-package seams,
  llm_tracker wrap, fragment granularity).
- `docs/design/TRACKING_PIPELINE.md` — NOW CURRENT: documents the full v2
  pipeline (rounds, sender rules, correction loop, status pin, staleness,
  body posture, enrichment merge, migrations 0041–0045).
- `docs/plans/archive/95-tracking-v2-interview-rounds-and-signal-quality.md`
  — especially `## Deviations from plan` (11 items; several are relevant to
  the new complaints, e.g. EMAIL_RECEIVED occurred_at semantics).

Key seams you will touch or investigate:

| Area | Files |
|---|---|
| IMAP sync + on-demand body | `src/services/email/sync.py` (UID cursor logic in `_fetch_imap_messages`; PEEK/readonly invariants — do not regress) |
| Classification + dispatch | `src/services/email/classifier.py`, `src/llm/prompts/classify_email.py` (few-shot block, sender rules, round upsert, pin policy all hang off `_post_classify_dispatch`) |
| Grouping / detected processes | `src/services/email/processes.py` (canonical keys, parking, rejection-guard regex) |
| Corrections / sender rules | `src/services/email/{corrections,sender_rules,few_shot,pii_scrub}.py` |
| Rounds | `src/services/applications/rounds.py`, `src/ui/templates/components/tracking/_rounds_section.html`, calendar producer in `src/services/email/calendar_sync.py` |
| Status machine + pin | `src/services/applications/{state,pins}.py` |
| Suggestions (Apply/Dismiss) | `src/services/applications/email_suggestions.py`, routes in `src/ui/routes/email.py`, UI mount in `_conversation_section.html` |
| Tracking UI | `src/ui/tracking_ctx.py`, `src/ui/routes/tracking.py`, `src/ui/templates/components/tracking/*` (`tracking_card.html`, `_application_detail.html`, `_conversation_section.html`), `pages/tracking/tracking.html` |
| Job page | `src/ui/routes/jobs.py`, `src/ui/jobs_ctx.py`, `pages/jobs/*`, manual add-by-URL in `src/services/jobs/add_by_url.py` |
| Crons | `src/scheduler/jobs.py` (`tracking.sync_emails` 10min, `tracking.classify_emails` 10min +2, `tracking.sync_calendars` 45min, `tracking.staleness_sweep` weekly) |

Practical notes: `nix run .#dev` (dev DB on 127.0.0.1:5433, owner is
**user_id=2**); mint a session via `services.auth.issue_jwt_async` (see the
agent memory note "reference-dev-session-mint"); migrations are at
`0045_full_body_optin`; gates are `ruff check . && ruff format --check .` +
`uv run pytest` + Playwright for UI. **Never point destructive tests at the
dev DB; never mutate the owner's tracking data during diagnosis beyond what
they've asked for.** Shut the dev stack down when done.

## 2. Reported bugs — diagnose FIRST, with live repro

**B1. Manual card moves don't work.** The owner cannot drag cards on the
kanban board. Investigate the drag-and-drop wiring end to end
(`tracking_board.html` / `stage_column.html` drag handles, SortableJS or
whatever base.js wires, the status-update route it posts to, CSRF headers,
and whether plan 95h's pin stamping in `update_status` changed anything).
Reproduce in Playwright with a real drag gesture. This may predate v2 —
check git history if unclear. This is a trust-critical bug: the § 3.8 pin
contract is meaningless if manual moves don't work at all.

**B2. Rejection didn't update the card from the outside.** A rejection email
existed, but the card stayed put until the owner opened the slide-over
conversation and clicked Apply. Two threads to pull apart:
- By design, REJECTION → CLOSED is human-confirm (asymmetric autonomy — do
  not silently change that without asking). The real gap is **surfacing**:
  the Apply/Dismiss affordance only mounts inside the conversation section
  (95i deviation). The plan 90-era suggestion banner never got a v2 mount.
  Design an outside-the-card surface: suggestion chip on the kanban card
  and/or a pending-suggestions strip at the top of Tracking (the detected
  processes/going-quiet strips are the pattern).
- Verify the suggestion was actually CREATED when that rejection classified
  (query the dev DB: `suggested_status`, `suggestion_applied_at`,
  EMAIL_STATUS_SUGGESTED events) — if not, that's a classifier/linking bug,
  not a surfacing gap.

**B3. Newer emails not appearing.** The owner believes new mail is being
read but not shown. Diagnose the full path with dev-DB queries before
touching code:
- Is sync fetching? (`email_account.last_synced_uid`, `last_sync_at`,
  newest `email_message.received_at` vs the owner's actual inbox). Check
  the UID-cursor search (`UID <last+1>:*`) for cursor pathologies
  (UIDVALIDITY change, cap-500 truncation, cursor advancing past unfetched
  mail).
- Is classification running? (`classification IS NULL` backlog,
  `unclassified_reason` values, ApiUsage rows, cost-cap hits).
- Or is it a SURFACING gap: a linked message only ever appears inside its
  card's conversation; an unlinked non-signal message appears NOWHERE.
  There is no inbox/email-log page. If that's the root cause, the fix is a
  product decision (see Q5 below).
Report which link in the chain is broken with evidence.

**B4. "Track it" stage picker: wrong default + no Closed option.** In the
detected-processes panel, the per-row stage select should default to the
derived signal but sometimes doesn't, and CLOSED is missing entirely — the
Google group derives "Closed" yet the picker offers no Closed choice. Root
cause is known (start here, then verify): plan 95b's
`track_stage_options` / `_TRACK_STATUS_OVERRIDES` in `src/ui/tracking_ctx.py`
+ `src/ui/routes/tracking.py` deliberately excluded CLOSED, so when
`p.status == "CLOSED"` no `<option>` matches and the browser silently shows
the first option (Applied) — exactly the "default doesn't match the signal"
symptom. Fix: include a Closed option (needs a `closed_reason` —
`rejected_by_them` from the derived timeline; `track_process` already
handles closed_reason when the derived status is CLOSED, but the OVERRIDE
path currently nulls it — handle both), and audit any other status where
the derived value can't be represented in the picker. Pin with a render
test: for every derivable group status, the select contains a matching
`selected` option.

## 3. New requirements (owner's words, organized)

**R1. Interview-scheduling intelligence.** Identify "please pick a time /
send availability" emails; work with the calendar timezone-aware; suggest
possible slots; ultimately automate the loop — drafting and even SENDING
scheduling emails in the owner's voice. This is a large new surface (consent
posture! Naavik currently never sends mail). Scope it honestly — likely its
own phased slice set (detect → suggest → draft → send-with-confirm), with
the send step gated exactly like auto-apply consent.

**R2. Reschedule-aware interview-process detection (the system-design
brainstorm — discuss BEFORE planning).** The owner reports interview emails
that aren't identified or tied together. Current mechanics you must present
to the owner as the baseline for the discussion: per-message LLM
classification over a 240-char snippet (2k excerpt opt-in), thread keying by
References/In-Reply-To/Message-ID at sync, deterministic receipt regexes,
canonical-company grouping, forward-only stage mapper, round upsert keyed
application+kind+date. Known structural weaknesses to put on the table:
message-at-a-time classification (no thread/process-level pass), no ICS/
calendar-invite parsing from email bodies (invites carry the ground truth:
times, reschedules, cancellations), no notion of "the FINAL invite" (latest
non-cancelled invite wins; past vs future awareness), snippet-starved
context, and no cross-thread process assembly beyond company keys. Candidate
directions to brainstorm (present as an option matrix, don't pre-decide):
thread-level or process-level classification passes; parsing `text/calendar`
MIME parts / .ics attachments into structured invite events; an
invite-supersedence state machine (reschedule/cancel aware) feeding rounds;
embedding-assisted chain linking (pgvector is already in the stack);
a periodic "process reconciliation" job that re-derives rounds/stage from
ALL evidence rather than incremental dispatch only. Tie this to B3 — if new
mail isn't flowing, detection quality can't be judged yet.

**R3. Entity-relationship completeness.** Everything about a job — email
threads, messages, rounds, contacts, docs, application, calendar events —
must be reachable from the Job. Map today's actual FK graph (it's mostly
`application_id`-centric; threads/messages link to Application, not Job;
detected-process mail links to nothing until tracked). Identify the gaps
(e.g. mail on a job with no application yet; multiple applications per job)
and propose the canonical entity model. This underpins R4.

**R4. Job-page redesign, two state-dependent views (brainstorm with owner).**
Replace/rework the tracking slide-over: it should be linked to the original
job posting and be an expandable modal (slight job-page redesign too).
Owner's sketch:
- **Pre-apply view** (review state): resume, cover letter, tailoring, JD —
  the current Discover-ish concerns.
- **Post-apply view** (applied/recruiter screen onward): email
  conversations, interview process/rounds, JD, contacts, plus access to the
  docs used to apply.
Brainstorm the optimal information architecture for both views (wireframe-
level, componentization memo against the existing partial catalog), leaving
room for future expansions (interview prep etc.). This is a designer-grade
pass — check `docs/design/SCREENS.md` / `COMPONENTS.md` conventions before
inventing components.

**R5. Smaller UX fixes** (bundle into early slices):
- "Mark done" for a round = the checkbox/state icon itself on the round row,
  not a side button (`_rounds_section.html`).
- Kanban `tracking_card.html` visual refresh (it now carries status + round
  + quiet + pin + context chips — it's crowded; design the hierarchy).
- Collapsible conversations in the slide-over (threads currently render as
  `<details>` but the section itself needs collapse/expand-all and less
  noise).
- Per-email signal detail in the conversation: not just the
  `interview_request` chip but WHAT the email contributed — extracted
  company/role/stage/round, the transition it caused or suggested, and why
  (the data already exists on `EmailMessage` + EMAIL_STATUS_SUGGESTED
  payloads; this is a surfacing task).

## 4. Questions to resolve with the owner BEFORE writing the plan

Use AskUserQuestion; add your own as diagnosis surfaces them. At minimum:

1. **Rejection surfacing (B2):** keep human-confirm but surface Apply on the
   card/board chip + a pending-suggestions strip — or flip rejections to
   auto-apply-with-undo now that corrections exist? (Plan 95 explicitly
   chose human-confirm; changing it is an owner decision.)
2. **Email visibility (B3/Q5):** does the owner want a first-class
   inbox/email-log page (all synced mail, classification, link state), or
   only better per-job surfacing? This determines whether "new emails not
   showing" is a bug fix or a new screen.
3. **Scheduling automation (R1):** how far on the autonomy ladder — detect &
   badge only / suggest slots from calendar / draft reply for one-click send
   / auto-send with per-email confirm? What calendar is write-available
   (current integration is read-only ICS)? Sending mail needs SMTP or Gmail
   API — which, and is granting send scope acceptable?
4. **Invite parsing (R2):** is parsing `text/calendar` parts + storing
   structured invite rows (time, status, sequence, organizer) acceptable at
   rest? (It's metadata, not body text — but confirm the privacy posture.)
5. **Process assembly (R2):** comfort level with a reconciliation job that
   can MOVE cards (forward-only, pin-respecting) when re-derived evidence
   disagrees with current state?
6. **Job page (R4):** modal-first or dedicated page-first? What's
   must-have in v1 of each view vs deferred (interview prep etc.)? Should
   the tracking slide-over be fully replaced or kept as the quick view?
7. **Sequencing:** bugs (B1–B4) as an immediate `96a` fix slice ahead of the
   design work? (Recommend yes — detection quality can't be evaluated while
   new mail isn't flowing, and B1/B4 are small, high-trust fixes.)

## 5. Deliverable

`docs/plans/96-tracking-v3-*.md` — Status DRAFT → owner review, with:
frontmatter (`Type: design`, depends-on plan 95), a diagnosis section with
EVIDENCE for B1–B4 root causes, option matrices for R1/R2/R4 decisions
(capability / cost / risk / maintenance / lock-in), the resolved-questions
table, a risk table, a suggested slice sequence (96a bug fixes first), and a
per-slice § 6-style implementation guide (files / tests / acceptance) once
approved. Deviations discipline and gates carry over from plan 95 verbatim.
Do not start implementation in the planning session; a fresh kickoff prompt
(like this one) hands the approved plan to an execution session.
