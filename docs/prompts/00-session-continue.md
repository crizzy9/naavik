---
Status: ACTIVE
Type: prompt
Authored: 2026-04-30
Last updated: 2026-04-30
Purpose: Kickoff prompt for a fresh Claude Code session to author plans 08–10 (Stage 2 component lib + Stage 3 page templates + backend implementation) and their kickoff prompts. Successor to docs/prompts/archive/00-session-continue-2026-04-30.md.
---

# Naavik · session-continue prompt (Wave 2 — implementation kickoffs)

You're picking up Naavik mid-stream in a fresh session. The repo lives at `/home/nightwatcher/personal/dev/naavik`. Read these files in order — they're the canonical context:

1. `AGENTS.md` — agent guide + canonical workflow lifecycle (read § Workflow carefully)
2. `ROADMAP.md` — phase plan + progress
3. `DESIGN.md` (root) — visual contract: tokens, typography, components, voice
4. `docs/design/SCREENS.md` — 11-screen MVP catalog (functional contract per screen)
5. `docs/design/COMPONENTS.md` — 85-component library (graduated from plan 03)
6. `docs/design/BACKEND.md` — backend architecture (HTTP routes + services + cron + scrapers + ATS adapters + LLM + observability; graduated from plan 04)
7. `docs/design/DATA_MODEL.md` — 18 SQLModel entities + Settings (graduated from plan 05)
8. `docs/design/INTERACTIONS.md` — cross-cutting HTMX patterns (graduated from plan 06)
9. `docs/design/SAMPLE_DATA.md` — Phase 1 hardcoded fixtures (graduated from plan 07)
10. `docs/design/WORKFLOW.md` — UI sub-process (mockup → component → page)
11. `docs/plans/README.md` — plan-file conventions
12. `docs/plans/02-mvp-master-plan.md` — master plan (APPROVED, active)
13. `docs/plans/archive/03-component-catalog.md` through `07-sample-data.md` — graduation notes (each archived plan front-matter carries a detailed list of every Tier-1/2/3 fix folded in during graduation)
14. `docs/plans/archive/01-docs-realignment.md` — historical record (executed 2026-04-30)
15. `docs/prompts/archive/00-session-continue-2026-04-30.md` — predecessor session-continue prompt (USED)

Mockups (gitignored, locally only): `docs/design/mockups/Naavik — MVP screens (print).pdf` + bundle JSX at `docs/design/mockups/naavik-handoff/project/screens/<ScreenName>.jsx`. See `docs/design/mockups/README.md` for layout. Each `SCREENS.md` entry names its bundle JSX file. Bundle obsolete files to ignore: `Analytics.jsx`, `Dashboard.jsx`, `Jobs.jsx`, `ResumeGen.jsx`, `CoverLetter.jsx`.

## Where we are (state as of 2026-04-30 commit)

**Wave 0 (doc realignment) — COMPLETE.** Plan 01 archived 2026-04-30.

**Wave 1 (design docs) — COMPLETE.** Plans 03–07 graduated to `docs/design/`:

| Plan | → Design doc | Notable |
|---|---|---|
| 03 | `docs/design/COMPONENTS.md` | 85 components across 12 groups; full specs incl. 13 new components added during graduation (`bullet_textarea`, `confirm_modal`, `spinner`, `toast`, `empty_state`, `avatar`, `connection_status_card`, `deployment_badge`, 5 skeletons) |
| 04 | `docs/design/BACKEND.md` | Routes + 14 services + 7 ATS adapters + cron + scrapers + LLM abstraction + vault boundary + observability |
| 05 | `docs/design/DATA_MODEL.md` | 18 SQLModel entities + Settings; full DRAFT cascade through enum / state machines / KPIs; AppEvent payload schemas (§ M); Settings consumer mapping (§ L) |
| 06 | `docs/design/INTERACTIONS.md` | HTMX swap conventions, 6 form patterns (incl. file upload + tag chip toggle), SSE, drag-drop, modals (E.4 confirm modal centralized), keyboard shortcuts, toasts, errors (incl. H.4 optimistic UI rollback), base.html cross-cutting attrs |
| 07 | `docs/design/SAMPLE_DATA.md` | Phase 1 fixtures: 1 Profile, 4 Experiences, 14 Bullets, ~20 Jobs, 14 Applications (incl. 2 DRAFT), ~20 Contacts, ~40 OutreachMessages, ~20 EmailThreads, ~150 AppEvents, ~30 GeneratedDocuments, ~20 ApplicationScreenerAnswers, 1 Settings |

