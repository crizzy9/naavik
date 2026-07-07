`Status:` AWAITING REVIEW
`Type:` design
`Authored:` 2026-07-07
`Last updated:` 2026-07-07 (rev 2 — added §§ 3.7–3.10: manual add-by-URL, manual-override precedence, email chain on the card, cross-source job dedup)
`Depends on:` plan 90 (email monitoring), 2026-07 tracking redesign (`docs/design/TRACKING_PIPELINE.md`, migration 0041)

# Plan 95 — Tracking v2: interview rounds, signal quality, and the correction loop

## 1. Goal

Evolve the email-driven tracking pipeline from "one stage per application" to a
system that models **interview rounds within a stage**, **notices silence**
(abandoned processes), **knows who is talking** (employer vs agency vs
platform), and **learns from the owner's corrections** so the same
misclassification doesn't happen twice — all without breaking the six-stage
pipeline contract, the KPI derivations, or the privacy posture (no full email
bodies at rest). Plan-only: nothing here is implemented yet.

## 2. Context / why

The 2026-07 redesign made the pipeline *work* (classification was silently dead
before). Using it for a week surfaced the next layer of problems, all reported
by the owner:

1. A process is not one event — Camber ran a technical screen AND a system
   design round; both currently collapse into the single `ONSITE_LOOP`
   ("Interview Stage") bucket. The owner often *knows the full round plan*
   from recruiter-screen notes, but there is nowhere to put it.
2. Companies ghost. Nothing ever moves a silent application out of the active
   board; the pipeline only reacts to signal, never to its absence.
3. Agency/staffing recruiters (G2i, Camo People, TriEdge, RiseSmart) get
   extracted as "companies" even though they are intermediaries — sometimes
   for a real end-client, sometimes for nothing trackable at all.
4. Wrong stage sticks: ByteDance and Camber already rejected the owner but
   still showed "Interview Stage" — misclassification or company-variant
   splits ("mosaicapp.com" vs "Mosaic", "Brico" vs "Brico.ai") mean the
   rejection lands in a different group than the interviews. There is no
   correction affordance, and corrections don't feed back into anything.
5. Open question whether a trained ML model beats the current LLM call.
6. The IMAP fetch currently uses `UID FETCH (RFC822)`, which sets `\Seen` —
   sync **marks the owner's unread mail as read**. (Confirmed in
   `src/services/email/sync.py:_fetch_imap_messages`; RFC 3501 §6.4.5 — only
   `BODY.PEEK[...]` is side-effect-free.)
7. Manual tracking is high-friction: the "Add manually" modal requires
   company/role/description typed by hand — its URL field is stored but never
   scraped, even though a headless add-by-URL pipeline already exists (used
   by email inference). And a manually added job can't declare where it
   already stands (applied? interviewing?), so it enters the pipeline wrong.
8. Manual status changes vs email signal: both write to the same status, but
   there is no precedence rule. The owner's requirement is explicit —
   **manual overrides email**.
9. Opening a tracking card shows the status timeline but not the email
   conversation that produced it — the evidence is invisible.
10. A job tracked from email or manual entry can later be re-found by the
    scrapers as a "new" job — today that produces a second library row (the
    tier-3 dedup shadows one side, but the tracked stub never gets the
    scraped enrichment).

### Design principles carried forward (see `docs/design/TRACKING_PIPELINE.md`)

- **One write path** — every stage change goes through
  `applications.update_status`; the AppEvent log stays the audit trail.
- **Perception ≠ policy** — the LLM extracts facts; deterministic code decides.
- **Asymmetric autonomy** — cheap-to-undo moves auto-apply; destructive moves
  (close, delete, merge) require a human click.
- **Corrections are data** — every human override is persisted and reused, not
  discarded.

---

## 3. Proposal

### 3.0 Immediate fixes (small, ship first — "95a")

| Fix | Where | Why now |
|---|---|---|
| `BODY.PEEK[]` instead of `RFC822`, and `select("INBOX", readonly=True)` | `sync.py:_fetch_imap_messages` | Stops marking the owner's mail as read (item F below). Two-line change + fake-client test. |
| Company-key canonicalization | `inference._norm` / `processes._norm_company` | Strip legal suffixes (`inc`, `llc`, `ltd`), TLD-ish tails (`.ai`, `.io`, `.com`), collapse spaces/case before grouping and matching. Merges "Brico"/"Brico.ai", "Mosaic"/"mosaicapp.com", "ONO AI"/"Onoai" at the *grouping* layer, not just the fuzzy matcher. |
| Role-aware application match | `find_application_for_company` | When one company has 2+ live applications, prefer the row whose role tokens overlap the email's `extracted_role` (today: newest wins silently). |

