# Handoff — Tracking v3: execute plan 96, session 2 (96d → 96f + close-out)

You are CONTINUING an execution run in the Naavik repo. Session 1
(2026-07-08) landed **96a, 96b, and 96c1–c3** on `main` with green gates
(ruff + full pytest, 3577 passing at hand-off) and live Playwright QA per
slice. Your job: implement **96d, 96e, 96f**, then the plan close-out —
slice by slice, in order, one commit each, green gates per slice. All 15
owner decisions are resolved (plan § 4); do not relitigate them. If
implementation surfaces a genuine preference fork, use AskUserQuestion
(owner's standing instruction: ask even in autonomous mode).

## 1. Read first, in order

1. `CLAUDE.md` — repo conventions (Nix-first, service-package seams,
   llm_tracker wrap, fragment granularity, no PRs / no push, commit
   locally on `main`).
2. `docs/plans/96-tracking-v3-email-intelligence-job-surface.md` — THE
   contract. `Status:` is IN EXECUTION; § 5.4–5.6 are your slices, § 8 the
   files/tests/acceptance table, § 4 the owner's decisions, and the
   trailing `## Deviations from plan (running)` section is where you
   APPEND further deviations as they happen.
3. `docs/design/TRACKING_PIPELINE.md` — the pipeline you are extending
   (you will amend it at close-out).

## 2. What session 1 shipped (all on `main` — build on it, don't redo it)

| Commit | Slice | What landed |
|---|---|---|
| c7f8ebf | 96a | Drag rewire (base.js shared Sortable group + onEnd JSON fetch + closed-reason dialog + revert-on-error; move route 422/409s); pending-suggestions strip + amber card chip (`services.email.list_pending_suggestions`); CLOSED in the Track-it picker (+ `closed_reason` passthrough in `track_process`); receipt-on-DRAFT auto-advance (`inference._advance_draft_on_receipt`, pin-respecting); classify-tick stall alert (`scheduler.jobs._alert_on_classify_stall`) + commit-boundary characterization test; round mark-done is the row's state icon |
| d50d829 | 96b | `/emails` log page + `/_fragments/email/log` (keyset pagination on `(received_at, id)`, 50/page, load-more appends); filters (classification incl. `pending`, link state, account, date range, sender search); link-state chips (linked → company / detected / parked / dismissed); per-email signal detail component `components/email/_signal_detail.html` (extraction chips + transition outcome incl. `suppressed_by_pin` from event payloads); row actions (reclassify, flag sender, provider link, body PEEK); sidebar "Emails" entry; unclassified-backlog badge |
| 4acfa72 | 96c1 | Migration **0046** `email_thread.job_id` (+ backfill, applied to the dev DB — 163/533 threads linked); `services.email.service.link_thread`/`unlink_thread_links` used at every link site; `ui/job_surface_ctx.build_job_surface_ctx` (resolves by job OR application, all applications incl. soft-deleted re-application history, view derivation pre/post + override, `unlinked_job_threads`) |
| ac266ee | 96c2 | `pages/jobs/_job_surface.html` (ONE body), page mount `GET /jobs/{id}?application=&view=`, modal mounts `GET /_modal/job/{id}` + `GET /_modal/application/{id}`, `/_fragments/job-surface/*` for tab/application switches; `components/jobs/_surface_conversation.html` (collapsible threads, expand/collapse-all, signal detail, suggestion actions); render-equivalence test pins page ≡ modal body |
| 9de68db | 96c3 | Slide-over RETIRED (`_application_detail.html`, `_conversation_section.html`, old `job_detail.html` deleted); cards/list rows open `/_modal/application/{id}` and push `/jobs/{job_id}?application={id}`; `/tracking/{id}` 302s to the surface page (job-less apps render tracking with the modal open); board-card hierarchy pass (status pill + ≤2 chips + `+N` overflow); bullet-overrides extracted to `_bullet_overrides_section.html` (the PUT swap unit); legacy tests migrated |

Also done in session 1 (don't redo):
- Migrations are now at **0046**. 96d owns **0047** (`email_invite` +
  `interview_round.invite_uid`).
- App 63 (Path AI) was advanced DRAFT → APPLIED via a one-shot run of the
  production advance path (its receipt predated the 96a code).
- The DragTest QA application (id 111) was created and fully deleted.
- Deviations 1–11 are already recorded in the plan's
  `## Deviations from plan (running)` section.

## 3. Remaining slices (plan § 5.4–5.6, § 8 rows 96d–96f)

| Order | Slice | One-line scope | Commit prefix |
|---|---|---|---|
| 1 | **96d** | Migration 0047 (`email_invite` table + `interview_round.invite_uid`); `services/email/invites.py` — parse `text/calendar` MIME + `.ics` attachments from the already-fetched RFC822 via the **`icalendar`** library (new dep: pyproject AND flake — `nix build` must stay green); pure `resolve_final` supersedence fn (max-sequence non-cancelled REQUEST per (ics_uid, recurrence_id); CANCEL at ≥ sequence kills the chain) with vendor-fixture tests; invite→round upsert by `ics_uid` (reschedules MOVE `scheduled_at`, cancellation reverts to `planned`); past-due scheduled rounds complete on the existing 45-min `tracking.sync_calendars` cron (deterministic rider, no new cron); one-shot backfill task over stored `imap_uid` mail (PEEK, bounded) | `feat(tracking-v3/96d):` |
| 2 | **96e** | `services/email/reconcile.py` — **event-driven, per-application** (owner #13, NO standing cron): `reconcile_application` + group variant, triggered from `_post_classify_dispatch` (batch-dedup per tick), invite ingest, corrections, suggestion-apply; deterministic core (re-group with aliases/rules, re-fold timeline, re-resolve invite chains, diff rounds/status) + thread-level LLM pass for triggering threads only (`llm/prompts/classify_thread.py`, `tracked_call`, schema `{process_stage, rounds, rejection, needs_scheduling}`); writes ONLY via 95d round upserts + `update_status` forward-only with new `StatusChangeTrigger.RECONCILED`; § 3.8 pin suppression → suggestions; CLOSED absolute; idempotence pinned (no new evidence → zero writes) | `feat(tracking-v3/96e):` |
| 3 | **96f** | Classifier schema gains `action_needed: none\|send_availability\|pick_slot\|confirm_time` (+ deterministic keyword post-check like `end_client`); `services/scheduling/` slot engine (pure fn on zoneinfo, synced events + final invites block, working hours/tz from two new Settings fields `scheduling_timezone`/`scheduling_window`, DST unit matrix); owner-voice draft via `llm/prompts/draft_scheduling_reply.py` (Copy + Gmail compose deep-link `view=cm`; nothing persists but an AppEvent); "Needs scheduling" strip on Tracking. **Never sends** — no smtplib, no send scopes, static no-send guard test | `feat(tracking-v3/96f):` |
| 4 | **close-out** | Update `docs/design/TRACKING_PIPELINE.md` (invites + supersedence, event-driven reconciler contract, scheduling posture draft-only/read-only, email log, job surface, body-posture amendment: "structured invite metadata at rest, owner-approved 2026-07-08"); flip plan 96 `Status:` to EXECUTED, finalize the deviations section (must stay non-empty), move plan to `docs/plans/archive/`; move `docs/prompts/96-tracking-v3-execution.md` AND this prompt to `docs/prompts/archive/`; shut down the dev stack; hand-back summary | `docs(...)` |

Gates per slice, before its commit: `ruff check . && ruff format --check .`
+ `uv run pytest` green + Playwright QA against the live dev stack for
UI-touching slices. § 8's acceptance column is the manual QA script.

## 4. Practical notes (hard-won across both sessions)

- **Dev stack:** `nix run .#dev` (Postgres 5433, app 8003, owner is
  **user_id=2**). Check `ss -tln | grep -E ':8003|:5433'` for a half-dead
  stack first. FastAPI hot-reloads on edit. Shut the stack down when done.
- **Auth for QA:** mint a JWT via `services.auth.tokens.issue_jwt_async`
  against the dev DB (user_id=2); CSRF is plain double-submit — set BOTH
  `naavik_session` and a `naavik_csrf` cookie and send the same value as
  `X-CSRF-Token`. A ready mint script pattern: run
  `issue_jwt_async(session, user_id=2, keep_signed_in=True)` with
  `DATABASE_URL=postgresql+asyncpg://naavik:password@127.0.0.1:5433/naavik`
  and `NAAVIK_DEBUG=1`, `sys.path.insert(0, "src")`.
- **Live acceptance fixtures in the dev DB** (do not mutate destructively):
  the four **Headway invite messages (msgs 573–576 → app 55)** are the 96d
  supersedence acceptance — one technical-screen round at the final
  invite's time; a reschedule moves it; a cancel reverts it. The Anthuria
  pending rejection (msg 546 → app 89) still pends if you need a
  suggestion fixture. The Google detected group derives CLOSED.
- **96d body source:** `store_body_excerpt` is ON for the owner's account
  (id 1, user_id 2) since 2026-07-08 — new mail carries a 2k excerpt;
  older mail has `imap_uid` for on-demand PEEK (the backfill's read path).
  Note invites need the RAW MIME (ICS parts), which the sync loop already
  fetches per message — parse at sync time; the backfill PEEKs by UID.
- **sqlite test substrate quirks** (all existing test files show the
  pattern): register JSONB/ARRAY compile shims, drop CheckConstraints,
  and drop `alive_unique`/gin indexes; the shadow classes in
  `db/sample_data_models.py` may lack newer model fields — add with
  defaults if a ctx touches them. UI route tests use
  `@pytest.mark.uses_sample_data_shims` + `naavik_session=fake-1`; direct
  `session.get` bypasses shims — resolve via service seams (see
  `job_surface_ctx` for the pattern).
- **Playwright drag testing:** synthetic events don't trigger SortableJS —
  real gesture (hover card → `mouse.down()` on `.drag-handle` → ~12
  interpolated `mouse.move` steps → `mouse.up()`). The board's content is
  clipped by `max-w-7xl`: scroll the board's overflow container
  (`#tracking-main [class*=overflow-x-auto]`) before computing drop
  coordinates for far-right columns. `inner_text()` returns CSS-uppercased
  text — compare case-insensitively.
- **Never** point destructive tests at the dev DB; leave
  `NAAVIK_CHAIN_REPLAY_DB_URL` unset; running alembic by hand needs
  `NAAVIK_DEBUG=1`.
- **Git quirks:** stage explicit paths (bare `git add -A` gets denied) and
  use `git commit -F <file>` for multi-line messages. A markdown formatter
  reflows `docs/plans/*.md` tables on save — edit content, let it reflow.
- **96e integration points that already exist:** `_post_classify_dispatch`
  (classifier.py) is where per-message side-effects run — the reconciler
  trigger collects affected application ids per tick in
  `classify_unprocessed`/`scheduler.jobs.classify_emails`; corrections
  live in `services/email/corrections.py` (reclassify/unlink/merge/flag);
  suggestion-apply in `services/applications` (`apply_email_suggestion`).
  Round upserts: `services/applications/rounds.py` (upsert key
  application + kind + scheduled-date; 96d adds `invite_uid` as an
  additional evidence key on the same producer seam).
- **96f strip pattern:** copy the pending-suggestions strip
  (`components/tracking/_suggestions_strip.html` + its tracking.html
  mount + `build_tracking_ctx` wiring) — same panel family.

## 5. Done criteria (whole plan)

- 96d, 96e, 96f merged locally with green gates, one commit each.
- `docs/design/TRACKING_PIPELINE.md` updated as listed in § 3 row 4.
- Plan 96 `Status:` → EXECUTED, deviations finalized (non-empty), plan
  moved to `docs/plans/archive/`; both kickoff prompts moved to
  `docs/prompts/archive/`.
- Dev stack shut down; hand-back summary of what shipped, what deviated,
  and what the owner should look at first.
