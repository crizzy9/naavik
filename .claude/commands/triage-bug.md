---
description: Root-cause and fix a bug. Launches devops first (repro + logs), then engineer (patch), escalating to architect or hacker as needed.
argument-hint: <bug description, issue URL, or stack trace>
---

Bug: $ARGUMENTS

1. **Spawn `devops` via Task** — reproduce, instrument, hypothesize root cause, write findings to `./traces/<run-id>/devops.log`. Prompt should require: exact reproduction steps, expected vs actual, one-paragraph root cause, and a failing-before / passing-after test sketch.

2. **Read devops's report.** Branch:
   - **Mechanical root cause** (typo, missing config, off-by-one, missing await) → spawn `engineer` with the proposed patch from devops as starting point.
   - **Architectural root cause** (the design enables this class of bug) → spawn `architect` first. Architect revises the relevant design doc + plan; THEN spawn engineer.

3. **If the bug touches auth, secrets, untrusted input, deserialization, file uploads, or external integrations** → spawn `hacker` in parallel with engineer (single message, two Task tool uses) for a security view of both the bug and the proposed fix.

4. **Engineer produces a fix** + a test that fails-before / passes-after the patch. Engineer runs `uv run ruff check .`, `uv run ruff format --check .`, and `uv run pytest -x` before declaring done. Then opens a PR via the github MCP — title under 70 chars, body has Summary + Test plan.

5. **Manager wrap-up**:
   - If the bug shifts ROADMAP scope (e.g. surfaced a missing Phase 2 task), update `ROADMAP.md` directly.
   - If the bug is a deviation from an active/recent plan, ensure the fix lands in that plan's `## Deviations from plan` section before the plan archives (AGENTS.md § Workflow step 7).
   - If the bug is a new failure mode, add a runbook entry to `docs/plans/POST_PHASE_1.md` § "When something goes wrong."
