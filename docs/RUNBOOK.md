# Naavik · DevOps Runbook

> **Last updated:** 2026-05-21 (added § 2.12 First-run authentication / 401 troubleshooting per plan 71 / 0.3.3.14)
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
#   [migrate] (alembic upgrade head completes)
#   [app] INFO:     Application startup complete.
#   [app] dev server up at http://localhost:8000 — visit /signup to create your account
```

### 2.2 `greenlet_spawn has not been called` / `libstdc++.so.6: cannot open shared object file`

**Symptom:** first DB write under `nix run .#dev` raises SQLAlchemy greenlet error OR Python complains it can't find `libstdc++.so.6`.

**Root cause:** `flake.nix` predates plan 10b. SQLAlchemy's greenlet bridge dlopens `libstdc++.so.6`; NixOS' Python venv doesn't ship it on the loader path.

**Fix:** pull latest `flake.nix` — orchestrator now exports `LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib`. Same fix `nix/devshell.nix` has had since plan 09.

### 2.3 `SECRET_KEY` rotation (post-vault)

**Symptom:** after rotating `SECRET_KEY`, users get 401 on requests with stale cookies.

**Root cause:** plan 26 (0.2.0.01) deleted the encrypted vault. `SECRET_KEY` now signs JWTs only; rotating it invalidates existing cookies (which is the correct behavior — the old signature can't verify under the new key).

**Fix:** users re-authenticate from `/login`. New cookies are issued against the new `SECRET_KEY`.

**Note:** there is no "vault locked" state to recover from after plan 26. `.env` is the source of truth for secrets. Filesystem permissions (`chmod 0600 .env`) are the operative defense.

**Important:** the vault was deleted. Don't reintroduce encrypted-at-rest secret stores; `tests/test_no_vault_imports.py` lints against regressions. New secret-handling code uses env vars via `pydantic-settings` in `src/config.py`.

### 2.4 Port 5432 in use / "the orchestrator can't start Postgres"

**Symptom:** `nix run .#dev` errors with `could not bind to port 5432`.

**Root cause:** the dev orchestrator is supposed to use **5433** to dodge system Postgres. If you see this on 5432, you have an outdated `flake.nix` OR you're running `uv run alembic upgrade head` directly against the wrong DB.

**Fix:** confirm dev DB runs on `127.0.0.1:5433`. The orchestrator sets `DATABASE_URL` to `postgresql+asyncpg://naavik:password@127.0.0.1:5433/naavik` automatically. If running raw `uv run alembic` outside the orchestrator, export `DATABASE_URL` manually.

**Verify:**
```bash
psql -h 127.0.0.1 -p 5433 -U naavik -d naavik -c 'select version()'
```

### 2.5 "UI shows mock-looking data after `nix run .#dev`"

**Removed in plan 60 / 0.2.7.17 (2026-05-20).** The dual memory/DB persistence mode (gated by `NAAVIK_PERSISTENCE`) is gone. Plan 60 collapsed `src/db/sample_data.py` to fixture-only consumption — `db/seed.py` populates Postgres from those fixtures at first boot; routes read through the `services/*` layer for tables that have been migrated, and still read fixture-data for tables that haven't (incremental migration tracked in follow-up plan 0.2.7.17a). The `NAAVIK_PERSISTENCE` env var no longer exists in `flake.nix`, `nix/devshell.nix`, or `.env.example`.

**Verify Postgres is the underlying store:** `psql -h 127.0.0.1 -p 5433 -U naavik -d naavik -c "SELECT headline FROM profile WHERE user_id=1"`.

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
# Plan 26 (0.2.0.01): secrets are env-only. Confirm env vars are set.
env | grep -E '^(ANTHROPIC|OPENAI|OLLAMA)' | head -5

# Check the Settings row for active provider.
psql -h 127.0.0.1 -p 5433 -U naavik -d naavik -c \
  "SELECT llm_provider, llm_model FROM settings WHERE user_id=1;"
```

**Fix:** set the relevant env var in `.env` (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `OLLAMA_BASE_URL`), `chmod 0600 .env`, restart the server. The Settings · LLM Provider tab surfaces a green indicator next to the configured provider; gray indicators mean the env var is unset.

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

### 2.12 First-run authentication / 401 troubleshooting

**Symptom:** operator clones the repo, runs the app, can't sign in or sign up.

**Decision tree** (post plan 83 / 0.7.0.36):

- **No users in the DB** → visit `/signup` (or `/login?mode=signup`). Plan 83 deleted the auto-seed dev user; first-time setup is signup-driven. Enter email + 12+ character password (letter + digit) → land on onboarding.
- **`/login` doesn't load at all** → check the orchestrator logs. `[migrate]` likely errored. Tail `nix run .#dev` output; if Postgres / alembic failed, fix that first.
- **`hx-put` / `hx-post` returns 401 mid-session** → the JWT cookie expired (24h default; 30d with keep-signed-in). Re-login at `/login` mints a fresh cookie.

**Diagnose:** visit `/setup-help` — public diagnostic page that surfaces the `user_count` signal + recovery recipes (signup CTA, orchestrator-log troubleshooting, destructive `rm -rf .naavik/db` reset).

**Fix:**

```bash
# Canonical — visit /signup on first boot:
nix run .#dev
# Open http://localhost:8000 → click "Create account" → fill form.

# Manual without the orchestrator — set NAAVIK_DEBUG so SECRET_KEY validator
# accepts a missing .env:
export NAAVIK_DEBUG=1
uv run fastapi dev src/main.py
# Then sign up at /login?mode=signup.

# Destructive — drop the dev DB so you can sign up from scratch.
rm -rf .naavik/db
nix run .#dev
```

**Verify:**
- `/setup-help` renders the user_count row as `fresh` (when 0 users) or `users present` (when ≥ 1).
- The orchestrator scrollback shows `dev server up at http://localhost:8000 — visit /signup to create your account` once the app finishes booting.
- `curl -s 127.0.0.1:8000/login | grep -iE 'create.account'` returns the signup link.

### 2.13 `FATAL: data directory "..." has invalid permissions` on `nix run .#dev`

**Symptom:** Postgres step in the orchestrator crashes immediately:

```
2026-MM-DD HH:MM:SS.SSS GMT [PID] FATAL:  data directory "/home/.../.naavik/db" has invalid permissions
2026-MM-DD HH:MM:SS.SSS GMT [PID] DETAIL:  Permissions should be u=rwx (0700) or u=rwx,g=rx (0750).
```

`ls -ld .naavik/db/` shows `drwxrwx---+` (the trailing `+` means an extended ACL is set).

**Root cause:** the parent of `.naavik/db/` (typically a directory under your `$HOME`) carries a POSIX default ACL — e.g. `setfacl -d -m user:another-user:rwx ~/personal/dev` for pair-sharing between local Unix users. Any subdir created under such a parent inherits the default ACL at creation time, including an `mask::rwx` entry that makes `stat()` report group-rwx mode bits. Postgres 14+ refuses any data-dir mode beyond 0700 (or 0750 with matching group) regardless of WHO has actual access — it only looks at the mode bits.

**Fix (auto-applied as of 0.7.0.43, 2026-05-22):** the orchestrator's `cli.preHook` in `flake.nix` now strips the parent's default ACL on every boot and re-enforces 0700 on `.naavik/db/` if it exists. Subsequent boots are clean even if your home dir has inherited ACLs.

**Manual recovery (if you're on an older naavik checkout pre-0.7.0.43, or the auto-strip itself failed):**

```bash
# Strip access ACLs + default ACLs from the data dir + parent
setfacl -bR ./.naavik/db
setfacl -k  ./.naavik/db
setfacl -k  ./.naavik           # stop future re-inheritance
chmod -R u=rwX,go= ./.naavik/db # 0700 on dirs / 0600 on files

# Verify — no `+` on the listing
ls -ld ./.naavik/db
# Expected: drwx------ ...
```

**Verify:**
- `ls -ld .naavik/db` shows mode `drwx------` (no trailing `+`).
- `getfacl .naavik/db` shows ONLY `user::rwx group::--- other::---` (no `user:<name>:rwx` entries).
- `nix run .#dev` boots through `[db]` cleanly.

**If it recurs after the auto-strip:** check whether some other tool is re-applying ACLs (sync utility, file-manager-set permission, NFS server policy). The auto-strip runs every boot, so it self-heals — but if the source of the ACL keeps adding it back, you'll see the strip in the preHook output every time.

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

### 3.5 Inspect secret usage

Plan 26 (0.2.0.01) deleted `~/.naavik/logs/vault-audit.log`. Secret material is env-loaded; access-log scrubbing for `Authorization` / `Cookie` headers + the request-tracing pipeline (Phase 2.5) replace the per-key audit trail. For "is this env var set" inspection:

```bash
env | grep -E '^(ANTHROPIC|OPENAI|OLLAMA|DISCORD|TELEGRAM|PORTFOLIO)' | sed 's/=.*$/=<redacted>/'
```

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

### 4.2 Recover from a missing `.env`

Plan 26 (0.2.0.01) deleted the encrypted vault. Secrets live in `.env`. Recovery is restore-from-backup:

```bash
# 1. Restore .env from your backup (any standard tool: tarball, rsync, etc.).
# 2. chmod 0600 .env
# 3. Restart the app.
```

If no backup exists, regenerate the secrets from each provider's console (Anthropic / OpenAI / Discord / Telegram) and write them to a fresh `.env`. Settings UI shows green indicators once env vars are present.

### 4.3 Restore from daily snapshot

Snapshots land at `~/.naavik/data/snapshots/snapshot-YYYY-MM-DD.marker` (marker file; plan 10 § C ships marker-only, full dump planned for Phase 6).

For now, use Postgres native dump/restore:
```bash
# Dump
pg_dump -h 127.0.0.1 -p 5433 -U naavik -d naavik > naavik-$(date +%F).sql

# Restore (against a fresh DB)
psql -h 127.0.0.1 -p 5433 -U naavik -d naavik < naavik-2026-05-16.sql
```

Self-hoster backup + DR procedure (canonical artifact list, off-site rotation recipes via restic / borg / s3 sync, full recovery walkthrough): see `docs/DEPLOYMENT.md` § Backups + disaster recovery.

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

-- 5. .env permissions (plan 26 post-vault check)
-- (shell)
stat -c '%a %U:%G %n' "${DATA_DIR:-.}/.env" .env 2>/dev/null | head -1
-- Healthy: `600 <user>:<group> .env`.
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
- **Reintroduce the vault.** Plan 26 (0.2.0.01) deleted `src/services/vault.py`. `tests/test_no_vault_imports.py` lints against regressions. New secrets land in `.env` or in a Settings UI surface backed by env reads.
- **Extend the `naavik` CLI** for a fix. CLI is on the Phase 2 task `0.2.0.02` sunset track. Same disposition — only `serve` remains, and it's queued for removal.
- **Run `rm -rf ~/.naavik/`** to "reset" without confirming the user. That nukes snapshots + cached PDFs in addition to the DB.
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