These are execution-grade and could land as one small PR; they are listed here
because every later section builds on clean grouping.

---

### 3.1 Interview rounds inside a stage (items: multi-stage tracking + "multiple asks, same company")

**Problem.** `ApplicationStatus` is deliberately coarse (six values drive the
board, the KPIs, and the forward-only state machine). Real processes have 2–6
rounds inside `RECRUITER_SCREEN`+`ONSITE_LOOP`, and the owner often learns the
whole plan during the recruiter screen ("HM chat → take-home → system design →
panel"). Emails sometimes name the round; recruiter notes usually do.

**Options.**

| Option | Capability | Cost | Risk | Maintenance | Lock-in |
|---|---|---|---|---|---|
| A. Widen `ApplicationStatus` (add TECH_SCREEN, SYSTEM_DESIGN, …) | Low — one linear ladder can't express branching/parallel rounds | Medium (enum migration, every KPI/board/template touched) | **High** — breaks state machine, KPI buckets, drag-drop; real processes aren't linear | High | High (enum values are stable contracts) |
| B. JSONB `interview_plan` blob on Application | Medium — cheap to add, LLM fills it | Low | Medium — schemaless drift, hard to query ("how many system-design rounds this month?"), invisible to timeline | Medium | Low |
| C. **First-class `InterviewRound` table** (recommended) | High — rounds are queryable, link to the emails/calendar events that evidenced them, render as sub-timeline | Medium (one table + one panel + extractor wiring) | Low — stage machine untouched; rounds are *within* a stage | Low | Low |
| D. Generic "process graph" engine (configurable stage DAGs) | Highest | **Very high** | High — massive over-engineering for a single-user tracker | High | High |

**Recommendation: C.** Rounds become an entity; the six-stage pipeline stays
the contract for board/KPIs (a round never *is* a stage — it *evidences* one).

```
InterviewRound
  id, user_id, application_id (FK, CASCADE)
  round_no        int            — display order
  kind            enum: recruiter_screen | technical_screen | take_home |
                        system_design | hiring_manager | panel_onsite |
                        team_match | other
  title           str            — free text ("Virtual System Design Exercise")
  state           enum: planned | scheduled | completed | cancelled
  scheduled_at    timestamptz?   — from email/calendar when known
  outcome         enum?: passed | failed | pending
  source          enum: email | calendar | notes | manual
  email_message_id / calendar_event_id  (nullable evidence links)
  notes           text?
```

**How rounds get created (three producers, one consumer):**

1. **Email** — the classifier prompt gains `round_kind` (nullable, same
   vocabulary). An `interview_request` with a `round_kind` upserts a round on
   the linked application (upsert key: application + kind + scheduled_at-date,
   so the Camber "technical screen" and "system design" emails become two
   rounds, and three reminders about one round stay one round). This directly
   answers the "multiple asks for a single company" item: same application,
   next round — never a second application or a second detected process.
2. **Recruiter notes → process map** (the owner's explicit ask). A "Parse
   interview plan" action on the application detail slide-over: owner pastes
   or writes their recruiter-screen notes into the existing notes field →
   one LLM call extracts the *expected* rounds → rows created as
   `state=planned`. From then on, emails/calendar check them off
   (`planned → scheduled → completed`). The notes stay the human-readable
   source; the rounds are the structured projection. Never auto-parse notes
   on save — parsing is an explicit button (notes may contain anything).
3. **Calendar** — `calendar_sync` already fuzzy-matches events to
   applications; a matched event whose title looks like a round
   (interview/screen/design/panel) upserts `state=scheduled` with the event
   link.

**Stage derivation stays downstream:** a `completed` round of kind ≥
technical_screen implies `ONSITE_LOOP` via the existing stage-aware mapper —
rounds feed the same `update_status` path with `trigger=AUTO_FROM_EMAIL`.

**UI:** application slide-over gets a "Rounds" section (ordered checklist:
done/scheduled/planned with dates + evidence links); the board card gets a
compact `2/5 · system design` chip when rounds exist. Detected-process panel
rows show the round name when the email named one.

---

### 3.2 Abandoned / ghosted processes (silence as a signal)

**Problem.** The pipeline is purely event-driven; a company that stops
replying leaves a card on the board forever. `ClosedReason.GHOSTED` already
exists but nothing ever sets it.

**Options.**

| Option | Capability | Cost | Risk | Maintenance |
|---|---|---|---|---|
| A. Manual only (status quo) | — | — | Board rots; KPIs overstate active pipeline | — |
| B. **Staleness sweep + confirm-first nudge** (recommended) | Detects silence, keeps human on the trigger | Low (one scheduler job + one banner reusing the detected-process panel pattern) | Low — nothing closes without a click | Low |
| C. Full auto-close after N days | Hands-off | Low | **Medium-high** — long-latency companies (4–8 weeks is common) get killed; violates asymmetric autonomy (close = destructive-ish) | Low |

**Recommendation: B, with C as an opt-in setting.**

- Derive `last_signal_at` per application from the AppEvent log (max of
  status changes, EMAIL_RECEIVED, calendar matches, outreach sends, manual
  notes) — computed, not a new column, so it can never drift from the truth.
- Weekly scheduler job (`tracking.staleness_sweep`) buckets active
  applications: **quiet** (> 14d), **stale** (> 30d). Thresholds live in
  Settings (`staleness_quiet_days`, `staleness_stale_days`).
- UI: stale applications get an amber "no signal for N d" chip on the card,
  and a "Going quiet" strip on Tracking offering per row:
  **Mark ghosted** (→ `CLOSED/ghosted`, one click), **Nudge** (deep-link into
  the existing outreach draft flow), **Snooze 2w** (stamps a
  `staleness_snoozed_until`; JSONB `submission_artifacts` slot — no migration).
- Optional Settings toggle `auto_close_ghosted_after_days` (default off): when
  set, the sweep closes anything past the threshold with
  `trigger=CLEANUP_STALE` and a toast/notification — explicit opt-in to
  automation, mirroring the auto-apply consent pattern.
- KPI note: ghosted closes are already excluded from offer/interview rates by
  `closed_reason`; the sweep makes the "response rate" honest rather than
  changing its formula.

---

### 3.3 Agency / staffing / platform senders (items: incorrect naming + "should we even track agencies?")

**Problem.** "Company" extraction assumes the counterparty is the employer.
Agency recruiters break that assumption three ways: (a) the agency name gets
extracted as the company (TriEdge, Camo People), (b) the *end-client* is the
real process (G2i placing at a client; Camo People coordinating Ripple prep —
note: that email correctly extracted "Ripple" because the prompt says employer,
but only because the body named Ripple), (c) some are not processes at all
(RiseSmart is Intuit-side outplacement).

**The owner's instinct — "we might not want to track the agency ones" — is
right, with one refinement:** the *agency* is never the process, but an agency
email can still evidence a real process **at a named end-client**. So the rule
should be: track the end-client when one is identifiable; otherwise park the
email in a visible-but-collapsed group instead of promoting it to a detected
process. Parking rather than deleting matters because a G2i assessment can be
the first step of a real placement — silently dropping it would recreate the
"tracking is dead" failure mode this pipeline just escaped.

**Mechanisms, layered (recommend all three — they fail independently):**

1. **LLM sender-type extraction** (default judgment): classifier schema gains
   `sender_type: employer | ats | agency_recruiter | platform | outplacement |
   other` and `end_client: str | null` ("the company the agency is hiring
   FOR, if named"). Process detection then keys on
   `end_client or (company when sender_type == employer)`; `agency_recruiter`
   emails with no end-client group under a collapsed "Agencies & platforms"
   section of the panel — never auto-tracked, never auto-suggested.
2. **User flags as ground truth** (the "how can I flag it myself" ask): a new
   `SenderRule` table — `user_id, matcher (domain | company-key), value,
   treatment (agency | ignore | employer), created_from_message_id`. Panel
   rows and the email log get a "Flag sender…" action (Agency / Not
   job-related / Actually an employer). Rules are checked *before* the LLM
   result is applied, so a flag permanently overrides model judgment for that
   domain — deterministic, auditable, and reversible in Settings → Email.
3. **Seed heuristics**: a small static list of known staffing/outplacement
   domains (g2i.co, risesmart.com, camopeople.com, hired.com, …) ships as
   default `SenderRule` seeds the user can delete.

The precedence order is the point: **user rule > deterministic seed > LLM
guess** — the same perception-vs-policy split as the rest of the pipeline.

---

### 3.4 Mislabeled items: correction affordances + never-twice (item: ByteDance/Camber still "Interview Stage" after rejection)

**Diagnosis first.** Post-mortem on the two known cases (queryable today):
either the rejection email classified as `follow_up`/`other`, or it extracted
a company variant that grouped separately from the interview emails
(canonicalization, § 3.0, fixes the second cause). The plan assumes both
causes occur and addresses each.

**Correct-the-instance (UI affordances, all writing through existing seams):**

| Surface | Affordance | Effect |
|---|---|---|
| Detected-process row | "Wrong stage?" → inline picker | Overrides the derived stage for the group (stored on the messages' group via a `stage_override` on track; if already tracked, just drag the card — already supported) |
| Email log row (thread view) | "Reclassify as…" (six labels) | Sets `classification`, `auto_classified=False`, stamps a **`ClassificationCorrection`** row, re-runs the post-classify dispatch (link + transition) for that message |
| Detected-process row | "Merge into…" (company picker) | Creates a **`CompanyAlias`** (`alias_key → canonical_key`) used by grouping + matching forever after; relinks the group's messages |
| Application | "Unlink email" on a linked thread | Clears `application_id`, stamps correction — fixes wrong auto-links |

**Never-twice (the feedback loop):**

1. **`ClassificationCorrection` table** — `message_id, user_id,
   from_classification, to_classification, from_company, to_company,
   corrected_at`. Small, append-only. This is the system's labeled dataset;
   everything below consumes it.
2. **Few-shot injection**: `classify_email` prompt gains an
   "Owner corrections — follow these precedents" block built from the K most
   recent corrections whose sender-domain or subject-shape matches the email
   being classified (K≈5, snippet-truncated, so prompt cost stays bounded).
   This is per-user personalization *without training anything*.
3. **Regression evals**: corrections double as golden cases. An env-gated
   pytest (`NAAVIK_EVAL_LLM=1`) replays the correction set against the live
   prompt and reports accuracy — run before merging any prompt change, so
   prompt "improvements" can't silently regress on exactly the emails the
   owner already had to fix once.
4. **Rejection guard for groups**: when a group/application contains BOTH
   interview signals and a later rejection-shaped email that classified
   `follow_up`/`other`, flag the group with a "possible rejection — confirm?"
   chip instead of trusting either label. Cheap heuristic (regex on
   "not moving forward", "other candidates", "position has been filled")
   applied *only* as a tiebreaker prompt to the human — it never flips state
   itself.

---

### 3.5 Should we train our own ML model? (honest answer: not yet, probably never for n=1)

| Option | Quality | Cost/msg | Latency | Privacy | Build+maintain |
|---|---|---|---|---|---|
| A. Hosted small LLM (today: gpt-5.4-mini via tracked_call) | High, zero-shot handles novel templates | ~$0.0005–0.002 | ~1–2s | Snippet leaves machine (Ollama already supported as local alternative) | **None** |
| B. Fine-tuned local classifier (SetFit / DistilBERT) | Good on seen patterns, brittle on drift; separate NER model needed for company/role/stage extraction | ~0 | ~10ms | Fully local | **High**: labeling 1–5k examples, training pipeline, eval, re-training as ATS templates change; extraction quality drops hardest |
| C. **Hybrid cascade** (recommended *future* direction) — rules → correction-kNN via pgvector → LLM only on misses | ≥ A on seen mail (corrections are exact precedent), = A on novel | ~60–80% fewer LLM calls | Fast path ~ms | Mostly local | Low-medium: embeddings already in the stack (pgvector, `embed` method on providers) |

**Recommendation.** At ~10–40 job-related emails/day the LLM spend is cents
per month — the bottleneck is *label quality on edge cases*, not cost or
throughput, and a custom model makes edge cases worse (it can only know
patterns it was trained on, and one user generates too little data to train
on). The pragmatic ladder:

1. Now: § 3.4's corrections + few-shot (personalization without training).
2. When correction volume justifies it: **C** — embed each incoming
   (sender-domain + subject + snippet), kNN against embedded corrected
   examples; ≥0.92 cosine similarity with a corrected/confirmed label →
   reuse that label without an LLM call. The corrections table *is* the
   training set; there is just no training step to babysit.
3. B only if Naavik ever becomes multi-tenant SaaS where per-message LLM cost
   multiplies across users — file under Phase-3+, out of scope here.

---

### 3.6 Never mark mail as read (item F — this is a live bug)

`_fetch_imap_messages` issues `UID FETCH <uid> (RFC822)`; per RFC 3501 a
non-PEEK body fetch sets `\Seen`. Every sync since plan 90 has been marking
the owner's unread mail read. Fix (in § 3.0 immediate batch):

- `client.select("INBOX", readonly=True)` — EXAMINE semantics: the server
  rejects *all* flag mutations for the session (belt).
- `client.uid("FETCH", uid, "(BODY.PEEK[])")` — side-effect-free fetch even
  if a future code path opens the mailbox read-write (suspenders).
- Fake-client test asserting the fetch command contains `BODY.PEEK` and the
  select is readonly; plus a comment pinning WHY (this exact regression is
  invisible in tests otherwise — fakes don't track flags).

No design alternatives worth a matrix here; PEEK is the standard answer.

---

### 3.7 Manual tracking by URL — "paste a link, get the whole process"

**Problem.** The manual-entry modal treats the URL as an optional metadata
field and makes the human do the machine's job (typing company, role, and a
description that the scoring pipeline then reads). Meanwhile
`inference._scrape_posting_url` already implements exactly the desired flow —
SSRF-guarded fetch → Crawl4AI → LLM `extract_job` enrichment → `upsert_job` —
but only email receipts can reach it. And a manually tracked job has no way
to say "I already applied three weeks ago and I'm mid-interview", so it
enters the pipeline as a raw library row instead of where it actually stands.

**Options for the parse path.**

| Option | Capability | Cost | Risk | Maintenance |
|---|---|---|---|---|
| A. Keep manual typing, add "fetch" button that only fills the form | Low — human still curates every field | Low | Low | Low |
| B. **URL-first modal: paste → full add-by-URL pipeline → editable preview → confirm** (recommended) | High — same extraction quality as Discover; human corrects instead of transcribes | Medium (one route + modal rework; pipeline exists) | Low — preview step catches bad extractions before anything persists | Low |
| C. Fire-and-forget: paste → job appears when scrape finishes | High + zero friction | Medium | Medium — silent failures (JS-walled postings, logins) leave ghosts; no correction point | Medium |

**Recommendation: B.** Modal becomes URL-first: paste → the existing headless
pipeline runs (spinner via hx-indicator; typical 3–8s) → an editable preview
renders (company, role, location, description, salary, board — all
LLM-extracted, all correctable) → confirm. The typed-fields path stays as the
fallback tab for postings that can't be fetched (auth walls, PDFs). Scoring
and JD enrichment run exactly as for scraped jobs — "it does our whole
process" falls out of reusing `upsert_job` + the existing score-pending cron.

**Initial state selection (the "applied / not applied / todo / interview"
ask).** The confirm step gains one control — "Where does this stand?":

| Choice | Effect (all through existing seams) |
|---|---|
| **To review** (default) | `queue_state=unswiped` — lands in Discover like any scraped job |
| **Todo / saved** | `queue_state=saved` |
| **Applied** | Application created (`status=APPLIED`, `applied_at` date picker defaulting today), job `queue_state=applied` — mirrors `_create_inferred_application` |
| **Recruiter screen / Interview stage / Offer** | Application created at that status with the back-dated APPLIED → stage AppEvent trail, exactly like `processes.track_process` derives it — so KPIs and the timeline stay honest |

That last row reuses the trail-writing pattern from `track_process` (§ plan
context) rather than inventing a second way to create mid-stage applications.
Email linking then works automatically: the company now exists in the DB, so
the classifier's company-match links future (and re-classified past) mail.

### 3.8 Manual status updates vs email signal — precedence contract

**Problem.** Two writers, one field. Today an email-driven forward transition
auto-applies no matter what the human last did; the owner's requirement:
**manual should override**.

**Options.**

| Option | Capability | Cost | Risk | Maintenance |
|---|---|---|---|---|
| A. Last-writer-wins (status quo) | — | — | Email can silently undo a deliberate human decision minutes after it was made | — |
| B. Hard lock: any manual change permanently disables email transitions for that application | Simple mental model | Low | Tracking goes half-dead exactly on the applications the owner touches most; the pipeline's core value (auto-advance) silently evaporates | Low |
| C. **Provenance-aware precedence** (recommended): manual moves *pin* the status; email may still *suggest*, and may auto-apply only strictly-forward moves that don't contradict the pin | Keeps automation where it helps, human always wins conflicts | Medium | Low — worst case is one extra confirmation click | Low |

**Recommendation: C, with a precise contract:**

1. Every status write already records its `trigger` in the AppEvent payload —
   provenance exists; no new column needed for detection. Policy reads "was
   the latest STATUS_CHANGE manual?"
2. **Backward manual moves pin.** If the owner drags a card backward (e.g.
   email auto-advanced to Interview Stage, owner says "no, still recruiter
   screen"), that pair (application, rejected-status) is remembered — the
   email pipeline will not re-apply a transition *to the same status* the
   human just reverted; it downgrades to a banner suggestion. Stored as
   `submission_artifacts["status_pin"] = {rejected: "ONSITE_LOOP", at: …}` —
   JSONB slot, no migration.
3. **Forward manual moves don't block better news.** Owner sets Recruiter
   Screen manually → an OFFER email still auto-applies (it's strictly
   forward and uncontradicted). This is why B is wrong: overriding must mean
   "my correction sticks", not "automation off".
4. **CLOSED set manually is absolute** — any application the human closed
   never receives auto transitions again, only suggestions (reopening is a
   human act; this also covers "I withdrew").
5. Every suppressed auto-transition still emits `EMAIL_STATUS_SUGGESTED`
   (`applied: false`), so nothing is silently swallowed — the card shows the
   pending suggestion chip and the timeline records that the email arrived.

This is the same asymmetric-autonomy principle already in the pipeline,
extended with one more asymmetry: **human intent outranks machine inference,
in both directions, forever-per-decision rather than forever-per-application.**

### 3.9 Email chain on the tracking card

**Problem.** The application slide-over shows the status timeline but not the
correspondence that produced it; verifying "why is this at Interview Stage?"
means leaving the app for Gmail.

**Proposal (no options matrix — this is a straightforward read-surface):**
a "Conversation" section on `_application_detail.html`, fed by the existing
`email.list_threads_for_application` seam (already IDOR-safe, already
shimmed in tests):

- Threads render newest-first: sender, decoded subject, classification chip
  (colored by the existing vocabulary), relative date, 240-char snippet on
  expand — snippet-only by design; the privacy contract (no bodies at rest)
  is unchanged, and the row deep-links to the provider via the message id
  when the owner needs the full text.
- Suggestion state renders inline: an email whose transition auto-applied
  shows "→ Interview Stage · auto"; a pending rejection suggestion shows the
  Apply/Dismiss pair (same buttons the banner uses — one component, two
  mounts).
- Reclassify affordance from § 3.4 mounts here too — the chain is the natural
  place to spot "that rejection got tagged follow-up".
- Interleaving option: rather than a separate section, thread events can
  merge into the existing status timeline (they're both AppEvent-backed).
  Recommended: keep **separate sections** — the timeline answers "what
  changed", the conversation answers "what did they say"; interleaving buries
  status flips under reminder emails. Revisit if the card feels fragmented.

### 3.10 Cross-source identity: scraper re-finds a tracked job

**Problem.** A job tracked from email (stub row: `source=email`,
`url=manual://…`, one-sentence description) or manual entry can reappear via
LinkedIn/Greenhouse scraping as a *different* Job row. Tier-3 dedup
(`services/jobs/dedup.py`) already catches the pair cross-source (trigram
company 0.6 + role 0.4, threshold 88) — but it only *shadows* the new row
(`duplicate_of_id`), so the canonical tracked row keeps its stub data and the
fresh JD/salary/URL sit hidden in the shadow.

**Options.**

| Option | Capability | Cost | Risk | Maintenance |
|---|---|---|---|---|
| A. Status quo (shadow only) | Dedup'd in lists, but tracked row stays a stub; scoring/tailoring read the stub description | — | Docs generated from a one-line description | — |
| B. Repoint: delete stub, move Application FK to the scraped row | Clean single row | Medium | **High** — breaks evidence links (email_message.application_id fine, but round/message links reference the old job via application; job_id churn ripples into events, embeddings, generated docs) | Medium |
| C. **Enrichment merge into the canonical row** (recommended): keep the tracked row's identity, copy the scraped row's substance onto it, shadow the scraped row | Tracked row becomes fully scored/tailorable; every FK stays stable | Medium (one merge function + tests) | Low — field-level merge is append/upgrade-only | Low |

**Recommendation: C.** Identity is the row the human's history hangs off;
substance is whatever the freshest source saw. Merge contract
(`jobs.dedup.enrich_canonical(canonical, shadow)`), applied whenever
`find_duplicate` shadows a row whose canonical is `source ∈ {email, manual}`
(and by the nightly backfill sweep for pairs that already exist):

| Field | Rule |
|---|---|
| `url`, `url_type` | Replace when canonical's is a `manual://` stub; keep otherwise |
| `description` / `description_html` | Replace when canonical's is the receipt/process stub text; keep human-typed manual descriptions (marker: stub descriptions are machine-written with a known prefix) |
| `salary_min/max`, `posted_at`, `location`, `board`, `criteria`, `skills_required`, `visa_restrictions` | Fill-if-empty |
| `apply_url` + resolution fields | Take scraped row's if canonical unresolved |
| `score`, embeddings | Cleared → re-queued (`score.recompute` picks it up) since the description changed materially |
| `source`, `external_id`, timestamps, `queue_state`, Application links | **Never touched** — identity + human state |

An `AppEvent` (`kind=NOTE_ADDED`, actor `job_dedup_merge`) records the merge
on the linked application so the timeline explains why docs went stale. The
merge is idempotent (re-running with the same shadow is a no-op) and one-hop
(shadows are never merge sources twice), matching the existing dedup-graph
invariant.

Edge case worth pinning in tests: two live applications at the same company
for *different roles* must not merge (role weight 0.4 + threshold 88 already
guards this; add a characterization test with "Senior SWE" vs "Staff PM").

### 3.11 Data-model & migration summary (if the whole plan is approved)

New tables: `interview_round`, `sender_rule`, `classification_correction`,
`company_alias` — all small, all FK'd to user + evidence rows, all additive
(no changes to existing columns; zero risk to the 0041 data). One migration,
`0042_tracking_v2`. Classifier schema gains `round_kind`, `sender_type`,
`end_client` (prompt + Pydantic only — extraction columns already exist for
company/role/stage; new facts land in the same pattern:
`extracted_round_kind`, `extracted_sender_type`, `extracted_end_client` on
`email_message`).

§§ 3.7–3.10 deliberately require **no schema changes**: the manual-URL flow
reuses `upsert_job` + Application creation, the status pin lives in the
`submission_artifacts` JSONB slot, the email chain is a read surface over
existing tables, and the enrichment merge writes existing Job columns.

### 3.12 Suggested build sequence

| Slice | Contents | Size |
|---|---|---|
| 95a | § 3.0 immediate fixes + § 3.6 PEEK/readonly | S — one PR |
| 95b | Corrections: `ClassificationCorrection` + reclassify/unlink/merge affordances + `CompanyAlias` (§ 3.4 items 1, UI, aliases) | M |
| 95c | Sender rules + LLM sender_type/end_client + collapsed agency group (§ 3.3) | M |
| 95d | `InterviewRound` + email/round upsert + notes→plan parser + rounds UI (§ 3.1) | L |
| 95e | Staleness sweep + going-quiet strip (§ 3.2) | S–M |
| 95f | Few-shot injection + eval harness (§ 3.4 items 2–3) | M |
| 95g | (deferred) embedding cascade (§ 3.5-C) | M — only if volume/cost warrants |
| 95h | Manual precedence contract + status pin (§ 3.8) — small, high-trust win | S |
| 95i | Email chain on the card (§ 3.9) | S–M |
| 95j | URL-first manual tracking + initial-state selection (§ 3.7) | M |
| 95k | Enrichment merge on cross-source dedup (§ 3.10) | M |

Ordering rationale: 95a unblocks correct grouping for everything; 95b creates
the corrections substrate that 95c/95f consume; rounds (95d) is the biggest
UX win but depends on nothing except 95a, so it can be pulled forward if the
owner prefers. 95h should ride early (it's the trust contract that makes the
rest of the automation acceptable); 95i pairs naturally with 95b since the
chain is where reclassify affordances mount; 95k depends only on 95a's
canonicalization.

### 3.13 Risks

| Risk | Mitigation |
|---|---|
| Round upsert duplicates rounds from reworded reminder emails | Upsert key includes kind + date; `round_no` display-only; merge affordance on the rounds list |
| Canonicalization over-merges distinct companies ("Stripe" / "Stripe Press") | Canonical keys only *group*; Track-it confirm screen shows the member emails; alias table lets the user split/merge explicitly |
| Few-shot block bloats the classify prompt | Cap K=5, snippet-truncate exemplars, count tokens in eval harness |
| Staleness sweep nags about genuinely slow processes | Snooze affordance + per-user thresholds; auto-close strictly opt-in |
| Agency end-client extraction invents clients | `end_client` requires the name to appear verbatim in subject/snippet (deterministic post-check before use) |
| readonly EXAMINE breaks providers that need SELECT | Feature-flag fallback to SELECT + PEEK (PEEK alone already prevents the flag write) |
| Add-by-URL scrape fails on walled postings (LinkedIn auth, Workday JS) | Preview step surfaces the failure; typed-fields fallback tab always available; never persist a half-extracted row without confirm |
| Status pin logic confuses "why didn't it advance?" | Suppressed transitions always render as suggestion chips + timeline entries — the system explains itself instead of going quiet |
| Enrichment merge overwrites human-typed manual descriptions | Stub-marker check: only machine-written receipt/process descriptions are replaceable; manual text is never touched |
| Mid-stage manual creation skews funnel KPIs (application "reaches" a stage the pipeline never observed) | Back-dated AppEvent trail is written exactly as `track_process` does, so KPI queries see the same shape; characterization test pins it |

## 4. Open questions

1. Staleness defaults: 14d quiet / 30d stale acceptable? Should "stale" also
   consider stage (e.g., post-onsite silence matters faster than post-apply)?
2. Rounds vocabulary: is the 8-kind enum in § 3.1 enough, or keep `kind`
   free-text with suggested values?
3. Should agency-parked emails ever notify (Discord/Telegram), or stay
   silent until visited?
4. For § 3.4's rejection guard: comfortable with regex heuristics flagging
   "possible rejection", or LLM-only?
5. Few-shot corrections include email snippets in future prompts — fine for
   cloud providers, or gate that feature to local/Ollama sessions?
6. Manual add-by-URL: should "Applied" be the default initial state instead
   of "To review"? (You mostly add jobs you already applied to — but
   defaulting to Applied would mis-file pasted jobs you're merely eyeing.)
7. Status pin scope: is per-decision pinning (§ 3.8.2 — remembers the exact
   rejected status) right, or do you want a visible per-application
   "automation off" toggle as well?
8. Email chain: snippet-only rendering (privacy contract) with a deep-link
   out to Gmail — sufficient, or is this the moment to revisit the
   full-body-opt-in follow-up (0.5.0.05a)?

## 5. Approval checklist

- [ ] § 3.0 immediate fixes (canonicalization, role-aware match, PEEK/readonly) approved to build now
- [ ] `InterviewRound` model + three producers (email / notes-parse / calendar) — approach approved
- [ ] Staleness: confirm-first nudge (auto-close opt-in only) — approved
- [ ] Agency handling: end-client-or-park rule + `SenderRule` user flags — approved
- [ ] Corrections loop: correction table + affordances + few-shot + eval harness — approved
- [ ] ML stance: no custom model; embedding cascade deferred — agreed
- [ ] Manual tracking: URL-first modal + initial-state selection (with back-dated event trail) — approved
- [ ] Manual-over-email precedence contract (§ 3.8: pin on backward moves, forward news still flows, manual CLOSED absolute) — approved
- [ ] Email chain section on the application card (snippet-only) — approved
- [ ] Cross-source dedup: enrichment merge into the tracked canonical row — approved
- [ ] Build sequence 95a→95k (95g deferred) — agreed
