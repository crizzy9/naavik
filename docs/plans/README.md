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

- **Filename:** `NN-kebab-case-name.md` where `NN` is a two-digit ordinal (e.g. `01-docs-realignment.md`, `08-stage-2-impl.md`). Ordinal reflects authoring order, not priority.
- **Front-matter required at top:**
  - `Status:` `DRAFT` · `AWAITING REVIEW` · `APPROVED` · `EXECUTED` · `GRADUATED → docs/design/<name>.md`
  - `Type:` `execution` · `design`
  - `Authored:` `YYYY-MM-DD`
  - `Last updated:` `YYYY-MM-DD`
  - `Depends on:` (optional) — other plan IDs that must land first
- **Body sections (in order):**
  1. **Goal** — one paragraph
  2. **Context / why** — what motivates this
  3. **Proposal** — the actual plan content (tables, scope-per-item, file-by-file edits, design sketches, build sequence, risk table — whatever the plan needs to communicate intent and gather approval).
  4. **Open questions** — things needing user input before approval
  5. **Approval checklist** — the user ticks these off when approving the plan (plan-acceptance gate, not implementation tracking)
- **No code edits** while a plan is in `DRAFT` or `AWAITING REVIEW`. Plan-only.
- **One plan per concern.** If two ideas tangle, split them.

### Plan content vs. ROADMAP tracking (per `AGENTS.md` § Single-doc-tracking principle)

A plan stays rich. It describes scope, design decisions, sub-section deliverables, build sequence, file lists — whatever the plan needs to communicate intent. **All of that lives in the plan file.**

What does NOT live in plan files: the project-wide `[ ]` / `[~]` / `[x]` ledger that gates "is Phase X done?". That single bit lives in `ROADMAP.md`'s per-phase tables. The plan describes the work; ROADMAP records its completion.

| In the plan | In ROADMAP |
|---|---|
| Goal + context / why | Phase header + deliverable line |
| Detailed scope per sub-section | One row per phase task with one-line description |
| File-by-file edits, code snippets, design sketches | (not duplicated) |
| Build sequence, risk + mitigation table, spec-impact summary, test plan per fix | (not duplicated) |
| Approval checklist (`[ ]` for "user agrees with this approach") | (not duplicated — this is plan-acceptance, not tracking) |
| (not duplicated — see ROADMAP →) | The `[ ]` / `[~]` / `[x]` task ledger that says "is Phase 2 task 2.3 done?" |
| (not duplicated — see ROADMAP →) | Plan-to-phase mapping (each phase header points at the implementing plan) |
| (not duplicated — see ROADMAP →) | Phase 1.x deferred backlog + pre-Phase-2 paper cuts tables |

When the plan ships, the implementer marks the ROADMAP row `[x]` and archives the plan — the plan's rich detail stays preserved in `docs/plans/archive/`, ROADMAP's checkbox is the authoritative "done" gate.

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

The state of plans changes — list this directory and `./archive/` to see what's currently in each. **Wave structure + per-wave checklists live in `ROADMAP.md` § Phase 1.** This README only tracks plan-file conventions and historical authoring order.

Authoring history (plans on the MVP implementation arc, per `ROADMAP.md`):

- 01 — Docs realignment (archived; EXECUTED 2026-04-30)
- 02 — MVP master plan (archived; EXECUTED 2026-04-30; content distributed to `ROADMAP.md` § Phase 1, `AGENTS.md` § Workflow, `docs/prompts/00-session-continue.md`, this README)
- 03 — Component catalog (archived; GRADUATED → `docs/design/COMPONENTS.md`)
- 04 — Backend architecture & API design (archived; GRADUATED → `docs/design/BACKEND.md`)
- 05 — Data model (archived; GRADUATED → `docs/design/DATA_MODEL.md`)
- 06 — Interactions spec (archived; GRADUATED → `docs/design/INTERACTIONS.md`)
- 07 — Sample data (archived; GRADUATED → `docs/design/SAMPLE_DATA.md`)
- 08 — Stage 2 component library implementation (pending; spawns from `docs/prompts/00-session-continue.md`)
- 09 — Stage 3 page implementation (pending; spawns after plan 08 is approved)
- 10 — Backend implementation (multi-wave) (pending; spawns after plan 09 is approved)

Wave dependencies between them are captured in `ROADMAP.md` § Phase 1 § Implementation waves.

