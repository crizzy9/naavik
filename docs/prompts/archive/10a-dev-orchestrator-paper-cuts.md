---
Status: USED
Type: implementation kickoff (paper cuts)
Plan: docs/plans/archive/10a-dev-orchestrator-paper-cuts.md (EXECUTED 2026-05-02)
Authored: 2026-05-02
Used: 2026-05-02
Prerequisite: Plan 10 Wave 3 / § B EXECUTED (2026-05-02). Backend substrate is live; this prompt fixes dev-experience paper cuts before plan 11 (Phase 2 scrapers) starts.
---

# Naavik · POST_PHASE_1 paper cuts (PC.1 / PC.2 / PC.3)

You are starting a fresh session to ship the three "POST_PHASE_1 paper cuts" tracked in `ROADMAP.md` § POST_PHASE_1 paper cuts (PC.1, PC.2, PC.3). These are dev-experience fixes that block plan 11 (Phase 2 scrapers) from feeling clean. Per ROADMAP, "ship as a single tiny plan (`docs/plans/10a-dev-orchestrator-paper-cuts.md`) or fold inline into the start of plan 11" — we're going with the dedicated plan since PC.1 needs root-cause investigation.

PC.1 is **urgent** and gates everything: until the dev orchestrator reliably brings the `[app]` step up, every developer touching this repo loses ~5min per session restart.

---

## Context — PC.1 reproduction + analysis (2026-05-02)

### Symptoms observed by user

**First run (started 20:02:08 GMT):**

```
[db-init    ] ... ✅ postgresql.conf set up
[deps    ] Resolved 70 packages in 2ms
[deps    ] Checked 61 packages in 0.82ms
[db    ] 2026-05-02 20:02:08.107 GMT [3203459] LOG:  starting PostgreSQL 17.9 ...
[db    ] 2026-05-02 20:02:08.120 GMT [3203459] LOG:  database system is ready to accept connections
[migrate    ] INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
[migrate    ] INFO  [alembic.runtime.migration] Will assume transactional DDL.
^C   ← user kills it at 20:02:49 (41s after db ready, ~40s after migrate's 2nd INFO line)
```

**Second run (started 20:13:07 GMT) — proves the hang is real:**

```
[migrate    ] INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
[migrate    ] INFO  [alembic.runtime.migration] Will assume transactional DDL.
[db    ] 2026-05-02 20:18:07.936 GMT [3264303] LOG:  checkpoint starting: time
[db    ] 2026-05-02 20:18:07.962 GMT [3264303] LOG:  checkpoint complete: ...
^C   ← user kills it at 20:34:41 (21m 34s after db ready)
```

That 21-minute gap is the smoking gun. `[app]` step **never** appears. The `[db]` checkpoint at 20:18 is just postgres' idle 5-minute timer — confirms postgres is alive and idle, with no other workload connected. Migrate is wedged.

**Cross-terminal symptom:**

While `nix run .#dev` is running (and migrate is wedged), in a separate terminal:

```
$ uv run fastapi dev src/main.py
^C   ← absolutely zero output. Just the cursor sitting there.
```

The moment the user kills `nix run .#dev`, the very same `uv run fastapi dev src/main.py` command runs and binds `:8000` cleanly:

```
$ uv run fastapi dev src/main.py
   FastAPI   Starting development server 🚀
   ...
   server   Server started at http://127.0.0.1:8000
```

That tells us: **something the orchestrator is holding actively blocks any second `uv run` invocation.** Killing the orchestrator releases it.

### Root-cause hypotheses (rank-ordered by likelihood)

The implementing agent should test these in order, not blindly try the first one. Confirm with measurement before fixing.

**H1 — uv project lock contention (most likely).** uv coordinates concurrent operations on the same project via a lockfile (location varies by version: typically `.venv/.lock`, `.venv/uv-lock`, or under `XDG_CACHE_HOME`). When `uv run <cmd>` is invoked, uv may:

1. Acquire the project lock.
2. Run an implicit `uv sync` to ensure the venv matches `uv.lock`.
3. Release the lock.
4. Exec the command.

If step 2 is fast (no install needed), the lock is held for milliseconds — not noticeable. **But if the running command itself is `uv run`-wrapped**, the parent uv may keep the lock for the lifetime of the child. The orchestrator's `migrate` step is `uv run alembic upgrade head` and the `app` step is `uv run fastapi dev src/main.py`. If migrate's uv keeps the lock and migrate's child (alembic) wedges, the lock is held forever — blocking any other `uv run` (including the orchestrator's own `app` step, which has `depends_on.migrate.condition = process_completed_successfully` so it never reaches the lock-acquire path, but ALSO blocking the user's manual `uv run fastapi dev` from another terminal).