**Tier-1 cascade locked across the docset:** `Application.status` is a six-stage enum (`DRAFT · APPLIED · RECRUITER_SCREEN · ONSITE_LOOP · OFFER · CLOSED`). DRAFT is pre-submission, hidden in Tracking by default, surfaced in Discover · review & apply (manual path) and the Auto-apply queue card on Discover (auto-apply path). DESIGN.md bumped to v1.3.

**Plan status:**

- 02 (Master plan) — APPROVED, active.
- 03 / 04 / 05 / 06 / 07 — GRADUATED + archived.
- 08 (Stage 2 component library impl) — **NOT YET AUTHORED**. Spawns from this prompt.
- 09 (Stage 3 page implementation) — **NOT YET AUTHORED**. Spawns after plan 08 is approved.
- 10 (Backend implementation, multi-wave) — **NOT YET AUTHORED**. Spawns after plan 09 is approved (it consumes BACKEND.md + DATA_MODEL.md exhaustively).

**Prompts status:**

- `docs/prompts/archive/00-session-continue-2026-04-30.md` — USED 2026-04-30 (drove the Wave 1 graduation session).
- `docs/prompts/00-session-continue.md` — this file.
- `docs/prompts/archive/HANDOFF_PROMPT.md`, `docs/prompts/archive/CLAUDE_DESIGN_PROMPT.md` — used during the mockup batch (April 2026).
- `08-stage-2-impl.md`, `09-stage-3-impl.md`, `10-backend-impl.md` — to be authored this session, AFTER each corresponding plan is approved.

## Mission for this session

In order:

1. **Author plan 08 (Stage 2 component library implementation)** at `docs/plans/08-stage-2-impl.md`. Format per `docs/plans/README.md`. Scope: turn `docs/design/COMPONENTS.md` into actual Jinja partial files at `src/ui/templates/components/` plus `_macros.html`, `base.html` refinements per COMPONENTS.md § F, and the `/_design/components` fixture page per COMPONENTS.md § F.3. Build order per COMPONENTS.md § G (Shell first → Atomics → Forms → Onboarding → Profile/Bullet → Overview → Discover → Discover-review → Tracking → Outreach → Settings → Skeletons). Acceptance criteria: 85 component files exist, every component renders without error in `/_design/components`, `uv run ruff check` passes, Lucide icons render after fragment swaps, all required `base.js` handlers (per COMPONENTS.md § F.2 + INTERACTIONS.md § I.1) are wired.

2. **Pause for user review of plan 08.** User reads, ticks the approval checklist, calls out issues. Revise until APPROVED. **Do not author the kickoff prompt until plan 08 is APPROVED.**

3. **Author kickoff prompt 08** at `docs/prompts/08-stage-2-impl.md`. Per `AGENTS.md` § Workflow, the prompt is what the user pastes into a fresh Claude Code session to drive the actual coding. Required sections: Goal, Required reading, Deliverables, Quality bar, Forbidden patterns, Hand-back format. Reference COMPONENTS.md + DESIGN.md + INTERACTIONS.md + bundle JSX as the visual source of truth.

4. **Author plan 09 (Stage 3 page implementation)** at `docs/plans/09-stage-3-impl.md`. Scope: per-screen page handlers in `src/ui/routes/` returning `HTMLResponse` with hardcoded sample data imported from `src/db/sample_data.py` (per SAMPLE_DATA.md). Build order: simplest first — Login → Settings → Profile → Profile editor → Bullet modal → Onboarding → Overview → Tracking → Outreach → Discover → Discover · review & apply. Visual QA: Playwright screenshot at desktop (1440×900) + mobile (375×812), compare to bundle JSX. Acceptance: every screen renders without error, matches mockup, every interaction noted in SCREENS.md exists (even when stub-handler-backed). Per-screen sub-plans only escalate if a screen turns out more complex than expected (Discover · review & apply being the likely candidate).

5. **Pause for user review of plan 09.** Revise until APPROVED.

6. **Author kickoff prompt 09** at `docs/prompts/09-stage-3-impl.md`. Same lifecycle as plan 08's prompt. Per-screen reading list (each screen's bundle JSX + SCREENS.md section + COMPONENTS.md component-to-screen index from § J).

