---
description: Root-cause and fix a bug. Launches devops first (repro + logs), then engineer (patch), escalating to architect or hacker as needed.
argument-hint: <bug description, issue URL, or stack trace>
---

Bug: $ARGUMENTS

1. **Spawn `devops` via Task** — reproduce, instrument, hypothesize root cause, write findings to `./traces/<run-id>/devops.log`. Prompt should require: exact reproduction steps, expected vs actual, one-paragraph root cause, + failing-before / passing-after test sketch.

2. **Read devops's report.** Branch:
   - **Mechanical root cause** (typo, missing config, off-by-one, missing await) → spawn `engineer` w/ proposed patch from devops as starting point.
   - **Architectural root cause** (design enables this class of bug) → spawn `architect` first. Architect revises relevant design doc + plan; THEN spawn engineer.

3. **Bug touches auth, secrets, untrusted input, deserialization, file uploads, or external integrations** → spawn `hacker` in parallel with engineer (single message, two Task tool uses) for security view of both bug + proposed fix.

4. **Engineer produces fix** + test that fails-before / passes-after patch. Engineer runs `uv run ruff check .`, `uv run ruff format --check .`, + `uv run pytest -x` before declaring done. Then opens PR via github MCP — title under 70 chars, body has Summary + Test plan.

5. **Manager wrap-up**:
   - Bug shifts ROADMAP scope (e.g. surfaced missing Phase 2 task) → update `ROADMAP.md` directly.
   - Bug is deviation from active/recent plan → ensure fix lands in that plan's `## Deviations from plan` section before plan archives (AGENTS.md § Workflow step 7).
   - Bug is new failure mode → add runbook entry to `docs/plans/POST_PHASE_1.md` § "When something goes wrong."
