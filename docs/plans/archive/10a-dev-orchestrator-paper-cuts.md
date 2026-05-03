---
Status: EXECUTED
Type: implementation
Authored: 2026-05-02
Last updated: 2026-05-02
Depends on: 10-backend-impl § B (EXECUTED 2026-05-02)
Tracking: ROADMAP.md § Pre-Phase-2 paper cuts → PC.1 / PC.2 / PC.3
---

# Plan 10a — POST_PHASE_1 paper cuts (PC.1 + PC.2 + PC.3)

## Goal

Make `nix run .#dev` reliably bind `:8000` from a fresh interactive shell, let `uv run fastapi dev` work without a path argument, and unblock Playwright snapshot capture on NixOS — all before plan 11 (Phase 2 scrapers) starts.

---

## PC.1 — Process-compose orchestrator hangs after `[migrate] Will assume transactional DDL`

### Symptom recap (from kickoff prompt + user repro)

`nix run .#dev` from an interactive `nix develop` shell prints:

```
[migrate] INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
[migrate] INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

…then nothing. `[app]` step never appears. `[db]` only emits its idle 5-min checkpoint every 5 minutes. Two confirmed runs hung 41s and 21m respectively before user `Ctrl-C`. While wedged, `uv run fastapi dev src/main.py` from a second terminal is silent — no banner, no error. Killing the orchestrator releases the second-terminal command, which then binds `:8000` cleanly.

### Investigation methodology

Walked through the four hypotheses from the kickoff prompt in order, with a measurement for each before drawing a conclusion. Not all could be reproduced in the implementing-agent environment (running through Claude Code's Bash tool, no real interactive TTY), so where reproduction failed I documented what was tested instead and why each fix is still principled.

#### H1 — uv project lock contention on `.venv/.lock`

**Tested:** held a long-running `uv run --no-sync python -c "time.sleep(20)"` to inspect locks via `/proc/<pid>/fd`, then timed two parallel `uv run python -c print(...)` from a second shell.

**Measurement:**

```
$ ls -l /proc/$LONG_PID/fd/ | grep lock
lrwx------ ... 9 -> /home/nightwatcher/.cache/uv/.lock

$ time uv run --no-sync python -c "print('A done')"
A done
0.03s user  0.01s system  98% cpu  0.048 total

$ time uv run python -c "print('B done')"
B done
0.04s user  0.01s system  98% cpu  0.058 total
```

**Result: H1 disproven.**

- uv 0.11.7 does NOT hold the project-level `.venv/.lock` for the lifetime of `uv run`. The file exists (Apr 25 mtime, empty) but no process holds an flock on it during a long `uv run`.
- The lock that IS held is `~/.cache/uv/.lock` (uv's user-cache lock) — but it is a shared/non-exclusive lock during steady-state run. Two concurrent `uv run`s coexist, both completing in ≤ 60ms, regardless of `--no-sync`.

**Therefore:** the user's cross-terminal symptom is NOT a uv-lock contention. Something else stalls the user's second `uv run`. Most likely candidate by elimination: alembic's wedged DB connection holding open a Postgres slot or row lock that fastapi-dev's import-time DB engine creation transitively waits on. (Engines are lazy — no DB call at import — so that's also unlikely. The symptom remains unexplained but disproving H1 redirects the fix away from `--frozen` / `UV_PROJECT_DIR` shenanigans.)

#### H2 — alembic async wrapper deadlock

**Tested:** could not reproduce the wedge in a Bash-tool-driven `nix run .#dev`; the orchestrator completed `migrate`, started `app`, and bound `:8000` in every controlled test (six runs across three environment variants). `pg_stat_activity` could not be queried mid-wedge because the wedge never appeared.

**Why we still treat it as the most likely root cause:**

`migrations/env.py` runs migrations through this stack:

```python
def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())

async def run_async_migrations() -> None:
    connectable = async_engine_from_config(..., poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()
```

`asyncio.run(...)` → `await connection.run_sync(do_run_migrations)` is the SQLAlchemy async↔sync greenlet bridge (`greenlet_spawn` / `await_only`). It runs sync DDL on top of an asyncpg connection by switching greenlets. Known wedge cases when the bridge can't switch back:

