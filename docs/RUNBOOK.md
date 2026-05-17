# Naavik · DevOps Runbook

> **Last updated:** 2026-05-16
> **Audience:** devops agent + human operators debugging Naavik in dev or production.
> **Companion docs:** `docs/AGENT_OPS.md` (agent system), `docs/plans/POST_PHASE_1.md` (post-Phase-1 testing playbook + monitoring), `README.md` § Troubleshooting (user-facing), `AGENTS.md` § Workflow (how this runbook gets updated).

This is the single-source operational guide for debugging Naavik. The `devops` agent reads this first when invoked. Human operators read it when something breaks at 3 AM.

**Rule:** every new failure mode the devops agent encounters in production lands here as a numbered runbook entry BEFORE the bug is closed. Drift is the #1 source of repeat outages.

---

## 1. Quick triage

```
Something is broken. Ask in this order:

1. Can you reproduce it?
   - YES → § 2 (known failure modes) → fix or § 3 (diagnostic recipes) → root-cause
   - NO  → § 4 (instrument + log + come back when it recurs)

2. Is the dev orchestrator up? (`nix run .#dev` running cleanly)
   - YES → narrow to the failing surface (page / endpoint / job / migration)
   - NO  → § 2.1 (orchestrator startup failures)

3. Did this work yesterday?
   - YES → `git log --since='yesterday'` to find the smoking gun
   - NO  → never worked; check ROADMAP for whether it should ship yet
```

---

## 2. Known failure modes (alphabetical by symptom)

### 2.1 `[seed]` or `[app]` step never prints in `nix run .#dev`

**Symptom:** orchestrator boots Postgres, alembic completes, then either hangs or prints nothing for the FastAPI app.

**Root causes seen in production:**
- **TTY / SIGTTIN** (plan 10a). fastapi-cli's worker opens `/dev/tty`; process-compose-spawned background process groups receive `SIGTTIN`, never bind `:8000`. Fixed by `exec setsid -w uv run --no-sync ... < /dev/null` in `flake.nix` + `coreutils` in devTools.
- **alembic async wedge** (suspected, not actual). `migrations/env.py` using async engine + psycopg in the same process. Mitigation: `migrations/env.py` switched to sync psycopg.
- **PYTHONPATH leak from outer shell.** Mitigation: `unset PYTHONPATH` in the orchestrator preamble.

**Fix:** pull latest `flake.nix` (plan 10a-or-later). Verify `setsid -w` wraps both `[migrate]` and `[app]` lines. Verify `coreutils` is in devTools.

**Verify:**
```bash
nix run .#dev
# Expect:
#   [seed] dev user: shyam.padia930@gmail.com
#   [seed] dev password: <16-char>
#   [app] INFO:     Application startup complete.
#   [app] [boot] dev credential available at ~/.naavik/dev-credentials
```

### 2.2 `greenlet_spawn has not been called` / `libstdc++.so.6: cannot open shared object file`

**Symptom:** first DB write under `nix run .#dev` raises SQLAlchemy greenlet error OR Python complains it can't find `libstdc++.so.6`.

**Root cause:** `flake.nix` predates plan 10b. SQLAlchemy's greenlet bridge dlopens `libstdc++.so.6`; NixOS' Python venv doesn't ship it on the loader path.

**Fix:** pull latest `flake.nix` — orchestrator now exports `LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib`. Same fix `nix/devshell.nix` has had since plan 09.

### 2.3 Vault locked — `SECRET_KEY` mismatch

**Symptom:** Settings · Deployment renders a rose **Vault locked** banner. API requests that read encrypted secrets return 503. Boot logs show `key_fingerprint mismatch: stored=<X> expected=<Y>`.

**Root cause:** the env's `SECRET_KEY` no longer matches what encrypted the on-disk vault at `~/.naavik/secrets.enc`. Most common: someone rotated `.env` without running `naavik vault rotate-key` first.

**Fix (option A — restore old key):**
```bash
# In your shell or .env, restore the SECRET_KEY value that was set when the vault was first created.
export SECRET_KEY='<the-original-value>'
# Restart the app.
```

**Fix (option B — re-encrypt vault with new key):**
```bash
naavik vault rotate-key --old="$OLD_SECRET_KEY" --new="$NEW_SECRET_KEY"
export SECRET_KEY="$NEW_SECRET_KEY"
# Restart the app.
```

