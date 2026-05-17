---
description: Open the PR using `.github/pull_request_template.md` structure, ensure the last commit message has `Closes #<N>` referencing the plan's GitHub Issue, and fill every template section honestly. Use right before opening any PR, when prepping to push to remote, when reviewing your own PR body before submit. Triggers on phrases like "open pr", "create pr", "push the pr", "pr description", "pr body", "ready for review", "closes issue", "pr template".
---

# engineer-pr-template

The PR template at `.github/pull_request_template.md` is the contract every reviewer reads. `Closes #N` in the last commit (or PR body) is what makes Issue auto-close + Project Status auto-move-to-Done on merge — that's the automation plan 16 Phase 1 wired up. This skill walks every section + verifies the trailer.

## When to invoke

- About to run `gh pr create` / use the GitHub MCP `create_pull_request`.
- Pushing a branch with `git push -u origin <branch>` and the next step is opening a PR.
- Reviewing your own PR body before clicking Submit.
- After amending a commit and wondering "did I keep the Closes #N?".

## What this skill does

### 1. Verify `Closes #<N>` lives in the last commit message

The Phase 1 git hook `.claude/hooks/git/prepare-commit-msg` auto-appends this when the branch is named `<type>/<task-id>-<slug>` AND `<task-id>` is in `.claude/github-issue-map.json`. Confirm:

```bash
git log -1 --pretty=%B
```

Expect the last line to be `Closes #<N>` (or `Fixes #<N>` / `Resolves #<N>`).

**If missing** (e.g. you used `git commit --amend` which the hook skips):
- Option A: redo as a NEW commit (preferred — preserves history):
  ```bash
  git commit --allow-empty -m "Closes #<N>"
  ```
- Option B: amend to add the trailer manually:
  ```bash
  git commit --amend --message "$(git log -1 --pretty=%B)

  Closes #<N>"
  ```

**If branch name doesn't match the regex** (e.g. `feat/whatever-no-task-id`):
- The hook silently no-op'd. Append `Closes #<N>` to the PR body manually (GitHub's `Closes #N` detection works from PR body too).

### 2. Read the PR template

```bash
cat .github/pull_request_template.md
```

The current template has 6 sections you must fill (no placeholders left):

```markdown
## Summary
- <1-3 bullets, what + why. Link the ROADMAP task ID + plan.>

## Linked
Closes #<N>

Plan: `docs/plans/<NN>-<kebab-name>.md`
ROADMAP task: `<X.Y>` (e.g., `2.11`, `PC.5`, `A.8`)

## Test plan
- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run pytest -x`
- [ ] <integration test or Playwright visual baseline if relevant>
- [ ] Manual smoke: <commands you ran + what you observed>

## Deviations from plan
- <bullets keyed to traces/<run-id>/engineer-deviations.log, or "no material deviations">

## Security review checklist
- [ ] No new code that leans on `src/services/vault.py` or `src/cli/` (Phase 2 sunset tasks 2.11 / 2.12).
- [ ] Input validated at system boundaries (Pydantic models / form parsers).
- [ ] No secrets in logs / API responses / template renders.
- [ ] CSRF + JWT cookie flags preserved on new POST routes.
- [ ] Untrusted text into Typst templates is escaped.

## Screenshots
- <desktop 1440×900 + mobile 375×812 if any UI change>

## Notes for reviewer
- <follow-ups, scope deferrals, areas wanting extra eyes>
```

### 3. Section-by-section guidance

- **Summary** — 1–3 bullets. Lead with the WHY, not the WHAT (the diff shows the what). Link the ROADMAP task + plan path.
- **Linked** — must include `Closes #<N>` so the Issue auto-closes on merge. The plan path is the active path until archive (do NOT pre-archive to make the path nicer).
- **Test plan** — actual commands you ran, with outcomes. Don't tick a box you didn't run. Manual smoke = the Manual QA Gate evidence (see `engineer-manual-qa-gate` skill).
- **Deviations from plan** — bullets keyed to `traces/<run-id>/engineer-deviations.log`. If genuinely "no material deviations", say so but be ready for skepticism — real plans almost always have one.
- **Security review checklist** — ONLY tick boxes you actually verified. Don't pre-fill. Hacker will fail the PR if untrue.
- **Screenshots** — UI changes only. Path under `tests/visual/screenshots/` or attached directly to the PR. Include both viewports.
- **Notes for reviewer** — areas you want extra eyes on. Be specific (file:line) when calling out scope deferrals.

### 4. Branch + title conventions

- **Branch name** (regex from plan 16 § C.6 + `docs/AGENT_OPS.md § 2.8`):
  ```
  <type>/<task-id>-<slug>
    type    ∈ { feat, fix, chore, docs, refactor }
    task-id ∈ { A.11, 2.11, 2.12a, PC.5, DEF-03, A.8 } — must be in .claude/github-issue-map.json
    slug    = kebab-case description
  ```

- **PR title** — under 70 chars. Format like a commit message: `feat(<scope>): <one-line summary>`.

### 5. Open via GitHub MCP

```python
mcp__plugin_claude-code-home-manager_github__create_pull_request(
    owner="crizzy9",
    repo="naavik",
    title="<70-char title>",
    head="<branch>",
    base="main",
    body="""<filled template body>""",
)
```

Or via `gh pr create`:
```bash
gh pr create --title "<title>" --body "$(cat <<'EOF'
<filled template>
EOF
)"
```

Always use a HEREDOC for the body to preserve formatting.

## Canonical references

- `.github/pull_request_template.md` — the canonical template.
- `.claude/agents/engineer.md` § GitHub interaction (PR fields list).
- `.claude/hooks/git/prepare-commit-msg` — the auto-`Closes #N` hook.
- `docs/AGENT_OPS.md` § 2.7 (Project automation rules) + § 2.8 (git hook install).
- Plan 16 § C.6 — branch-naming regex.
- Engineer agent system prompt (this file's authoring instructions for `Closes #N` trailer).

## When NOT to invoke

- Mid-implementation — open the PR after quality gates pass + manual QA gate passes.
- Trivial doc-only PRs that don't have a plan / Issue (rare; usually they do).
- Compaction events.

## Forbidden during invocation

- Do NOT submit a PR without `Closes #<N>`. The automation breaks; manager has to manually mirror Project Status → Done.
- Do NOT pre-fill the security review checklist. Tick only what you verified. Hacker fails PRs with pre-filled false claims.
- Do NOT write "no material deviations" if `traces/<run-id>/engineer-deviations.log` has entries. Lift the bullets from the log.
- Do NOT bypass the PR template structure to "save time". Reviewers depend on knowing where to look.
- Do NOT `git commit --no-verify` to skip pre-commit hooks. The hook failed for a reason — fix it.
