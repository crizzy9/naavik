## Summary
<!-- 1–3 bullets. What changed and why. Link the ROADMAP task ID + plan. -->
- 

## Linked
<!-- Use `Closes #N` so the linked Issue auto-closes on merge. -->
Closes #

Plan: `docs/plans/<NN>-<kebab-name>.md`
ROADMAP task: `<X.Y>` (e.g., `2.11`, `PC.5`, `A.8`)

## Test plan
<!-- Bulleted markdown checklist. Include test commands + expected outcomes. -->
- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run pytest -x`
- [ ] <relevant integration test or Playwright visual baseline>
- [ ] Manual smoke: <commands you ran + what you observed>

## Deviations from plan
<!--
Per AGENTS.md § Workflow step 7: any non-trivial divergence from the plan must be captured.
For each, name: what changed, why, impact on follow-up plans, any new operational surface.

If you introduced a new env var, on-disk path, port, schedule, or secret-handling rule,
ALSO propagate it to README.md / CLAUDE.md / docs/plans/POST_PHASE_1.md in this PR.

Use "no material deviations" only if the plan really shipped exactly as spec'd (rare).
-->
- 

## Security review checklist
<!-- Use when the PR touches auth / secrets / untrusted input / file uploads / scrapers / ATS adapters. -->
- [ ] No new code that leans on `src/services/vault.py` or `src/cli/` (Phase 2 sunset tasks 2.11 / 2.12).
- [ ] Input validated at system boundaries (Pydantic models / form parsers).
- [ ] No secrets in logs / API responses / template renders.
- [ ] CSRF + JWT cookie flags preserved on new POST routes.
- [ ] Untrusted text into Typst templates is escaped.

## Screenshots
<!-- Required for any UI changes — desktop (1440×900) + mobile (375×812) per docs/design/WORKFLOW.md. -->

## Notes for reviewer
<!-- Anything else: known follow-ups, scope deferrals, areas you want extra eyes on. -->
