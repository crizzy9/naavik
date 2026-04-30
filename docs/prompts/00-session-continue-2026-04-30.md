---
Status: ACTIVE
Type: prompt
Authored: 2026-04-30
Last updated: 2026-04-30
Purpose: Kickoff prompt for a fresh Claude Code session to continue Naavik MVP plan/design/implementation work.
---

# Naavik · session-continue prompt (2026-04-30)

You're picking up Naavik mid-stream in a fresh session. The repo lives at `/home/nightwatcher/personal/dev/naavik`. Read these files in order — they're the canonical context:

1. `AGENTS.md` — agent guide + canonical workflow lifecycle (read § Workflow carefully)
2. `ROADMAP.md` — phase plan + progress
3. `DESIGN.md` (root) — visual contract: tokens, typography, components, voice
4. `docs/design/SCREENS.md` — 11-screen MVP catalog (functional contract per screen, with mockup references per screen)
5. `docs/design/WORKFLOW.md` — UI sub-process (mockup → component → page)
6. `docs/plans/README.md` — plan-file conventions
7. `docs/plans/02-mvp-master-plan.md` — master plan (APPROVED)
8. `docs/plans/03-component-catalog.md` — APPROVED, ready to graduate
9. `docs/plans/04-backend-architecture.md` — APPROVED, ready to graduate
10. `docs/plans/05-data-model.md` — AWAITING REVIEW
11. `docs/plans/06-interactions-spec.md` — AWAITING REVIEW
12. `docs/plans/archive/01-docs-realignment.md` — historical record (executed 2026-04-30)

Mockups (gitignored, locally only): `docs/design/mockups/Naavik — MVP screens (print).pdf` + bundle JSX at `docs/design/mockups/naavik-handoff/project/screens/<ScreenName>.jsx`. See `docs/design/mockups/README.md` for layout. Each `SCREENS.md` entry names its bundle JSX file.

## Where we are (state as of 2026-04-30 commit)

**Phase 1 doc realignment is complete.** Workflow is codified in `AGENTS.md` § Workflow:

```
ROADMAP → plan (docs/plans/) → user review → design doc (docs/design/) → prompt (docs/prompts/) → implement → archive
```

**Plan status:**
- 01 (Docs realignment) — EXECUTED + archived
- 02 (Master plan) — APPROVED, active
- 03 (Component catalog) — APPROVED, ready to graduate to `docs/design/COMPONENTS.md`
- 04 (Backend architecture & API design) — APPROVED, ready to graduate to `docs/design/BACKEND.md` (covers HTTP routes + services + cron + scraping + application logic + integrations + LLM abstraction + observability)
- 05 (Data model) — AWAITING REVIEW, will graduate to `docs/design/DATA_MODEL.md`
- 06 (Interactions spec) — AWAITING REVIEW, will graduate to `docs/design/INTERACTIONS.md`
- 07 (Sample data) — held until plan 05 is approved; will graduate to `docs/design/SAMPLE_DATA.md`
- 08 (Stage 2 component library impl) — not yet authored; spawned after plan 03 graduates
- 09 (Stage 3 page implementation) — not yet authored; spawned after plan 08 is approved
- 10 (Backend implementation) — not yet authored; spawned after plans 04 + 05 graduate

**Prompts status:**
- `docs/prompts/archive/HANDOFF_PROMPT.md` — used 2026-04-29 (drove the Claude Design handoff)
- `docs/prompts/archive/CLAUDE_DESIGN_PROMPT.md` — used 2026-04 (drove the MVP mockup batch)
- `docs/prompts/00-session-continue-2026-04-30.md` — this file

## Mission for this session

In order:

1. **Review plan 05 (data model)** with the user. Format: TL;DR (2–3 sentences) + key structural calls + open questions with your recommendations. The user will either approve as-is, override specific items, or call out missing pieces. After approval: lock decisions in the plan file, mark `Status: APPROVED`, tick the approval checklist.

2. **Review plan 06 (interactions spec)** with the user. Same format.

3. **Author plan 07 (sample data)** — Phase 1 hardcoded fixtures per `docs/design/DATA_MODEL.md` (graduated from plan 05). Format follows the same plan template per `docs/plans/README.md`. Sample data covers: 1 Profile (Shyam Padia), 4–6 Experience rows, 12–18 Bullet rows, ~20 Job rows across queue states, ~12 Application rows across the 5 status values + closed bucket (mix of `docs_state`, `referral_state`, `recruiter_state`), ~20 Contact rows, ~40 OutreachMessage rows, ~20 EmailThread rows, ~150 AppEvent rows, ~30 GeneratedDocument rows, 1 Settings singleton.

4. **Review plan 07** with the user.

5. **Graduate plans 03–07 to design docs.** For each:
   - Take the plan content (cleaned up of approval-checklist scaffolding) and write to `docs/design/<NAME>.md`.
   - Move the plan file to `docs/plans/archive/`.
   - Set the archived plan's front-matter to `Status: GRADUATED → docs/design/<NAME>.md`.
   - For plan 03 (~70 components), the GRADUATION step is where the remaining 67 component specs get fleshed out per the § F sample-spec format. That's substantial work — consider authoring it incrementally and asking the user to review batches.
   - Note: plans 03 and 04's main content is already substantial; graduation = light cleanup + filename change + move. Plan 05's content is also substantial; graduation = fill in the remaining model definitions per § C sample format. Plan 06 and 07 graduate verbatim.

6. **Author plan 08 (Stage 2 component library implementation)** referencing `docs/design/COMPONENTS.md` + `DESIGN.md` + the bundle JSX. The plan should describe: per-component implementation order (atomics first), build batches, validation per batch, the `/_design/components` fixture page, base.html refinements (Lucide CDN + post-swap reinit + macros import), acceptance (component count matches COMPONENTS.md exactly).

