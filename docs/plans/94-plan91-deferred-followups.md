# Plan 94 — plan-91 deferred follow-ups: ownership rollout + data-model hardening

- **Type:** execution
- **Status:** DRAFT
- **Predecessor:** `docs/plans/91-full-codebase-refactor-audit.md` (its § Deviations
  deferred 5.6, 7.3, 7.4-schema-half; Open Q2 locked "defer 7.5, do 7.1–7.4 this
  round" — 7.1/7.2 shipped as 0038/0039). Plans 92–93 finished the layout, so the
  seam surfaces referenced here are the package `__init__`s.

## Slice A — 5.6: `get_owned_*` rollout (semantics-preserving)

The ~40 hand-rolled ownership checks reduce to: 4 per-file helpers
(`jobs._job_or_404`, `discover._job_or_404`, `discover._application_owned_or_404`,
`tracking._application_or_404`) + ~25 inline sites (api/applications.py ×7,
outreach.py ×7, discover.py ×5, tracking.py ×2, email.py ×2, + strays).

Design (locks in the plan-91 1.4 pattern):

- Shared plain-async helpers in `src/api/deps.py` — `owned_job_or_404`,
  `owned_application_or_404(..., allow_deleted=False)`, `owned_contact_or_404`,
  `owned_email_thread_or_404` — one implementation of the fetch + user_id + 404
  (IDOR → 404, never 403, no cross-user existence oracle).
- The `Depends()` forms (`get_owned_application`/`get_owned_contact`/`get_owned_bullet`)
  delegate to them. **API routes keep `require_password_complete`** — they call the
  plain helpers with `current_user.id`; converting them to the RAS-based deps would
  silently downgrade the auth tier (that unification is Open Q6's RAS→RPC plan).
- Per-site semantics are preserved exactly, including the two inconsistencies found:
  API application routes and two discover cover-section routes do NOT gate on
  `deleted_at` (UI tracking/discover helpers do, per plan 86). They keep
  `allow_deleted=True` and the inconsistency is recorded below as a finding for Q6.

## Slice B — 7.4: input validation at the Pydantic edge

- `max_length` (+ URL/email format checks where applicable) on unbounded
  Profile/Job/Contact string inputs in the API models.
- Bound the free-`dict[str, Any]` route bodies (settings/outreach/contacts
  PUT/POST) so malformed input is a 422 at the edge, not an asyncpg 500.
- RED tests first per surface.

## Slice C — 7.3: closed-vocabulary CHECK constraints

Candidate columns (plan 91): `Job.url_type` / `Job.apply_kind` /
`Job.apply_resolved_via`, `Project.kind`, `EmailThread.provider` /
`EmailMessage.provider`, `OutreachMessage.channel`, `ApiUsage.method`, and the
closed-vocab `Settings.*` strings. Process per column:

1. Derive the code-enforced vocabulary (writers only).
2. Audit live dev-DB values (`:5433`); a column whose live rows violate the derived
   vocab is skipped (or data-normalized in-migration only when unambiguous) — a blind
   CHECK reintroduces the plan-91 1.5 "invalid input value" crash class.
3. Add `CheckConstraint` at the model level (applies to sqlite `create_all` in tests)
   + alembic migration `0040` for Postgres. Up/down tested on the live dev DB.

## Re-judged skips (recorded up front; rationale re-validated post-teardown)

- **4.4 `stages_free` runner** — still a rewrite of working orchestration for zero
  behaviour gain; the free stages are characterized by the bundle suite. SKIP.
- **4.6 notify single event→message model** — the dual renderers are verbatim,
  tested, and load-bearing patch seams (10 tests). Rendering unification changes
  outbound message text for no user ask. SKIP.
- **5.3 `run_structured_llm`** — the 16 `tracked_call` sites still carry per-site
  `get_provider`/`llm_tracker` patch seams; the tracker-bypass wrappers plan 91
  worried about were already deleted (5.3 deviation). SKIP.
- **7.5 JSONB→relational** — still deferred per Open Q2: three invasive schema
  projects (bullet-override table, append-only trace, email dual-store read path)
  each needing their own migration + read-path plan. Unchanged appetite. DEFERRED.

## Gate

Per slice: nix ruff check + format --check, full pytest (baseline 3350 / 15, count
only grows). Slice C additionally: alembic upgrade+downgrade against the live dev
Postgres. Final: live Playwright owner pass, net-zero data, teardown (leave
:8000/:5432).

## Findings for the Q6 RAS→RPC re-audit

- `api/applications.py` ownership checks don't gate `deleted_at` (UI does, plan 86);
  `discover.py` cover-section GET/PUT (two sites) likewise.
- Auth-tier split remains: `/api/v1/*` uses `require_password_complete`; UI + the
  `get_owned_*` deps use `require_authed_session`.

## Deviations from plan

(recorded during execution)
