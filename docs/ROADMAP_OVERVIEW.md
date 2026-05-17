# Naavik · Roadmap Overview

> **Last updated:** 2026-05-16
> **Companion:** `ROADMAP.md` — the canonical 800-line ledger. THIS doc is the one-page executive digest agents load instead of the full ROADMAP when they only need state, not detail.

---

## 1. Where we are (one sentence)

Phase 1 (MVP — 11 screens + backend substrate) ✅ shipped 2026-05-03; Phase A (agent system) ✅ bootstrapped 2026-05-16; **next product work is Phase 2 (job scraping) + the pre-Phase-2 paper cuts** (PC.5, PC.6 still open; PC.1–PC.4, PC.7 done).

---

## 2. Phase status table

| Phase | Goal | Plan | Status | Started | Shipped |
|---|---|---|---|---|---|
| 0 | Foundation + infra (Nix, FastAPI, Postgres, Docker) | (executed inline) | ✅ Complete | 2026-04 | 2026-04-25 |
| 1 | MVP — 11 screens + backend (auth, vault, LLM, services, ATS, Typst) | `docs/plans/archive/08-...`, `09-...`, `10-...`, `10a-...`, `10b-...`, `10c-...` | ✅ Complete | 2026-04-30 | 2026-05-03 |
| **2** | **Job scraping + discovery (Crawl4AI + per-site scrapers + AI extraction + dedup + cron); vault + CLI sunset** | `docs/plans/11-phase-2-scrapers.md` (to author) | 🟡 Queued | — | — |
| 3 | Intelligent scoring + matching (tag-based + LLM + visa filter + gap analysis + UI) | `docs/plans/12-phase-3-scoring.md` (to author) | ⚪ Future | — | — |
| 4 | Application tracking + auto-apply (multi-axis state already shipped in Phase 1; needs polish + analytics) | `docs/plans/13a-tracking-polish.md` (to author) | ⚪ Future | — | — |
| 5 | Email monitoring + outreach (Gmail/Outlook OAuth + classifier + LinkedIn DM + Calendar) | `docs/plans/13-phase-5-email.md` + `14-phase-5-outreach.md` (to author) | ⚪ Future | — | — |
| 6 | Optimization + polish (observability + light mode + LaTeX + semantic match) | `docs/plans/15-phase-6-polish.md` (to author; splits 15a/b/c) | ⚪ Future | — | — |
| **A** | **Agent system (6 subagents + 13 commands + Projects mirror + tracing + budget)** | `docs/AGENT_OPS.md` | 🟢 Active | 2026-05-16 | A.1–A.7 done; A.8 (first end-to-end /build) open |

---

## 3. Active work (next 5 items, highest priority first)

Per ROADMAP § Pre-Phase-2 paper cuts + § Phase A:

| Task ID | Title | Priority | Estimate | Notes |
|---|---|---|---|---|
| **A.8** | First end-to-end `/build` shipping a real paper cut | HIGH | ~1 h | Validates the full agent loop end-to-end. Recommended target: PC.5 (1h). |
| **PC.5** | `SECRET_KEY` boot-time enforcement (refuse `change-me-in-production` or < 32 bytes outside DEBUG) | MEDIUM | ~1 h | `src/config.py` validator + clear error message. |
| **PC.6** | Password complexity rules (min 12 chars, digit + letter) + must-change-on-first-login flag for env-injected dev creds | MEDIUM | ~2 h | `src/services/auth.py:hash_password` + tests. |
| **2.12** | Vault deprecation → env-only secrets (delete vault + AES-GCM + audit log; alembic 0003 drops fingerprint cols; UI flips to "configured via env" indicators) | HIGH | ~2–3 d | Sequence BEFORE 2.11. Touches ~15 files; mostly deletions. |
| **2.11** | CLI sunset (after 2.12: delete `src/cli/`, drop `[project.scripts]`, collapse server entrypoint) | HIGH | < 1 d | Independent of scrapers (2.1–2.10). |

After these clear, Phase 2 proper (2.1–2.10 scrapers) begins.

---

## 4. Recently shipped (last 5 plans)

| Plan | Status | Shipped | Highlights |
|---|---|---|---|
| `10c-first-time-setup` | EXECUTED | 2026-05-12 | `NAAVIK_PERSISTENCE=db` parity in `nix develop`; `/login` signup-link promotion + signup-disabled banner; `~/.naavik/dev-credentials` persistence + lifespan echo |
| `10b-phase-1-finalization` | EXECUTED | 2026-05-03 | Orchestrator greenlet fix; signup endpoint; `naavik` CLI subcommands; Settings · LLM Provider form-wrap |
| `10a-process-compose-paper-cuts` | EXECUTED | 2026-05-02 | `setsid -w` fix for TTY/SIGTTIN; `app.py` shim; Playwright NixOS support |
| `10-backend-impl` § C (Wave 5) | EXECUTED | 2026-05-03 | 14 services + Typst document generator + DRAFT lifecycle + Greenhouse/Lever/Ashby ATS adapters + APScheduler crons |
| `10-backend-impl` § B (Wave 4) | EXECUTED | 2026-05-02 | 20 SQLModel entities + Alembic + bcrypt+JWT+CSRF auth + AES-256-GCM vault + LLM abstraction + DB-backed accessor swap |