7. **Pause for user review of plan 08.** After approval, **author the kickoff prompt at `docs/prompts/08-stage-2-impl.md`**. The prompt is what the user will paste into yet-another fresh session to drive actual coding. Include per `AGENTS.md` § Workflow: required reading list, deliverables, quality bar, forbidden patterns, hand-back format.

8. **Repeat for plan 09 (Stage 3 page implementation)** and `docs/prompts/09-stage-3-impl.md`. Plan 09 covers per-screen build order (simplest first), each screen's page handler returning hardcoded sample data, Playwright visual QA against the bundle JSX.

9. **Repeat for plan 10 (backend implementation)** and `docs/prompts/10-backend-impl.md`. Plan 10 consumes `docs/design/BACKEND.md` and `docs/design/DATA_MODEL.md` exhaustively. It splits across multiple sub-waves (initial models + auth, then scrapers, then scoring + document generation, then tracking + email, then outreach, then observability) per plan 02 § C.

The user reviews each plan. **You don't write actual application code in this session** — that happens in the implementation sessions triggered by `docs/prompts/08`, `09`, `10`.

## Hard rules (non-negotiable)

- **Tech stack:** HTMX + Jinja2 + Tailwind CSS + DaisyUI + Lucide icons (stroke 1.5). No JS framework (no React, Vue, Svelte, Solid). No Bootstrap. No Heroicons / Phosphor.
- **11-screen MVP** per `docs/design/SCREENS.md`. **No `/generate/*` routes** — resume tailoring + cover letter drafting both live inside Discover · review & apply (`/discover/:id`).
- **Application state is multi-axis** per plan 05: `status` (5-stage post-submission: `APPLIED · RECRUITER_SCREEN · ONSITE_LOOP · OFFER · CLOSED`) + `closed_reason` + `docs_state` + `referral_state` + `recruiter_state` + computed `outreach_engagement`. **Never collapse into a flat enum.** No `FOUND` / `SCORED` / `APPROVED` / `DOCS_GENERATED` / `INTERVIEWING` / `REJECTED` / `WITHDRAWN`.
- **Single long-form bullets.** No `oneline` / `detailed` split. No `default_include` toggle. No metric (`revenue` / `percentage` / `team_size`) sub-fields. AI trims at apply time using `selection_override` (`always_include` / `never_include` / null = AI auto-decides).
- **Tag chips:** 9-tag vocabulary only (`ai-ml · backend · frontend · devops · data-eng · genai · leadership · platform · product`). Never with AI sparkle.
- **Score circle:** 0–100 number, no `%` mark, no "match" word.
- **Single dark mode.** No light variants.
- **Sidebar IA:** Overview · Profile · Jobs (`/discover`) · Tracking · Outreach · Settings. Nothing else.

## Workflow rules

- Always read `AGENTS.md` § Workflow before starting any non-trivial task. It's the contract.
- Plans live in `docs/plans/`. Front-matter required: `Status` (DRAFT → AWAITING REVIEW → APPROVED → EXECUTED / GRADUATED), `Type` (execution / design), `Authored`, `Last updated`, `Depends on`.
- Approval checklist at the bottom of every plan. User ticks; agent doesn't proceed without approval.
- After execution / graduation, plan moves to `docs/plans/archive/` with terminal status.
- Implementation prompts at `docs/prompts/`. After implementation lands, prompt moves to `docs/prompts/archive/` with `Status: USED`.
- Mockup references: each plan / design doc that touches a screen names the relevant bundle JSX file (per SCREENS.md per-screen "Mockup:" lines). Mockups are gitignored locally — read them when on disk; flag if missing.
- Prefer `context7` MCP for library docs (FastAPI, SQLModel, HTMX, DaisyUI, Lucide, Sortable.js, etc.) over web search.
- Use `impeccable` skill primarily during plan 08 + plan 09 graduation/implementation prompt authoring (UI design judgement). `frontend-design` skill paired when distinctive code is needed. `claude-api` skill for plan 10's LLM abstraction work.

## When in doubt

- Spec ambiguity: SCREENS.md > DESIGN.md > mockup > ask the user.
- Component already exists in COMPONENTS.md: use it, don't duplicate.
- Backend route doesn't exist yet: stub with sample data; flag in summary.
- Mockup shows behavior the spec doesn't: document in your summary; user folds into SCREENS.md if correct.
- Anything that would re-introduce a removed pattern (oneline/detailed bullets, /generate/* routes, flat status enum, AI sparkle on tag chips, theme switcher): hard refuse with a pointer to the removal note in `docs/plans/archive/01-docs-realignment.md` or this prompt's hard rules.

## First action

Run:

```bash
ls docs/plans/ docs/plans/archive/ docs/prompts/ docs/prompts/archive/
```

Confirm:
- `docs/plans/`: README.md, 02-mvp-master-plan.md, 03-component-catalog.md, 04-backend-architecture.md, 05-data-model.md, 06-interactions-spec.md
- `docs/plans/archive/`: 01-docs-realignment.md
- `docs/prompts/`: 00-session-continue-2026-04-30.md (this file)
- `docs/prompts/archive/`: HANDOFF_PROMPT.md, CLAUDE_DESIGN_PROMPT.md

Then read the canonical files listed at the top of this prompt. Then ask the user: **"Ready to review plan 05 (data model) first, or do you want a different starting point?"**

Don't write code in this session. Don't graduate plans without approval. Don't author plan 07 until plan 05 is approved. Don't author plan 08 until plans 03–07 are all approved (because plan 08 references the graduated COMPONENTS.md which only exists after plan 03 graduates). Don't author the implementation prompts (`docs/prompts/08`, `09`, `10`) until each corresponding plan is approved.
