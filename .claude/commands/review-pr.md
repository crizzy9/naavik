---
description: Engineer + hacker review a PR in parallel. Engineer = correctness/style/tests. Hacker = security/secrets/injection. Synthesized verdict with PR comments.
argument-hint: <PR number or URL>
---

PR: $ARGUMENTS

1. **Fetch diff** via `gh pr diff $ARGUMENTS` (or via github MCP if URL is full GitHub link). Also fetch PR description + linked issue (if any).

2. **In one message, spawn `engineer` + `hacker` via Task in parallel.** Each gets:
   - Full PR diff (as code block in prompt).
   - PR description + linked issue text.
   - Request for verdict + line-level comments.
   - Pointers to relevant section of `AGENTS.md` + touched design doc(s).

   **Engineer's brief:** correctness (does it implement plan?), style (ruff conformance, type hints, async usage, no raw SQL in routes), tests (failing-before / passing-after, coverage of new branches), code quality (no premature abstraction, no unnecessary comments, no extension of CLI/vault sunset surface). Verdict: `APPROVE | APPROVE_WITH_NOTES | REQUEST_CHANGES`.

   **Hacker's brief:** security (per hacker agent's default attack-surface list + Naavik-specific watch list). Verdict: `APPROVE | APPROVE_WITH_NOTES | REQUEST_CHANGES | BLOCK`.

3. **Post synthesized review to PR** using `mcp__plugin_claude-code-home-manager_github__pull_request_review_write`:
   - `method: create` → pending review w/ body = combined verdict header.
   - `add_comment_to_pending_review` per line-level finding from either agent (prefix `[engineer]` / `[hacker]` so authorship is clear).
   - `method: submit_pending` → event maps from combined verdict (`APPROVE` if both approve; `REQUEST_CHANGES` if either requests changes; `COMMENT` if APPROVE_WITH_NOTES only).

4. **Print synthesized verdict** in chat:
   - Engineer verdict + 1-line rationale.
   - Hacker verdict + severity (if not approve) + 1-line rationale.
   - **Manager recommendation** (one-line): merge / request changes / block. Hacker `BLOCK` overrides any other verdict.
