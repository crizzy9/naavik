# `docs/plans/` — work-in-progress plans

> **Purpose:** Every non-trivial change starts as a plan in this folder. Plans are reviewed, then either executed inline (for housekeeping) or graduated into design docs in `docs/design/` and triggered by prompts in `docs/prompts/` (for feature work).
>
> **Canonical workflow lives in `AGENTS.md` § Workflow.** This README is the reference for plan-file conventions; AGENTS.md owns the lifecycle.
>
> **Last updated:** 2026-04-30

---

## Folder layout (under `docs/`)

| Folder | Purpose | Lifecycle |
|---|---|---|
| `plans/` | Work-in-progress plans authored before any non-trivial change. One plan per coherent unit of work. | Drafted → reviewed → approved → executed → archived under `plans/archive/` (or graduated into a design doc + the plan archived). |
| `plans/archive/` | Plans that have been executed or graduated. Kept as audit trail. | Append-only. |
| `design/` | **Canonical** design documents — the contract for what gets built. SCREENS.md, DESIGN.md, WORKFLOW.md, plus any new docs that graduate from approved plans. | Stable; edited only when a new approved plan changes the contract. |
| `prompts/` | Active kickoff prompts for implementation sessions. One prompt per active implementation plan. | Created when a plan is approved and ready to implement; archived once the implementation lands. |
| `prompts/archive/` | Prompts that have already driven their implementation. Kept for reference. | Append-only. |
| `misc/` | Reference material that doesn't fit elsewhere — third-party screenshots, scratch notes, exported logs, vendor PDFs we want to keep. | Append-only; light maintenance. |
| `design/mockups/` | Committed mockup PNGs and the canonical PDF. Output artifacts from Claude Design. | Versioned; replaced when a new mockup batch is produced. |

---

## Workflow (summary; full version in `AGENTS.md` § Workflow)

```
ROADMAP    Plan          Review     Design doc    Prompt          Implement   Archive + roadmap mark
   │         │              │            │            │                │              │
   ▼         ▼              ▼            ▼            ▼                ▼              ▼
docs/    docs/plans/    user ticks   docs/design/  docs/prompts/   user runs    docs/plans/archive/
roadmap  NN-name.md     checklist    NAME.md       NN-name.md      the prompt   docs/prompts/archive/
                        in plan      (graduates    (kickoff for                  ROADMAP.md task → [x]
                                     from plan)    fresh session)
```

Two flavors of plan:

1. **Execution plan** — changes existing docs / config / housekeeping. Reviewed → executed inline → archived to `plans/archive/`. No design doc, no prompt. (Example: plan 01 doc realignment.)
2. **Design plan** — proposes a new design contract (component catalog, data model, route table, interactions spec, etc.). Reviewed → content graduates into `docs/design/NAME.md` → plan archived. If the design contract triggers downstream code work, a follow-up implementation plan is authored that references the new design doc. (Examples: plans 03–07.)
3. **Implementation plan** — proposes how to BUILD against existing design contracts. Reviewed → agent authors a kickoff prompt at `docs/prompts/NN-name.md` → user uses the prompt to drive implementation → after implementation lands, both the plan and prompt are archived, ROADMAP items marked complete. (Examples: plans 08–10.)

---

## Plan file conventions

- **Filename:** `NN-kebab-case-name.md` where `NN` is a two-digit ordinal (e.g. `01-docs-realignment.md`, `02-mvp-master-plan.md`). Ordinal reflects authoring order, not priority.
- **Front-matter required at top:**
  - `Status:` `DRAFT` · `AWAITING REVIEW` · `APPROVED` · `EXECUTED` · `GRADUATED → docs/design/<name>.md`
  - `Type:` `execution` · `design`
  - `Authored:` `YYYY-MM-DD`
  - `Last updated:` `YYYY-MM-DD`
  - `Depends on:` (optional) — other plan IDs that must land first
- **Body sections (in order):**
  1. **Goal** — one paragraph
  2. **Context / why** — what motivates this
  3. **Proposal** — the actual plan content (tables, checklists, file-by-file edits, design sketches, whatever fits)
  4. **Open questions** — things needing user input before approval
  5. **Approval checklist** — the user ticks these off when approving
- **No code edits** while a plan is in `DRAFT` or `AWAITING REVIEW`. Plan-only.
- **One plan per concern.** If two ideas tangle, split them.

---

## Tooling strategy reminders

When authoring or executing a plan, prefer these (cheaper / faster / more accurate):

| Need | Use |
|---|---|
| Library docs (FastAPI, SQLModel, HTMX, DaisyUI, Pydantic, Jinja2, Lucide, Tailwind) | `context7` MCP — `query-docs` and `resolve-library-id`. **Always preferred over web search for library docs.** |
| Nix / NixOS / nixpkgs / home-manager / flake questions | `nixos` MCP — `nix` and `nix_versions`. |
| GitHub repo ops (issues, PRs, commits, releases) | `github` MCP. |
| Open-ended research not in context7 | `tavily` MCP (`tavily_search`, `tavily_research`). |
| Codebase-wide research (multiple files, broad questions) | `Explore` agent (subagent_type). |
| Implementation planning for complex tasks | `Plan` agent. |
| Claude Code feature questions | `claude-code-guide` agent. |
| Claude API / Anthropic SDK code | `claude-api` skill. |
| Design system / token / component work | `design-system`, `frontend-design`, `ui-ux-pro-max` skills. |
| PR review pass | `review` skill. |
| Security review (auth, scrapers, secrets) | `security-review` skill. |
| Quality / cleanup pass after a change | `simplify` skill. |
| Per-task progress tracking | `TaskCreate` / `TaskUpdate`. |

---

## Index

The state of plans changes — list this directory and `./archive/` to see what's currently in each. Plans on the implementation roadmap (per `02-mvp-master-plan.md`):

- 01 — Docs realignment (archived; executed 2026-04-30)
- 02 — MVP master plan (active; APPROVED)
- 03 — Component catalog (design plan; produces `docs/design/COMPONENTS.md`)
- 04 — Route table (design plan; produces `docs/design/ROUTES.md`)
- 05 — Data model (design plan; produces `docs/design/DATA_MODEL.md`)
- 06 — Interactions spec (design plan; produces `docs/design/INTERACTIONS.md`)
- 07 — Sample data (design plan; produces `docs/design/SAMPLE_DATA.md`)
- 08 — Stage 2 — component library implementation
- 09 — Stage 3 — page implementation
- 10 — Backend models + initial routes

Open `02-mvp-master-plan.md` for the wave dependencies between them.