7. **Author plan 10 (backend implementation)** at `docs/plans/10-backend-impl.md`. Scope: implement BACKEND.md exhaustively. Multi-wave per master plan § C: Wave 3 (initial models + auth), Wave 6 (real backend — all services, LLM abstraction, Typst compilation), Phase 2+ (scrapers + cron + auto-apply + email + outreach + observability). The plan should split clearly along these waves so the kickoff prompt can drive Wave 3 + Wave 6 first while Phase 2+ work waits for its time. Acceptance: SQLModel models match DATA_MODEL.md 1:1, Alembic initial migration creates every table + enum + index, all routes from BACKEND.md § B–D respond, sample data seeded via `src/db/seed.py` consuming `src/db/sample_data.py`. Vault boundary enforced (no secrets in DB). LLM abstraction + cost tracking via ApiUsage. Auth (JWT cookie + bcrypt) lands.

8. **Pause for user review of plan 10.** Revise until APPROVED.

9. **Author kickoff prompt 10** at `docs/prompts/10-backend-impl.md`. Same lifecycle.

You don't write actual application code in this session — that happens in the implementation sessions triggered by `docs/prompts/08`, `09`, `10`. The deliverable here is plans + prompts.

## What this session does NOT do

- ❌ No application code (`src/**/*.py`, `src/ui/templates/**/*.html`, `migrations/versions/*.py`)
- ❌ No `nix run .#dev`, no Playwright screenshots, no `uv run alembic upgrade`, no `uv run ruff check` against actual code
- ❌ No graduating already-graduated docs in `docs/design/`
- ❌ No modifying SCREENS.md / DESIGN.md / DATA_MODEL.md / BACKEND.md / INTERACTIONS.md / SAMPLE_DATA.md / COMPONENTS.md unless the user explicitly identifies a contract bug that needs fixing before plan 08–10 can be authored coherently
- ❌ No skipping plan-review gates ("just go ahead and author the prompt") — each plan must be APPROVED by the user before its kickoff prompt is authored

## What comes after this session (separate fresh sessions, kicked off by the prompts authored here)

The lifecycle (per `AGENTS.md` § Workflow) for each implementation plan:

```
This session              Implementation session (fresh paste of the prompt)
─────────────────────     ──────────────────────────────────────────────
Author plan 08    ──→     Implement 85 Jinja partials + base.html refinements
Author prompt 08          + _macros.html + /_design/components fixture page
                          (paste docs/prompts/08-stage-2-impl.md)

Author plan 09    ──→     Implement 11 page templates + Playwright visual QA
Author prompt 09          (paste docs/prompts/09-stage-3-impl.md)

Author plan 10    ──→     Implement SQLModel models + Alembic + LLM abstraction
Author prompt 10          + auth + services. Plan 10 may split into per-wave
                          sub-prompts (10a Wave 3, 10b Wave 6, 10c Phase 2+).
                          Each sub-prompt = its own fresh impl session.
```

**Minimum 4 fresh sessions ahead** (1 planning [this one] + 3 implementation). Realistically 5–7 because plan 10 splits per-wave and Discover · review & apply (the most complex Stage 3 screen) may escalate to its own sub-plan.

After each implementation session lands code:

- Plan moves to `docs/plans/archive/` with `Status: EXECUTED` (or `GRADUATED → ...` if the plan also produced a design doc, but plans 08–10 are pure execution plans, no graduation).
- Prompt moves to `docs/prompts/archive/` with `Status: USED`.
- ROADMAP.md task(s) marked `[x]` with deliverable note.
- The implementation-session's agent does this archival as the last step before handing back.

**You (the user) drive the implementation sessions** by pasting the kickoff prompt into a fresh Claude Code window. The prompts are self-contained — they list every file to read, every file to write, every check to run, and every forbidden pattern. You don't have to re-explain context.

## Hard rules (non-negotiable)

