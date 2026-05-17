---
description: Reject any plan that proposes a new `naavik` CLI subcommand or any extension of `src/services/vault.py` — both are on the Phase 2 sunset track (tasks 2.11 and 2.12). Force the redesign toward the Settings UI surface OR `.env.example` slot per the post-2.12 pattern. Use whenever a plan touches `src/cli/`, the vault, AES-GCM, secrets.enc, key.bin, or any operator-facing capability that "should be a CLI command". Triggers on phrases like "new CLI subcommand", "naavik <command>", "vault scope", "AES-GCM", "secrets.enc", "key.bin", "encrypted secrets", "extend the vault", "secret rotation", "CLI command for".
---

# architect-sunset-guard

The `naavik` CLI script and the encrypted vault at `src/services/vault.py` are on a hard sunset track:

- **Phase 2 task 2.12** — vault deprecation. Delete `src/services/vault.py`, the AES-GCM / PBKDF2 / audit-log machinery, the `~/.naavik/secrets.enc` + `~/.naavik/key.bin` files, and the Alembic columns for key fingerprints. Switch to standard self-hosted-app pattern: env-based secrets via gitignored `.env`. Documented in `AGENTS.md § Key Conventions § CLI`.

- **Phase 2 task 2.11** — CLI sunset. Sequenced AFTER 2.12. Delete `src/cli/`, drop `[project.scripts]` from `pyproject.toml`, collapse the server entrypoint. Most of the CLI's reason-to-exist (`init`, `vault status`, `vault rotate-key`) IS the vault; 2.12 leaves only `serve` to delete.

**Architect's job at this checkpoint: reject any plan that doubles down on either path.** New operator capability ships through Settings UI OR `.env.example`. Period.

## When to invoke

- Plan proposes a new `naavik <subcommand>` (`init`, `vault X`, `serve`, etc.).
- Plan extends `src/services/vault.py` — new scopes, new key types, new rotation flows, new audit-log fields.
- Plan introduces new code under `src/cli/` (other than `src/cli/__main__.py` deletions).
- Plan proposes a "small CLI helper" or "operator script" that feels like it could be a Settings UI surface or an env var.
- Plan mentions AES-GCM, PBKDF2, key fingerprints, `secrets.enc`, `key.bin`, or anything implying "encrypted vault stays".
- Plan touches `~/.naavik/dev-credentials` and proposes ANYTHING beyond what plan 10c shipped (the existing pattern is the template).

## What this skill does

1. **Scan the plan body** for the forbidden patterns. Look for:
   - `src/cli/...`
   - `src/services/vault.py`
   - `naavik <verb>` in command examples
   - `[project.scripts]` additions in pyproject.toml diffs
   - AES-GCM / PBKDF2 / audit-log extensions
   - New `.naavik/` paths beyond what already exists
   - Operator workflows phrased as "the operator runs `<command>`" without a UI alternative

2. **If you find any of these, HALT plan authoring.** Surface to the user via AskUserQuestion with three concrete options:

   **Option A — Redesign as Settings UI surface.** Most operator capabilities (re-enter API key, view current vault status, rotate a secret, view audit log) already have a Settings UI home. The Settings · LLM Provider / Settings · Notifications / Settings · Deployment tabs are the post-2.12 home. Propose a wireframe + route handler (`/api/v1/settings/<thing>`) + HTMX swap target.

   **Option B — Redesign as `.env.example` slot.** For genuinely-secret material the operator must supply (LLM API key, Discord webhook URL, SECRET_KEY), the standard self-hosted-app pattern is a gitignored `.env` file. Propose the env var name + a one-line `.env.example` entry + a `config.py` validator if it's required.

   **Option C — Plan 10c pattern (read-only env-gated artifact).** If the capability is "emit some operator-facing artifact at boot" (like `~/.naavik/dev-credentials`), the existing pattern is:
   - Mode 0600 file at `~/.naavik/<artifact>`
   - Env-gated: only written when `NAAVIK_DEBUG=1 AND <feature-flag-env> unset AND Settings.deployment_mode == SELF_HOSTED`
   - Plain `cat ~/.naavik/<artifact>` retrieves it (NOT a new CLI subcommand)
   - Lifespan echo on boot for visibility

   Refuse to write a fourth option that re-introduces CLI/vault.

3. **Document the rejection in the plan's `## Deviations from plan` section** (or, if pre-approval, in `Open questions`). Cite ROADMAP § Phase 2 task 2.11 / 2.12.

## Worked example — plan 10c (the canonical successor pattern)

Plan 10c originally surfaced the question "how does the operator see the auto-generated dev password under `nix run .#dev`?". The lazy answer was "add `naavik dev-credentials` CLI subcommand". The sunset-guard answer that shipped:

- File: `~/.naavik/dev-credentials` (mode 0600)
- Written only when `NAAVIK_DEBUG=1 AND NAAVIK_DEV_PASSWORD unset AND Settings.deployment_mode == SELF_HOSTED`
- Lifespan echo on boot: `[boot] dev credential available at ~/.naavik/dev-credentials`
- Retrieval: `cat ~/.naavik/dev-credentials`
- No CLI subcommand. No vault extension.

That's the template every future operator-facing capability follows post-2.12.

## Canonical references

- `AGENTS.md` § Key Conventions § CLI (the sunset rule, codified 2026-05-10).
- `ROADMAP.md` § Phase 2 task 2.11 (CLI sunset) + task 2.12 (vault deprecation).
- `CLAUDE.md` line 1 — current operational state including `~/.naavik/dev-credentials` pattern.
- `docs/RUNBOOK.md` § 2.3 + § 4.2 + § 7 — vault is a sunset-track surface; do not extend.
- `.claude/agents/manager.md` § "CLI sunset (do NOT approve)" — manager enforces this at PLAN GATE.
- `.claude/agents/engineer.md` § "CLI + vault sunset" — engineer enforces at implementation.
- `.claude/agents/hacker.md` § "Naavik-specific watchlist" — hacker flags the same on PR review.

## When NOT to invoke

- Plan EXPLICITLY removes vault/CLI code (the sunset tasks 2.11 / 2.12 themselves).
- Plan touches the `naavik-alembic` script — that's alembic's own CLI surface, not a Naavik feature. Untouchable by 2.11.
- Plan adjusts the `naavik` shim to make it _smaller_ (collapse a redundant flag, delete dead code).
- Compaction events.

## Forbidden during invocation

- Do NOT bend the rule "just this once" because a CLI command feels operationally cleaner. Plan 10c demonstrates the env-gated pattern works for the same operator workflows.
- Do NOT propose a new `~/.naavik/<something>` path without verifying it matches the 10c pattern (mode 0600, env-gated, lifespan-echoed, no CLI retrieval).
- Do NOT recommend "we'll just deprecate later" — that's how surfaces accumulate. Reject at plan time; the deprecation backlog is full.
- Do NOT extend the vault even for "transitional" use. 2.12 is sequenced first specifically so 2.11 has nothing left to delete.
