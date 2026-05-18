---
description: Reject ANY proposal — in plans, design docs, code, or PR diffs — to extend `src/services/vault.py`, add new vault scopes, write new AES-GCM / PBKDF2 / audit-log code, or introduce new code dependent on `~/.naavik/secrets.enc` / `~/.naavik/key.bin`. Vault is sunset per Phase 2 task 2.12 — sequenced BEFORE the CLI sunset 2.11. The post-2.12 alternative is env-based secrets via gitignored `.env` (and the plan 10c `~/.naavik/dev-credentials` env-gated artifact pattern for operator-facing material). Shared cross-agent skill. Triggers on phrases like "vault", "vault scope", "extend vault", "AES-GCM", "PBKDF2", "secrets.enc", "key.bin", "encrypted vault", "vault audit", "key rotation", "new key fingerprint", "vault helper", "secrets management".
---

# naavik-vault-sunset-guard

`src/services/vault.py` + everything it touches (`~/.naavik/secrets.enc`, `~/.naavik/key.bin`, AES-256-GCM, PBKDF2, audit log spec) on hard sunset:

- **Phase 2 task 2.12** — vault deprecation. Delete `src/services/vault.py`, AES-GCM/PBKDF2 machinery, encrypted on-disk files, Alembic columns for key fingerprints. Switch to env-based secrets (standard self-hosted-app pattern) via gitignored `.env`.
- Sequenced **BEFORE** Phase 2 task 2.11 (CLI sunset) because most of CLI's reason-to-exist (`init`, `vault status`, `vault rotate-key`) IS the vault; deleting vault first leaves only `serve` for 2.11.

**Every agent enforces.** Architect rejects plans. Engineer refuses to write code. Hacker flags during PR review. Manager won't approve at PLAN GATE. Cross-agent enforcer.

## When to invoke

- Architect drafting plan mentioning secrets, encryption, vault, key rotation, or operator-secret material.
- Engineer reading plan + noticing routes through `src/services/vault.py`.
- Engineer editing any file importing from `src.services.vault` or touching `~/.naavik/secrets.enc` / `~/.naavik/key.bin`.
- Hacker reviewing PR adding vault scope, weakening audit log spec, or introducing new code dependent on vault.
- Manager at PLAN GATE inspecting architect-handoff.
- User asks "how should I handle secret X" or "add a vault scope for Y".

## Steps

### Step 1 — Scan for forbidden patterns

```bash
Grep -nE "src\.services\.vault|services/vault\.py|secrets\.enc|key\.bin|AES-GCM|PBKDF2|vault\.(get|set|rotate|status|audit)" \
     <changed files or plan body>
```

Also look for:
- Mentions of "key fingerprint" / "encrypted vault" / "encrypted secret storage" / "vault audit log" / "rotate-key"
- New Alembic migration touching `secrets_fingerprint` / `key_fingerprint` / vault-related columns
- New env vars like `VAULT_*` / `*_VAULT_KEY` / `ENCRYPTED_*`
- New on-disk paths under `~/.naavik/` implying encrypted storage (`*.enc`, `*.encrypted`, `*.gpg`)

### Step 2 — Found → HALT + reject

Surface to user (or manager if architect asking) via AskUserQuestion w/ three concrete alternatives:

**Alternative A — Env var via `.env.example`.** For genuinely-secret material operator must supply (LLM API key, Discord webhook URL, SECRET_KEY, OAuth client secret):

```bash
# .env.example (committed, all-placeholders)
# Required for X feature
NEW_SECRET_NAME=               # description: what it is and what consumes it
```

```bash
# .env (gitignored, real values)
NEW_SECRET_NAME=actual-value-here
```

Pattern: `src/config.py` declares field as `SecretStr | None = None` via pydantic-settings; consumers read from `Settings()`. No vault, no encryption-at-rest beyond what filesystem gives.

**Alternative B — Settings UI surface.** For operator capabilities that look like "operator runs `<command>` to manage secret X" (e.g. re-enter API key, view current status, rotate token):

- Route: `/settings/<area>` HTMX page + `/api/v1/settings/<thing>` POST endpoint.
- Storage: env var (Alternative A) once 2.12 lands; Settings DB column for "configured: bool" indicator.
- Response model surfaces `configured: bool`, NEVER value.

**Alternative C — Plan 10c env-gated artifact.** For "emit operator-facing artifact at boot" (canonical successor pattern):