**Verify:** `naavik vault status` — stored + expected fingerprints match. Banner disappears in Settings · Deployment.

**Important:** Phase 2 task 2.12 deletes the vault entirely. Secrets move to env-var-only via gitignored `.env`. Don't add new vault scopes (AGENTS.md § Key Conventions § CLI).

### 2.4 Port 5432 in use / "the orchestrator can't start Postgres"

**Symptom:** `nix run .#dev` errors with `could not bind to port 5432`.

**Root cause:** the dev orchestrator is supposed to use **5433** to dodge system Postgres. If you see this on 5432, you have an outdated `flake.nix` OR you're running `uv run alembic upgrade head` directly against the wrong DB.

**Fix:** confirm dev DB runs on `127.0.0.1:5433`. The orchestrator sets `DATABASE_URL` to `postgresql+asyncpg://naavik:password@127.0.0.1:5433/naavik` automatically. If running raw `uv run alembic` outside the orchestrator, export `DATABASE_URL` manually.

**Verify:**
```bash
psql -h 127.0.0.1 -p 5433 -U naavik -d naavik -c 'select version()'
```

### 2.5 "UI shows mock-looking data after `nix run .#dev`"

**Symptom:** Profile edits don't persist. KPIs look static. Jobs list is the hardcoded sample data, not seeded.

**Root cause:** `NAAVIK_PERSISTENCE` is `memory` instead of `db`. The orchestrator sets `db` automatically (plan 10b); raw `uv run fastapi dev` doesn't.

**Fix:**
```bash
export NAAVIK_PERSISTENCE=db
uv run fastapi dev
```

Plan 10c also wired `NAAVIK_PERSISTENCE=db` into `nix develop`'s shellHook, so interactive dev shells should be in parity. If you still see memory mode under `nix develop`, your `nix/devshell.nix` predates plan 10c.

**Verify:** `psql -h 127.0.0.1 -p 5433 -U naavik -d naavik -c "SELECT headline FROM profile WHERE user_id=1"` — edit the profile in the UI, re-run, value should change.

### 2.6 Process-compose Ctrl-C leaves orphan processes

**Symptom:** after Ctrl-C, `ps -ef | grep fastapi` shows the FastAPI worker still running. Re-running `nix run .#dev` errors on port bind.

**Root cause:** `setsid -w` doesn't forward signals from process-compose. The `[app]` / `[migrate]` workers detach into their own sessions and don't see SIGINT.

**Fix:** plan 10a (2026-05-03 orphan-cleanup) added `shutdown.command` to process-compose that `pkill`s by tight cmdline pattern. Pull latest `flake.nix`.

**Verify after pull:**
```bash
nix run .#dev  # Ctrl-C after boot
ps -ef | grep -E 'fastapi|naavik' | grep -v grep
# Should be empty.
```

### 2.7 Alembic migration failure ("Can't locate revision X")

**Symptom:** `uv run alembic upgrade head` fails with "Can't locate revision identified by 'X'" or "Multiple head revisions are present."

**Root causes:**
- Dev DB has a revision row pointing to a deleted migration file (you reset state without dropping `alembic_version`).
- Two migration files conflict on the same `down_revision`.

**Fix:**
```bash
# Nuclear: wipe the dev DB and re-seed.
rm -rf .naavik/db
nix run .#dev   # re-initializes Postgres + runs migrations + seeds

# Surgical: clear alembic_version + re-upgrade.
psql -h 127.0.0.1 -p 5433 -U naavik -d naavik -c "DELETE FROM alembic_version;"
uv run alembic upgrade head
```

**Multi-head fix:** `uv run alembic merge -m "merge heads" head1 head2` then upgrade.

### 2.8 Playwright fails on NixOS / "Executable doesn't exist at /home/.../chromium..."

**Symptom:** `tests/visual/capture.py` errors with "Executable doesn't exist" or "Failed to launch chromium."

**Root cause:** pip-installed Playwright tries to download its own browser binaries; NixOS' non-FHS dynamic linker rejects them.

**Fix:** plan 10a wired `nodejs_22` + `PLAYWRIGHT_NODEJS_PATH` into the dev shell. Also pinned `playwright>=1.58.0,<1.59` to match `pkgs.playwright-driver.browsers`'s chromium-1208.