- **Tech stack:** HTMX + Jinja2 + Tailwind CSS + DaisyUI + Lucide icons (stroke 1.5). No JS framework (no React, Vue, Svelte, Solid). No Bootstrap. No Heroicons / Phosphor.
- **11-screen MVP** per `docs/design/SCREENS.md`. **No `/generate/*` routes** — resume tailoring + cover letter drafting both live inside Discover · review & apply (`/discover/:id`).
- **Application status: 6 values** per `docs/design/DATA_MODEL.md` § D — `DRAFT · APPLIED · RECRUITER_SCREEN · ONSITE_LOOP · OFFER · CLOSED`. Tracking hides DRAFT + CLOSED by default. Multi-axis sub-states (`docs_state`, `referral_state`, `recruiter_state`) are independent of status.
- **Single long-form bullets.** No `oneline` / `detailed` split. No `default_include` toggle. No metric (`revenue` / `percentage` / `team_size`) sub-fields. AI trims at apply time using `selection_override`.
- **Tag chips:** 9-tag vocabulary only (`ai-ml · backend · frontend · devops · data-eng · genai · leadership · platform · product`). **Never with AI sparkle** (sparkle is for AI-generated content only — cover-letter paragraphs, drafted screener answers, recommended outreach moves, model attribution).
- **Score circle:** 0–100 number, no `%` mark, no "match" word.
- **Single dark mode.** No light variants in MVP.
- **Sidebar IA:** Overview · Profile · Jobs (`/discover`) · Tracking · Outreach · Settings. Tracking icon is `inbox` (per SCREENS.md, **not** `kanban-square` from bundle). Sidebar width 256px (per DESIGN.md, **not** 240px from bundle).
- **No charts on Overview in MVP.** Funnel / BarChart / LineChart from bundle's `Overview.jsx` are leftovers from when Analytics was on Overview — explicitly NOT in MVP, deferred to Phase 6.
- **Secrets boundary:** the DB stores no secret material. Anthropic / OpenAI / Ollama API keys, OAuth refresh tokens, ATS cookies, Discord/Telegram tokens, Netlify build hooks — all live encrypted on disk at `~/.naavik/secrets.enc` (AES-256-GCM, key from `SECRET_KEY` env). Settings stores at most a sha256 fingerprint or "configured" boolean. ATSCredential rows hold metadata only.
- **Modal-confirm route:** `GET /_modal/confirm?title=&message=&action=&label=&tone=&method=` (query params), **not** `/_modal/confirm/{action_id}` (path param).
- **Resume upload route:** `POST /api/v1/extraction/upload` (per BACKEND.md), **not** `/api/v1/profile/upload-resume`.
- **Manual application logger route:** `POST /api/v1/applications/manual` (per BACKEND.md fix), **not** `/api/v1/applications/{id}/manual`.

## Workflow rules

- Always read `AGENTS.md` § Workflow before starting any non-trivial task. It's the contract.
- Plans live in `docs/plans/`. Front-matter required: `Status` (DRAFT → AWAITING REVIEW → APPROVED → EXECUTED / GRADUATED), `Type` (execution / design / implementation), `Authored`, `Last updated`, `Depends on`. **No `Approved` field** — that's not part of the convention.
- Approval checklist at the bottom of every plan. User ticks; agent doesn't proceed without approval.
- After execution / graduation, plan moves to `docs/plans/archive/` with terminal status + a graduation note in the front-matter listing every fix folded in.
- Implementation prompts at `docs/prompts/`. After implementation lands, prompt moves to `docs/prompts/archive/` with `Status: USED`.
- Mockup references: each plan / design doc that touches a screen names the relevant bundle JSX file (per SCREENS.md per-screen "Mockup:" lines). Mockups are gitignored locally — read them when on disk; flag if missing.
- Prefer `context7` MCP for library docs (FastAPI, SQLModel, HTMX, DaisyUI, Lucide, Sortable.js, etc.) over web search.
- Use `impeccable` skill primarily during plan 08 + plan 09 graduation/implementation prompt authoring (UI design judgement). `frontend-design` skill paired when distinctive code is needed. `claude-api` skill for plan 10's LLM abstraction work.
- Use `TaskCreate` to track plan-by-plan progress through the session. Mark each task `in_progress` when starting, `completed` when done.

## Per-plan scope sketches

### Plan 08 — Stage 2 component library implementation

What to write into the plan:

