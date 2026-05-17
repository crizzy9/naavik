---
description: Reject ANY proposal — in plans, design docs, code, or PR diffs — to extend `src/services/vault.py`, add new vault scopes, write new AES-GCM / PBKDF2 / audit-log code, or introduce new code dependent on `~/.naavik/secrets.enc` / `~/.naavik/key.bin`. Vault is sunset per Phase 2 task 2.12 — sequenced BEFORE the CLI sunset 2.11. The post-2.12 alternative is env-based secrets via gitignored `.env` (and the plan 10c `~/.naavik/dev-credentials` env-gated artifact pattern for operator-facing material). Shared cross-agent skill. Triggers on phrases like "vault", "vault scope", "extend vault", "AES-GCM", "PBKDF2", "secrets.enc", "key.bin", "encrypted vault", "vault audit", "key rotation", "new key fingerprint", "vault helper", "secrets management".
---

# naavik-vault-sunset-guard

`src/services/vault.py` and everything it touches (`~/.naavik/secrets.enc`, `~/.naavik/key.bin`, AES-256-GCM, PBKDF2, the audit log spec) is on a hard sunset track:

- **Phase 2 task 2.12** — vault deprecation. Delete `src/services/vault.py`, the AES-GCM/PBKDF2 machinery, the encrypted on-disk files, the Alembic columns for key fingerprints. Switch to env-based secrets (standard self-hosted-app pattern) via gitignored `.env`.
- Sequenced **BEFORE** Phase 2 task 2.11 (CLI sunset) because most of the CLI's reason-to-exist (`init`, `vault status`, `vault rotate-key`) IS the vault; deleting the vault first leaves only `serve` for 2.11 to delete.

**Every agent enforces this rule.** Architect rejects plans. Engineer refuses to write the code. Hacker flags during PR review. Manager won't approve at PLAN GATE. This skill is the cross-agent enforcer.

## When to invoke

- Architect drafting a plan that mentions secrets, encryption, vault, key rotation, or operator-secret material.
- Engineer reading a plan and noticing it routes through `src/services/vault.py`.
- Engineer editing any file that imports from `src.services.vault` or touches `~/.naavik/secrets.enc` / `~/.naavik/key.bin`.
- Hacker reviewing a PR that adds vault scope, weakens audit log spec, or introduces new code dependent on the vault.
- Manager at PLAN GATE inspecting an architect-handoff.
- User asks "how should I handle secret X" or "add a vault scope for Y".

## What this skill does

### Step 1 — Scan for forbidden patterns

```bash
Grep -nE "src\.services\.vault|services/vault\.py|secrets\.enc|key\.bin|AES-GCM|PBKDF2|vault\.(get|set|rotate|status|audit)" \
     <changed files or plan body>
```

Also look for:
- Mentions of "key fingerprint" / "encrypted vault" / "encrypted secret storage" / "vault audit log" / "rotate-key"
- New Alembic migration that touches `secrets_fingerprint` / `key_fingerprint` / vault-related columns
- New env vars named like `VAULT_*` / `*_VAULT_KEY` / `ENCRYPTED_*`
- New on-disk paths under `~/.naavik/` that imply encrypted storage (`*.enc`, `*.encrypted`, `*.gpg`)

### Step 2 — If found, HALT + reject

Surface the issue to the user (or to manager if architect is asking) via AskUserQuestion with three concrete alternatives:

**Alternative A — Env var via `.env.example`.** For genuinely-secret material the operator must supply (LLM API key, Discord webhook URL, SECRET_KEY, OAuth client secret):

```bash
# .env.example (committed, all-placeholders)
# Required for X feature
NEW_SECRET_NAME=               # description: what it is and what consumes it
```

```bash
# .env (gitignored, real values)
NEW_SECRET_NAME=actual-value-here
```

Pattern: `src/config.py` declares the field as `SecretStr | None = None` via pydantic-settings; consumers read from `Settings()`. No vault, no encryption-at-rest beyond what the filesystem already gives.

**Alternative B — Settings UI surface.** For operator capabilities that look like "the operator runs `<command>` to manage secret X" (e.g. re-enter API key, view current status, rotate a token):

- Route: `/settings/<area>` HTMX page + `/api/v1/settings/<thing>` POST endpoint.
- Storage: env var (Alternative A) once 2.12 lands; Settings DB column for "configured: bool" indicator.
- Response model surfaces `configured: bool`, NEVER the value.

**Alternative C — Plan 10c env-gated artifact.** For "emit an operator-facing artifact at boot" (the canonical successor pattern):

