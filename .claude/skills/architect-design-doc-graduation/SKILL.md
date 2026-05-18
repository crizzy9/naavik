---
description: Graduate a `Type: design` plan's content into a permanent semantic-named design doc (`docs/design/SEMANTIC.md`) per `AGENTS.md § Workflow step 4`. The plan stays at `docs/plans/NN-name.md` and links to the design doc. Execution plans skip this step. Use when an approved plan has `Type: design` in frontmatter, when the plan introduces a new contract (components / routes / data model / interactions), or when the user asks "graduate the plan" / "make this a design doc". Triggers on phrases like "graduate the plan", "design doc graduation", "make this permanent", "semantic name", "promote to docs/design", "type: design".
---

# architect-design-doc-graduation

Plans = scratch (HOW work happens; archived once shipped). Design docs = permanent contracts other plans reference forever (`COMPONENTS.md`, `DATA_MODEL.md`, `BACKEND.md`, `INTERACTIONS.md`). Approved `Type: design` plan → proposal content graduates into semantic-named doc at `docs/design/SEMANTIC.md`; plan stays in `docs/plans/` as lifecycle record. `Type: execution` plans skip — plan body IS the contract.

## When to invoke

- Approved plan has `Type: design` in frontmatter + you're about to start next implementation step.
- Plan introduces new contract (component spec, data model state machine, HTMX pattern, screen catalog row).
- User: "graduate the plan" / "promote to docs/design" / "make this a design doc".
- Pre-archive review: plan has `Type: design`, has it graduated yet?

## Steps

1. **Check plan frontmatter.** Look for `Type: design` or `Type: execution`.
   - `Type: execution` → no graduation. Plan body is contract. Stop.
   - `Type: design` → continue.

2. **Propose semantic name.** Match precedent:

   | Plan content | Semantic doc |
   |---|---|
   | Component catalog / per-partial specs | `docs/design/COMPONENTS.md` |
   | Backend route / service API contract | `docs/design/BACKEND.md` |
   | Data model + state machines | `docs/design/DATA_MODEL.md` |
   | HTMX interaction patterns (autosave / SSE / modal / drag-drop) | `docs/design/INTERACTIONS.md` |
   | Sample data + seed fixtures | `docs/design/SAMPLE_DATA.md` |
   | Threat model (hacker authors directly) | `docs/design/THREAT_MODEL-<slug>.md` |
   | Screen catalog row | (already in `SCREENS.md`; no new file) |
   | Brand-new contract type | ALL-CAPS semantic name; ask user if uncertain |

3. **Create doc file** at `docs/design/<SEMANTIC>.md` w/ standard top-matter:
   ```markdown
   # <Doc title>

   > **Last updated:** YYYY-MM-DD
   > **Status:** Canonical — graduated from `docs/plans/archive/NN-name.md`.
   > **Scope:** <one paragraph: what contract covers + does NOT cover>.
   > **Companion docs:** <cross-references>.

   ---

   <plan proposal content, cleaned of plan-lifecycle metadata>
   ```

4. **Lift plan Proposal content** into new doc. Remove plan-flavored sections:
   - Drop "Approval checklist" — gated plan acceptance, not contract.
   - Drop "Open questions" — resolved by approval.
   - Drop "Risk + mitigation" table unless risks are about CONTRACT itself (not implementation).
   - Keep file-by-file detail, code snippets, design sketches, option-matrix rationale.

5. **Update plan file** to link new doc:
   - Change `Status: DRAFT` to `Status: GRADUATED → docs/design/<SEMANTIC>.md`.
   - Add one-line pointer at top of proposal: "See `docs/design/<SEMANTIC>.md` for canonical contract."
   - Plan stays in `docs/plans/` until shipped + deviations written, then archived per AGENTS.md § Workflow step 8.

6. **Update cross-references.** Search files that referenced plan path:
   ```bash
   grep -rn "docs/plans/NN-name.md" --include="*.md"
   ```
   Per hit: append "(see `docs/design/<SEMANTIC>.md` for canonical contract)" or update link entirely.

7. **Bump `ROADMAP.md` "Last updated"** if design doc is referenced from ROADMAP row.

## Worked example — plan 03 → COMPONENTS.md

- Plan: `docs/plans/03-component-catalog.md` w/ `Type: design`
- Approved 2026-04-30
- Graduated to: `docs/design/COMPONENTS.md`
- Plan body: `Status: GRADUATED → docs/design/COMPONENTS.md`
- Plan archive: `docs/plans/archive/03-component-catalog.md` once Stage 2 implementation shipped
- Cross-refs updated: `DESIGN.md`, `SCREENS.md`, `WORKFLOW.md`, `BACKEND.md` all link to `COMPONENTS.md` directly (not the plan)

## Canonical references

- `AGENTS.md` § Workflow step 4 (graduation rule).
- `AGENTS.md` § Naming convention table (plan vs design doc paths).
- `.claude/agents/architect.md` § "Design doc graduation".
- `docs/design/COMPONENTS.md` — canonical worked example (graduated from plan 03).
- `docs/design/DATA_MODEL.md` — graduated from plan 05.
- `docs/design/BACKEND.md` — graduated from plan 04.

## When NOT to invoke

- Plan has `Type: execution` — body is contract, no graduation.
- Plan still DRAFT (not user-approved) — graduation is post-approval.
- "Contract" is one-off (e.g. single screen's polish pass, not reusable pattern).
- Compaction events.

## Forbidden during invocation

- Do NOT archive plan + delete original. Plan stays as lifecycle record (`Authored:`, `Approved:`, `GRADUATED:`, then `EXECUTED:`).
- Do NOT use non-semantic name (e.g. `NN-COMPONENTS.md` or `plan-03-components.md`). Semantic names are stable cross-reference targets; ordinal names rot.
- Do NOT skip cross-ref update. Stale links to plan path silently degrade as plans archive.