- File at `~/.naavik/<artifact>` (mode 0600, owner = runtime user).
- Triple-gate: written only when `NAAVIK_DEBUG=1 AND <feature-flag-env> unset AND Settings.deployment_mode == SELF_HOSTED`.
- Lifespan echo on boot: `[boot] <artifact> available at ~/.naavik/<artifact>`.
- Retrieval: plain `cat ~/.naavik/<artifact>`. NOT CLI subcommand.
- Reference impl: `~/.naavik/dev-credentials` (plan 10c) — that's the template.

Refuse fourth option re-introducing vault.

### Step 3 — Document rejection

Inside plan being authored: add to plan's `Open questions` section (or `## Deviations from plan` if post-approval). Cite `ROADMAP.md § Phase 2 task 2.12` + three alternatives surfaced.

Inside PR review: add hacker finding w/ alternatives. Verdict at minimum `REQUEST_CHANGES`.

## Exceptions (the only ones)

- **Plan 2.12 itself.** Exists specifically to DELETE vault. Code removing vault scopes / encrypted files / Alembic columns is entire point.
- **Bug fixes touching vault code while it still exists.** Vault causing production incident before 2.12 ships → smallest possible fix lands (devops applies). Don't bolt new functionality on; minimal patch is acceptable.
- **`naavik-alembic` script.** Alembic's own CLI surface, not Naavik vault feature. Untouchable by this rule.

Outside these, every other interaction with vault is forbidden.

## Worked examples

### Reject — extending vault scopes

```python
# In plan or code:
vault.set("scope:gmail_oauth_refresh_token", token_value, audit_caller="oauth_callback")
```

Reject. Recommend: move OAuth refresh token to env var (Alternative A) once 2.12 lands; in interim, store unencrypted in `Settings.oauth_refresh_token` (field already exists). Cite Phase 2 task 2.12.

### Reject — new AES-GCM helper

```python
# In "new operator capability" plan:
def encrypt_user_export(data: bytes) -> bytes:
    return aes_gcm_encrypt(data, key=vault.get_key("export_key"))
```

Reject. Naavik exports already exist at `~/.naavik/data/snapshots/`; they use `pg_dump` (transit encryption via TLS, at-rest is filesystem-managed). Adding new encryption is gold-plating against 2.12 direction.

### Accept — plan 10c-style env-gated artifact

```python
# In "show me my OAuth client secret for debugging" plan:
async def write_oauth_debug_artifact(settings: Settings) -> None:
    if not (settings.debug and settings.deployment_mode == SelfHosted and not os.getenv("NAAVIK_OAUTH_DEBUG_SECRET")):
        return
    path = Path.home() / ".naavik" / "oauth-debug"
    path.write_text(f"client_id={settings.oauth_client_id}\nclient_secret={settings.oauth_client_secret.get_secret_value()}\n")
    path.chmod(0o600)
    logger.info(f"[boot] oauth debug artifact at {path}")
```

Accept. Matches plan 10c triple-gate + mode 0600 + plain `cat` retrieval pattern.

## Canonical references

- `AGENTS.md` § Key Conventions § CLI — sunset rule (codified 2026-05-10).
- `ROADMAP.md` § Phase 2 task 2.12 — vault deprecation.
- `ROADMAP.md` § Phase 2 task 2.11 — CLI sunset (depends on 2.12).
- `CLAUDE.md` line 1 — current operational state (mentions `~/.naavik/dev-credentials` triple-gate).
- `docs/RUNBOOK.md` § 2.3 + § 4.2 — vault is active hazard surface (not to extend).
- Plan 10c — canonical successor pattern (`docs/plans/archive/10c-first-time-setup.md`).
- `.claude/agents/architect.md` § "CLI + vault sunset" (forbidden patterns).
- `.claude/agents/engineer.md` § "CLI + vault sunset".
- `.claude/agents/hacker.md` § "Naavik-specific watchlist" — vault deprecation track.
- `.claude/agents/manager.md` § "CLI sunset (do NOT approve)".
- `architect-sunset-guard` skill — architect's enforcement at plan time.

## When NOT to invoke

- Proposal is to DELETE vault code (Phase 2 task 2.12 work).
- Work on `naavik-alembic` (alembic's CLI surface, not vault).
- Minimal bug fix to existing vault code while it still exists (devops dispatch).
- Compaction events.

## Forbidden during invocation

- Do NOT bend rule for "transitional" use. 2.12 sequenced before 2.11 specifically so 2.11 has nothing left to delete; transitional vault use defeats sequencing.
- Do NOT recommend "we'll deprecate later" — that's how vault accumulated scopes. Reject at proposal time; deprecation backlog is full.
- Do NOT skip this check in PR review because "diff looks clean". Vault extensions often hide in service helpers or test fixtures.
- Do NOT propose Alternative D — there isn't one. Three options exhaust design space; fourth is just vault wearing different name.
