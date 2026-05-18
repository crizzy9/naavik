---
description: Pull the relevant section from `docs/RUNBOOK.md` for a given failure-mode symptom — orchestrator startup hang, asyncpg auth fail, vault lock mismatch, port 5432 conflict, mock-looking UI data, orphan processes after Ctrl-C, alembic migration failure, Playwright NixOS crash, LLM auth 401, APScheduler not firing, trace logs missing. Use whenever something breaks, when devops is dispatched on a bug, when the user reports a symptom. Triggers on phrases like "runbook", "runbook for", "known failure mode", "why does", "<symptom> debugging", "orchestrator hang", "vault locked", "port 5432", "mock data", "orphan process", "alembic failure", "playwright fails".
---

# devops-runbook-lookup

`docs/RUNBOOK.md` = canonical jump table for known Naavik failure modes. Each entry: Symptom → Root cause → Fix → Verify. This skill is lookup index — find matching § 2.X entry from symptom, Read it. Do NOT duplicate runbook content into conversation; cite + Read.

## When to invoke

- Devops dispatched on bug — first action: identify matching § 2.X entry.
- User reports symptom matching known failure mode.
- Pre-flight sanity ("does this look like § 2.5 again?").
- Architect referencing runbook entry in plan.

## Jump table (symptom → runbook §)

| Symptom | RUNBOOK § |
|---|---|
| `[seed]` or `[app]` never prints in `nix run .#dev` (orchestrator hang) | § 2.1 |
| `greenlet_spawn has not been called` OR `libstdc++.so.6: cannot open shared object file` | § 2.2 |
| Vault locked banner / `SECRET_KEY` mismatch / `key_fingerprint mismatch` boot error | § 2.3 |
| Port 5432 in use / "orchestrator can't start Postgres" | § 2.4 |
| UI shows mock-looking data / profile edits don't persist | § 2.5 |
| Process-compose Ctrl-C leaves orphan FastAPI workers | § 2.6 |
| Alembic migration failure ("Can't locate revision X" / "Multiple head revisions") | § 2.7 |
| Playwright fails on NixOS / "Executable doesn't exist at /home/.../chromium..." | § 2.8 |
| LLM provider auth error / `401 Unauthorized` on score_job | § 2.9 |
| APScheduler job not firing (auto_apply / daily_db_snapshot) | § 2.10 |
| Trace logs missing for `/build` run | § 2.11 |

## Diagnostic recipes (RUNBOOK § 3)

| Goal | § |
|---|---|
| Inspect CI failure (`gh run view`) | § 3.1 |
| Inspect API cost telemetry (`api_usage` SQL) | § 3.2 |
| Inspect DRAFT lifecycle (stuck drafts SQL) | § 3.3 |
| Inspect APScheduler state (`apscheduler_jobs` SQL) | § 3.4 |
| Inspect vault audit log (`~/.naavik/logs/vault-audit.log`) | § 3.5 |
| Inspect trace run (`./traces/watch.sh`) | § 3.6 |
| Inspect HTMX swap failures (browser devtools Network) | § 3.7 |

## Recovery procedures (RUNBOOK § 4)

| Procedure | § |
|---|---|
| Reset dev DB to clean state | § 4.1 |
| Recover from corrupted vault (`secrets.enc.bak.*`) | § 4.2 |
| Restore from daily snapshot (pg_dump/restore) | § 4.3 |
| Tear down + recreate dev orchestrator stack | § 4.4 |

## Other sections

| § | Content |
|---|---|
| 1 | Quick triage decision tree (3 questions) |
| 5 | Quality gates (ruff/pytest/live-DB/Playwright) |
| 6 | Monitoring playbook (daily SQL checks + per-incident response template) |
| 7 | Anti-patterns (do NOT do these) |
| 8 | Extending runbook (how to add new § 2.X entries) |
| 9 | Pointer index (where to read for which symptom-area) |

## Workflow

1. **Identify symptom.** Translate user report or repro output → closest jump-table row.

2. **Read section directly:**
   ```
   Read docs/RUNBOOK.md
   ```
   Use offset + limit to load only relevant § 2.X if file is large enough that full-load wastes context.

3. **Follow Symptom → Root cause → Fix → Verify:**
   - **Symptom** confirms right entry.
   - **Root cause** explains WHY (so you don't band-aid).
   - **Fix** = canonical remediation.
   - **Verify** = post-fix check.

4. **No matching entry → NEW failure mode.** Per `docs/RUNBOOK.md § 8`:
   - Reproduce + diagnose + fix as usual.
   - BEFORE closing bug, add `### 2.<next-N>` entry w/ Symptom → Root cause → Fix → Verify.
   - Cross-link from `README.md § Troubleshooting` if user-facing.
   - PR reviewer bounces PR if new failure mode closed without runbook entry.

## Worked example

User: "my orchestrator boots Postgres + alembic finishes but then nothing else prints; no [app] line."

→ Jump table → § 2.1 (orchestrator startup hang).
→ Read RUNBOOK.md § 2.1.
→ Root cause: TTY / SIGTTIN bug from plan 10a's process-compose-spawned worker.
→ Fix: pull latest `flake.nix`, verify `setsid -w` + `coreutils` + `< /dev/null` redirect.
→ Verify: `nix run .#dev` → expect `[seed]`, `[app] INFO: Application startup complete.`, `[app] [boot] dev credential available at ~/.naavik/dev-credentials`.

## Canonical references

- `docs/RUNBOOK.md` — authoritative file.
- `docs/RUNBOOK.md § 9` — pointer index.
- `.claude/agents/devops.md` § "Common known failure modes (jump table to RUNBOOK)".
- `.claude/agents/devops.md` § "Required reading on cold start" (steps 1–3).

## When NOT to invoke

- Pure forward-progress engineering (no symptom to look up).
- Compaction events.

## Forbidden during invocation

- Do NOT duplicate runbook content into conversation or other files. Cite + Read.
- Do NOT close bug fix without adding runbook entry for new failure mode. Drift is #1 source of repeat outages (RUNBOOK § 8).
- Do NOT patch symptom while ignoring root-cause section. `try/except` swallow is worse than original crash.
- Do NOT `rm -rf ~/.naavik/` to "reset" without warning user. Nukes vault + dev-credentials in addition to DB.
