---
Status: EXECUTED
Type: implementation
Authored: 2026-05-01
Last updated: 2026-05-02 (executed)
Approved: 2026-05-01
Executed: 2026-05-02
Depends on: 08-stage-2-impl (executed), 04-backend-architecture (graduated → docs/design/BACKEND.md), 05-data-model (graduated → docs/design/DATA_MODEL.md), 06-interactions-spec (graduated → docs/design/INTERACTIONS.md), 07-sample-data (graduated → docs/design/SAMPLE_DATA.md)
Wave order: this plan is **Wave 3** in ROADMAP.md § Phase 1 (Scenario A — linear: 08 → 09 → 10 W3 → 10 W6). Plan 09 shipped 2026-05-02; plan 10 W3 swaps stub bodies for DB-backed handlers without changing pages.
---

# 09 · Stage 3 page implementation

## Goal

Implement the 11 Phase 1 MVP page templates per `docs/design/SCREENS.md` by composing the partials shipped in plan 08, render each via per-screen FastAPI handlers in `src/ui/routes/`, wire every interaction noted in SCREENS.md (stub-handler-backed where backend is pending), back the data with `src/db/sample_data.py` per SAMPLE_DATA.md, and visual-QA each via Playwright at desktop (1440×900) + mobile (375×812). After this lands, every Phase 1 screen renders end-to-end with realistic sample data — no DB, no auth, no LLM, no Typst, no ATS submission required (those swap in later via plan 10 Wave 3 + Wave 6 + Phase 2+ sub-prompts).

## Context / why

Plan 08 ships the component library; plan 09 makes it visible. Until plan 09 lands, every authenticated route still hits the `placeholder.html` stub — the user can't see Discover, Tracking, Profile, etc. as real screens. That breaks two things: (a) the team can't sanity-check the design end-to-end against the bundle JSX, and (b) plan 10 (backend) can't be tested against real handlers because there are no real handlers to wire DB-backed code into.

The session-continue prompt + ROADMAP.md split Phase 1 into Wave 4 (Stage 3 pages) and Wave 5 (interactions); plan 09 covers both — every page handler ships with HTMX wiring against the stub fragment + JSON routes, and every per-screen interaction documented in INTERACTIONS.md § J fires correctly. Wave 5 doesn't need its own plan; folding interactions into Wave 4 is cleaner because each interaction is per-screen-specific.

The contract plan 09 builds against:

- **Visual:** `DESIGN.md` (tokens) + bundle JSX at `docs/design/mockups/naavik-handoff/project/screens/<ScreenName>.jsx` (most-detailed visual reference) + the historical PDF.
- **Functional:** `docs/design/SCREENS.md` per-screen specs.
- **Components:** `docs/design/COMPONENTS.md` § J component-to-screen index — every page composes only from the 85 partials shipped in plan 08.
- **Routes:** `docs/design/BACKEND.md` § B (page routes), § C (HTMX fragment routes), § D (JSON API), § F (per-screen interaction map). Plan 09 implements page routes and stub-handler-backed fragment + JSON routes.
- **Interactions:** `docs/design/INTERACTIONS.md` § J (per-screen interaction recap).
- **Data:** `docs/design/SAMPLE_DATA.md` (canonical Phase 1 fixtures + accessor pattern in § M). Plan 09 builds `src/db/sample_data.py` to spec.
- **Lifecycle:** `docs/design/DATA_MODEL.md` § A multi-axis state, § E state transitions, § J custom screener questions; `BACKEND.md` § K.1 DRAFT lifecycle (auto-create on `/discover/{job_id}` first visit; submit flips DRAFT → APPLIED).

## Proposal

### A · Scope

**In scope (this plan ships these files):**

| Surface                         | Files                                                                                                                                                                                                                          |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Page templates                  | 11 templates at `src/ui/templates/pages/<screen>.html` per SCREENS.md inventory + COMPONENTS.md § J                                                                                                                            |
| Page handlers                   | Per-screen handlers in `src/ui/routes/{auth,overview,profile,discover,tracking,outreach,settings,fragments}.py` — replace plan 08's placeholder bodies with real `templates.TemplateResponse(...)` calls against the new pages |
| Sample data module              | `src/db/sample_data.py` + `src/db/sample_data_models.py` per SAMPLE_DATA.md (~1,500 lines of frozen Pydantic-modeled fixtures + accessors per § M)                                                                             |
| Stub fragment endpoints         | Every `/_fragments/...` and `/_modal/...` route in BACKEND.md § C, returning sample-data fragments (modal-confirm route was shipped in plan 08; this plan adds the rest)                                                       |
| Stub JSON API endpoints         | Every `/api/v1/...` route in BACKEND.md § D plan 09's HTMX fires against, returning canned Pydantic responses with limited in-memory mutation                                                                                  |
| SSE stubs                       | Stubs for the 4 streams in BACKEND.md § E (extraction, cover-letter, email-signal, log-tail) — fire fake events on a timer; HTMX polling fallback wired per INTERACTIONS.md § C.2                                              |
| Discover keyboard map           | `src/ui/static/keys.js` gets the `'/discover'` and `'/discover/:id'` handler maps (plan 08 shipped the empty registry)                                                                                                         |
| Per-screen Playwright snapshots | `tests/visual/screenshots/<screen>-<viewport>.png` for every screen at desktop (1440×900) + mobile (375×812); committed alongside the code as the visual-QA baseline                                                           |
| Tests                           | `tests/test_sample_data.py` (round-trip), `tests/test_pages.py` (per-screen GET → 200 + key markup), `tests/test_stub_endpoints.py` (per-route shape)                                                                          |
| SCREENS.md updates              | `Impl: [ ] → [x]` per screen as it lands; `Last updated:` bumped at end                                                                                                                                                        |

**Out of scope (deferred):**

- ❌ DB persistence (every fixture lives in `sample_data.py`; mutations live in module-level state cleared on restart) — plan 10 Wave 3.
- ❌ Real auth (JWT cookie + bcrypt) — plan 10 Wave 3. Plan 09 sets a fake session cookie on `/api/v1/auth/login`.
- ❌ Real LLM calls — plan 10 Wave 3 abstraction; plan 10 Wave 6 prompt wiring.
- ❌ Real Typst compilation — plan 10 Wave 6.
- ❌ Real ATS submission — plan 10 Wave 6 (Greenhouse / Lever / Ashby first; rest Phase 1.x).
- ❌ Real scraping, cron, email, outreach, observability — Phase 2-6 sub-prompts.
- ❌ CI-side visual-diff regression tests. Plan 09 captures the **first** snapshot set; per-PR diff is a follow-up plan once snapshots stabilize.
- ❌ Real CSRF rotation — plan 10 Wave 3.
- ❌ Light mode — Phase 6.