- File at `~/.naavik/<artifact>` (mode 0600, owner = runtime user).
- Triple-gate: written only when `NAAVIK_DEBUG=1 AND <feature-flag-env> unset AND Settings.deployment_mode == SELF_HOSTED`.
- Lifespan echo on boot: `[boot] <artifact> available at ~/.naavik/<artifact>`.
- Retrieval: plain `cat ~/.naavik/<artifact>`. NOT a CLI subcommand.
- Reference implementation: `~/.naavik/dev-credentials` (plan 10c) — that's the template.

Refuse a fourth option that re-introduces the vault.

### Step 3 — Document the rejection

If you're inside a plan being authored: add to the plan's `Open questions` section (or `## Deviations from plan` if post-approval). Cite `ROADMAP.md § Phase 2 task 2.12` and the three alternatives surfaced.

If you're inside a PR review: add a hacker finding with the alternatives. Verdict at minimum `REQUEST_CHANGES`.

## Exceptions (the only ones)

- **Plan 2.12 itself.** That plan exists specifically to DELETE the vault. Code that removes vault scopes / removes the encrypted files / drops the Alembic columns is the entire point.
- **Bug fixes that touch vault code while it still exists.** If the vault is causing a production incident before 2.12 ships, the smallest possible fix lands (devops applies it). Don't bolt new functionality on, but a minimal patch is acceptable.
- **`naavik-alembic` script.** That's alembic's own CLI surface, not a Naavik vault feature. Untouchable by this rule.

Outside of these, every other interaction with the vault is forbidden.

## Worked examples

### Reject — extending vault scopes

```python
# In a plan or code:
vault.set("scope:gmail_oauth_refresh_token", token_value, audit_caller="oauth_callback")
```

Reject. Recommend: move OAuth refresh token to env var (Alternative A) once 2.12 lands; in the interim, store unencrypted in `Settings.oauth_refresh_token` (the field already exists). Cite Phase 2 task 2.12.

### Reject — new AES-GCM helper

```python
# In a "new operator capability" plan:
def encrypt_user_export(data: bytes) -> bytes:
    return aes_gcm_encrypt(data, key=vault.get_key("export_key"))
```

Reject. Naavik exports already exist at `~/.naavik/data/snapshots/`; they use `pg_dump` (transit encryption via TLS, at-rest is filesystem-managed). Adding new encryption is gold-plating that goes against 2.12's direction.

### Accept — plan 10c-style env-gated artifact

```python
# In a "show me my OAuth client secret for debugging" plan:
async def write_oauth_debug_artifact(settings: Settings) -> None:
    if not (settings.debug and settings.deployment_mode == SelfHosted and not os.getenv("NAAVIK_OAUTH_DEBUG_SECRET")):
        return
    path = Path.home() / ".naavik" / "oauth-debug"
    path.write_text(f"client_id={settings.oauth_client_id}\nclient_secret={settings.oauth_client_secret.get_secret_value()}\n")
    path.chmod(0o600)
    logger.info(f"[boot] oauth debug artifact at {path}")
```

Accept. Matches the plan 10c triple-gate + mode 0600 + plain `cat` retrieval pattern.

## Canonical references

- `AGENTS.md` § Key Conventions § CLI — the sunset rule (codified 2026-05-10).
- `ROADMAP.md` § Phase 2 task 2.12 — vault deprecation.
- `ROADMAP.md` § Phase 2 task 2.11 — CLI sunset (depends on 2.12).
- `CLAUDE.md` line 1 — current operational state (mentions `~/.naavik/dev-credentials` triple-gate).
- `docs/RUNBOOK.md` § 2.3 + § 4.2 — vault is an active hazard surface (not to be extended).
- Plan 10c — the canonical successor pattern (the file `docs/plans/archive/10c-first-time-setup.md`).
- `.claude/agents/architect.md` § "CLI + vault sunset" (forbidden patterns).
- `.claude/agents/engineer.md` § "CLI + vault sunset".
- `.claude/agents/hacker.md` § "Naavik-specific watchlist" — vault deprecation track.
- `.claude/agents/manager.md` § "CLI sunset (do NOT approve)".
- `architect-sunset-guard` skill — architect's enforcement at plan time.

## When NOT to invoke

- The proposal is to DELETE vault code (Phase 2 task 2.12 work).
- The work is on `naavik-alembic` (alembic's CLI surface, not the vault).
- The work is a minimal bug fix to existing vault code while it still exists (devops dispatch).
- Compaction events.

## Forbidden during invocation

- Do NOT bend the rule for "transitional" use. 2.12 is sequenced before 2.11 specifically so 2.11 has nothing left to delete; transitional vault use defeats the sequencing.
- Do NOT recommend "we'll deprecate later" — that's how the vault accumulated scopes. Reject at proposal time; the deprecation backlog is full.
- Do NOT skip this check in PR review because "the diff looks clean". Vault extensions often hide in service helpers or test fixtures.
- Do NOT propose Alternative D — there isn't one. Three options exhaust the design space; a fourth is just the vault wearing a different name.