Full archive at `docs/plans/archive/`.

---

## 5. Plan-to-phase mapping

| Phase | Plan(s) |
|---|---|
| Phase 0 | (executed inline, pre-plan workflow) |
| Phase 1 | `08-stage-2-impl`, `09-stage-3-impl`, `09a-stage-3-bugfix`, `10-backend-impl` (Waves 3 + 6 = ROADMAP Waves 4 + 5), `10a-process-compose-paper-cuts`, `10b-phase-1-finalization`, `10c-first-time-setup` |
| Phase 2 | `11-phase-2-scrapers` (to author) — splits 11a (LinkedIn + Greenhouse + Lever + Ashby) and 11b (Workday + Indeed + Generic + n8n migration) |
| Phase 3 | `12-phase-3-scoring` (to author) |
| Phase 4 | Most ships in plan 10 Wave 6 (already done); polish + analytics in `13a-tracking-polish` (to author) |
| Phase 5 | `13-phase-5-email` + `14-phase-5-outreach` (to author; sequenced) |
| Phase 6 | `15-phase-6-polish` (to author; splits 15a observability + 15b light mode + 15c LaTeX + ML scoring) |
| Phase A | `docs/AGENT_OPS.md` (operational guide; no traditional plan file — meta-work tracked directly in ROADMAP) |

---

## 6. Deferred + backlog

`ROADMAP.md` § Phase 1 deferred items (Phase 1.x) holds the long tail. Highlights worth knowing about:

- Workday / LinkedIn / Indeed / Generic ATS adapters → Phase 2 (need credentials + Playwright)
- Stale-DRAFT cleanup cron → small follow-up post-Phase-2
- Postmortem-on-failure (Playwright screenshot + AI summary on ATS failure) → diagnostic boost; ship with Phase 2
- OIDC for self-hosted (Authentik / Keycloak / Okta) → Phase 2+
- Refresh-token rotation → Phase 1.x backlog (Wave 3 shipped JWT but not rotation)
- Light mode → Phase 6
- Argon2id vault upgrade → moot once 2.12 deletes the vault
- Visual regression as a PR gate (Playwright + pixelmatch in CI) → after PC.3 stabilizes
- Full `NAAVIK_PERSISTENCE` env-var removal (migrate remaining ~20 accessors to DB reads) → Phase 1.x; small focused plan

---

## 7. Active conventions worth knowing

- **CLI sunset:** do NOT extend `src/cli/` or the vault. Phase 2 tasks 2.11 / 2.12 delete them. (AGENTS.md § Key Conventions § CLI.)
- **Single-doc-tracking:** all task ledger lives in `ROADMAP.md` only. Plans describe the work; ROADMAP records completion. (AGENTS.md § Single-doc-tracking principle.)
- **Deviations gate:** every plan in `docs/plans/` MUST have a `## Deviations from plan` section before archive. (AGENTS.md § Workflow step 7.)
- **GitHub Mirror:** `ROADMAP.md` → GitHub Project v2 is one-way. Manager syncs FROM ROADMAP TO Project, never the reverse. (`docs/AGENT_OPS.md` § 6.)
- **Visual contract frozen:** Inter + JetBrains Mono + Lucide (stroke 1.5) + indigo/cyan palette + dark mode primary. (`DESIGN.md`, `docs/design/WORKFLOW.md` for process.)

---

## 8. When to read the full ROADMAP

This overview is enough for: standups, status updates, agent context loading at `/build` start, deciding which paper cut to pick next.

You need the **full `ROADMAP.md`** for: per-wave task ledger (the `[ ]/[~]/[x]` checkboxes), authoring or revising a phase header, full per-task notes column, full architecture sketch + tech-stack table + decision log + deployment paths + n8n migration strategy + portfolio integration.

---

## 9. Pointers

| If you need... | Read |
|---|---|
| Phase-level task ledger | `ROADMAP.md` § Phase N |
| Agent system reference | `docs/AGENT_OPS.md` |
| Architecture entry point | `docs/ARCHITECTURE.md` |
| Devops runbook | `docs/RUNBOOK.md` |
| Visual contract | `DESIGN.md` (root) |
| UI sub-process (process + checklists + patterns) | `docs/design/WORKFLOW.md` |
| Deployment guide (4 paths + config + ops) | `docs/DEPLOYMENT.md` |
| Post-Phase-1 testing playbook + monitoring | `docs/plans/POST_PHASE_1.md` |
| Canonical workflow | `AGENTS.md` § Workflow |
| Plan archive (what shipped) | `docs/plans/archive/` |
| Active plans (what's being implemented) | `docs/plans/` |
| Design contracts | `docs/design/` |