**Test H1:** while the orchestrator is up and migrate is in its wedged state, run from another terminal:

```bash
ls -la .venv/.lock .venv/uv-lock /tmp/uv-* ~/.cache/uv/locks/ 2>/dev/null
lsof 2>/dev/null | grep -E '\.lock|uv' | head -20
fuser -v .venv/.lock 2>/dev/null   # which pid holds it
```

If a pid from the orchestrator's process tree holds a uv lock, H1 is confirmed.

**Fix H1:** several options, pick whichever measurement supports:

- Add `--no-sync` (or `--frozen` / `--locked`, depending on uv version) to the orchestrator's `uv run` invocations so the lock isn't acquired on every run. This requires the venv already be in sync — the `deps` step ensures that, so it's safe.
- Replace `uv run X` in the orchestrator with direct `.venv/bin/X` invocations once `deps` has synced. This bypasses uv's wrapper entirely for `migrate` and `app`.
- Configure uv to use a per-process lock dir via `UV_PROJECT_DIR` so concurrent `uv run` invocations don't contend.

**H2 — alembic async wrapper deadlock.** `migrations/env.py` (currently shipped) uses an async-engine pattern:

```python
async def run_async_migrations() -> None:
    connectable = async_engine_from_config(..., poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())
```

Alembic's upstream-blessed path is sync. The async wrapper has known wedge cases when:

- the async engine doesn't release its connection back to the loop cleanly
- `import models` (which we added at the top of env.py for `target_metadata = SQLModel.metadata`) has an import-time side effect that opens a connection or registers an asyncio task

**Test H2:** while orchestrator is in the wedged state:

```bash
psql -h 127.0.0.1 -p 5433 -U naavik -d naavik -c \
  "SELECT pid, state, wait_event, wait_event_type, query, query_start \
   FROM pg_stat_activity WHERE datname='naavik' ORDER BY query_start;"
```

If a session is `idle in transaction` or stuck on a `wait_event` (especially `Lock` or `transactionid`), H2 is confirmed.

Then `py-spy dump --pid <migrate-pid>` (install `py-spy` in dev shell if missing) — if the trace shows it stuck in `loop.run_until_complete` or `asyncio.events`, H2 is the smoking gun.

