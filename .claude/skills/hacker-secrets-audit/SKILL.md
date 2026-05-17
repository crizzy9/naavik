---
description: Scan a diff (or full codebase) for hardcoded secrets, weak hashing, env-var bypass paths, and secret-leaking log/template patterns. Cross-checks Naavik-specific invariants — `~/.naavik/dev-credentials` triple-gate (NAAVIK_DEBUG + NAAVIK_DEV_PASSWORD unset + SELF_HOSTED), vault audit log (never values), portfolio public API allowlist, agent-memory single-writer rule (`.claude/memory/` writes only via `scripts/agent-memory.sh`). Use on every PR that touches auth / secrets / env handling / vault / Settings / `.claude/memory/`, before merging anything security-sensitive. Triggers on phrases like "secrets audit", "scan for secrets", "hardcoded keys", "leak check", "secret in logs", "env var leak", "dev credentials", "vault audit", "memory store write", "agent memory single writer".
---

# hacker-secrets-audit

Hardcoded secrets are the second-most-common production incident after auth bypass. This skill is the systematic scan — covers the canonical patterns (literal keys, weak hashing, env-var fallback bypass, log/template leaks) plus the Naavik-specific invariants (10c dev-credentials triple-gate, vault audit log spec, portfolio public API allowlist).

## When to invoke

- On every PR review that touches:
  - `src/services/auth.py`, `src/services/vault.py`, `src/config.py`
  - `src/api/v1/settings*`, `src/ui/routes/settings*`
  - `src/llm/*` (API key handling)
  - `src/services/llm_tracker.py` (logging)
  - `src/api/portfolio/*` (public API allowlist)
  - Anything that touches `~/.naavik/secrets.enc`, `~/.naavik/key.bin`, `~/.naavik/dev-credentials`
- Whenever `.env.example` is touched.
- Before merging anything with the `security` or `auth` label.

## What this skill does

### 1. Hardcoded literal secrets

```bash
# Run against the diff
Grep -nE "(SECRET_KEY|API_KEY|TOKEN|PASSWORD|WEBHOOK_URL|BOT_TOKEN)\s*=\s*['\"][^'\"]{8,}['\"]" \
     <changed files>
```

Patterns to find (false positives common — eyeball each hit):
- `SECRET_KEY = "some-real-key"` → reject
- `ANTHROPIC_API_KEY = "sk-ant-..."` → reject
- `DATABASE_URL = "postgresql://user:realpassword@..."` → reject (use env var)
- AWS-style: `AKIA[0-9A-Z]{16}` → reject
- GitHub PAT: `ghp_[A-Za-z0-9]{36}` → reject
- Generic `[A-Za-z0-9_-]{32,}` adjacent to "key" / "token" / "secret" → eyeball

False-positive patterns (typically OK):
- Test fixtures with obvious-fake values (`"test-secret"`, `"x" * 32`)
- `.env.example` (showcasing the var name with a placeholder)
- Documentation showing usage

### 2. Weak hashing

```bash
Grep -nE "hashlib\.(md5|sha1)\b|hmac\..*\b(md5|sha1)\b" <changed files>
```

- `hashlib.md5(...)` / `hashlib.sha1(...)` in auth context → reject (use bcrypt for passwords, HS256 for JWT signing, SHA-256+ for fingerprints).
- bcrypt cost factor — check production is 12, tests are 4 via `NAAVIK_BCRYPT_COST`.
- JWT algorithm — must be HS256 (or stronger); reject `algorithm="none"` or `algorithm="RS256"` without keypair.

### 3. Env-var fallback bypass

```bash
Grep -nE "os\.environ\.get\([^)]*\)\s*or\s+['\"][^'\"]+['\"]" <changed files>
Grep -nE "Settings\(\s*secret_key=" <changed files>
```

Reject patterns like:
- `os.environ.get("SECRET_KEY") or "dev-fallback"` — fallback bypasses the validator
- `Settings(secret_key="default-when-env-missing")` — same
- `getattr(settings, 'X', 'fallback')` where X is a secret — same

PC.5 is the canonical fix: `src/config.py` validator refuses startup if `SECRET_KEY == "change-me-in-production"` or `< 32 bytes` outside of `NAAVIK_DEBUG`. Verify this is honored in the diff.

### 4. Secret leaks in logs / API responses / template renders

```bash
# Logging
Grep -nE "log(ger)?\.(info|debug|warning|error)\([^)]*(api_key|secret_key|password|token)" <changed files>

# API response models (Pydantic)
Grep -nE "(api_key|secret_key|password)\s*:\s*str" <changed files>

# Template renders
Grep -nE "\{\{\s*(api_key|secret_key|password|token)\b" <changed files>
```

Specifically check:
- `services/llm_tracker.py` does NOT log the prompt / response content if either could contain a secret.
- Settings API response models declare `configured: bool`, never `api_key: str` (`/api/v1/settings/llm`).
- Template variables for secret-related state are bool / status only.
- Audit log spec (`~/.naavik/logs/vault-audit.log`): every entry is `{caller, key, op, scope, ts}` — values **never** appear.