### B · Sample data module (`src/db/sample_data.py` + `src/db/sample_data_models.py`)

Per SAMPLE_DATA.md verbatim. Two-file split:

- `src/db/sample_data_models.py` — lightweight Pydantic models matching DATA_MODEL.md § C field shape exactly. **Critical:** these classes are `BaseModel` (not `SQLModel(table=True)`) so plan 09 doesn't accidentally fight the SQLAlchemy registry. Plan 10 Wave 3 introduces `src/models/*.py` as `SQLModel(table=True)` — both use the same field names so the eventual swap is mechanical.
- `src/db/sample_data.py` — frozen instances of those models per the SAMPLE_DATA.md inventory (1 User, 1 Profile, 4 Experiences, 14 Bullets, 6 Skills, 2 Educations, 4 Projects, 1 Certification, ~20 Jobs, 14 Applications, ~20 Contacts, ~25 ContactApplicationLinks, ~40 OutreachMessages, ~20 EmailThreads, ~150 AppEvents, ~30 GeneratedDocuments, ~20 ApplicationScreenerAnswers, 0 ATSCredentials, ~30 ApiUsage, 1 Settings) + every accessor in § M. **`ApiUsage` was promoted to a Phase 1 entity (#19) on 2026-05-01** so Settings cost cards have data from day one — plan 09 includes ~30 historical ApiUsage rows in the fixture so Settings · LLM Provider's "THIS MONTH / AVG / RATE" cards render with realistic numbers.

**Async accessors from day one.** Every accessor is declared `async def` even though it returns from in-memory lists — for example:

```python
# src/db/sample_data.py
async def applications_visible_in_tracking(user_id: int) -> list[Application]:
    return [a for a in APPLICATIONS if a.user_id == user_id and a.status in {
        ApplicationStatus.APPLIED, ApplicationStatus.RECRUITER_SCREEN,
        ApplicationStatus.ONSITE_LOOP, ApplicationStatus.OFFER,
    }]
```

This means Wave 4 (plan 10 § B) only swaps **the function body** — signatures stay identical. Page handlers thread `session: AsyncSession = Depends(get_session)` and `current_user: User = Depends(get_current_user)` from day one; in plan 09 the `session` arg is unused (sample_data accessors ignore it), but Wave 4 lights it up without touching call sites. This was added 2026-05-01 to avoid a sync→async codemod during Wave 4.

**In-memory mutation:** sample_data.py exposes a small mutable shim — `_apply_status_override(app_id, status)`, `_create_draft(user_id, job_id)`, `_record_screener_answer(app_id, q_id, text)`, `_apply_failure_to_draft(app_id, kind, message)` — so stub endpoints can persist for the lifetime of the server process. Lists are `mutable=True` (frozen=False on the module-level lists, even if individual records are frozen Pydantic models; new records are appended). Tests reset state via a fixture.

**Realism rules locked** per SAMPLE_DATA.md § N — every fixture row must satisfy all 14 rules (date anchoring, salary realism, score distribution, DRAFT coverage, fictional contacts, etc.). **Plus an additional rule** (added 2026-05-01): at least 1 DRAFT row carries `submission_artifacts.last_failure = {kind: "auth_required" | "captcha", message, captured_at}` so the **"Stuck in queue · {N}"** right-rail card on Discover has data.

**Round-trip test:** `tests/test_sample_data.py` validates every fixture round-trips through Pydantic — fails CI if a model field is added in DATA_MODEL.md but missing in fixtures.

### C · Per-screen build order (simplest first)

Each screen passes its own acceptance gate (§ G) before the next starts. Order tuned so primitives + simpler patterns land before composites depend on them. Stage 3 numbering — `9.x` — matches ROADMAP.md § Phase 1 § Wave 4 row order.

| #    | Screen                    | Mockup                                 | SCREENS.md § | Page handler                                           | Notable patterns                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ---- | ------------------------- | -------------------------------------- | ------------ | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 9.1  | Login                     | `screens/Login.jsx` · PDF § 1          | § 1          | `routes/auth.py:get_login`                             | auth_shell; full-form submit (B.2); in-button spinner (A.5); error toast (H.1)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| 9.2  | Settings                  | `screens/Settings.jsx` · PDF § 12      | § 11         | `routes/settings.py:get_settings`, `:get_settings_tab` | tabs (`/settings/{tab}`); **all 6 tabs ship full UI scaffolding** (LLM Provider · Deployment · Account · Notifications · Auto-Apply · Sources) — backend persistence stubbed in Wave 3, real persistence in Wave 4; SSE log tail (C.3) on Deployment tab                                                                                                                                                                                                                                                                                                                                                                                                                        |
| 9.3  | Profile (read-only)       | `screens/Profile.jsx` · PDF § 4        | § 4          | `routes/profile.py:get_profile`                        | sticky right-rail anchor nav (no hx-\* — plain anchor links); application_readiness_card; (read-only — no autosave)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| 9.4  | Profile editor            | `screens/ProfileEdit.jsx` · PDF § 5    | § 5          | `routes/profile.py:get_edit`                           | per-field autosave (B.1); bullet drag-drop (D.1); modal open (E); confirm modal (E.4) on Discard / Remove role; OOB autosave indicator (A.3)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| 9.5  | Bullet editor (modal)     | `screens/BulletModal.jsx` · PDF § 6    | § 6          | `routes/fragments.py:bullet_editor_modal`              | tag chip toggle (B.6); selection_override radio; modal save → HX-Trigger: closeModal (E.2); confirm modal on Delete bullet                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| 9.6  | Onboarding                | `screens/Onboarding.jsx` · PDF § 2     | § 2          | `routes/auth.py:get_onboarding`                        | 3-step wizard via `?step=`; file upload (B.5); SSE extraction stream (C.3); **SSE `done` event auto-progresses to step 3** via `HX-Trigger: extractionDone` response header that swaps `#onboarding-step-content` to step-3 partial (no full-page redirect); commit form on step 3 (B.2) → redirect /                                                                                                                                                                                                                                                                                                                                                                           |
| 9.7  | Overview                  | `screens/Overview.jsx` · PDF § 3       | § 3          | `routes/overview.py:get_overview`                      | KPI strip × 4 (no charts in MVP); priority actions × 5–8; email signal feed × 4–6; pipeline strip × 5 stages; SSE email-signal stub fires every ~30s                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| 9.8  | Tracking                  | `screens/Tracking.jsx` · PDF § 10      | § 9          | `routes/tracking.py:get_tracking`                      | view toggle (board/list); 4 visible columns + closed toggle; integrations row + needs-followup banner; Sortable.js drag-drop (D.2) with optimistic rollback (H.4); DRAFT + CLOSED hidden by default                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| 9.9  | Outreach                  | `screens/Outreach.jsx` · PDF § 11      | § 10         | `routes/outreach.py:get_outreach`                      | 2-pane left/right; row click swaps right pane (A.2); inline edit on draft (B.3); recommended_move_card; provider_chip; confirm modal on Disconnect LinkedIn                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| 9.10 | Discover                  | `screens/Discover.jsx` · PDF § 7       | § 7          | `routes/discover.py:get_discover`                      | swipe queue card stack; keyboard handlers (F.1) for ←/→/↑/⏎; skip/save/auto-apply stubs return next-card fragment via outerHTML swap; right rail Up next + **Stuck in queue · {N}** (`up_next_card` `state="stuck"` for DRAFTs with `submission_artifacts.last_failure`) + Saved + Tip; optimistic rollback (H.4)                                                                                                                                                                                                                                                                                                                                                               |
| 9.11 | Discover · review & apply | `screens/DiscoverDetail.jsx` · PDF § 8 | § 8          | `routes/discover.py:get_review`                        | 3-column workspace; **eager DRAFT auto-creation by default per `Settings.eager_review_generation=True`** (BACKEND.md § K.1; matches SCREENS.md § 8 "generating skeletons"); **lazy path** (when `eager_review_generation=False` OR `daily_llm_cost_cap_usd` exceeded): empty workspace with explicit "Tailor for this job" CTA — click creates DRAFT + runs `pre_generate`; SSE cover-letter generation (C.3); inline edit cover letter sections (B.3); inline edit screener answers (B.3); Submit gates on `unreviewed_required_count == 0`; **failure banner** when `submission_artifacts.last_failure` populated (auto-apply tried + failed); confirm modal on Discard draft |

**Per-screen sub-plan escalation criterion:** if a screen's route + template + sample-data wiring exceeds **~250 LOC combined** OR more than 1.5 working days of implementation surface (visual QA included), escalate to a sub-plan (`09a-discover-review-impl.md` is the most likely candidate). Decision is made by the implementing agent during the session and surfaced in the hand-back report; the parent plan 09 stays the primary contract.

### D · Stub-handler convention

Every endpoint plan 09's HTMX fires against follows the same shape contract:

1. **Same URL** as BACKEND.md § C / § D (so plan 10 swaps in real handlers without changing pages).
2. **Same response shape** as BACKEND.md will eventually return — Pydantic models for JSON, the same template partials for HTML fragments.
3. **Limited in-memory mutation** — the module-level mutable shim in `sample_data.py` (e.g., `_apply_status_override`) lets stub endpoints persist across requests for the server process. Resets on restart.
4. **No real I/O** — no DB, no LLM calls, no Typst compile, no ATS POST, no email send, no LinkedIn API. SSE streams use `asyncio.sleep` + a hardcoded event sequence.
5. **Realistic timing** — stubs return after a small delay (50–200ms for typical, 300–800ms for "AI" endpoints, 2–5s spread for SSE chunks) so loading skeletons + spinners actually visible.
6. **Failure surfaces work** — every stub has an `?fail=1` or `?fail=<kind>` query param that returns a 4xx/5xx response, so optimistic-rollback (H.4) and error-toast (H.1) flows are testable without injecting failures via DB.

#### D.1 Inventory — page-driving stub endpoints

| Endpoint                                                                                    | Method          | Source           | Stub behavior                                                                                                                                                                                                                                                                                                                                                                                                     |
| ------------------------------------------------------------------------------------------- | --------------- | ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST /api/v1/auth/login`                                                                   | POST            | BACKEND.md § D.1 | Set fake `naavik_session=fake-1` cookie; return 204 + `HX-Redirect: /` for the seeded user (Shyam — already has a Profile in sample data). For an "onboarding-pending" sentinel email (`onboarding@test`) the response redirects to `/onboarding`. **This is a Wave-3 stub**; Wave 4 wires real bcrypt + JWT + DB-backed Profile lookup, replacing the hardcoded sentinel. `?fail=1` → 401 + rose alert fragment. |
| `POST /api/v1/auth/logout`                                                                  | POST            | § D.1            | Clear cookie + `HX-Redirect: /login`.                                                                                                                                                                                                                                                                                                                                                                             |
| `GET /api/v1/auth/me`                                                                       | GET             | § D.1            | Return User from sample data (Shyam).                                                                                                                                                                                                                                                                                                                                                                             |
| `PUT /api/v1/profile/{field}`                                                               | PUT             | § D.2            | Mutate in-memory profile; return field payload + OOB `autosave_indicator` partial.                                                                                                                                                                                                                                                                                                                                |
| `POST /api/v1/extraction/upload`                                                            | POST            | § D.2            | Validate PDF + size; return `{extraction_id: "fake-1", status: "queued"}`.                                                                                                                                                                                                                                                                                                                                        |
| `GET /api/v1/extraction/{id}/stream`                                                        | GET (SSE)       | § D.2, § E       | Hardcoded event sequence: `progress` × 5, `field` × 6, `done`. ~6s total.                                                                                                                                                                                                                                                                                                                                         |
| `POST /api/v1/profile/from-extraction`                                                      | POST            | § D.2            | Return Profile + `HX-Redirect: /`.                                                                                                                                                                                                                                                                                                                                                                                |
| `POST /api/v1/bullets` / `PUT /api/v1/bullets/{id}` / `DELETE /api/v1/bullets/{id}`         | POST/PUT/DELETE | § D.2            | Mutate in-memory bullet list; return updated bullet partial via OOB.                                                                                                                                                                                                                                                                                                                                              |
| `POST /api/v1/bullets/{id}/rewrite`                                                         | POST            | § D.2            | Return a hardcoded "rewritten" version of the bullet text + `edited` chip.                                                                                                                                                                                                                                                                                                                                        |
| `POST /api/v1/bullets/reorder`                                                              | POST            | § D.2            | Return 204; mutate in-memory order_index.                                                                                                                                                                                                                                                                                                                                                                         |
| `GET /api/v1/jobs` / `GET /api/v1/jobs/{id}`                                                | GET             | § D.3            | Return Job(s) from sample data.                                                                                                                                                                                                                                                                                                                                                                                   |
| `POST /api/v1/jobs/by-url`                                                                  | POST            | § D.3            | Return a hardcoded "scraped" Job — appended to in-memory list with high score.                                                                                                                                                                                                                                                                                                                                    |
| `POST /api/v1/discover/{id}/skip\|save\|auto-submit`                                        | POST            | § D.3            | Mutate `Job.queue_state`; for `auto-submit`, also create DRAFT Application + AppEvent. Return next-card fragment swapping `#discover-card`.                                                                                                                                                                                                                                                                       |
| `GET /api/v1/applications` / `GET /api/v1/applications/{id}`                                | GET             | § D.4            | Return Application(s) from sample data.                                                                                                                                                                                                                                                                                                                                                                           |
| `POST /api/v1/applications/{id}/submit`                                                     | POST            | § D.4            | Validate `unreviewed_required_count == 0`; flip DRAFT → APPLIED; emit AppEvent; redirect or return next-screen fragment.                                                                                                                                                                                                                                                                                          |
| `DELETE /api/v1/applications/{id}/discard`                                                  | DELETE          | § D.4            | Soft-delete DRAFT (status=CLOSED, closed_reason=withdrawn_by_me, deleted_at). Return 204 + `HX-Redirect: /discover`.                                                                                                                                                                                                                                                                                              |
| `POST /api/v1/applications/{id}/cover-letter/generate`                                      | POST → SSE      | § D.4, § E       | Hardcoded chunk sequence: 4 sections × 3–5 chunks each. ~4s total.                                                                                                                                                                                                                                                                                                                                                |
| `PUT /api/v1/applications/{id}/cover-letter/sections/{section}`                             | PUT             | § D.4            | Mutate in-memory; return updated section partial.                                                                                                                                                                                                                                                                                                                                                                 |
| `PUT /api/v1/applications/{id}/screeners/{q_id}`                                            | PUT             | § D.4            | Mutate in-memory; mark `reviewed_at`; return updated `screener_question_card` partial.                                                                                                                                                                                                                                                                                                                            |
| `POST /api/v1/applications/move`                                                            | POST            | § D.4            | Mutate Application.status; emit AppEvent. Return 204.                                                                                                                                                                                                                                                                                                                                                             |
| `POST /api/v1/applications/manual`                                                          | POST            | § D.4            | Append a new MANUAL Application; redirect `/tracking`.                                                                                                                                                                                                                                                                                                                                                            |
| `GET /api/v1/applications/{id}/bundle`                                                      | GET             | § D.4            | Return a fake ZIP `application/zip` with placeholder PDFs from sample-data fixture path.                                                                                                                                                                                                                                                                                                                          |
| `GET /api/v1/integrations`                                                                  | GET             | § D.5            | Return canned `[{provider, account, last_sync_at, status}]`.                                                                                                                                                                                                                                                                                                                                                      |
| `GET /api/v1/integrations/gmail/connect`                                                    | GET             | § D.5            | Stub OAuth start — redirect to a fake callback `/api/v1/integrations/gmail/callback?code=fake-1`.                                                                                                                                                                                                                                                                                                                 |
| `GET /api/v1/integrations/gmail/callback`                                                   | GET             | § D.5            | Set integration row `(provider=gmail, account=shyam@gmail.com, last_sync_at=now, status=connected)` in-memory; redirect `/tracking?connected=gmail`.                                                                                                                                                                                                                                                              |
| `POST /api/v1/integrations/gmail/disconnect`                                                | POST            | § D.5            | Mark integration row disconnected; return 204 + `HX-Redirect: /tracking`.                                                                                                                                                                                                                                                                                                                                         |
| `/api/v1/integrations/outlook/{action}` / `/api/v1/integrations/calendar/{action}`          | GET / POST      | § D.5            | Identical stub pattern as gmail (connect / callback / disconnect).                                                                                                                                                                                                                                                                                                                                                |
| `GET /api/v1/email/threads`                                                                 | GET             | § D.5            | Return EmailThread[] from sample data; supports `?app_id=` and `?classification=` filters.                                                                                                                                                                                                                                                                                                                        |
| `GET /api/v1/email/threads/{id}`                                                            | GET             | § D.5            | Return EmailThread with messages (sample data already includes 2-6 messages per thread).                                                                                                                                                                                                                                                                                                                          |
| `POST /api/v1/email/threads/{id}/draft-reply`                                               | POST            | § D.5            | Return a hardcoded "draft reply" text (single string body).                                                                                                                                                                                                                                                                                                                                                       |
| `GET /api/v1/tracking/email-signals`                                                        | GET (SSE)       | § D.5, § E       | Hardcoded event sequence; loops every 30–60s with synthetic EmailThread events from sample data.                                                                                                                                                                                                                                                                                                                  |
| `GET /api/v1/contacts` / `POST /api/v1/contacts` / `GET\|PUT\|DELETE /api/v1/contacts/{id}` | various         | § D.6            | CRUD against in-memory CONTACTS; `?company=` + `?app_id=` filters.                                                                                                                                                                                                                                                                                                                                                |
| `POST /api/v1/contacts/find`                                                                | POST            | § D.6            | Return a hardcoded list of 3-5 "found" contacts (LinkedIn search stub).                                                                                                                                                                                                                                                                                                                                           |
| `POST /_fragments/settings/test-connection`                                                 | POST            | § C              | Sleep 400ms, return `connection_status_card` ok variant. `?fail=1` → error variant.                                                                                                                                                                                                                                                                                                                               |
| `GET /api/v1/settings/llm/usage`                                                            | GET             | § D.7            | Return canned tokens / cost.                                                                                                                                                                                                                                                                                                                                                                                      |
| `GET /api/v1/settings/deployment/logs`                                                      | GET (SSE)       | § D.7, § E       | Hardcoded log lines per SCREENS.md § 11 example, looping every ~30s.                                                                                                                                                                                                                                                                                                                                              |
| `POST /api/v1/settings/deployment/restart`                                                  | POST            | § D.7            | Return 202 (self-hosted) or 405 (cloud — toggleable via `Settings.deployment_mode`).                                                                                                                                                                                                                                                                                                                              |
| `POST /api/v1/outreach/draft` / `POST /api/v1/outreach/send` / `POST /api/v1/outreach/skip` | POST            | § D.6            | Mutate in-memory OutreachMessage; emit AppEvent.                                                                                                                                                                                                                                                                                                                                                                  |
| `GET /api/v1/tracking/email-signals`                                                        | GET (SSE)       | § D.5, § E       | Hardcoded event sequence; loops every 30–60s with new EmailThread events.                                                                                                                                                                                                                                                                                                                                         |

#### D.2 Page-route fragment endpoints

These match BACKEND.md § C exactly:

- `/_fragments/profile/bullet-row/{id}` — single `bullet_edit_row` partial
- `/_fragments/discover/next-card` — next `swipe_card` (or `empty_state` if queue exhausted)
- `/_fragments/discover/match-breakdown/{id}` — `match_breakdown` partial
- `/_fragments/apply/tailored-bullets/{job_id}` — list of `tailored_bullet_row`s
- `/_fragments/apply/cover-letter-section/{app_id}/{section}` — `cover_letter_section` (GET=view, POST=save+view)
- `/_fragments/apply/screener/{app_id}/{q_id}` — `screener_question_card` (GET=view, PUT=save)
- `/_fragments/tracking/board` — `tracking_board`
- `/_fragments/tracking/list` — list of `tracking_list_row`s
- `/_fragments/tracking/followup-banner` — `followup_banner`
- `/_fragments/outreach/app-detail/{id}` — right-pane partial
- `/_fragments/outreach/draft/{contact_id}` — `outreach_message_card`
- `/_fragments/overview/priority-actions` — list of `priority_action_row`s
- `/_fragments/overview/email-signal` — list of `email_signal_row`s
- `/_fragments/overview/pipeline-strip` — `pipeline_strip`
- `/_fragments/onboarding/step/{n}` — step-N partial (`step=1|2|3`)

### E · Visual QA pipeline

For each screen:

1. After implementing the page handler + template, boot dev: `nix run .#dev` (or `uv run fastapi dev src/main.py`).
2. Run a Playwright script (`tests/visual/capture.py`) parametrized over the 11 screens × 2 viewports, saving to `tests/visual/screenshots/<screen>-<viewport>.png`. Script lives at `tests/visual/capture.py`; defaults: desktop 1440×900, mobile 375×812. Authenticated routes get a fake session cookie injected before navigation.
3. Open the bundle JSX via `docs/design/mockups/naavik-handoff/project/index.html` in the local browser and side-by-side compare with the screenshot. Record any deltas in the hand-back report; fix obvious ones, defer ambiguous ones to user review.
4. When visual parity is close enough (within DESIGN.md token tolerances + bundle JSX intent), commit the screenshot alongside the page template + handler.
5. Flip SCREENS.md per-screen `Impl: [~]` → `[x]`; bump SCREENS.md `Last updated:`.

**No CI-side visual diff in plan 09.** The first set of snapshots is the baseline; per-PR diff (Playwright + a comparator like pixelmatch) is a follow-up plan once snapshots stabilize and the team has a sense of how flaky font / scrollbar rendering will be across environments.

**Bundle JSX availability:** the bundle is gitignored locally. If absent, the implementing agent flags it in the hand-back report and falls back to the PDF mockup. Don't block on missing bundle — the PDF + SCREENS.md spec is enough to ship a screen; visual parity refinement happens when the bundle is regenerated.

### F · Discover keyboard map (in `keys.js`)

Plan 08 shipped `keys.js` with an empty registry. Plan 09 fills it for the two screens that need it (per INTERACTIONS.md § F.1):

```javascript
// src/ui/static/keys.js — extended in plan 09
const handlers = {
  "/discover": {
    ArrowLeft: () => click("discover-skip-btn"),
    ArrowRight: () => click("discover-auto-apply-btn"),
    ArrowUp: () => click("discover-save-btn"),
    Enter: () => click("discover-review-btn"),
  },
  "/discover/:id": {
    "meta+k": () => activeTabIs("cover-letter") && triggerRewriteSelection(),
    "meta+Enter": () => activeTabIs("cover-letter") && triggerRegen(),
    "meta+c": () => activeTabIs("cover-letter") && copyCoverLetterToClipboard(),
  },
};
```

Buttons in the Discover swipe action bar carry the matching `id="discover-skip-btn"` etc., so `click(id)` resolves.

The page handler sets `<body data-template="/discover/:id">` (not `data-template="/discover/123"`) — the **template path**, not the URL — per INTERACTIONS.md § F.1.

### G · Per-screen acceptance gate

Each of the 11 screens must pass before the next one starts:

- [ ] Page renders without 500 / Jinja error
- [ ] Composes only partials shipped in plan 08 (no inline ad-hoc markup beyond layout `<div>`s + `<section>`s)
- [ ] Visual parity with bundle JSX at 1440×900 + 375×812 (Playwright snapshot committed)
- [ ] Every interaction noted in SCREENS.md § per-screen § Interactions exists
- [ ] Every HTMX target referenced (`hx-target="#..."`) resolves to an element on the page
- [ ] Browser console clean — no Lucide-not-defined, no Sortable errors, no 404s for `/static/*`, no failed fragment requests
- [ ] Lucide icons paint after any fragment swap on the page (test by triggering one swap manually)
- [ ] Mobile viewport (375×812) renders without broken layouts — test specifically the sidebar drawer, modal bottom-sheet, Tracking stage list
- [ ] SCREENS.md per-screen `Impl: [x]` flipped; SCREENS.md `Last updated:` bumped to today
- [ ] Stub endpoints fire correctly — manual smoke (e.g., on Discover, click Skip → next card swaps in; on Tracking, drag a card → status flips)

### H · Cross-screen acceptance (after all 11)

- [ ] Discover right-swipe creates an in-memory DRAFT Application with `Job.queue_state = QUEUED_FOR_AUTO_APPLY`; the auto-apply queue card on Discover shows it
- [ ] First visit to `/discover/{id}` for a Job without an existing Application creates an in-memory DRAFT (BACKEND.md § K.1) **when `Settings.eager_review_generation=True`**; renders the lazy "Tailor for this job" CTA when `False`
- [ ] **"Stuck in queue · {N}" right-rail card** on Discover renders for DRAFTs with `submission_artifacts.last_failure` populated (test against the seeded fixture row from § B); click → navigates to `/discover/{job_id}` showing a failure banner with `Retry submission` + `Discard draft` actions
- [ ] **Settings · LLM Provider cost cards** (`THIS MONTH` / `AVG / GENERATION` / `RATE LIMIT`) render with realistic numbers from the seeded ApiUsage fixture rows
- [ ] **Settings ships all 6 tabs** with full UI scaffolding: LLM Provider, Deployment, Account, Notifications, Auto-Apply, Sources — each tab navigable via `/settings/{tab}` deep-link
- [ ] **Onboarding step 2 → step 3 auto-progresses** on SSE `done` event via `HX-Trigger: extractionDone` header that swaps `#onboarding-step-content`
- [ ] Tracking default view hides DRAFT + CLOSED; a Phase 1.x `Show drafts` toggle stub is wired (returns DRAFT rows when toggled — actual UI lands in Phase 1.x but the endpoint exists)
- [ ] Confirm modal opens for: Delete bullet, Discard draft application, Disconnect Gmail, Remove experience role
- [ ] Optimistic rollback (H.4) fires on Discover swipe error — test by hitting `/api/v1/discover/{id}/skip?fail=1`
- [ ] Auto-save indicator shows `saving` → `saved` → `error` states correctly (test the error state via `?fail=1` query)
- [ ] Sortable.js works on Profile editor bullet list AND on Tracking Kanban (cross-column drop)
- [ ] All 4 SSE streams stub correctly (extraction, cover-letter, email-signal, log-tail)
- [ ] All 6 keyboard shortcuts in INTERACTIONS.md § F.3 fire on the right pages
- [ ] Tag chips: 9-tag vocabulary only (no invented tags); no sparkle on chips
- [ ] Score circles: 0–100 number, no `%`, no "match" word
- [ ] No re-introduced `/generate/cover-letter` or `/generate/resume` route — both flows live inside `/discover/{id}` only
- [ ] No `kanban-square` icon for Tracking (uses `inbox`)
- [ ] **All sample-data accessors are async** — every signature in `src/db/sample_data.py` is `async def` from day one (so Wave 4's swap is body-only)

### I · Tests

- `tests/test_sample_data.py` — every fixture row round-trips through Pydantic; counts match SAMPLE_DATA.md inventory; visa-rule coverage assertion (≥2 `us_citizen_only` jobs scoring 0); DRAFT coverage (≥2 DRAFT applications); recruiter-silence stress (≥1 `silent ≥ 6d`).
- `tests/test_pages.py` — for each of the 11 screens, GET the route returns 200; assert key markup is present (e.g., on Discover the page contains `id="discover-card"`, on Tracking it contains 4 `[data-column]` elements, on Profile editor it contains `id="autosave-indicator"`). Single parametrized test.
- `tests/test_stub_endpoints.py` — for each stub endpoint in § D.1 + § D.2, smoke-test that the response is 2xx and the response body matches the documented shape (e.g., next-card fragment is `<article id="discover-card">...`, autosave-indicator is `<div id="autosave-indicator" hx-swap-oob="outerHTML">`, etc.). Includes the `?fail=1` failure-mode tests.
- `tests/test_draft_lifecycle.py` — the DRAFT state machine: GET `/discover/{job_id}` creates a DRAFT; POST `/api/v1/applications/{id}/submit` flips to APPLIED; DELETE `/api/v1/applications/{id}/discard` flips to CLOSED with `closed_reason=withdrawn_by_me`; submitting a DRAFT with unreviewed required screener answers returns 409.
- `tests/visual/capture.py` — Playwright parametrized capture script (manual run, not part of `uv run pytest` default).

All tests run via `uv run pytest tests/` (excluding `tests/visual/`).

### J · Risks + mitigations

| Risk                                                                                        | Mitigation                                                                                                                                                                                                             |
| ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Sample-data drift from DATA_MODEL.md**                                                    | `tests/test_sample_data.py` round-trip catches every field add/remove; sample_data_models.py mirrors DATA_MODEL.md § C 1:1                                                                                             |
| **Stub endpoint shape drift from BACKEND.md**                                               | `tests/test_stub_endpoints.py` asserts exact response shapes; plan 10 reuses the same test file when it swaps stubs for real handlers                                                                                  |
| **Discover · review & apply complexity**                                                    | Escalation criterion in § C: >250 LOC OR >1.5 days → spawn `09a-discover-review-impl.md`; the implementing agent makes the call mid-session and reports it back                                                        |
| **Playwright dep not in dev shell**                                                         | Add `python312Packages.playwright` (or `playwright` via uv) to `nix/devshell.nix`; `playwright install chromium` runs once on first dev-shell entry. Documented in plan 09 + the kickoff prompt.                       |
| **Bundle JSX gitignored locally**                                                           | If absent, agent uses PDF mockup + SCREENS.md spec; flags missing bundle in hand-back. Visual parity refinement happens when bundle regenerates.                                                                       |
| **In-memory mutation surprises**                                                            | Document in `sample_data.py` module docstring + Settings · Deployment "Server restart resets state" hint card. Sample-data tests use a fixture that resets state between runs.                                         |
| **SSE stub timing flake in tests**                                                          | Stub streams use deterministic delays; tests poll for completion or assert on the final event without timing assertions.                                                                                               |
| **`hx-boost`'d links navigate too aggressively**                                            | Add `hx-boost="false"` to: external "Open ATS · greenhouse.io" links, Settings tab links across `/settings/{tab}` (deep-link case, full nav still preferred), Bundle download `/api/v1/applications/{id}/bundle` link. |
| **Mobile sidebar drawer regression after plan 08**                                          | `tests/test_pages.py` includes a mobile-viewport assertion for one authenticated page (asserts `body[data-sidebar-open]` toggles via the hamburger).                                                                   |
| **`hx-headers` JSON-quoting collision** with the body's `'{"X-CSRF-Token": "..."}'` pattern | Plan 08 already used the standard double-quote pattern; verify the rendered HTML doesn't have stray quote escaping. Smoke test on every page.                                                                          |
| **Mobile drag-drop on Tracking Kanban**                                                     | Sortable.js handles touch devices natively; manual smoke on a real phone or BrowserStack — Playwright `--device="iPhone 12"` captures the visual but doesn't simulate touch-drag. Doc in hand-back.                    |
| **Optimistic rollback brittleness**                                                         | Tests in `tests/test_optimistic_rollback.py` (smaller file) cover the canonical happy + failure paths for Discover swipe and Kanban drop.                                                                              |

### K · Build order (informational calendar)

11 screens at ~3–6h each + sample_data.py + tests. Realistic ship: 8–12 working days.

```
Day 1: sample_data.py + sample_data_models.py + accessor catalog + tests/test_sample_data.py
Day 2: 9.1 Login + 9.2 Settings (LLM tab + Deployment tab — others stubbed)
Day 3: 9.3 Profile read-only + 9.4 Profile editor (per-field autosave + bullet drag-drop)
Day 4: 9.5 Bullet editor modal + 9.6 Onboarding (3 steps + SSE extraction stub)
Day 5: 9.7 Overview (KPI strip + priority actions + email signal SSE + pipeline strip)
Day 6: 9.8 Tracking (board + list views; Sortable Kanban + optimistic rollback)
Day 7: 9.9 Outreach (2-pane + recommended move + AI draft)
Day 8: 9.10 Discover (swipe queue + keyboard handlers + right rail)
Day 9-10: 9.11 Discover · review & apply (3-column workspace; SSE cover letter; screener review; DRAFT lifecycle); escalate to 09a if scope balloons
Day 11: cross-screen acceptance (§ H); Playwright snapshot pass; SCREENS.md `Impl:` flips; archive plan + prompt
```

The kickoff prompt sequences these; plan 09 doesn't enforce a calendar.

### L · Out-of-scope items explicitly forbidden

- ❌ DB persistence (plan 10 Wave 3)
- ❌ Real LLM calls (plan 10 Wave 6)
- ❌ Real Typst compilation (plan 10 Wave 6)
- ❌ Real auth (plan 10 Wave 3)
- ❌ Real ATS submission (plan 10 Wave 6)
- ❌ Real scrapers / cron / email / outreach (Phase 2-5)
- ❌ Re-introducing oneline/detailed bullet split
- ❌ Re-introducing `/generate/cover-letter` or `/generate/resume` standalone routes — both folded into `/discover/{id}` only
- ❌ Re-introducing flat status enum without DRAFT — 6-value pipeline locked
- ❌ Adding Funnel / BarChart / LineChart to Overview — Phase 6
- ❌ Re-introducing AI sparkle on tag chips — sparkle is for AI content only
- ❌ Light mode — Phase 6
- ❌ OIDC / SSO for self-hosted — Phase 2+
- ❌ Manual job entry full modal (only `+ Add by URL` lite path on Discover; full modal Phase 1.x)
- ❌ Application detail slide-over on Tracking — Phase 1.x sub-prompt
- ❌ `Show drafts` UI on Tracking (the endpoint exists in plan 09 stubs; the UI toggle lands Phase 1.x)
- ❌ CI-side visual regression diffing — follow-up plan once snapshots stabilize
- ❌ Theme toggle in sidebar
- ❌ DaisyUI classes (already removed in plan 08)

## Open questions

1. **Sample-data module two-file split: `sample_data_models.py` (Pydantic) + `sample_data.py` (instances).** Recommendation: **keep two files**. Plan 10 Wave 3 introduces `src/models/*.py` as `SQLModel(table=True)`; if Pydantic models lived in `models/` from the start they'd collide with SQLAlchemy registration. The two-file split keeps plan 09 clean and the swap mechanical. Risk if we don't: sample_data_models.py becomes redundant in plan 10. Cost to swap later: trivial (delete + reroute imports).

2. **In-memory mutation scope.** Should stub endpoints persist across requests (server-process scoped) or be purely read-only? Recommendation: **persist**, otherwise interactions like "drag a Tracking card" don't visually move it and the screen feels broken. Document the "server restart resets state" caveat. Open: should the dev orchestrator (`nix run .#dev`) trigger reload + state clear on file change, or preserve mutation across reloads? Recommend **reload clears state** — predictable baseline.

3. **Playwright in dev shell.** Add `playwright` to `nix/devshell.nix` now (plan 09 ships it) or document install instructions and let the agent install ad hoc? Recommendation: **add to devshell now**. One-time `playwright install chromium` per dev shell entry; reproducible across machines.

4. **Per-screen sub-plan threshold.** Currently set at >250 LOC OR >1.5 days. Is that right, or should we be more conservative (e.g., >150 LOC) so sub-plans spawn earlier? Recommendation: **250 LOC**. Splitting too early creates plan/prompt churn; the agent's judgment in-session is the better signal.

5. **Snapshot baseline commit.** Commit the Playwright snapshots alongside the code (in `tests/visual/screenshots/`) or in a separate "snapshots" PR? Recommendation: **alongside the code**. Each screen's snapshot lands with its template + handler in the same commit.

6. **SSE stubbing mechanism.** Real `text/event-stream` server response with `asyncio.sleep` between chunks (HTMX SSE consumer works), or HTMX polling fallback (per INTERACTIONS.md § C.2)? Recommendation: **real SSE**. Polling fallback is documented; the primary path is SSE because that's what plan 10 will keep.

7. **Auth bypass for plan 09.** Plan 10 Wave 3 wires real auth; plan 09 has no auth dep. Should plan 09's page handlers skip the auth check entirely (any cookie OK), or simulate the auth flow with a fake session cookie set on `POST /api/v1/auth/login`? Recommendation: **simulate fake session**. `POST /api/v1/auth/login` sets a `naavik_session=fake-1` cookie; subsequent page handlers check for ANY value on that cookie. `POST /api/v1/auth/logout` clears it. This matches the eventual auth flow shape and exercises the redirect-to-login behavior; plan 10 swaps the cookie value for a real JWT.

8. **`+ Add by URL` modal scope.** SCREENS.md says "+ Add by URL" is the partial Phase 1 path. Should plan 09 implement it as a full modal flow (paste URL → scrape preview → confirm → enter queue) using a stub `/api/v1/jobs/by-url`? Recommendation: **yes — full modal flow with stub scrape**. The stub returns a hardcoded "scraped" job. Same for the manual entry on Tracking (`+ Add manually`). These exercise the modal pattern and the manual flow — small lift, high coverage.

9. **`Show drafts` toggle.** SCREENS.md defers the UI toggle to Phase 1.x. Should plan 09 wire the endpoint behind it (`GET /api/v1/applications?status=DRAFT`)? Recommendation: **wire the endpoint, hide the UI toggle**. Plan 10 / Phase 1.x flips the UI toggle.

## Approval checklist

User ticks each item before plan moves to APPROVED. Agent does NOT author the kickoff prompt until all are ticked.

### Scope coherence

- [x] § A — 11 page templates + sample data module + stub fragment + JSON endpoints + per-screen Playwright snapshots is one coherent unit
- [x] Out-of-scope list correctly defers DB / auth / LLM / Typst / ATS / scrapers / observability to plan 10 + later phases

### Sample data module (§ B)

- [x] Two-file split (`sample_data_models.py` + `sample_data.py`) — Pydantic now, SQLModel in plan 10 Wave 3
- [x] Inventory matches SAMPLE_DATA.md exactly (1 User, 1 Profile, 4 Experiences, 14 Bullets, ..., 1 Settings; ~150 AppEvents; 14 Applications incl. 2 DRAFT)
- [x] In-memory mutation shim documented (server-process scoped; reset on restart)
- [x] All 14 realism rules from SAMPLE_DATA.md § N enforced
- [x] `tests/test_sample_data.py` round-trip validates every fixture

### Per-screen build order (§ C)

- [x] 11 screens in simplest-first order (Login → Settings → Profile → Profile editor → Bullet modal → Onboarding → Overview → Tracking → Outreach → Discover → Discover · review & apply)
- [x] Each screen names its bundle JSX + SCREENS.md section + page handler module + key interaction patterns
- [x] Sub-plan escalation criterion explicit (>250 LOC OR >1.5 days → 09a sub-plan)

### Stub-handler convention (§ D)

- [x] Same URLs as BACKEND.md § C / § D — plan 10 swaps in real handlers without changing pages
- [x] Same response shapes — Pydantic models for JSON, real partials for HTML fragments
- [x] Limited in-memory mutation (server-process scoped)
- [x] No real I/O (no DB, no LLM, no Typst, no ATS, no email)
- [x] `?fail=1` failure-mode query for testing optimistic rollback + error toasts
- [x] Endpoint inventory in § D.1 + § D.2 covers every page interaction

### Visual QA pipeline (§ E)

- [x] Playwright capture at 1440×900 + 375×812
- [x] Snapshots committed to `tests/visual/screenshots/`
- [x] Bundle JSX side-by-side comparison; PDF mockup fallback if bundle absent
- [x] No CI-side diff in plan 09 (follow-up plan)
- [x] SCREENS.md `Impl:` flip on each screen ship

### Discover keyboard map (§ F)

- [x] `keys.js` extended with `'/discover'` and `'/discover/:id'` maps
- [x] Buttons carry `id="discover-skip-btn"` etc. for handler-click resolution
- [x] `<body data-template="/discover/:id">` carries the **template path**, not the URL

### Acceptance gates (§ G + § H)

- [x] Per-screen gate: page renders + composes only plan 08 partials + visual parity + interactions exist + console clean + Lucide repaints + mobile renders + SCREENS.md flipped + stub smoke
- [x] Cross-screen gate: DRAFT auto-creation works, Tracking hides DRAFT/CLOSED, confirm modals open for destructive actions, optimistic rollback works on `?fail=1`, all SSE stubs fire, all keyboard shortcuts work, tag-vocab + score-rules respected, no `/generate/*` routes, no `kanban-square`

### Tests (§ I)

- [x] `tests/test_sample_data.py` — round-trip + count + realism rules
- [x] `tests/test_pages.py` — per-screen GET + key markup
- [x] `tests/test_stub_endpoints.py` — every stub endpoint shape + `?fail=1` paths
- [x] `tests/test_draft_lifecycle.py` — DRAFT state machine
- [x] `tests/visual/capture.py` — Playwright parametrized capture (manual run)

### Risks (§ J)

- [x] Sample-data drift caught by round-trip test
- [x] Stub endpoint shape drift caught by stub-endpoint tests
- [x] Discover · review escalation criterion explicit
- [x] Playwright added to nix devshell.nix
- [x] Bundle JSX absence handled (PDF fallback)
- [x] In-memory mutation reset on restart documented
- [x] SSE stub timing avoids flake
- [x] `hx-boost="false"` on external/special links

### Out-of-scope (§ L)

- [x] No DB / auth / LLM / Typst / ATS / scrapers (plan 10)
- [x] No oneline/detailed bullet split, no `/generate/*` routes, no flat status enum without DRAFT
- [x] No Funnel/BarChart/LineChart on Overview
- [x] No AI sparkle on tag chips
- [x] No light mode / theme toggle
- [x] No OIDC / SSO (Phase 2+)
- [x] No CI-side visual diff (follow-up plan)

### Open questions (§ Open questions)

- [x] Q1 Two-file split for sample data — agree?
- [x] Q2 In-memory mutation scope (persist within process, reset on restart) — agree?
- [x] Q3 Playwright in nix devshell.nix now — agree?
- [x] Q4 Sub-plan threshold at >250 LOC — agree?
- [x] Q5 Snapshots commit alongside code — agree?
- [x] Q6 Real SSE (not polling fallback) — agree?
- [x] Q7 Auth simulation via fake session cookie — agree?
- [x] Q8 `+ Add by URL` modal as full flow with stub scrape — agree?
- [x] Q9 `Show drafts` endpoint wired without UI toggle — agree?

Once every box is ticked, plan moves to APPROVED. Agent then authors `docs/prompts/09-stage-3-impl.md` driving a fresh implementation session (after plan 10 is also approved, per the user's reorder request 2026-05-01).
