---
Status: EXECUTED
Type: design
Authored: 2026-04-30
Last updated: 2026-04-30
Executed: 2026-04-30
Depends on: 01-docs-realignment
---

> **Executed 2026-04-30.** This master plan orchestrated Wave 0 (doc realignment, plan 01) and Wave 1 (design docs, plans 03–07) successfully. Both waves complete; their outputs landed at:
>
> - Plan 01 → archived (EXECUTED)
> - Plan 03 → `docs/design/COMPONENTS.md`
> - Plan 04 → `docs/design/BACKEND.md`
> - Plan 05 → `docs/design/DATA_MODEL.md`
> - Plan 06 → `docs/design/INTERACTIONS.md`
> - Plan 07 → `docs/design/SAMPLE_DATA.md`
>
> **Content distributed to keep ROADMAP.md as single source of truth (no drift):**
>
> - § A document map → actual filesystem state in `docs/` (filesystem wins).
> - § B four canonical design docs → the graduated docs themselves at `docs/design/*.md` (docs win).
> - § C implementation waves → `ROADMAP.md` § Phase 1 § Implementation waves (with per-wave checklists for Waves 2–6).
> - § D tools / skills / MCPs strategy → `docs/plans/README.md` § Tooling strategy reminders + `AGENTS.md` § Workflow.
> - § E per-plan scope sketches (03–07) → graduation notes on each archived plan.
> - § E per-plan scope sketches (08, 09, 10) → `docs/prompts/00-session-continue.md` § Per-plan scope sketches.
> - § F phase mapping → `ROADMAP.md` § Phase 1 cross-references to BACKEND.md / DATA_MODEL.md / etc.
> - § G open questions → all locked; answers folded into the graduated design docs.
>
> **Going forward:** every active plan in `docs/plans/` is a single in-flight piece of work — never a "master" or "meta" plan. `ROADMAP.md` alone tracks the long arc + per-wave checklists.

# 02 · MVP master plan

## Goal

Define the full path from "11 mockups + canonical SCREENS.md" to "MVP shipped end-to-end (UI + backend models + routes + sample data)" as a coordinated set of design docs and implementation waves, so that we never build a piece without an upstream contract and never write a contract that doesn't get built.

**Visual context (gitignored, kept locally):**

- `DESIGN.md` — visual contract (tokens, typography, components, voice). Always read first for any UI work.
- `docs/design/mockups/Naavik — MVP screens (print).pdf` — the canonical mockup PDF.
- `docs/design/mockups/naavik-handoff/project/screens/<ScreenName>.jsx` — most detailed visual reference per screen. SCREENS.md per-screen entries name the JSX file.
- `docs/design/mockups/README.md` — directory map and obsolete-file callouts.

Every implementation plan (08, 09, 10) must instruct its prompt to (a) read DESIGN.md for tokens, (b) read the relevant SCREENS.md sections for the functional spec, and (c) open the bundle JSX files for the screens it touches as the visual source of truth.

## Context / why

We have:

- A canonical visual contract (`DESIGN.md`)
- A canonical functional spec per screen (`docs/design/SCREENS.md`)
- A workflow doc that names the three Stages (mockup → component derivation → page implementation) but doesn't address backend models, routes, or interactions (`docs/design/WORKFLOW.md`)
- A roadmap that lists phases but mixes UI tasks, backend tasks, and infrastructure tasks together (`ROADMAP.md`)

What's **missing**:

- A consolidated **component catalog** (Stage 2 produces files in `templates/components/` — but nothing names them up front)
- A consolidated **route table** (page handlers, fragment handlers, JSON API endpoints — currently scattered through SCREENS.md "Interactions" sections)
- A canonical **data model** (SQLModel definitions — currently sketched in ROADMAP.md but not authoritative)
- A canonical **interactions spec** (HTMX patterns, OOB swaps, SSE streams, drag-drop — partly described per-screen but not cross-cut)
- A **sample data spec** for Phase 1 (hardcoded fixtures used by page handlers before the backend lands)