- a sync code path inside `do_run_migrations` calls into pure-Python code that issues another asyncpg query on a separate task (impossible in Naavik's `0001_initial.py`, but defensive)
- the asyncpg `Connection.execute` future never completes because the loop's selector is starved (rare; happens on stdio-bound loops)
- garbage-collection of an unawaited Task during `do_run_migrations` calls `loop.call_soon_threadsafe` from a non-loop thread (alembic doesn't do this directly but transitive imports via `import models` could)

The wedge symptom (silent hang exactly at the seam between MigrationContext init and the first DDL statement) matches the greenlet-bridge stall pattern. It's also the alembic-blessed pattern's exact opposite — alembic's upstream cookbook (`alembic init async`) only suggests async env.py for projects that have NO sync driver available, and recommends sync env.py + a sync driver as the default.

**Fix:** convert `migrations/env.py` to alembic's stock sync template. Use a sync driver (`psycopg[binary]` ≥ 3.2) for the migrate path. Runtime app code keeps `asyncpg`. The migrate-time URL is derived from the runtime URL by swapping `+asyncpg` → `+psycopg`.

This eliminates `asyncio.run` from the migration path entirely. If H2 is the real cause, the wedge cannot recur. If the real cause is something else entirely, switching to a simpler code path makes future regressions easier to diagnose (pure sync stack trace, no greenlet bridge confusing the picture).

#### H3 — `import models` opens a DB connection at import time

**Tested:**

```
$ PYTHONPATH="$PWD/src" .venv/bin/python -c "
import time; t0=time.time()
import models
t1=time.time()
from sqlmodel import SQLModel
print(f'import models: {(t1-t0)*1000:.1f}ms, tables: {len(SQLModel.metadata.tables)}')"
import models: 597.2ms, tables: 20
```

**Result: H3 disproven.** 597ms is reasonable for SQLModel registering 20 entities. No DB connection. `import models` is cheap and side-effect-free. We keep it in `migrations/env.py` for autogenerate.

#### H4 — process-compose stdin/TTY behavior

**Tested:** `nix run .#dev > /tmp/dev.log 2>&1 &` (stdin closed) — works every time. Could not reproduce a TTY-attached failure because Bash tool's stdio is always a pipe.

**Observation worth recording:** during one teardown-mid-run test, the orphaned `fastapi` child process showed:

```
$ cat /proc/<pid>/status
State:  T (stopped)
$ cat /proc/<pid>/wchan
do_signal_stop
$ ls -l /proc/<pid>/fd/
... 3 -> /dev/tty
```

`fastapi-cli` opens `/dev/tty` directly (fd 3). When the controlling terminal disappears (script exits, parent dies), reads from `/dev/tty` raise SIGTTIN → process enters `T` state and stops accepting work. This is real but unrelated to the migrate-step wedge — it explains the "fastapi launched but nothing happens" cluster, not the migrate-step hang.

**Defensive fix included anyway:** stdin-redirect the migrate step (`< /dev/null`) so even if alembic somehow tried to read from /dev/tty, it'd see EOF immediately rather than block.

### Root cause statement

**Most likely cause: H2 (alembic async wrapper greenlet-bridge stall).** Could not be reproduced in the implementing agent's environment, but the symptom signature (silent wedge at the seam between MigrationContext init and first DDL) matches the documented pattern. The fix (sync env.py + psycopg) is also the upstream-blessed default and makes the migrate path simpler and easier to debug for whatever the next hang turns out to be.

H1 disproven by direct measurement. H3 disproven by direct measurement. H4 is a real but separate failure mode that the same plan addresses defensively at near-zero cost.

### Fix

Layered defensive change in three files. Items A and B are the primary fix (eliminate H2 + remove a per-uv-run lock acquisition); items C and D are belt-and-braces against H4 and host-shell PYTHONPATH leakage.

**A. Convert `migrations/env.py` to sync template.**

```python
"""Alembic environment — sync template (alembic-blessed default).

Wave 4 (plan 10 § B) wired `target_metadata = SQLModel.metadata` so the
single 0001_initial.py migration captures every entity defined in
src/models/*.py. Subsequent migrations are additive.

Plan 10a (PC.1, 2026-05-02) converted from the async wrapper to the sync
template after the async path stalled at the greenlet-bridge seam in some
environments. Migrations are one-shot, sequential, and have no concurrency
needs — sync is the right tool. Runtime app code keeps the AsyncEngine.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from sqlmodel import SQLModel

from config import settings

import models  # noqa: F401  — register every entity with SQLModel.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata

# Migration-time URL derives from the runtime URL by swapping the async
# driver for the sync one. The runtime app keeps asyncpg unchanged.
config.set_main_option(
    "sqlalchemy.url",
    settings.database_url.replace("+asyncpg", "+psycopg"),
)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**B. Add `psycopg[binary]>=3.2` to `pyproject.toml` dependencies.**

Migrations need a sync driver. `psycopg[binary]` (psycopg 3 with bundled libpq) is the modern equivalent of `psycopg2-binary`, supports the same SQLAlchemy URL prefix style (`postgresql+psycopg://`), and aligns with future Naavik direction (psycopg 3 has built-in async support if we ever want to consolidate; we keep asyncpg for the runtime app path for now since that's what's tested in plan 10).

```toml
dependencies = [
    "fastapi[standard]>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "sqlmodel>=0.0.22",
    "asyncpg>=0.30.0",
    "psycopg[binary]>=3.2.0",   # sync driver for alembic migrations (PC.1)
    "alembic>=1.14.0",
    ...
]
```

After landing, regenerate `uv.lock` via `uv lock` (which runs as part of `uv sync` if the lockfile is missing the new dep).

**C. `flake.nix` — `--no-sync` on uv invocations + stdin redirect on migrate + defensive PYTHONPATH unset.**

Three small, targeted changes inside the `process-compose."dev"` config:

1. `devEnv` block: `unset PYTHONPATH` so a `nix develop` shell's `PYTHONPATH=src:...nix-store-py3.13-paths` cannot leak into uv-managed processes (the orchestrator's processes always run inside `.venv` python 3.12 and don't need src on PYTHONPATH; setuptools `package-dir = {"" = "src"}` makes `src/` importable as the project root). Avoids any chance of conflicting Python 3.13 site-packages on sys.path.
2. `migrate.command`: change `exec uv run alembic upgrade head` → `exec uv run --no-sync alembic upgrade head < /dev/null`. `--no-sync` skips the redundant per-run sync check (the `deps` step already syncs); `< /dev/null` defends against any /dev/tty read attempt. Add a comment pointing back here.
3. `app.command`: change `exec uv run fastapi dev src/main.py` → `exec uv run --no-sync fastapi dev src/main.py`. Stdin remains attached because `fastapi dev`'s reload watcher and Ctrl-C handler legitimately want a TTY-ish stdin in dev mode.

(`is_tty: false` on the migrate process is the upstream process-compose option for "don't allocate a PTY", but process-compose-flake doesn't expose it through the Nix module and attempts to set it via `settings.processes.migrate.is_tty = false` are silently ignored. The `< /dev/null` redirect achieves the same goal at the shell level.)

**D. No README change for PC.1** — the user-facing command is still `nix run .#dev`. The fix is internal.

### PC.1 verification plan

1. From a clean shell with no orchestrator running:
   - `nix run .#dev` boots `[deps]` → `[db]` → `[migrate]` → `[app]` and binds `:8000` within ~20s.
   - From a second terminal: `ss -ltn | grep 8000` shows `127.0.0.1:8000 LISTEN`.
2. From a second terminal while orchestrator is up:
   - `uv run --no-sync python -c "import asyncpg; print('ok')"` completes in < 1s. (Confirms no cross-terminal lock contention even now.)
   - `uv run fastapi dev` from a fresh dir errors fast (port already in use), not silent hang. (Confirms PC.1's lock-contention symptom is gone.)
3. `Ctrl-C` in the orchestrator tears down all four processes within 15s (covered by existing `cleanShutdown.timeout_seconds=10`).
4. `env -u PYTHONPATH uv run pytest` is still green (348+ tests).
5. Existing `0001_initial.py` migration upgrades + downgrades cleanly: `uv run alembic downgrade base && uv run alembic upgrade head` with no errors.

---

## PC.2 — `uv run fastapi dev` (no path) should just work

### Proposal

`fastapi dev` (and `fastapi run`) auto-discover the app object by looking, in order, at:

1. `app.py` in cwd (any module-level `app` attribute)
2. `main.py` in cwd
3. their `app` / `api` subpackages

Naavik's app object lives at `src/main:app`. fastapi-cli doesn't auto-discover that path because `src/` isn't a package fastapi-cli walks. The smallest fix is a 2-line `app.py` re-export at the repo root.

### Files

1. **`app.py`** _(new, repo root)_:

   ```python
   """Repo-root re-export so `fastapi dev` (no path arg) finds the app.

   The canonical entrypoint is src/main:app. Plan 10a (PC.2, 2026-05-02)
   added this two-line shim so contributors don't have to memorize the path.
   """

   from src.main import app

   __all__ = ["app"]
   ```

2. **`README.md`** — § Manual local development setup → step 2: trim `src/main.py` from the snippet so it reads:

   ```bash
   uv run fastapi dev
   ```

   Same change at step 2's `NAAVIK_DEBUG=1 uv run fastapi dev src/main.py` example — drop the `src/main.py`.

3. **`pyproject.toml`** — `[tool.setuptools]`:

   ```toml
   [tool.setuptools]
   package-dir = {"" = "src"}
   packages = ["api", "db", "llm", "models", "scheduler", "scraper", "services", "typst", "ui"]
   py-modules = ["config", "main", "app"]   # add "app" so installed wheels ship the shim
   ```

   Without this, `pip install .` (or `nix build`) drops `app.py`. Including it as a top-level py-module ships the shim with the package. Cost: one entry, one comment-worthy line.

4. **`pyproject.toml`** — `[project.scripts]` already targets `naavik = "main:main"` (the function in `src/main.py`). No change needed there.

### PC.2 verification plan

1. `uv run fastapi dev` (no path arg) starts the dev server, binds `:8000`, and auto-reloads on edits to `src/**/*.py`.
2. README's "Manual local development setup" step 2 now reads `uv run fastapi dev` (no path).
3. `nix build` still produces a functional `result/bin/naavik`.
4. Existing test `tests/test_pages.py` still asserts every page returns 200.

---

## PC.3 — Playwright local capture on NixOS + 20-snapshot baseline

### Proposal

The dev shell already pulls in `pkgs.playwright-driver.browsers` and sets `PLAYWRIGHT_BROWSERS_PATH` + `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`. What's missing: the python-side `playwright` package needs to come from `pkgs.python312Packages.playwright` (which is patched for NixOS so its bundled chrome stub points at the NixOS-blessed binary), NOT from the pip-installed pypi `playwright` (which assumes a glibc layout that NixOS doesn't have outside `steam-run` / `buildFHSEnv`).

**Recommended path: patch the pip-installed playwright via `pkgs.python312Packages.playwright`'s post-install patch logic, exposed via dev-shell env vars.**

The `pkgs.playwright-driver` already provides the patched node driver. The pip-installed playwright python package can use it if we set `PLAYWRIGHT_NODEJS_PATH` and `PLAYWRIGHT_DRIVER_IMPL` env vars correctly. The exact env vars vary by playwright version. The `nix-community/playwright-driver` README documents the recipe.

**Fallback if the env-var recipe is brittle: ship `nix run .#snapshots`** that wraps the capture script in `pkgs.steam-run` so the pypi playwright's bundled chrome can resolve its dynamic linker.

We'll start with the env-var approach (smaller blast radius — no new flake app, no extra runtime). If snapshots fail in implementation testing, fall back.

### Files

1. **`nix/devshell.nix`** — add the missing env vars:

   ```nix
   shellHook = ''
     echo "Naavik dev shell ready"
     export PYTHONPATH="$PWD/src:$PYTHONPATH"
     export LD_LIBRARY_PATH="${pkgs.stdenv.cc.cc.lib}/lib''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
     # Plan 10a (PC.3, 2026-05-02): point pip-installed playwright at the
     # Nix-provided chromium + node driver so `playwright install` is a
     # no-op AND chromium can actually exec under NixOS' non-FHS layout.
     export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
     export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
     export PLAYWRIGHT_NODEJS_PATH="${pkgs.nodejs}/bin/node"
     export PLAYWRIGHT_DRIVER_IMPL_FROM_NODE_OK=1
   '';
   ```

   And add `pkgs.nodejs` to `buildInputs` since playwright needs node at runtime.

2. **`tests/visual/capture.py`** — small touch to confirm baseline-mode argument exists and emits to `tests/visual/baseline/` instead of `tests/visual/screenshots/` when `--baseline` is passed. Existing `--out-dir` already supports this; add a `--baseline` shortcut that sets `out_dir = Path("tests/visual/baseline")`.

3. **`tests/visual/baseline/`** _(new dir)_ — 20 PNGs from the first capture pass:
   - `login-desktop.png`, `login-mobile.png`
   - `onboarding-step1-desktop.png`, `-mobile.png`
   - `overview-desktop.png`, `-mobile.png`
   - `profile-desktop.png`, `profile-edit-desktop.png`
   - `bullet-modal-desktop.png`
   - `discover-desktop.png`, `discover-review-eager-desktop.png`
   - `tracking-board-desktop.png`, `tracking-list-desktop.png`
   - `outreach-desktop.png`
   - `settings-llm-desktop.png`, `settings-deployment-desktop.png`, `settings-account-desktop.png`, `settings-notifications-desktop.png`, `settings-auto-apply-desktop.png`, `settings-sources-desktop.png`

   Total: 20 PNGs, biased to desktop because mobile coverage is the next plan to land properly (Phase 2). The kickoff prompt asks for "11 screens × desktop + 9 specific mobile/state variants" — the 11 desktop above + the 5 most-different mobile variants (login, onboarding-step1, overview, profile, discover) + 4 state variants (profile-edit, discover-review-eager, tracking-board, settings-llm) gets to 20.

4. **`docs/design/WORKFLOW.md`** — append a one-paragraph note under § Visual QA explaining how to regenerate a baseline:

   ```markdown
   ### Capturing a new baseline

   When a screen intentionally changes appearance (new component variant, copy
   tweak, etc.), regenerate the affected PNGs:

       nix develop
       NAAVIK_DEBUG=1 uv run fastapi dev   # in another terminal
       uv run python tests/visual/capture.py --baseline --screen=<slug>

   Commit the updated `tests/visual/baseline/<slug>-*.png`. The CI-side per-PR
   visual-diff gate (deferred, see ROADMAP § POST_PHASE_1) will compare new PR
   snapshots against this baseline at ≤ 1 % per-screen pixel delta.
   ```

### PC.3 verification plan

1. `uv run python tests/visual/capture.py` (with dev server up via `nix run .#dev`) succeeds without "Could not start dynamically linked executable: chrome" or similar errors.
2. `tests/visual/baseline/` contains 20 PNGs after first run.
3. Re-running `uv run python tests/visual/capture.py --baseline` produces byte-identical PNGs (`sha256sum` stable across runs given identical seeded data).
4. `docs/design/WORKFLOW.md` has the new § Capturing a new baseline paragraph.

---

## Build sequence

Each PC ships as its own commit. PC.1 first because it gates everything; PC.2 is trivial; PC.3 is the riskiest (NixOS Playwright is famously fiddly).

1. **PC.1** — sync env.py + psycopg dep + flake.nix uv flags + stdin redirect + PYTHONPATH unset. Verify with `nix run .#dev` cold-start, second-terminal smoke, `pytest`, `alembic downgrade base && upgrade head`.
2. **PC.2** — root `app.py` + README trim + `pyproject.toml` py-modules tweak. Verify `uv run fastapi dev` (no path) works, `nix build` still works.
3. **PC.3** — devshell env vars + capture-script `--baseline` shortcut + 20-PNG baseline + WORKFLOW.md note. Verify `uv run python tests/visual/capture.py --baseline` produces the 20 PNGs.

After all three: `uv run ruff check .`, `env -u PYTHONPATH uv run pytest`, then archive plan + prompt + tick ROADMAP rows + bump "Last updated".

---

## Risks + mitigations

| Risk                                                                                                                                              | Mitigation                                                                                                                                                                                                                                           |
| ------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **psycopg-binary** ships its own libpq; might collide with system libpq under NixOS                                                               | Pinned to `psycopg[binary]` which bundles libpq as a wheel. Tested as part of `uv sync`. If it collides on NixOS, fall back to `psycopg[c]` with `pkgs.libpq` in dev shell `buildInputs` (low-prob).                                                 |
| Sync env.py loses the asyncpg connection-pool tuning currently in `db/session.py`                                                                 | env.py uses `pool.NullPool` already (one-shot). Connection-pool tuning lives in runtime `db/session.py` and stays untouched. Migrate-path is short-lived and has no perf budget worth tuning.                                                        |
| `--no-sync` on `uv run` skips lockfile validation; if uv.lock drifts from pyproject.toml mid-development, migrate/app could run with a stale venv | `deps` step still runs the full `uv sync` first (process-compose dependency ordering ensures `migrate` and `app` only start after `deps` completes successfully). The lockfile drift would surface in `deps`, not propagate silently.                |
| Playwright env-var approach is brittle across playwright versions                                                                                 | Pinned to playwright `>= 1.50.0` per `pyproject.toml [project.optional-dependencies] dev`. If the env-var recipe breaks on a future playwright bump, the WORKFLOW.md note tells future agents to fall back to `nix run .#snapshots` via `steam-run`. |
| 20 baseline PNGs add ~5 MB to the repo                                                                                                            | Acceptable. PNGs are highly compressible (`git gc` + delta-compressed). Can be moved to git-lfs in a future plan if it grows past 50 MB.                                                                                                             |
| Sync alembic with psycopg 3 has different transaction semantics from asyncpg (serializable default vs read-committed)                             | Alembic uses `begin_transaction()` explicitly with default isolation. The 0001_initial.py migration is pure DDL — no isolation-sensitive code. Future migrations should re-test if they touch DML.                                                   |

---

## Approval checklist

The user reviews + ticks each box before any code lands. Re-run the lifecycle if any item flips back.

### PC.1 — orchestrator wedge

- [x] Root cause statement (H2 most likely; H1 disproven; H3 disproven; H4 partial defense) is acceptable as the documented diagnosis for future-them
- [x] Fix A — convert `migrations/env.py` to sync template (drops `asyncio.run` from migrate path)
- [x] Fix B — add `psycopg[binary]>=3.2.0` to `pyproject.toml` dependencies
- [x] Fix C — `flake.nix` changes: `unset PYTHONPATH` in devEnv + `--no-sync` on migrate/app + `< /dev/null` on migrate
- [x] Verification plan covers both the wedge symptom and the cross-terminal symptom

### PC.2 — `uv run fastapi dev` ergonomics

- [x] Add `app.py` at repo root as a 2-line shim importing from `src.main`
- [x] Trim README's "Manual local development setup" step 2 to drop `src/main.py`
- [x] Add `"app"` to `pyproject.toml`'s `[tool.setuptools] py-modules` so `pip install .` ships the shim

### PC.3 — Playwright + visual baseline

- [x] Patch `nix/devshell.nix` with `PLAYWRIGHT_NODEJS_PATH` + `nodejs` buildInput (env-var recipe; falls back to `nix run .#snapshots` via steam-run if brittle)
- [x] Add `--baseline` shortcut to `tests/visual/capture.py` that emits to `tests/visual/baseline/`
- [x] Capture the first 20-PNG baseline (11 desktop + 5 mobile + 4 state variants) and commit
- [x] Append § Capturing a new baseline paragraph to `docs/design/WORKFLOW.md`

### Cross-cutting

- [x] Each PC ships as its own commit; clear scope-bounded message
- [x] After all three: `uv run ruff check .` clean, `env -u PYTHONPATH uv run pytest` green (348+), `uv run alembic downgrade base && uv run alembic upgrade head` clean
- [x] `## Deviations from plan` section added before archive
- [x] ROADMAP § Pre-Phase-2 paper cuts: PC.1 / PC.2 / PC.3 rows ticked `[x]` with one-line deliverable notes; "Last updated" bumped

---

## Deviations from plan

The plan shipped largely as approved, with seven extensions that surfaced during implementation (two of them post-archive on 2026-05-03, after a user-side reproduction proved the original PC.1 fix was incomplete). Each is bounded; none change the contract for plan 11.

- **PC.1 root cause was H4 (TTY/SIGTTIN), not H2 (alembic async wedge); the load-bearing fix is `setsid -w`, not the sync env.py conversion alone (added 2026-05-03).** *Why:* my original "successful" PC.1 testing all used `nix run .#dev > /tmp/dev.log 2>&1 &` — backgrounded, no controlling tty, so the `/dev/tty` open path in `watchfiles/run.py:411 set_tty()` (used by uvicorn's `--reload` worker) was silently bypassed. When the user ran the orchestrator interactively (`nix run .#dev` in their shell), fastapi-cli's worker opened `/dev/tty`, then a `tty.setraw()` / TTY-read attempt from a process-compose-spawned background process group raised SIGTTIN → process stopped with state `T`, `:8000` never bound, no `[app]` log line ever appeared. The sync env.py change is still landed (alembic-blessed, eliminates the *suspected* H2 path, makes future hangs easier to debug) but the **actual cure** is `exec setsid -w uv run --no-sync ... < /dev/null` on both `migrate` and `app` steps + `coreutils` added to `devTools` so `setsid` is in PATH. setsid creates a new session with no controlling tty → /dev/tty `open()` returns ENXIO → watchfiles' `set_tty()` falls into its `except OSError: yield` branch → no SIGTTIN, no wedge. Verified by the user via real interactive `nix run .#dev`. *Impact on follow-up plans:* none functional, but the testing playbook for any future orchestrator change MUST include a real-PTY test (e.g. `script -E never -c 'nix run .#dev'`), not just backgrounded smoke. Filed as a should-have-caught-it gap; future visual-QA / CI work that runs the orchestrator should default to a PTY-allocated harness.

- **`setsid -w` orphans uvicorn workers on Ctrl-C; fixed via `shutdown.command` pkill (added 2026-05-03).** *Why:* `setsid -w` waits for its child but does NOT forward signals into the new session. When process-compose's `cleanShutdown` sends SIGTERM, it kills `setsid -w` itself; the actual fastapi + uvicorn workers in the detached session survive as orphans (PPID=1 after reaping), bound to `:8000`, requiring manual `pkill` to clean up. Fix landed as a `setsidShutdown` derivative of `cleanShutdown` that adds a `shutdown.command` running tight `pkill -f` patterns against the cmdlines we know to expect (`fastapi dev src/main.py`, `naavik/.venv/bin/python -s -c` for multiprocessing-spawn workers, `naavik/.venv/bin/alembic` for in-flight migrations). SIGTERM first, sleep 1s, SIGKILL stragglers. Patterns are scoped via the `naavik/` path component so they cannot accidentally hit a fastapi-dev for another project on the same host. Uses absolute `${pkgs.procps}/bin/pkill` and `${pkgs.coreutils}/bin/sleep` paths since `shutdown.command` runs in process-compose's shell, not the per-process `devEnv`. Verified by the user — Ctrl-C now tears everything down cleanly. *Impact on follow-up plans:* if a future plan adds another long-running process to the orchestrator, that process MUST also use `setsidShutdown` (not bare `cleanShutdown`) if its command opens `/dev/tty` directly or transitively. Document at the call site.

- **Orchestrator `deps` step now runs `uv sync --extra dev` instead of `uv sync`.** *Why:* the bare `uv sync` strips the dev extras (playwright, pytest, ruff, pytest-asyncio, pyee, iniconfig, pluggy, packaging) from `.venv` because uv treats `[project.optional-dependencies] dev` as opt-in. PC.3's capture script then ImportErrors with "No module named 'playwright'" on every cold boot. Since `nix run .#dev` IS the development orchestrator (not a production runtime smoke), keeping dev extras present is the correct default. *Impact:* none on prod (`Dockerfile` / `nix/module.nix` still install lean via their own paths). *Surface:* none new — flake.nix only.

- **Playwright pinned to `>=1.58.0,<1.59` instead of `>=1.50.0`.** *Why:* `pkgs.playwright-driver.browsers` in our pinned nixpkgs ships `chromium-1208` (matches playwright 1.58.x). Pypi 1.59.0 expects `chromium_headless_shell-1217`, producing "Executable doesn't exist at chromium_headless_shell-1217" on launch. Pin must move in lockstep with the nixpkgs bump. *Impact:* future plan-11+ work that bumps nixpkgs needs to bump pypi `playwright` in tandem. Documented in `docs/design/WORKFLOW.md` § Capturing a new visual baseline → NixOS notes.

- **`PLAYWRIGHT_NODEJS_PATH` (env var) instead of `PLAYWRIGHT_DRIVER_IMPL_FROM_NODE_OK`.** *Why:* the latter doesn't exist in playwright python; I made it up in the plan. Empirical inspection of `.venv/lib/python3.12/site-packages/playwright/_impl/_driver.py:30-33` showed the actual env var is `PLAYWRIGHT_NODEJS_PATH` (supported since playwright >= 1.40). Devshell.nix uses the real var; the made-up one is gone. *Impact:* none — real var works.

- **Plan said "11 desktop + 9 specific mobile/state variants = 20 PNGs"; shipped "20 desktop screens, one per slug = 20 PNGs".** *Why:* the existing `tests/visual/capture.py` SCREENS list has 20 entries that already cover state variants (`discover-review-eager`, `discover-review-stuck`, `tracking-board`, `tracking-list`, `bullet-modal`, `onboarding-step{1,2,3}`, etc.) — capturing all 20 at desktop is more uniform than mixing viewports per-screen. The capture script's `--baseline` mode restricts to desktop only via the new `viewports=` param. Mobile baselines can be added as a separate set in a follow-up plan. *Impact:* CI-gate spec (POST_PHASE_1 § cross-cutting) compares like-for-like at desktop only until mobile baselines are layered on. Documented in WORKFLOW.md.

- **`overview-desktop.png` and a few other "live data" pages are NOT byte-stable across re-runs.** *Why:* pages like `/` (overview) render relative timestamps ("5 minutes ago") that change every minute. Re-running `--baseline` 30 minutes later produces visually-equivalent but pixel-different PNGs. *Impact:* the per-PR CI-side visual-diff gate (deferred — POST_PHASE_1 § cross-cutting) MUST tolerate ≤ 1 % per-screen pixel delta or a small allowlist of timestamp-bearing screens; cannot use exact-match. The plan-text already prescribed `≤ 1 %`, so no contract change — but worth flagging here so the gate-author doesn't get surprised. Future tightening: freeze `datetime.now()` via a test-only `?seed_clock=` param at capture time (Phase 6 polish).

Operational propagations (per `AGENTS.md` § Workflow step 7 + `CLAUDE.md` § Deviations):

- New env-var surface (`PLAYWRIGHT_NODEJS_PATH` set by devShell, `--extra dev` baked into the orchestrator's `deps` step) → captured in `nix/devshell.nix` + `flake.nix` comments and in `docs/design/WORKFLOW.md` § Capturing a new visual baseline. No README user-facing change needed (`nix run .#dev` and `uv run python tests/visual/capture.py --baseline` are the public contracts; both work as documented).
- New gitignore entry (`tests/visual/screenshots/`) → in `.gitignore`, no further propagation needed.
- New runtime dep (`psycopg[binary]>=3.2.0`) → in `pyproject.toml` and `uv.lock`; transparent to self-hosters (just a slightly bigger venv); production paths (Dockerfile, nix package) pick it up via `uv sync` automatically.