**Verify:**
```bash
nix develop
uv run python tests/visual/capture.py --baseline
ls tests/visual/baseline/  # should have 20+ PNGs
```

### 2.9 LLM provider auth error / `401 Unauthorized` on score_job

**Symptom:** `services/scorer.py` raises auth error. ApiUsage shows failure rows with `error_code=401`.

**Diagnose:**
```bash
# Check vault has a key for this provider.
naavik vault status   # shows scope counts, not values

# Check the Settings row.
psql -h 127.0.0.1 -p 5433 -U naavik -d naavik -c \
  "SELECT llm_provider, anthropic_configured, openai_configured FROM settings WHERE user_id=1;"
```

**Fix:** re-enter the API key via Settings · LLM Provider in the UI. The form-driven flow runs the key through the vault (plan 10b § B.11). If using env fallback (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY`), confirm the var is set in the process environment.

### 2.10 APScheduler job not firing

**Symptom:** `applications.auto_apply` (5min) or `admin.daily_db_snapshot` not running. No Discord notifications. No new rows in `~/.naavik/data/snapshots/`.

**Diagnose:**
```sql
-- Check the job is registered in the pg job store.
SELECT id, next_run_time FROM apscheduler_jobs ORDER BY next_run_time;
```

If the row is missing, the scheduler didn't register on lifespan. Check `src/main.py` lifespan + `src/scheduler/jobs.py` registration. Restart the app — `scheduler/__init__.py` is lifespan-managed.

If `next_run_time` is in the past, the job is supposed to run but isn't — check app logs for unhandled exceptions in the job body.

### 2.11 Trace logs missing for a `/build` run

**Symptom:** `claude /runs` shows a recent run, but `traces/<run-id>/` is empty.

**Root cause:** sub-agent didn't write to its log file. Most common: agent prompt's tracing format wasn't followed, OR the trace dir was created after the agent ran and the agent wrote to `traces/<wrong-run-id>/`.

**Diagnose:**
```bash
ls -la traces/<run-id>/                           # confirm dir exists
grep -r "<run-id>" .claude/agents/ .claude/commands/  # confirm prompts reference the same id
```

**Fix:** manager must pick the run-id at `/build` start and pass it verbatim to every Task call's prompt. If sub-agents wrote elsewhere, look for sibling `traces/<other-id>/` dirs created in the same minute.

---

## 3. Diagnostic recipes

### 3.1 Inspect a CI failure

```bash
gh run list --branch <branch> --limit 5
gh run view <run-id> --log | less
gh run view <run-id> --log-failed   # only failed steps
```

For a specific failed job:
```bash
gh run view <run-id> --job <job-id> --log
```

### 3.2 Inspect API cost telemetry

```sql
SELECT provider, model, COUNT(*) AS calls,
       SUM(cost_usd) AS total_cost, AVG(latency_ms) AS avg_ms,
       SUM(CASE WHEN ok THEN 0 ELSE 1 END) AS failures
FROM api_usage
WHERE occurred_at >= now() - interval '24 hours'
GROUP BY provider, model
ORDER BY total_cost DESC;
```

Expected for healthy production (single user, semi-active day): < 50 calls, < $1 spend, > 90% ok-rate. Spike → investigate the calling service.

### 3.3 Inspect DRAFT lifecycle

```sql
-- DRAFTs stuck >24h.
SELECT id, job_id, docs_state, created_at, updated_at
FROM applications
WHERE status = 'DRAFT' AND created_at < now() - interval '24 hours';

-- DRAFT generation failures.
SELECT id, job_id, docs_state, last_error
FROM applications
WHERE docs_state = 'failed';
```

Stuck DRAFTs feed the Discover right-rail `up_next_card state="stuck"` (plan 10 § C.3). If the rail shows none but the SQL returns rows, `services/application_service.stuck_drafts` query is mis-filtering.

### 3.4 Inspect APScheduler state

```sql
SELECT id, next_run_time, jobstore
FROM apscheduler_jobs
ORDER BY next_run_time NULLS LAST;
```

`next_run_time` NULL → job is paused. `next_run_time` in the past → scheduler is wedged.

### 3.5 Inspect vault audit log

```bash
tail -n 50 ~/.naavik/logs/vault-audit.log | jq .
```

Each line: `{caller, key, op, scope, ts}`. Values **never** appear. Use to trace "when was key X last rotated" or "why did read fail at time T".

### 3.6 Inspect a trace run

```bash
# Latest run.
./traces/watch.sh

# Specific run.
./traces/watch.sh 2026-05-16T09-30-15_a3f2b8

# From slash command.
claude /runs 10
claude /runs <run-id>
```

Per-agent log formats are documented in `docs/AGENT_OPS.md` § 7.2. Grep across runs:
```bash
grep -h "DEVIATION" traces/*/engineer.log | sort | uniq -c | sort -rn
```

### 3.7 Inspect HTMX swap failures

In browser devtools → Network tab → filter on `Fetch/XHR`. Failed HTMX requests show as 4xx/5xx; the swap target won't update.

Common: missing CSRF token (POST routes require double-submit). Fix in the page template: every `<form hx-post>` needs `hx-headers='{"X-CSRF-Token": "{{ csrf_token }}"}'`.

---

## 4. Recovery procedures

### 4.1 Reset dev DB to clean state

```bash
# Nuclear (drops the Postgres data dir; orchestrator re-initializes on next boot).
rm -rf .naavik/db

# Or surgical (downgrade + re-upgrade + re-seed).
uv run alembic downgrade base
uv run alembic upgrade head
uv run python -m db.seed
```

Both: ~10s on a warm machine.

### 4.2 Recover from corrupted vault

```bash
ls -lt ~/.naavik/secrets.enc.bak.*  # most recent backup first
cp ~/.naavik/secrets.enc.bak.<latest> ~/.naavik/secrets.enc
# Restart the app with the SECRET_KEY that encrypted that backup.
```

If no backup exists, the secrets are unrecoverable — start fresh:
```bash
rm ~/.naavik/secrets.enc ~/.naavik/key.bin
naavik init     # generates a fresh key + empty vault
# Re-enter secrets via Settings · LLM Provider / Settings · Notifications.
```

### 4.3 Restore from daily snapshot

Snapshots land at `~/.naavik/data/snapshots/snapshot-YYYY-MM-DD.marker` (marker file; plan 10 § C ships marker-only, full dump planned for Phase 6).

For now, use Postgres native dump/restore:
```bash
# Dump
pg_dump -h 127.0.0.1 -p 5433 -U naavik -d naavik > naavik-$(date +%F).sql

# Restore (against a fresh DB)
psql -h 127.0.0.1 -p 5433 -U naavik -d naavik < naavik-2026-05-16.sql
```

### 4.4 Tear down + recreate the dev orchestrator stack

```bash
pkill -f 'fastapi dev'
pkill -f 'naavik/.venv/bin/python'
pkill -f 'naavik/.venv/bin/alembic'
rm -rf .naavik/db
nix run .#dev
```

If `pkill` doesn't find them but the orchestrator still won't start, see § 2.6.

---

## 5. Quality gates

The devops agent owns these as CI surrogates. Run them in this order on every PR:

```bash
uv run ruff check .                         # lint
uv run ruff format --check .                # format
uv run pytest -x                            # tests (stop on first failure)
NAAVIK_LIVE_DB=1 uv run pytest -x          # gated live-DB tests
uv run python tests/visual/capture.py       # Playwright (UI changes only)
```

Specifics:
- `NAAVIK_BCRYPT_COST=4` for tests (10× speedup; production = 12).
- `NAAVIK_LIVE_DB=1` requires `DATABASE_URL` exported + Postgres reachable. Use the orchestrator's DB or a one-shot Docker.
- Playwright baselines are committed under `tests/visual/baseline/`. Diff threshold: 1% pixel delta per screen.

Failing any of these → engineer fixes; don't paper over with `# noqa` or `pytest.skip`.

---

## 6. Monitoring playbook (post-Phase-1)

From `docs/plans/POST_PHASE_1.md` § Cross-cutting concerns.

### Daily checks (manual until Phase 6 observability ships)

```sql
-- 1. Cost in last 24h
SELECT SUM(cost_usd) FROM api_usage WHERE occurred_at >= now() - interval '24 hours';
-- Healthy: < $1 single-user, < $5 multi-user (when applicable).

-- 2. Failure rate in last 24h
SELECT
  SUM(CASE WHEN ok THEN 1 ELSE 0 END)::float / NULLIF(COUNT(*), 0) AS ok_rate
FROM api_usage WHERE occurred_at >= now() - interval '24 hours';
-- Healthy: > 0.95.

-- 3. Stuck DRAFTs
SELECT COUNT(*) FROM applications WHERE status='DRAFT' AND created_at < now() - interval '24 hours';
-- Healthy: 0. > 5 → investigate scoring / generation.

-- 4. APScheduler health
SELECT id, EXTRACT(EPOCH FROM (now() - next_run_time)) AS overdue_seconds
FROM apscheduler_jobs WHERE next_run_time < now() - interval '5 minutes';
-- Healthy: empty result set.

-- 5. Vault audit anomaly
-- (shell)
tail -n 200 ~/.naavik/logs/vault-audit.log | jq -r '.op' | sort | uniq -c
-- Healthy: mostly `get` ops, few `set`, very few `delete` or `rotate-key`.
```

### Per-incident response template

```
1. Acknowledge — note the time, the symptom, the surface (UI / API / cron / scraper).
2. Repro — § 1 quick triage.
3. Diagnose — § 3 recipes for the affected surface.
4. Fix — apply, write failing-before / passing-after test.
5. Verify — run § 5 quality gates.
6. Runbook entry — if this was a NEW failure mode, add a § 2.X entry here.
7. Plan deviation — if the bug surfaced a flaw in a recent plan, ensure the plan's `## Deviations from plan` section captures it before archive.
8. Roadmap update — if scope shifts, update ROADMAP.md.
```

---

## 7. Anti-patterns (do NOT do these)

- **Patch the symptom while the root cause lives.** A `try/except` swallowing a real error is worse than the crash it hides.
- **Skip the failing test.** `pytest.skip` without an issue link is a debt you'll inherit.
- **Bypass `setsid -w`** in the orchestrator to "make it simpler." You'll bring back the SIGTTIN bug.
- **Add a new vault scope** for a fix. The vault is on the Phase 2 task 2.12 sunset track (AGENTS.md § Key Conventions § CLI). Move the secret to `.env` (post-2.12) or design the equivalent Settings UI surface.
- **Extend the `naavik` CLI** for a fix. CLI is on the Phase 2 task 2.11 sunset track. Same disposition.
- **Run `rm -rf ~/.naavik/`** to "reset" without confirming the user. That nukes the vault and dev-credentials file in addition to the DB.
- **Run `--no-verify`** on a commit to bypass pre-commit hooks. The hook failed for a reason; fix it.
- **Close a flaky test** without instrumenting it. Capture the flake's signature in `engineer.log` so the next devops invocation can see the pattern.

---

## 8. Extending this runbook

Every new failure mode the devops agent encounters lands here as a numbered entry BEFORE the bug is closed. The entry contract:

1. **Section** (`## 2. Known failure modes`).
2. **Number** (`### 2.<N>` where N = next available).
3. **Body**: Symptom → Root cause → Fix → Verify.
4. **Cross-link**: link from `README.md` § Troubleshooting if it's user-facing.

PRs that close a bug without updating this runbook get bounced by the hacker / engineer review.

---

## 9. Pointer index

| If you're debugging... | Read |
|---|---|
| First-time setup of the agent system | `docs/AGENT_OPS.md` § 2 |
| Backend API surface | `docs/design/BACKEND.md` |
| Data model + state machines | `docs/design/DATA_MODEL.md` |
| HTMX interaction patterns | `docs/design/INTERACTIONS.md` |
| Visual contract | `DESIGN.md` (root) |
| UI sub-process (skill routing, checklists, common patterns) | `docs/design/WORKFLOW.md` |
| Deployment guide (4 paths + config + ops) | `docs/DEPLOYMENT.md` |
| Architecture overview | `docs/ARCHITECTURE.md` |
| Phase 1 testing playbook (full) | `docs/plans/POST_PHASE_1.md` § Phase 1 testing playbook |
| Plan-to-plan dependencies | `ROADMAP.md` (each phase header has a `**Plan:**` line) |
| Past failures shipped through plans | `docs/plans/archive/*.md` § Deviations from plan |
