---
description: Run the canonical quality gates in order — `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -x`, optional `NAAVIK_LIVE_DB=1 uv run pytest -x`, optional Playwright capture. Emit a clean PASS/FAIL summary. Use after every fix lands, before any "ready for review" hand-back, before merging anything. Triggers on phrases like "build gates", "quality gates", "run ruff", "run pytest", "before merge", "lint check", "test suite", "ci surrogate".
allowed-tools: Read, Bash(uv:*), Bash(ruff:*), Bash(pytest:*)
---

# devops-build-gates

Devops owns the CI-surrogate quality gates. Every fix, every implementation, every refactor passes through these. Failing any of them → fix before hand-back, never paper over with `# noqa` or `pytest.skip`. Order matters: lint first (fast feedback), then format, then tests, then optional live-DB + visual.

## When to invoke

- After any fix / implementation lands and before declaring "done".
- Before opening a PR.
- Before merging a PR (manager's PR GATE check).
- Self-audit during devops debugging — confirm the fix didn't regress anything.

## What this skill does

Run these in order. Halt on first failure unless you have a specific reason to continue.

### 1. Lint

```bash
uv run ruff check .
```

Expected: clean exit (no findings). Any findings → engineer fixes before continuing.

Pre-existing failures from prior phases (e.g. `scripts/roadmap_parser.py`, `migrations/versions/*.py`) are out-of-scope for current dispatch — list them as observations in the hand-back, not failures of this dispatch.

### 2. Format check

```bash
uv run ruff format --check .
```

Expected: clean exit. Format violations → run `uv run ruff format .` (without `--check`) to auto-format, then re-verify with `--check`.

**Do NOT use `--fix` for ruff check.** Auto-fix can mask logical issues that need human review (e.g. unused import that was meant to be used). Diagnose, then fix manually.

### 3. Test suite

```bash
uv run pytest -x
```

`-x` stops on first failure for fast iteration. Expected: all green.

For test-failures that pre-existed your dispatch (out-of-scope from your change), list them as observations + don't claim ownership. Engineer's agent prompt says: "Fix only issues your changes caused."

For sub-test-suite runs during debugging:
```bash
uv run pytest tests/test_<file>.py -v          # single file, verbose
uv run pytest tests/test_<file>.py::test_X     # single test
uv run pytest -k "<pattern>"                   # by name pattern
```

### 4. Live-DB tests (gated)

If the fix / implementation touches DB-backed code:

```bash
NAAVIK_LIVE_DB=1 uv run pytest -x
```

Requires:
- `DATABASE_URL` exported (or use the orchestrator's DB at `postgresql+asyncpg://naavik:password@127.0.0.1:5433/naavik`).
- Postgres reachable. Confirm: `psql -h 127.0.0.1 -p 5433 -U naavik -d naavik -c 'select 1'`.

If the dev DB isn't running, note "live-DB gate skipped — orchestrator down" in the hand-back. Don't fake a pass.

Test performance reminder: `NAAVIK_BCRYPT_COST=4` should be set in the test env (10× faster than production's 12). The conftest typically handles this; verify if tests take >30s.

### 5. Playwright visual (UI changes only)

If the fix / implementation touches `src/ui/templates/` or `src/ui/static/`:

```bash
uv run python tests/visual/capture.py
```

This captures all pages at desktop + mobile viewports. Compares against `tests/visual/baseline/`. Threshold: 1% pixel delta per screen.

To capture a single screen for ad-hoc QA:
```bash
uv run python tests/visual/capture.py --page /<route> --viewport 1440x900 --out /tmp/qa-desktop.png
```

If baselines are stale (intentional UI change), update them:
```bash
uv run python tests/visual/capture.py --baseline
```

Baselines are committed; ad-hoc captures go to `tests/visual/screenshots/` (gitignored).

### 6. Summary report

Emit this exact shape in the hand-back:

```
Quality gates:
  ruff check .          PASS / FAIL (N findings)
  ruff format --check . PASS / FAIL
  pytest -x             PASS (N passed) / FAIL (test_X failed at <reason>)
  NAAVIK_LIVE_DB=1 pytest -x   PASS (N passed) / SKIPPED (orchestrator down) / FAIL
  Playwright            PASS (N screens, 0% diff) / SKIPPED (no UI changes) / FAIL (X screens diffed > 1%)
```

Pre-existing failures from upstream:
- List separately under "Pre-existing failures (out of scope):" with file:line.

## Failure handling

**ruff failures:** read the rule + line; fix manually. Don't `--fix` blindly.

**pytest failures:**
- Reproduce in isolation: `uv run pytest tests/<file>.py::<test> -v`
- Read the assertion + traceback
- Distinguish: your-fault (regression you introduced) vs pre-existing (unrelated)
- For your-fault: fix root cause. NEVER `pytest.skip` without an Issue link.
- For pre-existing: file an Issue if there isn't one; flag in hand-back; continue.

**Playwright failures:**
- Inspect the diff PNG at `tests/visual/screenshots/<slug>-{desktop|mobile}.png` vs `tests/visual/baseline/<slug>-{desktop|mobile}.png`.
- > 1% delta = regression. Fix the template / CSS.
- < 1% delta = ignorable noise (browser rendering jitter).
- Baseline genuinely outdated (intentional design change) → regenerate baseline + commit.

## Canonical references

- `docs/RUNBOOK.md` § 5 — quality gates (the canonical command list).
- `.claude/agents/devops.md` § "Quality gates".
- `.claude/agents/engineer.md` § Operating loop step "Quality gates".
- `CLAUDE.md` § Development Commands.
- `AGENTS.md` § Development Environment.

## When NOT to invoke

- During iterative debugging (run individual commands, not the full gate sweep).
- Pure documentation PRs (gates still relevant — JSON validity, markdown render — but quicker scans suffice).
- Compaction events.

## Forbidden during invocation

- Do NOT use `ruff check --fix` to silently fix things. Diagnose + fix manually so you understand what changed.
- Do NOT `pytest.skip(...)` to "fix" a failing test. The test is failing for a reason.
- Do NOT `# noqa` past a real issue. The lint rule fired for a reason.
- Do NOT `--no-verify` past pre-commit hooks. Same.
- Do NOT claim PASS for live-DB gate when the orchestrator wasn't running — say SKIPPED honestly.
- Do NOT use `git commit --amend` to bypass a failing hook. Fix the hook's complaint, re-stage, commit fresh.
