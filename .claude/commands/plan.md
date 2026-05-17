---
description: Architect drafts a docs/plans/NN-name.md for a scope — frontmatter + Goal + Proposal + Open questions + Approval checklist per AGENTS.md § Workflow step 2.
argument-hint: <scope description or roadmap task ID>
---

Scope: $ARGUMENTS

1. **Spawn `architect` via Task** with the scope and these required reads (in order):
   - `AGENTS.md` § Workflow (the 9-step lifecycle).
   - `AGENTS.md` § Single-doc-tracking principle (plans don't duplicate ROADMAP tracking tables).
   - `AGENTS.md` § Key Conventions § CLI (CLI + vault sunset — do NOT propose new subcommands or vault scopes).
   - `ROADMAP.md` § the relevant phase (where this scope lives).
   - `docs/plans/README.md` (plan-file conventions).
   - One or two recent archived plans for style (e.g. `docs/plans/archive/10c-first-time-setup.md`).
   - The relevant design doc(s) under `docs/design/` if this is a UI / data / backend extension.

2. **Architect produces** `docs/plans/NN-<kebab-name>.md` (NN = next unused ordinal across `docs/plans/` + `docs/plans/archive/`). The plan has:
   - Frontmatter: `Status: DRAFT`, `Type: design | execution`, `Authored: YYYY-MM-DD`, `Last updated: YYYY-MM-DD`, `Depends on: <plan refs or none>`.
   - **Goal + Why** (one paragraph each).
   - **Proposal** — file-by-file edits, code snippets where instructive, sequence of waves if multi-step, risk + mitigation table.
   - **Open questions** — explicit blockers for user approval.
   - **Approval checklist** — one `[ ]` per design decision the user must sign off on.

3. **If implementation needs a kickoff prompt**, architect also produces `docs/prompts/NN-<kebab-name>.md` with: Goal, Required reading, Deliverables, Quality bar, Forbidden patterns, Hand-back format (including the required deviations summary per AGENTS.md § What goes in a prompt).

4. **Open the GitHub Issue + add to Project** (after user approves the plan, not before):

   ```
   scripts/gh-project.sh create-issue <task-id> "<plan title>" --priority <CRITICAL|HIGH|MEDIUM|LOW> --milestone "<Phase X>"
   ```

   - `<task-id>` = the ROADMAP row ID (e.g., `PC.5`, `2.11`, `A.8`). If the plan introduces new scope not yet rowed in ROADMAP, ALSO add the ROADMAP row first.
   - Capture the Issue number and write it back into the plan's frontmatter as `GitHub: #<N>`.
   - Skip this step (with a warning) if `.claude/github-project.json` is missing.

5. **Print the plan path** + the GitHub Issue URL + surface the Open questions for user input. Do not proceed to implementation — that's a separate flow (`/build` picks it up after approval, or the user pastes the prompt into a fresh session).
