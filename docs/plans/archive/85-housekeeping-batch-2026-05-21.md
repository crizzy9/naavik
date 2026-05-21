---
Status: EXECUTED
Type: execution
Authored: 2026-05-21
Last updated: 2026-05-21
Depends on: docs/plans/archive/75-... (0.3.3.08a UI wiring derives from this)
            docs/plans/archive/76-... (0.4.0.21 mirrors plan 75 row 1 IDOR pattern)
            docs/plans/archive/80-... (0.4.0.23 derives from plan 80 CSV export)
GitHub: #196 (0.4.0.23) + #202-adjacent (0.4.0.21 needs filing)
Owner: manager (direct authoring per § Batching cap-of-10; locked defaults)
Shipped: 2026-05-21
---

# 85 · Housekeeping batch — 0.3.x + 0.4.x small follow-ups (cap 3)

## Goal

Knock out 4 small follow-up items in a single PR with parallel reviewer pair.
No design decisions; all mechanical; locked-default scope. Per manager.md
§ Batching small tasks (post-0.7.0.25).

## Why

Owner directive 2026-05-21: "continue going until all the pending items in
0.3.x and 0.4.x is not finished". These 4 are the surviving follow-ups in
0.3.x + 0.4.x once 0.4.5 deferred items are moved out (plan-85 author session
moved 0.3.3.04/09/16 → 0.4.5.01/02/03 in commit `9924c6f`).

## Included tasks

### § A — `0.3.3.24` Burstiness regen audit-trail completeness + cost-cap test determinism

- **Source:** PR #170 hacker LOW (L3 + L4 rolled).
- **Action:**
  - `src/services/document_generator.py:445` `regen_bullet_for_variance` currently swallows `LLMProviderError` without writing audit-trail key. Add audit-trail key write on the except branch — debuggers reading the trace need to see "regen attempted but failed" not silence.
  - Cost-cap test determinism — flake-prone test exists somewhere in `tests/test_document_generator.py`; engineer locates + tightens via fixed time + injected cost source.
- **Files:** `src/services/document_generator.py` + `tests/test_document_generator.py` (or similar test path).
- **Tests:** 2 new tests (regen-failure audit-trail row present; cost-cap deterministic threshold).
- **LOC estimate:** ~15 LOC + 2 tests.

### § B — `0.4.0.21` IDOR boundary on application mutation routes

- **Source:** PR #191 hacker MED (pre-existing). Mirror of 0.3.3.15 screener IDOR pattern closed in plan 75.
- **Action:** `src/api/applications.py:39,71,89,133` (the 4 mutation handlers — submit / discard / status / move) need explicit `Application.user_id == current_user.id` boundary. Service-layer JOIN pattern per plan 75 row 1:
  ```python
  app = await session.exec(
      select(Application).where(
          Application.id == application_id,
          Application.user_id == current_user.id,
          Application.deleted_at.is_(None),
      )
  ).one_or_none()
  if app is None:
      raise HTTPException(404, "Application not found")
  ```
  Returns 404 on cross-user OR not-exists (no enumeration leak). Apply to all 4 mutation handlers.
- **Files:** `src/api/applications.py`.
- **Tests:** 4 new tests (one per mutation route × cross-user → 404).
- **Manual QA:** not required for IDOR work; tests cover.
- **LOC estimate:** ~20 LOC + 4 tests.
- **MUST close before any multi-user expansion.**

### § C — `0.4.0.23` CSV export formula-injection defang

- **Source:** PR #195 hacker MED (Issue #196).
- **Action:** `src/services/application_service.py:list_for_export` returns operator-controllable fields via `csv.DictWriter` w/ RFC-4180 quoting that doesn't defang `=` / `+` / `-` / `@` / `\t` / `\r` formula leaders.
  - Add helper `_defang_csv_cell(value: str | int | None) -> str` that:
    - Returns empty string for None.
    - Coerces to string.
    - If first char is in `{"=", "+", "-", "@", "\t", "\r"}`, prepend single-quote `'`.
    - Returns the result for the CSV writer to wrap-quote as it sees fit (RFC 4180 quote-on-embed-comma still applies).
  - Apply to every operator-controllable field in the export dict: `company`, `role`, `team`, `location`, `external_url`.
  - Application-controlled fields (`status`, `applied_at`, `salary_min`, `salary_max`, `board`) are enum / typed — safer but defang anyway for defense-in-depth.
- **Files:** `src/services/application_service.py`.
- **Tests:** 3 new tests (formula-leader cells get prefixed; tab+CR get prefixed; non-leader cells untouched).
- **Manual QA:** export CSV from /tracking with a Job whose `company` field starts with `=cmd|'/c calc'!A1` → verify cell prefixed with `'` on download.
- **LOC estimate:** ~10 LOC + 3 tests.

## Build sequence

1. Commit 1: § A audit-trail completeness + test determinism (0.3.3.24).
2. Commit 2: § B IDOR boundary on 4 mutation routes (0.4.0.21).
3. Commit 3: § C CSV defang (0.4.0.23).
4. PR open via `gh pr create` with `.github/pull_request_template.md`.

Total: ~45 LOC + ~9 tests. No manual QA target — all changes verifiable via pytest.

## Test plan

- Tests: TBD-baseline (set after 0.7.0.39 merges) → +9 new across 3 sections.
- Ruff clean + format clean.
- All changes verifiable via pytest; no orchestrator boot needed.
- Mandatory teardown per 0.7.0.35 not applicable (no orchestrator dispatch).

## Risk + mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| § B IDOR pattern accidentally breaks legitimate cross-tab editor flow | LOW | MED | Tests cover the `app is None` path; positive-case test ensures legitimate same-user request still 200s |
| § C defang false-positives on legitimate values starting with `-` (e.g. negative salary in raw) | LOW | LOW | Salary fields are int / enum — never operator-typed leading `-`; documented in test |
| Engineer fails the parallel-route changes in § B and only edits 3 of 4 routes | MED | MED | Architect-as-reviewer verifies grep finds the right shape on all 4 handlers; tests assert per-route |

## Open questions

(empty — locked defaults per § Batching)

## Approval checklist

(empty — pre-approved)

## New / removed operational surface

None. All 4 items are internal hardening with no new env / CLI / on-disk / port / schedule.

## Deviations from plan

- **test_count_overshoot** — what: test_count_overshoot. why: defense-in-depth+positive-path+e2e. impact: none surface=none — § A net -1 vs plan (refactored existing test in-place); § B +2 vs plan (missing-app + positive owner); § C +1 vs plan (e2e on list_for_export call site). surface: port.
- **run-id-trace-dir-shared** — what: run-id-trace-dir-shared. why: run-id directory already populated by prior plan-85 author session. impact: none surface=none — appended engineer log to existing traces/2026-05-21T15-33-09_fccfbeb5/. surface: none.