### 5. Naavik-specific invariants

**`~/.naavik/dev-credentials` (plan 10c).** Verify any change to this preserves all three triggers:
- `NAAVIK_DEBUG=1` set
- `NAAVIK_DEV_PASSWORD` unset
- `Settings.deployment_mode == SELF_HOSTED`

Mode bits: 0600. Owner: the runtime user. Path: `~/.naavik/dev-credentials`, never world-readable.

Patterns to reject:
- Removing the `SELF_HOSTED` check → would write plaintext creds in cloud tier.
- Removing the `NAAVIK_DEBUG` check → would write in production.
- Weakening mode bits (0644 / 0666) → world-readable secret.
- Changing path to `/tmp/` or `/var/` → no longer per-user home.

**`NAAVIK_DEV_PASSWORD` + `SECRET_KEY` non-leak.** Confirm neither var:
- Appears in any log line.
- Appears in any `ps` / `/proc/$pid/environ` accessible file (i.e. never `echo $NAAVIK_DEV_PASSWORD > somefile`).
- Gets committed to git (check `.env` is in `.gitignore`; check `.env.example` is the only env file tracked).

**LLM provider keys.** Check `Settings.api_keys` flow:
- Storage path: vault today, env var post-2.12. **Don't extend vault scopes** — see `naavik-vault-sunset-guard` skill.
- Response surface: `/api/v1/settings/llm` returns `configured: bool`, never the key.
- Template rendering: provider_card partial shows configured/unconfigured chip, not the value.

**Portfolio public API allowlist** (no-auth path: `/api/portfolio/cv` + `/api/portfolio/resume.pdf`). MUST be allowlist-style (only the allowed fields ship). Reject if any of these appear in the response:
- Email, phone
- EEO answers (race / ethnicity / gender / disability / veteran status)
- Visa status
- Salary expectation
- Application questions / screener answers

**Agent memory single-writer rule** (Phase A row A.15, shipped 2026-05-17). The diff must NOT contain:
- Direct `Edit` / `Write` / `>` / `>>` against any path matching `.claude/memory/**` outside `scripts/agent-memory.sh`. The script is the sole writer; all other code paths read-only.
- Programmatic writes to `~/.claude/projects/<...>/memory/MEMORY.md`. That file is Claude Code's auto-managed personal memory; this codebase is read-only on it.
- Bypassing append-only JSONL invariant — no in-place updates to `.claude/memory/*.jsonl` rows; supersession only via the script's `--supersedes <id>` flag.
- New code that mints a parallel memory store outside `.claude/memory/` (drift trap — defeats the single-writer rule).

Patterns to reject (search the diff):

```bash
Grep -nE "(Edit|Write|fs\.write|open\(.+['\"]\.claude/memory)" <changed files>
Grep -nE "open\(.+memory/MEMORY\.md.*['\"]w" <changed files>
```

Allowed: `Read` / `Grep` / `jq` against `.claude/memory/**` from any code path; `Bash(scripts/agent-memory.sh:*)` invocations. See `docs/design/AGENT_MEMORY.md § 1` (single-writer rule).

### 6. Hand back the verdict

Append findings to `traces/<run-id>/hacker.log` per the verdict format:

```
VERDICT: <APPROVE | APPROVE_WITH_NOTES | REQUEST_CHANGES | BLOCK>
SEVERITY: <low | medium | high | critical>

FINDINGS:
  - <file:line> <one-line title>
    impact: <what an attacker could do — concrete>
    fix: <concrete remediation>
```

## Canonical references

- `.claude/agents/hacker.md` § "Default attack surfaces" — full 16-item checklist (this skill covers the secrets-related rows).
- `.claude/agents/hacker.md` § "Naavik-specific watchlist".
- `docs/ARCHITECTURE.md` § 4.2 — secret handling.
- `CLAUDE.md` line 1 — current `~/.naavik/dev-credentials` triple-gate spec.
- `docs/RUNBOOK.md` § 2.3 + § 3.5 — vault audit log + recovery.
- Plan 10c — the canonical successor pattern for "operator-facing secret material".

## When NOT to invoke

- Diffs that don't touch auth / secrets / env / vault / Settings / portfolio API / LLM.
- Pure UI / template fixes that don't render any secret-adjacent field.
- Compaction events.

## Forbidden during invocation

- Do NOT skip a finding because "the secret looks fake" — flag it; let the author confirm in their reply.
- Do NOT recommend a vault-scope extension as a fix for any leak. Vault is sunset; the post-2.12 pattern is env vars + Settings UI surface.
- Do NOT soften severity because the user pushed back. Impact is fact-based.
- Do NOT close a PR's audit before checking the Naavik-specific invariants (10c gate, vault audit spec, portfolio allowlist). The generic OWASP checks aren't enough.
