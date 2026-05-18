---
description: Run the canonical quality gates in order — `uv run ruff check .`, `uv run ruff format --check .`, `uv run pytest -x`, optional `NAAVIK_LIVE_DB=1 uv run pytest -x`, optional Playwright capture. Emit a clean PASS/FAIL summary. Use after every fix lands, before any "ready for review" hand-back, before merging anything. Triggers on phrases like "build gates", "quality gates", "run ruff", "run pytest", "before merge", "lint check", "test suite", "ci surrogate".
allowed-tools: Read, Bash(uv:*), Bash(ruff:*), Bash(pytest:*)
---

# devops-build-gates

Devops owns CI-surrogate quality gates. Every fix/implementation/refactor passes through. Failures → fix before hand-back; never paper over with `# noqa` or `pytest.skip`. Order matters: lint → format → tests → optional live-DB + visual.

## When to invoke

- After any fix/implementation lands, before declaring "done".
- Before opening PR.
- Before merging PR (manager PR GATE).
- Self-audit during devops debugging.

## Steps

Halt on first failure unless specific reason to continue.

### 1. Lint

```bash
uv run ruff check .
```

Clean exit expected. Findings → engineer fixes before continuing.

Pre-existing failures from prior phases (e.g. `scripts/roadmap_parser.py`, `migrations/versions/*.py`) are out-of-scope — list as observations, not failures of this dispatch.

### 2. Format check

```bash
uv run ruff format --check .
```

Clean exit expected. Violations → `uv run ruff format .` to auto-format, then re-verify w/ `--check`.

**Do NOT use `--fix` for ruff check.** Auto-fix masks logical issues needing human review (e.g. unused import meant to be used). Diagnose, fix manually.

### 3. Test suite

```bash
uv run pytest -x
```

`-x` stops on first failure (fast iteration). All green expected.

Pre-existing test failures (out-of-scope from your change) → observations + no ownership. Engineer prompt: "Fix only issues your changes caused."

Sub-suite runs during debugging:
```bash
uv run pytest tests/test_<file>.py -v          # single file, verbose
uv run pytest tests/test_<file>.py::test_X     # single test
uv run pytest -k "<pattern>"                   # by name pattern
```

### 4. Live-DB tests (gated)

Fix touches DB-backed code:

```bash
NAAVIK_LIVE_DB=1 uv run pytest -x
```

Requires:
- `DATABASE_URL` exported (or orchestrator DB at `postgresql+asyncpg://naavik:password@127.0.0.1:5433/naavik`).
- Postgres reachable: `psql -h 127.0.0.1 -p 5433 -U naavik -d naavik -c 'select 1'`.

Dev DB not running → note "live-DB gate skipped — orchestrator down" in hand-back. Don't fake pass.

Test perf reminder: `NAAVIK_BCRYPT_COST=4` should be in test env (10× faster than production's 12). Conftest typically handles; verify if tests > 30s.

### 5. Playwright visual (UI only)

Touches `src/ui/templates/` or `src/ui/static/`:

```bash
uv run python tests/visual/capture.py
```

Captures all pages at desktop + mobile. Compares against `tests/visual/baseline/`. Threshold: 1% pixel delta per screen.

Single screen ad-hoc QA:
```bash
uv run python tests/visual/capture.py --page /<route> --viewport 1440x900 --out /tmp/qa-desktop.png
```

Stale baselines (intentional UI change):
```bash
uv run python tests/visual/capture.py --baseline
```

Baselines committed; ad-hoc captures go to `tests/visual/screenshots/` (gitignored).

### 6. Summary

Emit in hand-back:

```
Quality gates:
  ruff check .          PASS / FAIL (N findings)
  ruff format --check . PASS / FAIL
  pytest -x             PASS (N passed) / FAIL (test_X failed at <reason>)
  NAAVIK_LIVE_DB=1 pytest -x   PASS (N passed) / SKIPPED (orchestrator down) / FAIL
  Playwright            PASS (N screens, 0% diff) / SKIPPED (no UI changes) / FAIL (X screens diffed > 1%)
```

Pre-existing failures from upstream → list separately under "Pre-existing failures (out of scope):" w/ file:line.

## Failure handling

**ruff failures:** read rule + line; fix manually. Don't `--fix` blindly.

**pytest failures:**
- Reproduce: `uv run pytest tests/<file>.py::<test> -v`
- Read assertion + traceback
- Distinguish your-fault (regression) vs pre-existing (unrelated)
- Your-fault: fix root cause. NEVER `pytest.skip` without Issue link.
- Pre-existing: file Issue if missing; flag in hand-back; continue.

**Playwright failures:**
- Inspect diff PNG at `tests/visual/screenshots/<slug>-{desktop|mobile}.png` vs `tests/visual/baseline/...`.
- > 1% delta = regression. Fix template/CSS.
- < 1% delta = ignorable noise (browser rendering jitter).
- Baseline genuinely outdated (intentional design change) → regenerate baseline + commit.

## Canonical references

- `docs/RUNBOOK.md` § 5 — canonical command list.
- `.claude/agents/devops.md` § "Quality gates".
- `.claude/agents/engineer.md` § Operating loop step "Quality gates".
- `CLAUDE.md` § Development Commands.
- `AGENTS.md` § Development Environment.

## When NOT to invoke

- Iterative debugging (individual commands, not full sweep).
- Pure documentation PRs (gates still relevant — JSON validity, markdown render — but quicker scans suffice).
- Compaction events.

## Forbidden during invocation

- Do NOT use `ruff check --fix` to silently fix. Diagnose + fix manually.
- Do NOT `pytest.skip(...)` to "fix" failing test. Test fails for a reason.
- Do NOT `# noqa` past real issue. Lint fired for a reason.
- Do NOT `--no-verify` past pre-commit hooks. Same.
- Do NOT claim PASS for live-DB gate when orchestrator wasn't running — say SKIPPED honestly.
- Do NOT `git commit --amend` to bypass failing hook. Fix hook's complaint, re-stage, fresh commit.