This plan defines those missing docs, the order they get authored, and the implementation waves that consume them. It does not author the docs themselves — each one becomes a follow-up plan in `docs/plans/`, reviewed individually, then graduated into `docs/design/<NAME>.md`.

## Proposal

### A · Document map (after this plan ships)

```
ROADMAP.md            ← phase progress (canonical)
DESIGN.md             ← visual contract (canonical)
AGENTS.md             ← agent guide + canonical workflow lifecycle
CLAUDE.md             ← Claude Code conventions
docs/
├── plans/            ← work-in-progress plans
│   ├── README.md
│   ├── 02-mvp-master-plan.md       ← this file
│   ├── 03-component-catalog.md     ← spawned from this plan (when authored)
│   ├── 04-backend-architecture.md  ← spawned (expanded from "route table" to full backend)
│   ├── 05-data-model.md            ← spawned
│   ├── 06-interactions-spec.md     ← spawned
│   ├── 07-sample-data.md           ← spawned
│   ├── 08-stage-2-impl.md          ← spawned (component library implementation plan)
│   ├── 09-stage-3-impl.md          ← spawned (page implementation plan, per-screen)
│   ├── 10-backend-impl.md          ← spawned (backend models + routes implementation plan)
│   └── archive/
│       └── 01-docs-realignment.md   ← executed 2026-04-30
├── prompts/         ← active implementation kickoff prompts (one per active impl plan)
│   ├── 08-stage-2-impl.md          ← authored when plan 08 is approved
│   ├── 09-stage-3-impl.md          ← authored when plan 09 is approved
│   ├── 10-backend-impl.md          ← authored when plan 10 is approved
│   └── archive/                    ← prompts archived once their implementation lands
│       ├── HANDOFF_PROMPT.md       ← used 2026-04-29 (Claude Design handoff that produced naavik-handoff/)
│       └── CLAUDE_DESIGN_PROMPT.md ← used to drive the MVP mockup batch
├── misc/                           ← reference material that doesn't fit elsewhere
└── design/
    ├── SCREENS.md                  ← canonical (already exists)
    ├── WORKFLOW.md                 ← UI sub-process (already exists)
    ├── COMPONENTS.md               ← graduated from plan 03
    ├── BACKEND.md                   ← graduated from plan 04
    ├── DATA_MODEL.md               ← graduated from plan 05
    ├── INTERACTIONS.md             ← graduated from plan 06
    ├── SAMPLE_DATA.md              ← graduated from plan 07
    └── mockups/                    ← committed PNGs/PDF
```

The lifecycle that produces this map is the canonical workflow in `AGENTS.md` § Workflow. Plans 03–07 are **design plans** (graduate to design docs, no separate prompt). Plans 08–10 are **implementation plans** (authored, approved, then trigger a prompt at `docs/prompts/NN-name.md` that the user runs to drive implementation; both plan and prompt archived after).

`SCREENS.md` and `DESIGN.md` stay canonical for their domains. The new design docs fill the explicit gaps.

### B · The four new canonical design docs

#### `docs/design/COMPONENTS.md` (planned in `03-component-catalog.md`)

The component library that Stage 2 will produce. One entry per Jinja partial in `src/ui/templates/components/`.

Each entry:

- **Name** (filename, snake_case)
- **Purpose** (one line)
- **Used by** (which screens / which other components include it)
- **API** (variables it accepts via Jinja `with {...}` or macro args)
- **Visual spec** (anchored to DESIGN.md tokens; no token re-definition)
- **Required Lucide icons**
- **Variants / states** (selected, disabled, loading, etc.)
- **Example invocation** (Jinja snippet)

Estimated: ~70 components grouped into 11 sections (Shell, Atomics, Forms, Onboarding, Profile/Bullet, Overview, Discover, Discover-review, Tracking, Outreach, Settings).

#### `docs/design/BACKEND.md` (planned in `04-backend-architecture.md`)

Comprehensive backend contract — far broader than just routes:

1. **HTTP route table** — page routes (HTML), HTMX fragment routes (`/_fragments/...`), JSON API routes (`/api/v1/...`), SSE streams. Per-screen interaction map.
2. **Service layer architecture** — 14 services (auth, profile, extraction, scraper, scorer, document_generator, application_service, email_monitor, email_classifier, contact_tracker, outreach_generator, notifications, portfolio_sync, llm_tracker) + 7 ATS adapters. Service patterns (async-first, Pydantic in/out, typed exceptions, idempotency, event emission).
3. **Scheduled jobs (cron)** — APScheduler catalog across phases 2-6: scraping cron per source, dedup, scoring, auto-apply, email sync, classification, recruiter-state derivation, outreach DM batching, admin (snapshots, costs, cleanup).
4. **Scraping architecture** — `BaseScraper` interface, 7 per-source scrapers (LinkedIn via RSShub, Workday, Greenhouse, Lever, Ashby, Indeed, generic), pipeline (extract → dedup → score → visa-filter → persist), anti-detection, n8n migration story.
5. **Application logic** — auto-apply background pipeline + manual review-and-apply foreground; document generation (bullet selection + trimming + Typst compilation + page-count validation); ATS submission per board (Greenhouse / Lever / Ashby APIs, Workday / LinkedIn / Indeed / generic Playwright).
6. **External integrations** — Gmail/Outlook OAuth + IMAP, LinkedIn Playwright DM (Phase 5), Discord webhook, Telegram bot, Google Calendar, n8n legacy import.
7. **LLM provider abstraction** — `LLMProvider` interface, Anthropic/OpenAI/Ollama implementations, versioned prompt templates, cost tracking via `ApiUsage`, error handling + provider fallback.
8. **Observability** — request logging, LLM tracking, scheduler status, error reporting, health check; Phase 6 Prometheus/Sentry/OTel additions.

#### `docs/design/DATA_MODEL.md` (planned in `05-data-model.md`)

The canonical SQLModel definitions. One section per model:

- **User / Profile** (identity, EEO/visa application questions)
- **Experience / Bullet / Skill / Education / Project / Certification** (resume sub-models)
- **Job** (scraped or manually-added opportunities; carries the *pre-application* queue lifecycle)
- **Application** (the canonical "I applied to X" record; carries the *post-submission* 5-stage status PLUS orthogonal sub-states for docs / referral / recruiter / outreach engagement)
- **Contact / ContactApplicationLink / OutreachMessage / EmailThread** (per-contact and per-application outreach state; queryable from the Application detail view)
- **AppEvent / AuditLog** (unified timeline events across the full lifecycle)
- **GeneratedDocument** (resume PDF + cover letter artifacts produced for an Application)
- **Settings** (per-user LLM provider, API keys encrypted, auto-apply config)

Each section: field list with types · indexes · relationships · validation rules · enum tables.

##### Lifecycle modeling principle (cohesive, multi-axis)

The job-search lifecycle has **multiple orthogonal state axes** that must be modeled as separate fields, not collapsed into a single flat enum. The previous design attempted a flat `FOUND → SCORED → APPROVED → DOCS_GENERATED → APPLIED → INTERVIEWING → OFFER → REJECTED → WITHDRAWN` enum and it failed because it conflated discovery, document-generation, recruiter engagement, referral status, and post-submission tracking into one linear path that real applications don't follow.

Plan 05 must define each axis explicitly:

| Axis | Lives on | States (Phase 1 starting set) | Notes |
|---|---|---|---|
| **Discovery / queue** | `Job` | `unswiped · saved · skipped · queued_for_auto_apply · applied` | Discover-side states. `applied` flips when an Application row is created from this Job. |
| **Application pipeline** (the canonical "5-stage" pipeline) | `Application.status` | `APPLIED · RECRUITER_SCREEN · ONSITE_LOOP · OFFER · CLOSED` | Surfaced on Tracking board. Drives Kanban columns and KPI rates. |
| **Application close reason** | `Application.closed_reason` (nullable; required when `status=CLOSED`) | `rejected_by_them · withdrawn_by_me · ghosted · accepted_other` | Hidden by default in Tracking. |
| **Document generation** | `Application.docs_state` (or via `GeneratedDocument` rows) | `none · generating · ready · stale · failed` | Drives the "AI · auto-fits 1pg" badge on Discover · review & apply, retries on failure. |
| **Referral** | `Application.referral_state` | `none · requested · in_flight · provided · declined` | Powered by Outreach contacts; `provided` enables the warm-intro pill. |
| **Recruiter engagement** | `Application.recruiter_state` | `none · engaged · responded · silent · stalled` | Auto-derived from email signals; surfaces `silent N days` urgency on Overview. |
| **Outreach engagement** (per-application aggregate) | computed view over `OutreachMessage` + `Contact` for that Application | `cold · active · awaiting_reply · referred · converted` | Drives Outreach left-rail grouping (Needs followup / Active / Cold). |
| **Application questions** | `Profile` (one-time per user) | per-field enums per § A (WorkAuthorization, VisaSponsorship, etc.) | Filled once at onboarding/profile-edit; auto-injected into application bundles. |
| **Bullet selection override** | `Bullet.selection_override` | `null · always_include · never_include` | Per-bullet manual override; default null = AI auto-decides. |

These axes are **independent**. An application can be `RECRUITER_SCREEN` + `referral_state=provided` + `docs_state=ready` + `recruiter_state=responded` simultaneously. Compound states (e.g. "interview happens tomorrow with referral pre-secured and docs ready") emerge from the intersection of axes — they are NOT new enum values.

Plan 05 must:

1. Enumerate every axis (the table above is the starting set; extend during authoring)
2. Define the SQLModel field for each (type, default, nullability)
3. Write the legal transitions per axis (state machine where it makes sense — e.g. `none → requested → in_flight → provided`)
4. Define the cross-axis derivations for KPIs (Active = `status in {APPLIED, RECRUITER_SCREEN, ONSITE_LOOP, OFFER}`; Response rate = applications where `recruiter_state ≥ engaged` ÷ total Applied; etc.)
5. Define the timeline event taxonomy (`AppEvent.kind`) so that every axis state change is captured for Tracking + Outreach timelines
6. Define which axes Tracking surfaces (status, closed_reason, recruiter_state silent flags) vs which Outreach surfaces (referral_state, outreach engagement) — UI consumers should read each axis they care about, not infer from a single field

Includes the application-questions taxonomy (US for now): `WorkAuthorization`, `VisaSponsorship`, `VeteranStatus`, `DisabilityStatus`, `Race`, `Gender`, `RelocateOpenness`, `NoticePeriod`, `SalaryExpectation`, `EarliestStart`.

#### `docs/design/INTERACTIONS.md` (planned in `06-interactions-spec.md`)

Cross-cutting interaction patterns:

- **HTMX swap conventions** — `hx-target`, `hx-swap`, OOB markers, when to use `innerHTML` vs `outerHTML` vs `beforeend`
- **Form submission patterns** — autosave per-field on blur (Profile editor), full-form submit (Login), inline edit (Cover letter sections)
- **SSE patterns** — Onboarding extraction stream, cover letter generation stream
- **Drag-and-drop** — Sortable.js for bullet reorder + Kanban card moves; HTMX `hx-post` on order-change event
- **Modals + bottom sheets** — `<dialog>` element pattern; HTMX-loaded content; backdrop dismissal
- **Keyboard shortcuts** — Discover swipe (←/→/↑/↵), Cover letter rewrite (⌘K), Cover letter regen (⌘↵)
- **Toast notifications** — HTMX OOB swap into a toast region

Includes the canonical request/response shapes for the most common interactions (e.g. "click bullet edit pencil → fragment swap returns Bullet editor modal HTML").

#### `docs/design/SAMPLE_DATA.md` (planned in `07-sample-data.md`)

Phase 1 hardcoded fixtures — what each page handler returns until the backend lands. Owner is Shyam Padia per AGENTS.md. Companies: Stripe, Anthropic, Plaid, Linear, Notion, Figma, Ramp, Discord, Snowflake, Airbnb, Databricks. Roles: Senior ML Engineer, Senior Backend, Staff Engineer, Engineering Manager, Founding Engineer.

