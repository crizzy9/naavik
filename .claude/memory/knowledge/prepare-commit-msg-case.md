---
Topic: prepare-commit-msg-case
Aliases: git hook case, branch task-id case, Closes #N missing, uppercase branch, lowercase branch, PR not auto-closing
First captured: 2026-05-17 (run 2026-05-17T08-40-13_4abef2)
Last referenced: 2026-05-17
Supersedes: none
Confidence: high
---

# prepare-commit-msg-case

## Context

The `.claude/hooks/git/prepare-commit-msg` regex matches `<type>/<task-id>-<slug>` where `<task-id>` is case-sensitive uppercase (`A.11`, `PC.5`, `DEF-12`). Engineer's first dispatch on PR #50 (PC.6, 2026-05-17) was branched as `feat/pc.6-password-complexity` (lowercase). The hook silently no-op'd the `Closes #N` append because `pc.6` didn't match `PC\.[0-9]+`. The PR's commits lacked the trailer; the linked Issue did not auto-close on merge. Surfaced 2026-05-17 mid-flight; engineer pivoted to `feat/PC.6-password-complexity` and the trailer began appending correctly.

## Resolution / pattern

Always use UPPERCASE task-id in branch names: `feat/PC.6-foo`, `fix/DEF-12-bar`, `chore/A.11-baz`. The hook never aborts a commit; lowercase branches silently fail to append the trailer. Documented in `docs/AGENT_OPS.md § 2.8`. Flipping the regex to case-insensitive is a separate paper cut (un-filed; would belong in Phase A).

## Related

- docs/AGENT_OPS.md § 2.8 — gotcha section + hook install instructions
- .claude/hooks/git/prepare-commit-msg — the hook script + regex
- traces/2026-05-17T03-16-16_75a522/engineer-deviations.log — the pivot entry
- docs/plans/archive/18-pc6-password-complexity.md § Deviations from plan
