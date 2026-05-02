---
Status: USED
Type: implementation kickoff
Plan: docs/plans/archive/09-stage-3-impl.md
Authored: 2026-05-01
Used: 2026-05-02
Prerequisite: Wave 2 (plan 08) shipped clean — `/_design/components` renders all 85 components, all placeholder routes 200, mobile drawer works, confirm modal works.
---

# Naavik · Stage 3 page implementation — implementation kickoff

Paste this entire file as the first message of a fresh Claude Code session **after Wave 2 (plan 08) ships and verifies clean**. The repo is at `/home/nightwatcher/personal/dev/naavik`.

## Goal

Implement the 11 Phase 1 MVP page templates per `docs/design/SCREENS.md` by composing the partials shipped in plan 08, render each via per-screen FastAPI handlers in `src/ui/routes/`, wire every interaction noted in SCREENS.md (stub-handler-backed where backend is pending), back the data with `src/db/sample_data.py` per SAMPLE_DATA.md (with **async accessors from day one** so plan 10 Wave 4's swap is body-only), and visual-QA each via Playwright at desktop (1440×900) + mobile (375×812). After this lands, every Phase 1 screen renders end-to-end with realistic sample data — no DB, no auth, no LLM, no Typst, no ATS submission required.

## Required reading (in order)

1. `AGENTS.md` § Workflow.
2. `CLAUDE.md`.
3. `ROADMAP.md` § Phase 1 § Implementation waves → Wave 3 row + per-wave checklist.
4. `docs/plans/09-stage-3-impl.md` — **THE PLAN.** Status: APPROVED. Read end-to-end. § B sample data, § C build order, § D stub-handler convention with full endpoint inventory, § G per-screen acceptance, § H cross-screen acceptance.
5. `DESIGN.md` (root) — visual contract. v1.3.
6. `docs/design/SCREENS.md` — **per-screen functional contract.** Read every screen's full section before implementing it. Each screen entry has `Layout`, `Components`, `Interactions`, `States` sections you MUST satisfy.
7. `docs/design/COMPONENTS.md` § J component-to-screen index — for each screen, the components it composes.
8. `docs/design/SAMPLE_DATA.md` — Phase 1 fixtures + § M accessor pattern + § N realism rules (14 rules; +1 added 2026-05-01: at least one DRAFT row carries `submission_artifacts.last_failure` for stuck-queue surface).
9. `docs/design/INTERACTIONS.md` — § J per-screen interaction recap is your interaction checklist; § B–H are the patterns.
10. `docs/design/BACKEND.md` § B (page routes), § C (HTMX fragment routes), § D (JSON API), § E (SSE streams), § F (per-screen interaction map), § K.1 (DRAFT lifecycle).
11. `docs/design/DATA_MODEL.md` § A axes, § C model definitions (incl. `Settings.eager_review_generation`, `daily_llm_cost_cap_usd`, `portfolio_cors_allowed_origins`, `ApiUsage`), § D enums, § E state transitions, § F KPI derivations, § J custom screener questions.
12. `docs/design/mockups/README.md` — bundle JSX layout. Mockups are gitignored locally; if missing, fall back to PDF `Naavik — MVP screens (print).pdf`.

Per-screen, before implementing:
- Read SCREENS.md § N for that screen.
- Open `docs/design/mockups/naavik-handoff/project/screens/<ScreenName>.jsx` if available.
- Look up the components in COMPONENTS.md § J.
- Look up the interaction patterns in INTERACTIONS.md § J.
- Look up the routes in BACKEND.md § F.

Open question answers (locked by user 2026-05-01): two-file sample-data split (`sample_data_models.py` + `sample_data.py`); in-memory mutation persists within process, resets on restart; Playwright added to nix devshell now; sub-plan threshold >250 LOC OR >1.5 days; Playwright snapshots commit alongside code; real SSE (not polling fallback); fake-session-cookie auth simulation; `+ Add by URL` ships full modal flow with stub scrape; `Show drafts` endpoint wired, UI toggle deferred.

## Deliverables

| Path | Description |
|---|---|
| `src/db/sample_data_models.py` | Lightweight Pydantic `BaseModel` classes matching DATA_MODEL.md § C field shape exactly (NOT `SQLModel(table=True)` — plan 10 Wave 4 introduces those). 19 entities + Settings + enums re-exported from a stub `models/enums.py` |
| `src/db/sample_data.py` | Frozen instances per SAMPLE_DATA.md inventory (1 User, 1 Profile, 4 Experiences, 14 Bullets, 6 Skills, 2 Educations, 4 Projects, 1 Certification, ~20 Jobs, 14 Applications incl. 2 DRAFT and ≥1 with `submission_artifacts.last_failure`, ~20 Contacts, ~25 ContactApplicationLinks, ~40 OutreachMessages, ~20 EmailThreads, ~150 AppEvents, ~30 GeneratedDocuments, ~20 ApplicationScreenerAnswers, **~30 ApiUsage rows for Settings cost cards**, 1 Settings) + every accessor in § M as `async def`. In-memory mutation shim per § B |
| `src/ui/templates/pages/login.html` | Auth-shell-extending template per SCREENS.md § 1 |
| `src/ui/templates/pages/onboarding.html` | 3-step wizard via `?step=`; SSE step-2; `HX-Trigger: extractionDone` auto-progresses to step 3 |
| `src/ui/templates/pages/overview.html` | Greeting + KPI strip × 4 + priority actions + email signal feed + pipeline strip |
| `src/ui/templates/pages/profile.html` | Read-only profile view + sticky right-rail anchor nav + application_readiness_card |
| `src/ui/templates/pages/profile_edit.html` | Per-field autosave + bullet drag-drop + bullet editor modal trigger + application_qs_form |
| `src/ui/templates/pages/discover.html` | Swipe queue + 4-button action bar + right rail (Up next + **Stuck in queue · {N}** + Saved + Tip) + keyboard hints |
| `src/ui/templates/pages/discover_review.html` | 3-column workspace; eager DRAFT auto-create gated on `Settings.eager_review_generation`; lazy "Tailor for this job" CTA otherwise; failure banner when `submission_artifacts.last_failure` populated |
| `src/ui/templates/pages/tracking.html` | Board / list view toggle; integrations row; needs-followup banner; 4 visible columns + closed toggle; Sortable.js Kanban with optimistic rollback |
| `src/ui/templates/pages/outreach.html` | 2-pane (apps left, detail right); recommended_move_card; contacts list; outreach_timeline |
| `src/ui/templates/pages/settings.html` | Tabs nav + tab-content area; **all 6 tabs** (LLM Provider, Deployment, Account, Notifications, Auto-Apply, Sources) with full UI scaffolding |
| `src/ui/routes/auth.py` | Real handlers replacing placeholders: `get_login`, `post_login`, `post_logout`, `get_me`, `get_csrf`, `get_onboarding`, `post_extraction_upload`, `get_extraction_stream`, `post_profile_from_extraction` |
| `src/ui/routes/overview.py` | `get_overview` + fragment endpoints (`/_fragments/overview/priority-actions`, `email-signal`, `pipeline-strip`) |
| `src/ui/routes/profile.py` | `get_profile`, `get_edit`, `put_field`, `put_application_questions`, `post_bullet`, `put_bullet`, `delete_bullet`, `post_bullet_rewrite`, `post_bullets_reorder` |
| `src/ui/routes/discover.py` | `get_discover`, `get_review` (with DRAFT auto-create or lazy CTA per `Settings.eager_review_generation`), `post_skip`, `post_save`, `post_auto_submit`, `get_jobs`, `get_job_by_id`, `post_job_by_url`, `post_rescore`, `get_saved`, `get_skipped`, fragment endpoints (`next-card`, `match-breakdown`, `tailored-bullets`, `cover-letter-section`, `screener`) |
| `src/ui/routes/tracking.py` | `get_tracking`, `post_application_move`, `post_application_manual`, `put_application_status`, `delete_application_discard`, `post_application_submit`, `get_application_bundle`, fragment endpoints (`board`, `list`, `followup-banner`) |
| `src/ui/routes/outreach.py` | `get_outreach`, `get_contacts`, `post_contact`, `put_contact`, `delete_contact`, `post_contacts_find`, `get_outreach_messages`, `post_outreach_draft`, `post_outreach_send`, `post_outreach_skip`, fragment endpoints (`app-detail`, `draft`) |
| `src/ui/routes/settings.py` | `get_settings`, `get_settings_tab`, `put_llm`, `post_llm_test`, `get_llm_usage`, `put_auto_apply`, `put_sources`, `put_notifications`, `post_notifications_test`, `get_deployment`, `post_deployment_restart`, `get_deployment_logs` (SSE), `get_account`, `put_account`, `put_account_password`, `post_account_delete` |
| `src/ui/routes/integrations.py` | Gmail + Outlook + Calendar OAuth stubs (connect / callback / disconnect); `GET /api/v1/integrations` |
| `src/ui/routes/email.py` | `get_email_threads`, `get_email_thread`, `post_email_thread_draft_reply`, `get_tracking_email_signals` (SSE) |
| `src/ui/routes/fragments.py` | Cross-cutting fragment endpoints not domain-specific (`/_fragments/onboarding/step/{n}`, etc.) |
| `src/ui/static/keys.js` | Extended with `'/discover'` + `'/discover/:id'` keyboard maps per plan § F |
| `tests/test_sample_data.py` | Round-trip every fixture through Pydantic; assert counts match SAMPLE_DATA.md inventory; visa-rule coverage (≥2 `us_citizen_only` jobs scoring 0); DRAFT coverage (≥2); recruiter-silence stress (≥1 `silent ≥ 6d`); stuck-queue coverage (≥1 DRAFT with `submission_artifacts.last_failure`) |
| `tests/test_pages.py` | Per-screen GET 200 + key markup assertion (parametrized over the 11 screens) |
| `tests/test_stub_endpoints.py` | Per-endpoint shape + `?fail=1` failure-mode coverage |
| `tests/test_draft_lifecycle.py` | DRAFT state machine: GET `/discover/{id}` creates DRAFT (eager) or shows lazy CTA; POST submit flips to APPLIED; DELETE discard flips to CLOSED `withdrawn_by_me`; submitting with unreviewed required screeners returns 409; failed auto-apply DRAFTs surface in stuck queue |
| `tests/visual/capture.py` | Playwright parametrized capture script — 11 screens × 2 viewports = 22 screenshots; saves to `tests/visual/screenshots/<screen>-<viewport>.png` |
| `tests/visual/screenshots/` | 22 baseline screenshots committed alongside code |
| `nix/devshell.nix` | Add `playwright` (Python package) + `playwright install chromium` shellHook (one-time per shell entry) |
| `docs/design/SCREENS.md` | Per-screen `Impl: [~] → [x]` flips as each screen ships; bump `Last updated:` |

## Build sequence (simplest first; gate on each)

For each screen:
1. Read the SCREENS.md section + open the bundle JSX (or PDF mockup).
2. Implement the page template at `src/ui/templates/pages/<screen>.html` composing only plan-08 partials.
3. Implement the page handler in the right `src/ui/routes/<domain>.py` module.
4. Implement the stub fragment + JSON endpoints that page fires against.
5. Run `uv run ruff check .` + `uv run pytest tests/test_pages.py::test_<screen>` + `uv run pytest tests/test_stub_endpoints.py -k <domain>`.
6. Boot dev (`NAAVIK_DEBUG=1 uv run fastapi dev src/main.py`) and smoke-test the screen at `http://localhost:8000/<route>`.
7. Capture Playwright snapshots: `uv run python tests/visual/capture.py --screen=<screen>` (writes desktop + mobile to `tests/visual/screenshots/`).
8. Side-by-side compare snapshot to bundle JSX. Fix obvious deltas; flag ambiguous ones in the hand-back report.
9. Flip SCREENS.md per-screen `Impl: [ ]` → `[x]`; bump `Last updated:`.

Build order:

| # | Screen | Estimate |
|---|---|---|
| 0 | `sample_data.py` + `sample_data_models.py` + `tests/test_sample_data.py` | 4-6 hours |
| 1 | Login | 2-3 hours |
| 2 | Settings (all 6 tabs) | 5-7 hours |
| 3 | Profile (read-only) | 3-4 hours |
| 4 | Profile editor | 5-7 hours |
| 5 | Bullet editor (modal) | 2-3 hours |
| 6 | Onboarding (3-step + SSE auto-progress to step 3) | 5-6 hours |
| 7 | Overview | 4-5 hours |
| 8 | Tracking (board + list + Sortable Kanban) | 6-8 hours |
| 9 | Outreach | 5-6 hours |
| 10 | Discover (swipe + keyboard + Stuck-in-queue card) | 5-6 hours |
| 11 | Discover · review & apply | 1.5-2 days **— escalate to `09a-discover-review-impl.md` sub-plan if scope >250 LOC** |

Total: ~10-12 working days.

## Quality bar (final gate)

```bash
uv run ruff check .                    # clean
uv run ruff format --check .           # clean
uv run pytest tests/                   # all green
NAAVIK_DEBUG=1 uv run fastapi dev src/main.py   # boots without warning
```

Manual cross-screen smoke (browser at `http://localhost:8000` after `POST /api/v1/auth/login` with the seeded user):

- Every screen renders without 500 / Jinja error.
- Every interaction noted in the per-screen SCREENS.md § Interactions exists and fires.
- Mobile viewport (375×812) renders without broken layouts.
- Discover right-swipe creates an in-memory DRAFT; auto-apply queue card shows it.
- First visit to `/discover/{id}` for a Job without an existing Application creates a DRAFT (when `eager_review_generation=True`); shows lazy CTA when `False`.
- Tracking default view hides DRAFT + CLOSED.
- Confirm modal opens for: Delete bullet, Discard draft application, Disconnect Gmail, Remove experience role.
- Optimistic rollback fires on `?fail=1` Discover swipe.
- Auto-save indicator cycles `saving → saved → error` correctly (test error via `?fail=1`).
- Sortable.js works on Profile editor bullets AND Tracking Kanban.
- All 4 SSE streams fire (extraction, cover-letter, email-signal, log-tail).
- Discover keyboard shortcuts (←/→/↑/⏎) work.
- Settings · LLM Provider cost cards render with realistic numbers from ApiUsage fixtures.
- Stuck-in-queue card on Discover renders for the seeded failed-DRAFT row.
- Onboarding step 2 → step 3 auto-progresses on SSE done.

`grep` checks (must be empty):

```bash
rg --no-config '\[#[0-9a-fA-F]' src/ui/templates/                # no arbitrary hex
rg --no-config 'def [a-z_]+\(' src/db/sample_data.py | rg -v 'async def'   # every accessor must be async
rg --no-config '/generate/(cover-letter|resume)' src/ui/templates/ src/ui/routes/   # no forbidden routes
rg --no-config 'kanban-square' src/ui/templates/                  # Tracking icon must be inbox
```

## Forbidden patterns

Same as plan 08 (no React/Vue/etc, no DaisyUI, no light mode, no inline styles, no script tags in components / fragments, no sparkle on tag chips, no `%` on score circles, no `kanban-square`, no `/generate/*` routes, no oneline/detailed bullet split, no flat status enum without DRAFT, no theme toggle, no Funnel/BarChart/LineChart on Overview).

Plus plan-09-specific:

- ❌ **Sync sample-data accessors.** Every accessor in `src/db/sample_data.py` is `async def` — even though it returns from in-memory lists. This makes plan 10 Wave 4's swap purely body-level. Failing this requirement = Wave 4 codemod across every page handler.
- ❌ **Real DB, real auth, real LLM, real Typst, real ATS, real scrapers, real email, real outreach, real observability** — every backend dependency is stubbed. The session goal is rendered pages + working interactions, NOT a working backend.
- ❌ **`SQLModel(table=True)` anywhere.** That's plan 10 Wave 4. Pydantic `BaseModel` only at this stage.
- ❌ **Eager DRAFT generation hardcoded.** Must check `Settings.eager_review_generation` (default True from sample_data.SETTINGS) — if False OR `daily_llm_cost_cap_usd` exceeded today, render the lazy "Tailor for this job" CTA instead of running `_pre_generate`.
- ❌ **Hardcoded "test email" sentinel for Login redirect** beyond the `email == "onboarding@test"` Wave-3 stub. Real DB-backed Profile lookup is plan 10 Wave 4.
- ❌ **CI-side visual-diff regression tests.** Plan 09 captures the **first** snapshot set as baseline; per-PR diff is a follow-up plan.

## Hand-back format

When complete:

1. **File list** — every file created or modified, grouped by directory.
2. **Test results** — `uv run pytest tests/ -v` output (must be all green); `uv run ruff check .` output (clean).
3. **Visual QA report** — for each of the 11 screens: snapshot path + a one-line note on bundle-JSX parity (e.g. "Login: visual parity, no deltas" or "Tracking: deltas in the integrations row spacing, fixed").
4. **Per-screen acceptance gate (§ G of plan 09)** — for each screen, confirm: page renders, components from plan 08 only, visual parity, interactions noted exist, console clean, Lucide repaints, mobile renders, SCREENS.md flipped.
5. **Cross-screen acceptance gate (§ H of plan 09)** — every checklist item.
6. **Any deviations from the plan** — every divergence with reason. Sub-plan escalation? File `docs/plans/09a-discover-review-impl.md` and update plan 09's front-matter `Children:` line.
7. **Archive step done** — confirm:
   - `mv docs/plans/09-stage-3-impl.md docs/plans/archive/09-stage-3-impl.md` (Status: APPROVED → EXECUTED).
   - `mv docs/prompts/09-stage-3-impl.md docs/prompts/archive/09-stage-3-impl.md` (Status: ACTIVE → USED).
   - `ROADMAP.md` Wave 3 row + per-task checklist marked `[x]` with deliverable note.
8. **Next** — confirm Wave 4 (plan 10 § B, `docs/prompts/10-backend-impl.md` PART 1) is now unblocked.

If you hit a blocker (a screen needs a component variant plan 08 didn't ship, sample-data accessor signature differs from BACKEND.md call site, mockup contradicts SCREENS.md), STOP and post a question. Don't make scope-creeping calls in-session.

Good luck.