Includes:

- 1 profile (Shyam)
- 4–6 experience records (Intuit, Plaid, ...)
- 12–18 bullets across roles, with the 9-tag vocab applied
- 5 education / project / certification entries
- ~20 jobs (Discover queue, mix of scored / saved)
- ~12 applications (one per visible Tracking card; mix across the 5 stages)
- ~10 contacts (Outreach view) with timeline events
- 6–8 email signal entries (Overview right rail)

### C · Implementation waves

```
Wave 0  Realign docs           ← plan 01 (this is gating)
Wave 1  Author 4 design docs   ← plans 03, 04, 05, 06 in parallel; plan 07 after them
Wave 2  Stage 2 — component library    ← plan 08
Wave 3  Backend models + initial routes ← plan 10 (returning sample data per plan 07)
Wave 4  Stage 3 — page templates       ← plan 09 (consumes Wave 2 + Wave 3)
Wave 5  Wire interactions               ← extends plan 09 per INTERACTIONS.md
Wave 6  Real backend integration        ← Phase 1.x in ROADMAP.md (real LLM, real DB, real auth)
```

Wave dependencies:

- Wave 0 must finish first (otherwise we're building from drifted specs).
- Wave 1 plans 03, 04, 05, 06 can be authored in parallel — they describe orthogonal axes (UI / routes / data / interactions). Plan 07 (sample data) depends on plan 05 (data model) so it lands slightly after.
- Wave 2 (component library) consumes COMPONENTS.md and DESIGN.md.
- Wave 3 (backend) consumes DATA_MODEL.md + BACKEND.md (in particular § H services, § I cron, § J scrapers, § K application logic).
- Wave 4 (page templates) consumes everything.
- Wave 5 wires interactions on top of Wave 4 pages.
- Wave 6 swaps hardcoded sample data for real DB-backed handlers.

### D · Tools / skills / MCPs strategy

Authoritative recipe — use these consistently, prefer the listed tool over alternatives:

| Need                                                                | Tool / skill / MCP          | Notes                                                                        |
| ------------------------------------------------------------------- | --------------------------- | ---------------------------------------------------------------------------- |
| FastAPI route signatures, dependency injection, response models     | `context7` MCP `query-docs` | Resolve library ID first via `resolve-library-id` (e.g. `tiangolo/fastapi`). |
| SQLModel relationships, Alembic migrations                          | `context7` MCP              | Library IDs: `fastapi/sqlmodel`, `sqlalchemy/alembic`.                       |
| HTMX hx-\* attributes, SSE extension, OOB swaps                     | `context7` MCP              | Library: `bigskysoftware/htmx`.                                              |
| DaisyUI components (`<dialog>`, drawer, tooltip, tabs)              | `context7` MCP              | Library: `saadeghi/daisyui`.                                                 |
| Tailwind utility lookups (rare; tokens already in DESIGN.md)        | `context7` MCP              | Library: `tailwindlabs/tailwindcss`.                                         |
| Jinja2 syntax, macro vs include trade-offs                          | `context7` MCP              | Library: `pallets/jinja`.                                                    |
| Pydantic v2 model patterns                                          | `context7` MCP              | Library: `pydantic/pydantic`.                                                |
| Lucide icon names, prop syntax                                      | `context7` MCP              | Library: `lucide-icons/lucide`.                                              |
| Sortable.js for drag-drop                                           | `context7` MCP              | Library: `SortableJS/Sortable`.                                              |
| Anthropic SDK / Claude API patterns (LLM provider abstraction)      | `claude-api` skill          | Triggers automatically when we open `src/llm/anthropic.py`.                  |
| Nix flake / NixOS module / dev shell tweaks                         | `nixos` MCP `nix`           | Use for any `flake.nix` / `nix/*.nix` change.                                |
| GitHub repo ops (PRs, issues, releases)                             | `github` MCP                | Always `get_me` first to check perms.                                        |
| Open-ended web research not in context7                             | `tavily` MCP                | Search → research → extract pattern.                                         |
| Multi-file codebase exploration                                     | `Explore` agent             | "very thorough" thoroughness for cross-cutting questions.                    |
| Structured implementation planning for a single doc                 | `Plan` agent                | Spawn for each new design doc plan (03–07).                                  |
| Claude Code feature questions                                       | `claude-code-guide` agent   | Hooks, slash commands, settings.json tweaks.                                 |
| Quality / dedup pass after a Wave finishes                          | `simplify` skill            | Reviews the diff for reuse opportunities.                                    |
| PR review (after each Wave)                                         | `review` skill              | Run before requesting human review.                                          |
| Security review (Wave 3 backend, Wave 6 auth)                       | `security-review` skill     | Run on auth + scraper + secrets paths.                                       |
| **UI design judgement / redesign / audit / polish / micro-interactions** | **`impeccable` skill** | **Primary UI design tool.** Use during Stage 2 + Stage 3 whenever a screen or component needs design judgement beyond mechanical assembly — visual hierarchy, accessibility audit, motion, anti-patterns, taking a "bland" wireframe to production-grade. |
| Frontend code generation (distinctive UI, fresh visuals) | `frontend-design` skill | Pair with `impeccable` when a page needs both judgement and creative code output. |
| Broader UI/UX intelligence — palettes, typography pairing, layout patterns, chart components, mobile patterns | `ui-ux-pro-max` skill | Reference for breadth (50+ styles, 161 palettes, 25 chart types). Useful when scoping Phase 6+ visuals or when a Phase 1 screen needs a pattern we haven't seen before. |
| Component spec lookup (shadcn-style patterns translated to DaisyUI) | `ui-styling` skill | Reference only; we don't ship shadcn. Helpful when DaisyUI's component is missing a behavior we need to compose ourselves. |
| Per-task progress tracking                                          | `TaskCreate` / `TaskUpdate` | One task per significant unit of work.                                       |

**Anti-patterns to avoid:**

- Don't web-search library docs when `context7` covers them. The cached / current results are more reliable.
- Don't spawn `general-purpose` agents for things that match a specialized agent (`Explore` for codebase, `Plan` for planning, `claude-code-guide` for Claude Code).
- Don't use `Bash` for read/grep operations that the dedicated tools handle (`Read`, `Grep`, `Glob`).

### E · Each plan's scope (per future plan)

Brief per-plan notes so we know what each deliverable contains. These are not sub-plans, just scope sketches.

#### Plan 03 — Component catalog (graduates to `docs/design/COMPONENTS.md`)

Contents:

- Inventory grouped by responsibility (Shell, Atomics, Forms, etc. — see § A above)
- Per-component: name, purpose, API, visual spec, variants, example invocation
- Cross-reference to SCREENS.md per-screen "Components" lists (which components feed which screen)
- Cross-reference to DESIGN.md token names (no token redefinition)

Tools used: `Read` SCREENS.md per-screen Components lists; `context7` for DaisyUI / Lucide reference.

#### Plan 04 — Backend architecture & API design (graduates to `docs/design/BACKEND.md`)

Originally scoped to "route table"; expanded after review feedback to cover the full backend stack. Contents:

- HTTP route layer (page routes, HTMX fragment routes, JSON API, SSE streams, per-screen interaction map, conventions)
- Service layer (14 services + 7 ATS adapters; patterns; cross-service flows)
- Scheduled jobs (APScheduler catalog phases 2-6)
- Scraping architecture (`BaseScraper`, per-source modules, pipeline, anti-detection, n8n migration)
- Application logic (auto-apply + manual paths, document generation, ATS submission per board)
- External integrations (Gmail/Outlook OAuth, LinkedIn Playwright, Discord/Telegram/Calendar, n8n legacy)
- LLM provider abstraction (interface, implementations, prompt templates, cost tracking)
- Observability (Phase 1 minimum, Phase 6 expansion)
- File layout under `src/`

Tools used: `Read` SCREENS.md per-screen Interactions sections + ROADMAP.md phase tasks; `context7` for FastAPI / APScheduler / Crawl4AI / Playwright patterns; `claude-api` skill for LLM-abstraction design.

#### Plan 05 — Data model (graduates to `docs/design/DATA_MODEL.md`)

Contents:

- SQLModel models per entity (Profile, Experience, Bullet, Job, Application, Contact, OutreachMessage, EmailThread, AppEvent, Settings)
- Enum tables (ApplicationStatus, WorkAuthorization, etc.)
- Relationships (FKs, back-populates, cascade rules)
- Indexes (especially for tag matching, score sorting, status filtering)
- Pgvector schema for semantic match (Phase 6 prep)
- Migration strategy (Alembic; one initial migration; subsequent ones additive)
- Validation rules (per-field constraints, computed properties)

Tools used: `context7` for SQLModel / Alembic / pgvector docs; `Plan` agent to design the schema iteratively.

#### Plan 06 — Interactions spec (graduates to `docs/design/INTERACTIONS.md`)

Contents:

- HTMX swap conventions
- Form submission patterns (autosave, full-form, inline edit)
- SSE patterns (extraction stream, cover-letter generation stream)
- Drag-and-drop conventions
- Modal / bottom sheet pattern
- Keyboard shortcuts (per-screen + global)
- Toast notification region (OOB target)
- Per-interaction request/response shapes (e.g. PUT /api/v1/bullets/:id → returns updated bullet partial)

Tools used: `context7` for HTMX `hx-ext="sse"`, OOB; reference SCREENS.md per-screen Interactions sections.

#### Plan 07 — Sample data (graduates to `docs/design/SAMPLE_DATA.md`)

Contents:

- 1 profile (Shyam Padia) with all EEO/visa fields
- 4–6 experience entries with realistic bullets (long form, 9-tag vocab)
- ~20 jobs for Discover queue
- ~12 applications across all 5 stages
- ~10 contacts with timeline events
- ~8 email signals
- Settings defaults (Anthropic Claude selected, auto-apply OFF, etc.)
- Stored as a Python module under `src/db/seed.py` so handlers can import directly during Phase 1 (before DB writes happen)

Tools used: data-only; no special tools.

#### Plan 08 — Stage 2 component library implementation (no graduation)

Contents:

- Per-component implementation order (atomics first, screen-specific last)
- Build batches (Shell + Atomics → Forms + Onboarding → Profile + Bullet → Overview → Discover → ... → Settings)
- Validation: each batch passes `uv run ruff check`, every component renders in a tiny fixture page at `/_design/components`
- Acceptance: component count matches COMPONENTS.md inventory exactly

Reference material for the prompt: `docs/design/COMPONENTS.md` (canonical) + `DESIGN.md` (tokens) + bundle's `kit/Components.jsx` (atomic primitives) + each screen's bundle JSX as a worked example of how the components compose.

Tools: `Write` for new files; `impeccable` skill primarily for any component needing design judgement (atoms first stay mechanical; screen-specific composites benefit from `impeccable`); `frontend-design` for distinctive code; `simplify` after each batch.

#### Plan 09 — Stage 3 page implementation (no graduation; per-screen sub-plans optional)

Contents:

- Per-screen build order: simplest first — Login → Settings → Profile → Profile editor → Bullet modal → Onboarding → Overview → Tracking → Outreach → Discover → Discover · review & apply
- Each screen: page handler in `src/main.py` (or per-domain router) returning `HTMLResponse`, hardcoded sample data, `[x]` in SCREENS.md Impl
- Visual QA: Playwright screenshot at desktop (1440×900) + mobile (375×812), compare to the bundle JSX rendered in Claude Design or the PDF page for that section
- Acceptance: every screen renders without error, matches mockup, all interactions noted in SCREENS.md exist (even if backed by stub handlers)

Mockup reference per screen comes from SCREENS.md § "Mockup:" line. The implementation prompt for each screen MUST tell the agent to read the bundle JSX before writing any page template — the JSX is the source of truth for visuals, SCREENS.md is the source of truth for behavior.

Tools: `Write` per page; `Bash` to run Playwright; `impeccable` skill on screens that need design judgement (Discover swipe card, Discover · review & apply); `simplify` post-build.

#### Plan 10 — Backend implementation (no graduation; references DATA_MODEL.md, BACKEND.md exhaustively)

Contents:

- SQLModel models per DATA_MODEL.md
- Alembic migrations (one init, then additive)
- Page route handlers wired to DB queries (replacing hardcoded sample data)
- JSON API endpoints under `/api/v1/`
- HTMX fragment endpoints
- Auth (JWT cookie + bcrypt forms) per Phase 1.7
- LLM provider abstraction per `src/llm/base.py` per Phase 1.3
- Settings persistence
- Tests for each route group (`tests/api/`, `tests/services/`)

Tools: `context7` heavily; `claude-api` skill for `src/llm/anthropic.py`; `security-review` after auth lands.

### F · Phase mapping

This plan replaces the implicit Phase 1 D.x / 1.x ordering in ROADMAP.md with the explicit Wave 0–6 ordering above. After this plan ships, ROADMAP.md gets a small update: replace "Phase 1 UI & Design" subsection's task table with a pointer to `docs/plans/02-mvp-master-plan.md` Wave 0–4. ROADMAP.md continues to track the bigger Phase 1–6 arc (Profile system, Job scraping, Scoring, Tracking, Email, Optimization).

### G · Open questions

1. **Per-screen sub-plans (Wave 4)** — should plan 09 (Stage 3) split into 11 sub-plans (one per screen)? Pro: tight review per screen; Con: 11 plan files, lots of churn. My recommendation: **single plan 09 with per-screen sections**, escalate to a sub-plan only if a screen turns out to be more complex than expected (Discover · review & apply being the likely candidate).
2. **Wave 3 vs Wave 4 ordering** — should backend land before page templates (so handlers always return real data) or alongside (handlers stub sample data per plan 07, then swap to DB-backed)? My recommendation: **alongside**, per § C above. Hardcoded sample data lets us iterate UI without DB churn; backend lands incrementally and swaps in handler by handler.
3. **Plan archive folder** — keep as `docs/plans/archive/` or move executed plans elsewhere? My recommendation: `docs/plans/archive/` — keeps history co-located.
4. **Master plan ownership of Phase 2+ scope** — this master plan is MVP-only. Phase 2 (job scrapers), Phase 3 (scoring), Phase 5 (email + outreach) get their own master plans when their time comes. My recommendation: **yes, scope this plan to MVP only**.
5. **Mockup regeneration trigger** — when do we run another Claude Design batch? Suggested triggers: (a) backend lands and we want deferred screens (Manual job entry modal, Application detail slide-over), (b) Phase 2+ visuals diverge from MVP. My recommendation: **trigger (a) is the next batch; do not regenerate MVP mockups until then**.

## Approval checklist

Tick to approve each. Anything unticked blocks Wave 1.

- [x] Document map (§ A) — folder layout matches what you want
- [x] Four new canonical design docs (§ B) — names, purposes, scope all correct
- [x] Implementation waves (§ C) — sequence and dependencies correct
- [x] Tools / skills / MCPs strategy (§ D) — preferences match yours - only thing missing is the impeccable tool
- [x] Per-plan scope sketches (§ E) — nothing missing, nothing extra
- [x] Phase mapping (§ F) — ROADMAP.md becomes a phase pointer; this plan owns Wave 0–4
- [x] Open questions (§ G) — your answers locked in
- [x] Confirm: spawn plans 03, 04, 05, 06 in parallel after this plan and 01 are both APPROVED
- [x] Confirm: plan 07 spawns after plan 05 is APPROVED
- [x] Confirm: plan 08 spawns after plan 03 is GRADUATED (i.e. COMPONENTS.md exists)
- [x] Confirm: plan 09 spawns after plan 08 is APPROVED
- [x] Confirm: plan 10 spawns after plans 04 and 05 are GRADUATED
