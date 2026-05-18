---
description: Open the PR using `.github/pull_request_template.md` structure, ensure the last commit message has `Closes #<N>` referencing the plan's GitHub Issue, and fill every template section honestly. Use right before opening any PR, when prepping to push to remote, when reviewing your own PR body before submit. Triggers on phrases like "open pr", "create pr", "push the pr", "pr description", "pr body", "ready for review", "closes issue", "pr template".
---

# engineer-pr-template

PR template at `.github/pull_request_template.md` is the contract every reviewer reads. `Closes #N` in last commit (or PR body) makes Issue auto-close + Project Status auto-move-to-Done on merge — automation plan 16 Phase 1 wired up. This skill walks every section + verifies trailer.

## When to invoke

- About to run `gh pr create` / use GitHub MCP `create_pull_request`.
- Pushing branch w/ `git push -u origin <branch>` + next step is opening PR.
- Reviewing your own PR body before Submit.
- After amending commit + wondering "did I keep the Closes #N?".

## Steps

### 1. Verify `Closes #<N>` in last commit message

Phase 1 git hook `.claude/hooks/git/prepare-commit-msg` auto-appends when branch is `<type>/<task-id>-<slug>` AND `<task-id>` in `.claude/github-issue-map.json`. Confirm:

```bash
git log -1 --pretty=%B
```

Expect last line `Closes #<N>` (or `Fixes #<N>` / `Resolves #<N>`).

**Missing** (e.g. used `git commit --amend` — hook skips):
- Option A — NEW commit (preferred — preserves history):
  ```bash
  git commit --allow-empty -m "Closes #<N>"
  ```
- Option B — amend to add trailer manually:
  ```bash
  git commit --amend --message "$(git log -1 --pretty=%B)

  Closes #<N>"
  ```

**Branch name doesn't match regex** (e.g. `feat/whatever-no-task-id`):
- Hook silently no-op'd. Append `Closes #<N>` to PR body manually (GitHub's detection works from body too).

### 2. Read PR template

```bash
cat .github/pull_request_template.md
```

Current template = 6 sections to fill (no placeholders left):

```markdown
## Summary
- <1-3 bullets, what + why. Link ROADMAP task ID + plan.>

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
- [ ] No new code leaning on `src/services/vault.py` or `src/cli/` (Phase 2 sunset tasks 2.11 / 2.12).
- [ ] Input validated at system boundaries (Pydantic models / form parsers).
- [ ] No secrets in logs / API responses / template renders.
- [ ] CSRF + JWT cookie flags preserved on new POST routes.
- [ ] Untrusted text into Typst templates is escaped.

## Screenshots
- <desktop 1440×900 + mobile 375×812 if any UI change>

## Notes for reviewer
- <follow-ups, scope deferrals, areas wanting extra eyes>
```

### 3. Section guidance

- **Summary** — 1–3 bullets. Lead w/ WHY, not WHAT (diff shows what). Link ROADMAP task + plan path.
- **Linked** — must include `Closes #<N>` for Issue auto-close. Plan path = active path until archive (do NOT pre-archive).
- **Test plan** — actual commands run, w/ outcomes. Don't tick what you didn't run. Manual smoke = Manual QA Gate evidence (`engineer-manual-qa-gate`).
- **Deviations from plan** — bullets keyed to `traces/<run-id>/engineer-deviations.log`. "no material deviations" → be ready for skepticism — real plans almost always have one.
- **Security review checklist** — ONLY tick boxes you actually verified. Don't pre-fill. Hacker fails PR if untrue.
- **Screenshots** — UI changes only. Path under `tests/visual/screenshots/` or attached directly. Both viewports.
- **Notes for reviewer** — areas wanting extra eyes. Specific (file:line) when calling out scope deferrals.

### 4. Branch + title conventions

- **Branch name** (regex from plan 16 § C.6 + `docs/AGENT_OPS.md § 2.8`):
  ```
  <type>/<task-id>-<slug>
    type    ∈ { feat, fix, chore, docs, refactor }
    task-id ∈ { A.11, 2.11, 2.12a, PC.5, DEF-03, A.8 } — must be in .claude/github-issue-map.json
    slug    = kebab-case
  ```

- **PR title** — under 70 chars. `feat(<scope>): <one-line summary>`.

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

Or `gh pr create`:
```bash
gh pr create --title "<title>" --body "$(cat <<'EOF'
<filled template>
EOF
)"
```

Always use HEREDOC for body to preserve formatting.

## Canonical references

- `.github/pull_request_template.md` — canonical template.
- `.claude/agents/engineer.md` § GitHub interaction (PR fields).
- `.claude/hooks/git/prepare-commit-msg` — auto-`Closes #N` hook.
- `docs/AGENT_OPS.md` § 2.7 (Project automation rules) + § 2.8 (git hook install).
- Plan 16 § C.6 — branch-naming regex.

## When NOT to invoke

- Mid-implementation — open PR after quality gates + manual QA gate pass.
- Trivial doc-only PRs without plan/Issue (rare; usually have).
- Compaction events.

## Forbidden during invocation

- Do NOT submit PR without `Closes #<N>`. Automation breaks; manager mirrors Project Status → Done manually.
- Do NOT pre-fill security review checklist. Tick only verified. Hacker fails PRs w/ false claims.
- Do NOT write "no material deviations" if `traces/<run-id>/engineer-deviations.log` has entries. Lift bullets from log.
- Do NOT bypass PR template to "save time". Reviewers depend on knowing where to look.
- Do NOT `git commit --no-verify` to skip pre-commit hooks. Hook failed for a reason.