**Fix H2:** convert `migrations/env.py` to the sync template (alembic's default). Use `psycopg2` or `psycopg[binary]` for migrations. Drop asyncpg from the migrate path. Async stays for the runtime app session — only migrate is sync.

**H3 — `import models` opens a DB connection at import time.** `migrations/env.py` does `import models  # noqa: F401`. That triggers `src/models/__init__.py` which imports every entity. None of those imports should open a DB connection. But a regression here would explain the hang.

**Test H3:** isolate the import.

```bash
DATABASE_URL=postgresql+asyncpg://naavik:password@127.0.0.1:5433/naavik \
  uv run python -c "import models; print('ok'); import asyncio; print('asyncio loaded')"
```

If this hangs or takes seconds, H3 is the cause. Check if any `models/*.py` does `engine.connect()` or similar at module-load.

**Fix H3:** remove the import-time side effect; defer it to function-call time.

**H4 — process-compose stdin/TTY behavior.** `cli.environment.PC_DISABLE_TUI = true` keeps process-compose in non-TUI mode, but it may still attach stdin to the controlling TTY. If `uv run alembic` mistakenly tries to read from stdin (e.g., a getpass prompt for SECRET_KEY decryption that we don't expect), it'd hang silently.

**Test H4:** run the orchestrator with stdin redirected from /dev/null:

```bash
nix run .#dev < /dev/null
```

If migrate completes when stdin is closed but hangs when stdin is a TTY, H4 is confirmed.

**Fix H4:** add explicit `< /dev/null` to the migrate step's command in `flake.nix`, or set `is_tty: false` (or whatever the process-compose-flake equivalent is) on the `migrate` process spec.

### Why the implementing agent's earlier session ran fine

When the agent that shipped plan 10 § B ran `nix run .#dev` to verify their work, it completed normally on the same machine. Two material differences from the user's run:

1. The agent ran the orchestrator with stdout redirected to a file in the background:

   ```bash
   nix run .#dev > /tmp/dev-orchestrator.log 2>&1 &
   ```

   Stdout is a pipe, not a TTY. Combined with `disown`, stdin is also detached.
2. The agent did NOT have an active `nix develop` shell with `PYTHONPATH` set when invoking. The user's interactive shell may have `PYTHONPATH` containing nix-store python3.13 paths (we observed this earlier — see plan 10 hand-back § Test results note about `env -u PYTHONPATH`).

Either of these alone could mask the wedge. Both together form a "the same code, different environment, different outcome" pattern.

**Test the difference systematically:**

```bash
# 1. Reproduce the user's failure
nix run .#dev   # interactive, stdin=TTY, your normal $PYTHONPATH

# 2. Try with stdin closed
nix run .#dev < /dev/null

# 3. Try with PYTHONPATH cleared
env -u PYTHONPATH nix run .#dev

# 4. Try with both
env -u PYTHONPATH nix run .#dev < /dev/null
```

If only #1 hangs and #2/#3/#4 don't, you've cornered the cause.

---

## Required reading (in order)

1. `AGENTS.md` § Workflow + § Roadmap Maintenance Rules.
2. `CLAUDE.md`.
3. `ROADMAP.md` § POST_PHASE_1 paper cuts (PC.1 / PC.2 / PC.3 rows).
4. `docs/plans/POST_PHASE_1.md` — operational playbook for what comes after Phase 1.
5. `flake.nix` — process-compose `"dev"` target's full config (lines 39–168).
6. `migrations/env.py` — alembic async wrapper.
7. `src/main.py` — currently the canonical FastAPI app entrypoint at `src/main:app`.
8. `pyproject.toml` — uv project + `[tool.setuptools]` package config + `[project.scripts]`.
9. `docs/prompts/archive/09-stage-3-impl.md` (briefly) — for the Playwright capture script context PC.3 will touch.
10. `tests/visual/capture.py` (if present) or `tests/visual/` directory listing.

---

## Workflow

This is a paper-cut bundle, not a major plan. Use the lightweight version of `AGENTS.md` § Workflow:

1. **Author plan** — `docs/plans/10a-dev-orchestrator-paper-cuts.md`. Required sections:
   - Front-matter (`Status: DRAFT`, `Type: implementation`, `Authored: <today>`, `Depends on: 10-backend-impl § B`)
   - Goal (one sentence)
   - PC.1 root-cause section: hypotheses, the experiments you ran, the measurement that nailed it, the fix
   - PC.2 + PC.3 brief proposals (file-by-file edits)
   - Approval checklist (one row per PC + per fix)
2. **Stop and request review.** Do not write any code until the user ticks the approval checklist.
3. **Implement** PC.1 → PC.2 → PC.3 in that order. Each ships as its own commit with a clear scope-bounded message.
4. **Update `ROADMAP.md`** § POST_PHASE_1 paper cuts: PC.1 / PC.2 / PC.3 rows from `[ ]` → `[x]` with a one-line deliverable note. Bump "Last updated".
5. **Archive** plan + this prompt to `docs/plans/archive/10a-dev-orchestrator-paper-cuts.md` and `docs/prompts/archive/10a-dev-orchestrator-paper-cuts.md` with `Status: EXECUTED` / `Status: USED`.

---

## PC.1 — Process-compose orchestrator app step never binds :8000

See § Context above for full reproduction + hypotheses. Bare summary:

- **Goal:** `nix run .#dev` from a clean state binds `:8000` on the user's interactive terminal within 60s. Concurrent `uv run fastapi dev` from another terminal works.
- **Investigation methodology** is non-negotiable:
  1. Reproduce the wedge in your own session.
  2. Inspect process state with `pg_stat_activity`, `lsof | grep '\.lock'`, and `py-spy dump --pid <migrate-pid>`.
  3. Walk through H1 → H4 in order; document which one(s) the measurement supported.
  4. Fix the confirmed root cause. No bandaids (e.g. "just sleep longer" or "add a healthcheck retry") without a documented root cause.
- **Acceptance:**
  - `nix run .#dev` from a fresh shell (no orchestrator already up) binds `:8000` within 60s. Verify with `ss -ltn | grep 8000` from a second terminal.
  - `uv run fastapi dev src/main.py` from a second terminal works while orchestrator is up.
  - `Ctrl-C` in the orchestrator tears everything down within 15s (already covered by `cleanShutdown.timeout_seconds=10`; verify regression-free).
  - `docs/plans/10a-dev-orchestrator-paper-cuts.md` § PC.1 has a clear root-cause writeup so future regressions land in the same trap.

---

## PC.2 — `uv run fastapi dev` (no path) should just work

Per ROADMAP. Recommended fix: thin `app.py` re-export at repo root.

- **Files:**
  - `app.py` (new, repo root) — exactly two lines: `from src.main import app` + a `__all__`.
  - `README.md` — drop `src/main.py` from the "Manual local development setup" snippet so the README's `uv run fastapi dev` command stays minimal.
  - Optionally `pyproject.toml` `[project.scripts]` cleanup if needed.
- **Acceptance:** `uv run fastapi dev` (no path argument) starts the dev server. README snippet matches.

---

## PC.3 — Playwright local capture on NixOS

Per ROADMAP. Two viable paths:

1. **Replace pip-installed `playwright`** with `pkgs.python312Packages.playwright` (NixOS-patched driver) in the dev shell (`nix/devshell.nix`).
2. **Ship `nix run .#snapshots`** flake app via `steam-run` / `buildFHSEnv` so the pip-installed playwright Just Works.

Capture the first 20-snapshot baseline alongside the dev-shell fix.

- **Files:** `nix/devshell.nix` (or `flake.nix`'s shell config), `tests/visual/capture.py`, new `tests/visual/baseline/*.png` (20 PNGs).
- **Acceptance:**
  - `uv run python tests/visual/capture.py` (or whatever the existing entry point is) succeeds on NixOS without "Could not start dynamically linked executable: chrome" errors.
  - `tests/visual/baseline/` contains 20 baseline PNGs (one per the 11 screens × desktop + 9 specific mobile/state variants per `docs/design/SCREENS.md`).
  - `docs/design/WORKFLOW.md` (or wherever the visual-regression playbook lives) gets a one-paragraph note on how to capture a new baseline.

---

## Quality bar

```bash
# In a fresh shell with no orchestrator running:
nix run .#dev                         # binds :8000 within 60s, output streams in interactive terminal
ss -ltn | grep 8000                    # listener present (from a second terminal)

# In another shell, while orchestrator is up:
uv run fastapi dev                     # works (PC.2: no path arg required, AND PC.1: no lock contention)

# Visual regression:
uv run python tests/visual/capture.py  # works on NixOS (PC.3)

# Standard quality:
uv run ruff check .                    # clean
env -u PYTHONPATH uv run pytest        # all green; no regression on plan-10 § B's 348 tests
```

---

## Forbidden patterns

- ❌ Bandaid the symptom (e.g. just bumping a sleep / readiness probe / adding `set -e`) without identifying the root cause for PC.1.
- ❌ Skip the plan-write-then-review step. We've been bitten by silent paper-cut shipping; the plan is what gets reviewed.
- ❌ Touching plan 10's archived content. PC.x land in their own plan + archive trail.
- ❌ Adding any Phase-2-onward scope (scrapers, scoring, etc.) — that's plan 11.
- ❌ Removing `import models` from `migrations/env.py` if the diagnosis shows it's not the cause (we need `target_metadata = SQLModel.metadata` for autogenerate to work in future migrations).
- ❌ Reverting plan 10 § B's accessor body swap or any other Wave-3 deliverable.

---

## Hand-back format

When complete:

1. **Plan content** — link to `docs/plans/10a-dev-orchestrator-paper-cuts.md`.
2. **PC.1 root-cause writeup** — what was wrong (cite the measurement that proved it), what fix landed, why other hypotheses were ruled out.
3. **Verification** — paste:
   - `ss -ltn | grep 8000` from inside the orchestrator
   - `uv run fastapi dev` from a second terminal while orchestrator is up
   - The clean-shutdown `Ctrl-C` timing
4. **PC.2 verification** — `uv run fastapi dev` starts cleanly with no path arg.
5. **PC.3 verification** — `uv run python tests/visual/capture.py` produces 20 PNGs; checksum-stable across re-runs.
6. **Test results** — `uv run pytest` summary (348+ tests still green).
7. **Files changed** — grouped by directory.
8. **Archive** — confirm plan + prompt moved to `archive/`, ROADMAP rows ticked, "Last updated" bumped.
9. **Next** — confirm plan 11 (Phase 2 scrapers) is now unblocked. Send the user the green light to author plan 11.
