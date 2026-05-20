# Naavik · Deployment Guide

> **Last updated:** 2026-05-16 (carved from `ROADMAP.md` § Deployment to keep ROADMAP tracking-only).
> **Audience:** self-hosters + operators.
> **Companion docs:** `README.md` § Quick Start (brief table linking here), `docs/RUNBOOK.md` (operations + known failure modes), `docs/AGENT_OPS.md` (agent system bootstrap).

This is the single deployment reference. Pick your path; the codebase is identical across all four.

---

## At a glance

| Path | When | Cost | Setup time |
|---|---|---|---|
| **NixOS module** | Homelab / Lumino-pattern hosts | Free | ~15 min |
| **Docker Compose** | Any Linux / macOS host | Free | ~5 min |
| **Managed cloud** | Don't want to self-host | $15/month | ~2 min |
| **Bare-metal dev** | Local development | Free | ~3 min |

---

## 1. Self-hosted: Nix Flake (NixOS) — recommended for homelab

Add Naavik to your NixOS flake inputs + enable the module.

```nix
inputs.naavik.url = "github:crizzy9/naavik";

# In your host's services.yml (Lumino pattern)
apps:
  tools:
    naavik:
      enable: true
      subdomain: "jobs"           # → jobs.crypticsoul.dev
      port: 8000
      settings:
        llm_provider: "anthropic" # or "openai" or "ollama"
        auto_apply: false
        portfolio_webhook: "https://api.netlify.com/build_hooks/..."
```

The NixOS module (`nix/module.nix`) follows Lumino's service patterns:

- Reads config from `settings.servicesConfig.apps.tools.naavik`
- Creates a systemd service with full hardening (ProtectHome, CapabilityBoundingSet, etc.)
- SOPS secrets for API keys (`sops.secrets."naavik_env"`)
- Traefik dynamic routing via `services.traefik.dynamicConfigOptions.http`
- PostgreSQL provisioned as a dependency
- `services` group membership for shared storage (GID 888)
- Data directory at `${appdata}/naavik` via `systemd.tmpfiles.rules`
- Migrations run automatically as a systemd `ExecStartPre`

**Reset / restart:** `systemctl restart naavik` on the host.

---

## 2. Self-hosted: Docker Compose (any Linux / macOS)

```bash
git clone https://github.com/crizzy9/naavik.git && cd naavik

# Optional: provide API keys / overrides (defaults work out of the box)
cp .env.example .env

# One command — Postgres + auto-migrate + app, all wired
docker compose up -d

# Open http://localhost:8000
```

- Migrations run automatically on first start.
- State persists in named volumes: `naavik-db-data` (Postgres) + `naavik-data` (snapshots, generated PDFs, dev-credentials).
- Secrets live in `.env` (gitignored, `chmod 0600`); see § Configuration for the slot inventory.
- To upgrade: `git pull && docker compose pull && docker compose up -d`.
- To reset: `docker compose down -v` (wipes volumes!).
- Override config via `docker-compose.override.yml` (gitignored).

---

## 3. Managed Cloud ($15/month)

For users who prefer not to self-host. Functionally identical to self-hosted — you bring your own AI credits (Anthropic / OpenAI API keys) or connect a local Ollama instance. Naavik handles the server, you handle the AI.

- Sign up at `jobs.crypticsoul.dev` (or your self-branded instance).
- Enter your API key in **Settings → LLM Provider**.
- Everything else works the same as self-hosted.

**There is no "cloud-only" feature.** The cloud tier is purely a convenience layer — no premium upsell anywhere in the core experience. Settings has a "Deployment" tab that shows your current mode for transparency.

---

## 4. Development (bare metal)

The repo is Nix-first. One command boots Postgres (with pgvector), runs migrations, seeds the canonical fixture set, and starts FastAPI dev with auto-reload:

```bash
nix run .#dev
```

Per-project Postgres data lives in `./.naavik/db/` (gitignored). Ctrl-C tears down cleanly. Open <http://localhost:8000>.

For an interactive dev shell (uv, ruff, typst, postgresql-client on PATH):

```bash
nix develop          # or set up direnv to load automatically
```

`direnv` users: an `.envrc` is included; `direnv allow` once and the shell loads on `cd`.

### First-time dev setup

On first `nix run .#dev`, the orchestrator's `seed` step prints + persists a dev credential. Three paths to retrieve it:

```bash
# 1. Read from stdout (orchestrator prints both at seed time and again ~750 ms after app startup)
nix run .#dev   # watch for `[seed] dev password: ...`

# 2. Read from disk (mode 0600, owner-readable only)
cat ~/.naavik/dev-credentials

# 3. Shred-after-read
cat ~/.naavik/dev-credentials && rm ~/.naavik/dev-credentials
```

