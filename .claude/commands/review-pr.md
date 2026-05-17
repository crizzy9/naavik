---
description: Engineer + hacker review a PR in parallel. Engineer = correctness/style/tests. Hacker = security/secrets/injection. Synthesized verdict with PR comments.
argument-hint: <PR number or URL>
---

PR: $ARGUMENTS

1. **Fetch the diff** via `gh pr diff $ARGUMENTS` (or via the github MCP if the URL is a full GitHub link). Also fetch the PR description and the linked issue (if any).

2. **In one message, spawn `engineer` and `hacker` via Task in parallel.** Each gets:
   - The full PR diff (as a code block in the prompt).
   - The PR description + linked issue text.
   - A request for verdict + line-level comments.
   - Pointers to the relevant section of `AGENTS.md` and the touched design doc(s).

   **Engineer's brief:** correctness (does it implement the plan?), style (ruff conformance, type hints, async usage, no raw SQL in routes), tests (failing-before / passing-after, coverage of new branches), code quality (no premature abstraction, no unnecessary comments, no extension of the CLI/vault sunset surface). Verdict: `APPROVE | APPROVE_WITH_NOTES | REQUEST_CHANGES`.

   **Hacker's brief:** security (per the hacker agent's default attack-surface list + Naavik-specific watch list). Verdict: `APPROVE | APPROVE_WITH_NOTES | REQUEST_CHANGES | BLOCK`.

3. **Post the synthesized review to the PR** using `mcp__plugin_claude-code-home-manager_github__pull_request_review_write`:
   - `method: create` → pending review with body = combined verdict header.
   - `add_comment_to_pending_review` per line-level finding from either agent (prefix `[engineer]` / `[hacker]` so authorship is clear).
   - `method: submit_pending` → event maps from the combined verdict (`APPROVE` if both approve; `REQUEST_CHANGES` if either requests changes; `COMMENT` if APPROVE_WITH_NOTES only).

4. **Print the synthesized verdict** in chat:
   - Engineer verdict + 1-line rationale.
   - Hacker verdict + severity (if not approve) + 1-line rationale.
   - **Manager recommendation** (one-line): merge / request changes / block. Hacker `BLOCK` overrides any other verdict.
