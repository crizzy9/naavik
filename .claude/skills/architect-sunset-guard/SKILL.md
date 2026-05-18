---
description: Reject any plan that proposes a new `naavik` CLI subcommand or any extension of `src/services/vault.py` — both are on the Phase 2 sunset track (tasks 2.11 and 2.12). Force the redesign toward the Settings UI surface OR `.env.example` slot per the post-2.12 pattern. Use whenever a plan touches `src/cli/`, the vault, AES-GCM, secrets.enc, key.bin, or any operator-facing capability that "should be a CLI command". Triggers on phrases like "new CLI subcommand", "naavik <command>", "vault scope", "AES-GCM", "secrets.enc", "key.bin", "encrypted secrets", "extend the vault", "secret rotation", "CLI command for".
---

# architect-sunset-guard

`naavik` CLI script + encrypted vault at `src/services/vault.py` on hard sunset:

- **Phase 2 task 2.12** — vault deprecation. Delete `src/services/vault.py`, AES-GCM / PBKDF2 / audit-log machinery, `~/.naavik/secrets.enc` + `~/.naavik/key.bin`, Alembic columns for key fingerprints. Switch to standard self-hosted-app pattern: env-based secrets via gitignored `.env`. Documented in `AGENTS.md § Key Conventions § CLI`.

- **Phase 2 task 2.11** — CLI sunset. Sequenced AFTER 2.12. Delete `src/cli/`, drop `[project.scripts]` from `pyproject.toml`, collapse server entrypoint. Most of CLI's reason-to-exist (`init`, `vault status`, `vault rotate-key`) IS the vault; 2.12 leaves only `serve` to delete.

**Architect's job: reject any plan doubling down on either path.** New operator capability ships through Settings UI OR `.env.example`. Period.

## When to invoke

- Plan proposes new `naavik <subcommand>` (`init`, `vault X`, `serve`, etc.).
- Plan extends `src/services/vault.py` — new scopes, key types, rotation flows, audit-log fields.
- Plan introduces new code under `src/cli/` (other than `src/cli/__main__.py` deletions).
- Plan proposes "small CLI helper" / "operator script" that feels like Settings UI surface or env var.
- Plan mentions AES-GCM, PBKDF2, key fingerprints, `secrets.enc`, `key.bin`, or anything implying "encrypted vault stays".
- Plan touches `~/.naavik/dev-credentials` + proposes ANYTHING beyond what plan 10c shipped (existing pattern is template).

## Steps

1. **Scan plan body** for forbidden patterns:
   - `src/cli/...`
   - `src/services/vault.py`
   - `naavik <verb>` in command examples
   - `[project.scripts]` additions in pyproject.toml diffs
   - AES-GCM / PBKDF2 / audit-log extensions
   - New `.naavik/` paths beyond existing
   - Operator workflows phrased as "operator runs `<command>`" without UI alternative

2. **Found any → HALT plan authoring.** Surface to user via AskUserQuestion w/ three concrete options:

   **Option A — Redesign as Settings UI surface.** Most operator capabilities (re-enter API key, view vault status, rotate secret, view audit log) already have Settings UI home. Settings · LLM Provider / · Notifications / · Deployment tabs = post-2.12 home. Propose wireframe + route handler (`/api/v1/settings/<thing>`) + HTMX swap target.

   **Option B — Redesign as `.env.example` slot.** For genuinely-secret material operator must supply (LLM API key, Discord webhook URL, SECRET_KEY), standard self-hosted-app pattern = gitignored `.env` file. Propose env var name + one-line `.env.example` entry + `config.py` validator if required.

   **Option C — Plan 10c pattern (read-only env-gated artifact).** If capability is "emit operator-facing artifact at boot" (like `~/.naavik/dev-credentials`):
   - Mode 0600 file at `~/.naavik/<artifact>`
   - Env-gated: written only when `NAAVIK_DEBUG=1 AND <feature-flag-env> unset AND Settings.deployment_mode == SELF_HOSTED`
   - Plain `cat ~/.naavik/<artifact>` retrieves (NOT new CLI subcommand)
   - Lifespan echo on boot for visibility

   Refuse to write fourth option re-introducing CLI/vault.

3. **Document rejection in plan `## Deviations from plan` section** (or pre-approval, in `Open questions`). Cite ROADMAP § Phase 2 task 2.11 / 2.12.

## Worked example — plan 10c (canonical successor pattern)

Plan 10c originally surfaced "how does operator see auto-generated dev password under `nix run .#dev`?". Lazy answer: "add `naavik dev-credentials` CLI subcommand". Sunset-guard answer shipped:

- File: `~/.naavik/dev-credentials` (mode 0600)
- Written only when `NAAVIK_DEBUG=1 AND NAAVIK_DEV_PASSWORD unset AND Settings.deployment_mode == SELF_HOSTED`
- Lifespan echo on boot: `[boot] dev credential available at ~/.naavik/dev-credentials`
- Retrieval: `cat ~/.naavik/dev-credentials`
- No CLI subcommand. No vault extension.

Template every future operator-facing capability follows post-2.12.

## Canonical references

- `AGENTS.md` § Key Conventions § CLI (sunset rule, codified 2026-05-10).
- `ROADMAP.md` § Phase 2 task 2.11 (CLI sunset) + task 2.12 (vault deprecation).
- `CLAUDE.md` line 1 — current operational state including `~/.naavik/dev-credentials` pattern.
- `docs/RUNBOOK.md` § 2.3 + § 4.2 + § 7 — vault is sunset-track surface; don't extend.
- `.claude/agents/manager.md` § "CLI sunset (do NOT approve)" — manager enforces at PLAN GATE.
- `.claude/agents/engineer.md` § "CLI + vault sunset" — engineer enforces at implementation.
- `.claude/agents/hacker.md` § "Naavik-specific watchlist" — hacker flags same on PR review.

## When NOT to invoke

- Plan EXPLICITLY removes vault/CLI code (sunset tasks 2.11 / 2.12 themselves).
- Plan touches `naavik-alembic` script — that's alembic's own CLI surface, not Naavik feature. Untouchable by 2.11.
- Plan adjusts `naavik` shim to make it _smaller_ (collapse redundant flag, delete dead code).
- Compaction events.

## Forbidden during invocation

- Do NOT bend rule "just this once" because CLI command feels operationally cleaner. Plan 10c demonstrates env-gated pattern works for same operator workflows.
- Do NOT propose new `~/.naavik/<something>` path without verifying it matches 10c pattern (mode 0600, env-gated, lifespan-echoed, no CLI retrieval).
- Do NOT recommend "we'll just deprecate later" — that's how surfaces accumulate. Reject at plan time; deprecation backlog is full.
- Do NOT extend vault even for "transitional" use. 2.12 sequenced first specifically so 2.11 has nothing left to delete.
