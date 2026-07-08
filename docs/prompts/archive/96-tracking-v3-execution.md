---
Status: ACTIVE
Type: prompt (execution handoff — implement approved plan 96, slice by slice)
Authored: 2026-07-08
Predecessor: docs/prompts/archive/96-tracking-v3-planning.md (executed), docs/plans/96-tracking-v3-email-intelligence-job-surface.md (APPROVED rev 2)
---

# Handoff — Tracking v3: execute plan 96

You are starting an EXECUTION session in the Naavik repo. The previous
session diagnosed the v2 bugs live, resolved all 15 design decisions with
the owner, and produced an APPROVED plan. Your job: implement it, slice by
slice, in order, with green gates per slice. No open design questions
remain — but if implementation surfaces a genuine preference fork, use
AskUserQuestion rather than guessing (owner's standing instruction: ask
even in autonomous mode).

## 1. Read first, in order

1. `CLAUDE.md` — repo conventions (Nix-first, service-package seams,
   llm_tracker wrap, fragment granularity, no PRs / no push, commit
   locally on `main`).
2. `docs/plans/96-tracking-v3-email-intelligence-job-surface.md` — THE
   contract. § 5 is the design per slice, § 8 the files/tests/acceptance
   table, § 4 the owner's 15 resolved decisions (do not relitigate them).
3. `docs/design/TRACKING_PIPELINE.md` — the v2 pipeline you are extending.
4. Optional context: `docs/plans/archive/95-tracking-v2-…md`
   `## Deviations from plan` — how v2 actually landed.

## 2. State you inherit (all already on `main`)

- **Hotfix `2b867f3`** (`fix(tracking/96-pre)`) already fixed the B3
  classify crash loop and was live-verified: backlog drained, Path AI
  receipt links to application 63, Headway invites classified. Plan § 3.3
  documents it; do not redo it. 96a only carries the residual guards.
- **`store_body_excerpt` is ON** for the owner's email account (id 1,
  user_id 2) since 2026-07-08 — new mail carries a 2k excerpt; older mail
  has snippet only (and `imap_uid` for on-demand PEEK).
- Migrations are at `0045`. Plan assigns **0046** to `email_thread.job_id`
  (96c1) and **0047** to `email_invite` + `interview_round.invite_uid`
  (96d) — in that order, because the job surface was pulled forward.
- The dev stack is SHUT DOWN. Start it fresh (see § 4).

## 3. Execution order and gates

Slices, one commit each, prefix `feat(tracking-v3/96X):`
(`fix(...)` for 96a):

| Order | Slice | One-line scope |
|---|---|---|
| 1 | **96a** | Drag-and-drop rewire, suggestion chip + pending-suggestions strip, CLOSED in the Track-it picker, B3 residual guards, receipt-on-DRAFT advance, round-row mark-done |
| 2 | **96b** | `/emails` log page + per-email signal-detail component |
| 3 | **96c1–c3** | `email_thread.job_id` (0046) + `job_surface_ctx`; the job surface (one body, modal + `/jobs/{id}` mounts, pre/post-apply views); slide-over retirement + board-card refresh |
| 4 | **96d** | `email_invite` (0047), ICS MIME parsing, supersedence (`resolve_final`), invite→round integration, past-due rider on calendar sync, backfill |
| 5 | **96e** | Event-driven reconciler (`reconcile_application`, triggers in dispatch/invites/corrections/suggestion-apply) + thread-level LLM pass, `trigger=RECONCILED` |
| 6 | **96f** | Scheduling assistant: `action_needed` detection, slot engine, owner-voice draft, "Needs scheduling" strip. **Never sends mail** — no smtplib, no send scopes |

Gates per slice, before its commit: `ruff check . && ruff format --check .`
+ `uv run pytest` green + Playwright QA against the live dev stack for any
UI-touching slice. The § 8 acceptance column is the manual QA script.

Deviations discipline: the moment implementation diverges from the plan,
note what/why/impact; append all of them to the plan's
`## Deviations from plan` section at the end (it must not be empty —
real implementations always deviate somewhere).

## 4. Practical notes (hard-won in the planning session)

- **Dev stack:** `nix run .#dev` (Postgres 5433, app 8003, owner is
  **user_id=2**). Before starting, check nothing is already bound
  (`ss -tln | grep -E ':8003|:5433'`) — a half-dead stack with a stale
  `postmaster.pid` in `.naavik/db/` produced confusing bind errors last
  session. Shut the stack down when you finish.
- **Authenticated browser/curl sessions:** mint a JWT with
  `services.auth.issue_jwt_async` against the dev DB (see agent memory
  "reference-dev-session-mint"); CSRF is plain double-submit
  (`naavik_csrf` cookie + `X-CSRF-Token` header).
- **Playwright drag testing (96a):** synthetic events don't trigger
  SortableJS — use a real gesture: hover the card (the grip handle is
  `opacity-0` until `group-hover`), `mouse.down()` on `.drag-handle`,
  ~10 intermediate `mouse.move` steps into the target column, `mouse.up()`,
  then assert the card's column after a reload AND capture the
  `/api/v1/applications/move` request/response. The planning session's
  repro script shape is in plan § 3.1.
- **Live acceptance fixtures already in the dev DB** (do not mutate them
  destructively): Snorkel AI rejection suggestion pending (msg 475 →
  app 22) for the 96a strip/chip; the Google detected group derives CLOSED
  for the 96a picker test; Headway invites (msgs 573–576 → app 55) for
  96d's supersedence acceptance; Path AI (app 63) for receipt-on-DRAFT.
- **Never** point destructive tests at the dev DB; leave
  `NAAVIK_CHAIN_REPLAY_DB_URL` unset; running alembic by hand needs
  `NAAVIK_DEBUG=1`.
- **Git quirks:** stage explicit paths (bare `git add -A` gets denied) and
  use `git commit -F <file>` for multi-line messages.
- A markdown formatter reflows tables in `docs/plans/*.md` on save —
  don't fight the padding; edit content, let it reformat.
- New dependency in 96d: `icalendar` — add to `pyproject.toml` AND the
  nix flake so `nix build` stays green.

## 5. Done criteria

- All six slices merged locally with green gates, one commit each.
- `docs/design/TRACKING_PIPELINE.md` updated: invites + supersedence,
  event-driven reconciler contract, scheduling posture (draft-only,
  read-only scopes), email log, job surface, amended body-posture note
  (structured invite metadata at rest, owner-approved 2026-07-08).
- Plan 96 `Status:` flipped to EXECUTED with a non-empty
  `## Deviations from plan`, moved to `docs/plans/archive/`.
- This prompt + the plan's kickoff lineage moved to
  `docs/prompts/archive/`.
- Dev stack shut down; a short hand-back summary of what shipped, what
  deviated, and anything the owner should look at first.