The credentials file is only written when (a) `NAAVIK_DEV_PASSWORD` env var is unset, (b) `NAAVIK_DEBUG=1` (orchestrator sets it; production stacks don't), and (c) the seeded `Settings.deployment_mode` is `SELF_HOSTED` (cloud-tier installs never persist plaintext creds).

To pin a credential up-front so reseeds don't surprise you:

```bash
export NAAVIK_DEV_PASSWORD='your-stable-password'
nix run .#dev
# With NAAVIK_DEV_PASSWORD set, the dev-credentials file is NOT written.
```

### Manual setup (without the Nix orchestrator)

If you prefer fine-grained control, see `README.md` § "Manual local development setup" — that's the long-form path with explicit `uv run alembic upgrade head` + `uv run python -m db.seed` + `uv run fastapi dev` steps.

---

## Nix flake outputs

```nix
{
  packages.x86_64-linux.default      # naavik Python package (built by `nix build`)
  packages.x86_64-linux.naavik       # alias

  nixosModules.default               # NixOS service module
  nixosModules.naavik                # alias

  apps.x86_64-linux.dev              # `nix run .#dev` — orchestrator
  apps.x86_64-linux.default          # `nix run` — runs the server

  devShells.x86_64-linux.default     # `nix develop` — interactive shell
}
```

---

## Cloud vs self-hosted: same codebase

The only differences:

| | Self-hosted | Cloud |
|---|---|---|
| **Server** | Your infrastructure | Managed by Naavik |
| **Cost** | Free | $15/month |
| **AI credits** | You provide API keys | You provide API keys |
| **Data** | On your servers | Encrypted at rest |
| **Code** | Identical | Identical |
| **Features** | All | All |

---

## Configuration

All env vars are optional; `src/config.py` provides working defaults. Override only what differs. See `README.md` § Configuration for the full env-var reference + `README.md` § "Dev / test env vars (not user-facing)" for the testing-only set.

Critical envs to consider in production:

| Var | Why |
|---|---|
| `SECRET_KEY` | JWT signing key. Must be >= 32 bytes. PyJWT warns on shorter keys. Plan 26 (0.2.0.01) removed the AES-256-GCM vault; rotating `SECRET_KEY` now just invalidates active sessions. |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `OLLAMA_BASE_URL` | At least one LLM provider. Plan 26: env-only post-vault. |
| `DISCORD_WEBHOOK_URL` / `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` / `PORTFOLIO_WEBHOOK_URL` | Optional outbound channels. Plan 26: env-only post-vault. |
| `DATABASE_URL` | Compose / NixOS provision their own; only override if connecting elsewhere. |
| `DATA_DIR` | State root for snapshots + PDFs + dev-credentials. Default `.naavik`; production typically `/var/lib/naavik` or `~/.naavik`. |

---

## Operations

Self-hoster checklist + runbooks: **`docs/RUNBOOK.md`**. Highlights:

- **Secrets via `.env`** (plan 26 / 0.2.0.01) — `cp .env.example .env && chmod 0600 .env`. Settings UI surfaces env-presence indicators (no values rendered). Edit `.env` + restart to rotate.
- **CLI** (`naavik`, `naavik-alembic`) — plan 50 (0.2.1.05, 2026-05-20) collapsed `naavik` to a uvicorn launcher; `src/cli/` is deleted. `naavik` (bare) boots the server (identical to `python -m main` / `uvicorn src.main:app`). `naavik-alembic` is unaffected.
- **Backups:** back up `.env` alongside the DB dump. `SECRET_KEY` must be preserved to validate JWTs issued before the backup.
- **Reset dev DB:** `rm -rf .naavik/db` OR `uv run alembic downgrade base && upgrade head && python -m db.seed`.
- **Rotate `SECRET_KEY`:** edit `.env`, restart. Active sessions are invalidated; users re-auth from the UI.

---

## Pointer index

| If you're looking for... | Read |
|---|---|
| Brief deployment summary | `README.md` § Quick Start |
| Daily operations + troubleshooting | `docs/RUNBOOK.md` |
| Configuration env vars (full) | `README.md` § Configuration |
| Manual dev setup (no Nix orchestrator) | `README.md` § Manual local development setup |
| First-time agent system bootstrap | `docs/AGENT_OPS.md` § 2 |
| Architecture (layers + cross-cutting) | `docs/ARCHITECTURE.md` |
| n8n migration strategy (Phase 2) | `docs/ARCHITECTURE.md` § External integrations |
| Portfolio integration (crypticsoul.dev) | `docs/ARCHITECTURE.md` § External integrations |