- **Goal:** Implement `docs/design/COMPONENTS.md` 1:1 — produce 85 Jinja partials + `_macros.html` + `base.html` refinements + `/_design/components` fixture page.
- **Build batches** (per COMPONENTS.md § G):
  1. Shell + base.html refinements (5 components: `auth_shell`, `sidebar`, `version_pill`, `api_status_dot`, `deployment_badge`)
  2. Atomics (15: `button`, `input`, `card`, `tag_chip`, `status_dot`, `status_badge`, `score_circle`, `ai_badge`, `kbd`, `field_label`, `info_card`, `spinner`, `toast`, `empty_state`, `avatar`)
  3. Forms (5: `editor_field`, `editor_card`, `autosave_indicator`, `modal`, `confirm_modal`)
  4. Onboarding (5: `step_indicator`, `dropzone`, `extraction_checklist`, `extracted_field_row`, `progress_bar`)
  5. Profile / Bullet (11: `profile_hero`, `contact_chip`, `experience_card`, `bullet_row`, `section_anchor_nav`, `application_readiness_card`, `application_qs_form`, `bullet_edit_row`, `tag_picker`, `selection_override`, `bullet_textarea`)
  6. Overview (4: `kpi_card`, `priority_action_row`, `email_signal_row`, `pipeline_strip`)
  7. Discover (8)
  8. Discover · review & apply (6)
  9. Tracking (8)
  10. Outreach (6)
  11. Settings (7)
  12. Skeletons (5)
- **Validation per batch:** `uv run ruff check`, every component renders in `/_design/components` fixture page without error, Lucide icons present.
- **`base.html` refinements** (COMPONENTS.md § F): full layout with persistent IDs (`#modal-region`, `#toast-region`, `#sidebar-badge-jobs`, `#sidebar-badge-tracking`), `hx-boost`, `hx-headers`, `hx-ext="sse,response-targets"`, `data-template`. Required `base.js` scripts: Lucide reinit, Sortable.js auto-init, modal-close listener, toast auto-dismiss, optimistic rollback, upload progress. Macros imported via `{% from "components/_macros.html" import ... %}`.
- **`/_design/components` fixture page** (COMPONENTS.md § F.3): renders every component in every variant. Gated on `Settings.debug`. Useful for visual QA during plan 08 implementation.
- **Acceptance:** component count matches COMPONENTS.md § A inventory (85). Every screen's "Components used" list (COMPONENTS.md § J) is satisfiable by combining existing partials. No inline styles, no arbitrary hex (`[#...]`) values. No script tags inside fragment responses.

### Plan 09 — Stage 3 page implementation

What to write into the plan:

- **Goal:** Per-screen page handlers in `src/ui/routes/` rendering Jinja templates with hardcoded sample data imported from `src/db/sample_data.py`.
- **Per-screen build order** (simplest first):
  1. Login (form-only, no sidebar)
  2. Settings (tabbed, mostly read-only at Phase 1)
  3. Profile (read-only)
  4. Profile editor (per-field autosave, drag-drop, modal)
  5. Bullet editor modal (component-only, opens from #4 + #8)
  6. Onboarding (3-step wizard)
  7. Overview (KPI strip + priority actions + email signal + pipeline strip)
  8. Tracking (Kanban board + list view)
  9. Outreach (2-pane)
  10. Discover (swipe queue)
  11. Discover · review & apply (3-column workspace; most complex)
- **Sample data wiring:** every page handler imports the relevant accessor from `src/db/sample_data.py` (per SAMPLE_DATA.md § M). Accessors: `discover_queue()`, `applications_visible_in_tracking()`, `applications_in_followup_state()`, `priority_actions()`, `auto_apply_queue()`, `draft_applications()`, etc.
- **HTMX wiring:** every interaction noted in SCREENS.md exists, even if stub-handler-backed (returns sample-data fragment, doesn't persist). Routes match BACKEND.md § B–C exactly.
- **Visual QA:** for each screen, Playwright screenshot at 1440×900 (desktop) + 375×812 (mobile), saved to `tests/visual/screenshots/<screen>-<viewport>.png`. Compare to bundle JSX rendered in Claude Design (or the PDF page). Update SCREENS.md per-screen `Impl:` checkbox to `[x]` when shipped.
- **Acceptance:** all 11 screens render. Tracking hides DRAFT + CLOSED by default. Discover · review & apply auto-creates a DRAFT Application on first visit (per BACKEND.md § K.1). All keyboard shortcuts wired (`/discover`, `/discover/:id` cover-letter mode). All HTMX targets (`#modal-region`, `#toast-region`, `#sidebar-badge-*`) work end-to-end.
- **Per-screen sub-plans:** if Discover · review & apply turns out more complex than expected, escalate to a sub-plan (`09a-discover-review-impl.md`).

### Plan 10 — Backend implementation

What to write into the plan:

- **Goal:** Implement `docs/design/BACKEND.md` exhaustively. Build SQLModel models per `docs/design/DATA_MODEL.md`. Replace hardcoded sample data with DB-backed handlers.
- **Wave split** (per master plan § C):
  - **Wave 3 (initial backend):** SQLModel for all 18 entities + Settings; Alembic initial migration; auth (JWT + bcrypt); LLM abstraction (`llm/base.py`, anthropic, openai, ollama implementations + cost tracking); profile_service partial; settings persistence (with vault boundary). Page routes from BACKEND.md § B respond. JSON API auth + profile endpoints respond.
  - **Wave 6 (real backend):** all 14 services from BACKEND.md § H complete. Document generation pipeline (Typst compile + bullet selection + page-count validation). Application_service DRAFT lifecycle. ApplicationScreenerAnswer model + lifecycle. ATS adapter dispatcher (greenhouse / lever / ashby for Phase 1.x). Vault service for `~/.naavik/secrets.enc`. Page handlers replace sample-data accessors with DB queries.
  - **Phase 2+:** scrapers (`scraper/*`), scraping cron, auto-apply pipeline, scoring, AppEvent emission everywhere.
  - **Phase 4+:** email integration (Gmail OAuth + IMAP), email_classifier, derive_recruiter_states cron.
  - **Phase 5+:** outreach (LinkedIn browser, outreach_generator, contact_tracker), Discord / Telegram / Calendar.
  - **Phase 6+:** Prometheus metrics, Sentry, OTel tracing.
- **Plan 10 may split into per-wave sub-plans** if the scope exceeds reasonable single-plan size: `10a-wave-3-models-auth-llm.md`, `10b-wave-6-services-pipeline.md`, `10c-phase-2-scrapers-cron.md`, etc. Use judgment when authoring.
- **Acceptance per wave:** model round-trip tests (`tests/test_sample_data.py` validates fixtures round-trip through Pydantic), `uv run alembic upgrade head` succeeds, `uv run pytest` passes, `uv run ruff check` passes. Vault boundary verified (no secrets in DB rows; rg-grep `secrets.enc` is the only place secret material lands).
- **Security review** (`security-review` skill) after auth lands and before Wave 6 ships. Especially: bcrypt cost, JWT cookie flags (HttpOnly + SameSite=Strict), CSRF double-submit, vault key derivation.

## When in doubt

- Spec ambiguity: `docs/design/SCREENS.md` > `DESIGN.md` > mockup (bundle JSX) > ask the user.
- Component already exists in `docs/design/COMPONENTS.md`: use it, don't duplicate.
- Backend route doesn't exist yet (during plan 09 authoring): stub with sample data; flag in summary.
- Mockup shows behavior the spec doesn't: document in your summary; user folds into SCREENS.md if correct.
- Anything that would re-introduce a removed pattern (oneline/detailed bullets, `/generate/*` routes, flat status enum without DRAFT, AI sparkle on tag chips, theme switcher, light mode, Funnel/Bar/Line on Overview): hard refuse with a pointer to the removal note in `docs/plans/archive/01-docs-realignment.md` or this prompt's hard rules.

## First action

Run:

```bash
ls docs/plans/ docs/plans/archive/ docs/prompts/ docs/prompts/archive/ docs/design/
```

Confirm:

- `docs/plans/`: README.md, 02-mvp-master-plan.md
- `docs/plans/archive/`: 01-docs-realignment.md, 03-component-catalog.md, 04-backend-architecture.md, 05-data-model.md, 06-interactions-spec.md, 07-sample-data.md (all `Status: GRADUATED → docs/design/<NAME>.md` with detailed graduation notes)
- `docs/prompts/`: 00-session-continue.md (this file)
- `docs/prompts/archive/`: 00-session-continue-2026-04-30.md (USED), HANDOFF_PROMPT.md, CLAUDE_DESIGN_PROMPT.md
- `docs/design/`: SCREENS.md, WORKFLOW.md, COMPONENTS.md, BACKEND.md, DATA_MODEL.md, INTERACTIONS.md, SAMPLE_DATA.md, mockups/

Then read the canonical files listed at the top of this prompt. Then ask the user: **"Ready to author plan 08 (Stage 2 component library implementation)? Or do you want a different starting point?"**

Don't write code in this session. Don't author the prompt for a plan that hasn't been APPROVED. Don't graduate or modify already-graduated docs without explicit instruction. Each plan-author → review → revise → approve → prompt-author cycle is sequential; the user reviews each plan and ticks the approval checklist before you author the corresponding kickoff prompt.
