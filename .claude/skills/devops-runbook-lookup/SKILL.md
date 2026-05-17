---
description: Pull the relevant section from `docs/RUNBOOK.md` for a given failure-mode symptom — orchestrator startup hang, asyncpg auth fail, vault lock mismatch, port 5432 conflict, mock-looking UI data, orphan processes after Ctrl-C, alembic migration failure, Playwright NixOS crash, LLM auth 401, APScheduler not firing, trace logs missing. Use whenever something breaks, when devops is dispatched on a bug, when the user reports a symptom. Triggers on phrases like "runbook", "runbook for", "known failure mode", "why does", "<symptom> debugging", "orchestrator hang", "vault locked", "port 5432", "mock data", "orphan process", "alembic failure", "playwright fails".
---

# devops-runbook-lookup

`docs/RUNBOOK.md` is the canonical jump table for known Naavik failure modes. Each entry has Symptom → Root cause → Fix → Verify. This skill is the lookup index — find the matching § 2.X entry from a symptom and Read it. Do NOT duplicate runbook content into the conversation; cite + Read.

## When to invoke

- Devops dispatched on a bug — first action is identifying the matching § 2.X entry.
- User reports a symptom that sounds like a known failure mode.
- Pre-flight sanity check ("does this look like § 2.5 again?").
- Architect referencing a runbook entry in a plan.

## What this skill does

### Jump table (symptom → runbook section)

| Symptom | RUNBOOK § |
|---|---|
| `[seed]` or `[app]` step never prints in `nix run .#dev` (orchestrator startup hang) | § 2.1 |
| `greenlet_spawn has not been called` OR `libstdc++.so.6: cannot open shared object file` | § 2.2 |
| Vault locked banner / `SECRET_KEY` mismatch / `key_fingerprint mismatch` boot error | § 2.3 |
| Port 5432 in use / "orchestrator can't start Postgres" | § 2.4 |
| UI shows mock-looking data / profile edits don't persist | § 2.5 |
| Process-compose Ctrl-C leaves orphan FastAPI workers | § 2.6 |
| Alembic migration failure ("Can't locate revision X" / "Multiple head revisions") | § 2.7 |
| Playwright fails on NixOS / "Executable doesn't exist at /home/.../chromium..." | § 2.8 |
| LLM provider auth error / `401 Unauthorized` on score_job | § 2.9 |
| APScheduler job not firing (auto_apply / daily_db_snapshot) | § 2.10 |
| Trace logs missing for a `/build` run | § 2.11 |

### Diagnostic recipe sections (RUNBOOK § 3)

| Goal | RUNBOOK § |
|---|---|
| Inspect a CI failure (`gh run view`) | § 3.1 |
| Inspect API cost telemetry (`api_usage` SQL) | § 3.2 |
| Inspect DRAFT lifecycle (stuck drafts SQL) | § 3.3 |
| Inspect APScheduler state (`apscheduler_jobs` SQL) | § 3.4 |
| Inspect vault audit log (`~/.naavik/logs/vault-audit.log`) | § 3.5 |
| Inspect a trace run (`./traces/watch.sh`) | § 3.6 |
| Inspect HTMX swap failures (browser devtools Network tab) | § 3.7 |

### Recovery procedures (RUNBOOK § 4)

| Procedure | RUNBOOK § |
|---|---|
| Reset dev DB to clean state | § 4.1 |
| Recover from corrupted vault (use `secrets.enc.bak.*`) | § 4.2 |
| Restore from daily snapshot (pg_dump/restore) | § 4.3 |
| Tear down + recreate the dev orchestrator stack | § 4.4 |

### Other sections

| Section | What's there |
|---|---|
| § 1 | Quick triage decision tree (3 questions) |
| § 5 | Quality gates (ruff / pytest / live-DB / Playwright) |
| § 6 | Monitoring playbook (daily SQL checks + per-incident response template) |
| § 7 | Anti-patterns (do NOT do these) |
| § 8 | Extending the runbook (how to add new § 2.X entries) |
| § 9 | Pointer index (where to read for which symptom-area) |

## Workflow

1. **Identify the symptom.** Translate the user's report or your repro output into the closest jump-table row.

2. **Read the section** directly:
   ```
   Read docs/RUNBOOK.md
   ```
   Use offset + limit to load only the relevant § 2.X section if the file is large enough that full-load wastes context.

3. **Follow the Symptom → Root cause → Fix → Verify shape:**
   - **Symptom** confirms you're on the right entry.
   - **Root cause** explains WHY the symptom appears (so you don't band-aid).
   - **Fix** is the canonical remediation.
   - **Verify** is the post-fix check.

4. **If no matching entry exists,** this is a NEW failure mode. Per `docs/RUNBOOK.md § 8`:
   - Reproduce + diagnose + fix as usual.
   - BEFORE closing the bug, add `### 2.<next-N>` entry with Symptom → Root cause → Fix → Verify.
   - Cross-link from `README.md § Troubleshooting` if user-facing.
   - PR reviewer bounces the PR if a new failure mode is closed without a runbook entry.

## Worked example

User reports: "my orchestrator boots Postgres + alembic finishes but then nothing else prints; no [app] line."

→ Jump table → § 2.1 (orchestrator startup hang).
→ Read RUNBOOK.md § 2.1.
→ Root cause: TTY / SIGTTIN bug from plan 10a's process-compose-spawned worker.
→ Fix: pull latest `flake.nix`, verify `setsid -w` + `coreutils` + `< /dev/null` redirect.
→ Verify: `nix run .#dev` and expect `[seed]`, `[app] INFO: Application startup complete.`, `[app] [boot] dev credential available at ~/.naavik/dev-credentials`.

## Canonical references

- `docs/RUNBOOK.md` — the authoritative file.
- `docs/RUNBOOK.md § 9` — pointer index (where to read for which symptom-area).
- `.claude/agents/devops.md` § "Common known failure modes (jump table to RUNBOOK)".
- `.claude/agents/devops.md` § "Required reading on cold start" (steps 1–3 are the RUNBOOK).

## When NOT to invoke

- Pure forward-progress engineering (no symptom to look up).
- Compaction events.

## Forbidden during invocation

- Do NOT duplicate runbook content into the conversation or other files. Cite + Read. The runbook is the source of truth.
- Do NOT close a bug fix without adding a runbook entry for a new failure mode. Drift is the #1 source of repeat outages (RUNBOOK § 8 codifies this).
- Do NOT patch the symptom while ignoring the root cause section. A `try/except` swallow is worse than the original crash.
- Do NOT `rm -rf ~/.naavik/` to "reset" without warning the user. That nukes vault + dev-credentials in addition to the DB.
