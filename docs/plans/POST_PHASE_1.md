# Naavik · Post-Phase-1 operational guide

> **Last updated:** 2026-05-02 (consolidated — all task tracking moved to `ROADMAP.md`; this doc is operational guidance only)
>
> **Renamed 2026-05-02** from `NEXT_STEPS.md` → `POST_PHASE_1.md` so the title makes the intent obvious: this is **how** to operate after Phase 1 ships (testing playbook, authoring workflow, monitoring, success criteria). It is **not** a tracking doc.

---

## Where to find what

**Single tracking principle (per `AGENTS.md` § Roadmap Maintenance Rules):** all task / backlog / phase tracking lives in `ROADMAP.md`. This doc and other supporting docs reference ROADMAP but never duplicate task tables.

| If you're looking for...                                                       | Read                                                                                                                                                                                   |
| ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Phase 2–6 task tables (what + when + status)                                   | `ROADMAP.md` § Phase 2, § Phase 3, § Phase 4, § Phase 5, § Phase 6                                                                                                                     |
| Phase 1.x deferred backlog                                                     | `ROADMAP.md` § Phase 1 deferred items (Phase 1.x)                                                                                                                                      |
| Pre-Phase-2 paper cuts (ship before plan 11)                                   | `ROADMAP.md` § Pre-Phase-2 paper cuts                                                                                                                                                  |
| Plan-to-phase mapping (which plan implements which phase)                      | Each ROADMAP phase header has a `**Plan:**` line pointing at `docs/plans/NN-name.md`                                                                                                   |
| Phase 1 deliverable spec                                                       | `ROADMAP.md` § Phase 1 → "Deliverable (end of Phase 1)"                                                                                                                                |
| Plan-file conventions                                                          | `docs/plans/README.md`                                                                                                                                                                 |
| Workflow lifecycle (plan → review → design doc → prompt → implement → archive) | `AGENTS.md` § Workflow                                                                                                                                                                 |
| Design contracts (visual / functional / data / interactions)                   | `DESIGN.md`, `docs/design/SCREENS.md`, `docs/design/COMPONENTS.md`, `docs/design/DATA_MODEL.md`, `docs/design/INTERACTIONS.md`, `docs/design/BACKEND.md`, `docs/design/SAMPLE_DATA.md` |
| Operational playbook for shipping Phase 1 + post-Phase-1 plans                 | This doc (below)                                                                                                                                                                       |

---

## What "Phase 1 done" looks like

After plan 10 Wave 6 ships, the deliverable line in `ROADMAP.md` § Phase 1 is satisfied:

> User uploads resume → AI extracts profile → user edits in UI → Discover queue **(seeded; real scraping is Phase 2)** scored + filtered → tailored resume + cover letter generated for any job → submit application via Greenhouse / Lever / Ashby (semi-auto for the rest) → email-signal-driven Tracking **(stubbed; real Gmail/Outlook is Phase 4)** → outreach drafts **(stubbed; real LinkedIn DM + email is Phase 5)** → portfolio API serves profile + downloadable resume.

Concretely, **end-to-end smoke after Phase 1**:

1. `nix run .#dev` boots Postgres + alembic + FastAPI in one terminal.
2. Visit `http://localhost:8000/login`. Log in as the seeded user (Shyam). (Plan 10c: the credential prints on first boot AND lands at `~/.naavik/dev-credentials` (mode 0600) for later retrieval via `cat`; the `[app]` lifespan also re-echoes it ~750 ms after startup so it's near the bottom of the orchestrator's scrollback.)
3. Land on Overview. Real KPIs from seeded `Application` rows. Email signal feed shows seeded `EmailThread` rows. Pipeline strip shows 5 stages.
4. Visit `/profile/edit`. Edit a bullet via the modal. Autosave indicator cycles `saving → saved`. Tag picker toggles. Drag a bullet to reorder — Sortable.js fires the reorder API; bullet order persists across reload.
5. Visit `/discover`. The seeded queue is sorted by score. Skip / Save / Auto-apply work via keyboard (←/↑/→). Auto-apply right-swipe creates a DRAFT; the queue advances.
6. Click a swipe card to open the in-place review (or `/discover/{id}` direct). DRAFT auto-creates (or shows lazy CTA per `Settings.eager_review_generation`). Tailored resume + cover letter render with realistic AI output. Cover-letter sections are click-to-edit. Screener questions render with `drafted` / `auto` / `user` chips.
7. Click "Submit application". DRAFT → APPLIED. Real Greenhouse submission against a public board (or mocked in dev). Tracking shows the new APPLIED row.
8. Visit `/tracking`. Drag a card from APPLIED to RECRUITER_SCREEN — Sortable.js fires `/api/v1/applications/move`; status persists.
9. Visit `/outreach`. Pick an application. The recommended-move card shows a real AI draft. Click "Send via LinkedIn" — stubbed in MVP (real LinkedIn is Phase 5).
10. Visit `/settings`. Switch LLM provider. Test connection — real API call, real round-trip latency. Cost cards show this-month aggregates from `ApiUsage`.
11. Visit `/_design/components` (toggle `Settings.debug=True` first via SQL or settings tab). All 85 components render in a single fixture page.
12. `curl http://localhost:8000/api/portfolio/cv` returns Profile JSON filtered for public consumption. The portfolio site at `crypticsoul.dev` builds against this.

---

## Phase 1 testing playbook (post-Wave-6)

After plan 10 Wave 6 ships, run these in order before declaring Phase 1 done:

### 1. Automated test suite

```bash
nix develop
uv run alembic upgrade head
uv run python -m src.db.seed
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/ -v
```

Every test green. Expected test files (post-Wave-6):

- `tests/test_sample_data.py` — fixture round-trip + counts + realism rules
- `tests/test_models.py` — SQLModel instantiation + relationships + CHECK constraints (incl. discarded-DRAFT corner case)
- `tests/test_seed.py` — clean DB seeded; round-trip via SQLModel matches fixtures
- `tests/test_auth.py` — bcrypt + JWT + cookie flags + CSRF + brute-force rate limit
- `tests/test_vault.py` — AES-GCM round-trip + PBKDF2 + key fingerprint mismatch + audit log + rotate-key CLI
- `tests/test_llm_provider.py` — every provider's methods + cost estimate + retry policy
- `tests/test_application_service.py` — DRAFT lifecycle + state-transition enforcement + service-layer computed state
- `tests/test_document_generator.py` — resume + cover letter + screeners + DRAFT reuse heuristic + cost-cap enforcement
- `tests/test_typst.py` — compile + native page-count metadata
- `tests/test_ats_adapters.py` — Greenhouse / Lever / Ashby submit + failure classification + resume-parsing override
- `tests/test_notifications.py` — Discord embed + Telegram outbound + per-event toggle
- `tests/test_portfolio_sync.py` — CV API filter + CORS + Netlify webhook + generic resume regen
- `tests/test_scorer_visa_filter.py` — deterministic visa filter
- `tests/test_pages.py` — every screen GET 200 + key markup
- `tests/test_stub_endpoints.py` — replaced by real endpoints in Wave 4; this file deletes after the swap
- `tests/test_draft_lifecycle.py` — DRAFT state machine end-to-end
- `tests/test_persistence_swap.py` — Wave 4 side-by-side smoke (deletes after smoke passes)
- Plan-09a tests landed: `test_application_qs_form`, `test_base_js`, `test_dialog_backdrop`, `test_discover_redesign`, `test_idempotent_scripts`, `test_inplace_expand`, `test_mobile_layouts`, `test_mobile_sidebar`, `test_scroll_spy`, `test_swipe_handler`

### 2. Visual QA

```bash
uv run python tests/visual/capture.py --all   # 22 snapshots: 11 screens × 2 viewports
```

Diff each snapshot against the committed baseline at `tests/visual/screenshots/`. Per-screen pixel delta should be ≤ 1 % (font rendering tolerance). Anything larger is a regression — investigate.

Open each snapshot side-by-side with the bundle JSX (`docs/design/mockups/naavik-handoff/project/screens/<ScreenName>.jsx`). Visual parity with the design intent.

### 3. End-to-end smoke (manual)

Run the 12-step end-to-end smoke listed at the top of this doc. Every step should work without manual nudging.

### 4. Security review (full)

Run `security-review` skill against the entire branch. Pay special attention to:

- Auth path — JWT cookie flags, CSRF rotation policy, brute-force rate limit
- Vault — AES-GCM, PBKDF2 iterations (100k), key fingerprint detection, audit log completeness, file-lock concurrency
- ATS adapters — input sanitization for ATS POST bodies (especially screener answer text — possible XSS into board UI)
- Document generator — Typst template injection from untrusted JD input; the Typst compile process should run with restricted filesystem access
- Portfolio public API — info leak (no email / phone / EEO / visa / salary)
- Cron — rate-limit guards on outbound integrations (LinkedIn 50/day, scraping per-source backoff)
- Logging — `vault-audit.log` never logs secret values; access log scrubs `Authorization` headers + cookies

Any HIGH / CRITICAL → fix before declaring Phase 1 done.

### 5. Cost telemetry sanity

After running the end-to-end smoke 5–10 times, check `ApiUsage` aggregates:

```sql
SELECT provider, model, COUNT(*) as calls, SUM(cost_usd) as total_cost_usd, AVG(latency_ms) as avg_latency_ms
FROM api_usage
WHERE occurred_at >= now() - interval '7 days'
GROUP BY provider, model;
```

Expected for 10 end-to-end runs against the seeded jobs (~10 DRAFTs × ~3 LLM calls each):

- ~30 ApiUsage rows total
- ~$1–3 cumulative cost on `claude-3.5-sonnet`
- Avg latency 400–1500 ms per `structured` call, 100–400 ms per `complete`

If costs blow past $5 / 10 runs, the DRAFT reuse heuristic (plan 10 § C.2) isn't firing — investigate.

### 6. NixOS module integration test

Spin up a NixOS VM with the `nix/module.nix` enabled (`naavik = true`), point at a SOPS secret for `naavik_env`, and verify the systemd service starts cleanly + Traefik routes the subdomain correctly. This is the deployment path for self-hosted users following the Lumino pattern; broken NixOS module = broken self-hosted-first promise.

### 7. Docker Compose integration test

```bash
git clone [email protected]:crizzy9/naavik.git fresh-test && cd fresh-test
cp .env.example .env  # edit SECRET_KEY + ANTHROPIC_API_KEY
docker compose up -d
# Visit http://localhost:8000 — should load without manual setup
```

If a fresh clone + `.env` edit doesn't bring up a working app in < 2 minutes, the self-hosted onboarding is broken.

---

## How to author the next plan (operational)

1. Pick the next plan from `ROADMAP.md` (the next phase header has the plan filename + scope).
2. Open a fresh Claude Code session at the repo root.
3. Paste a session-continue prompt similar to `docs/prompts/00-session-continue.md` but pointed at the new plan number. The prompt should:
   - List required reading (AGENTS.md, ROADMAP.md, BACKEND.md, DATA_MODEL.md, etc.) in order.
   - State the plan being authored (e.g. "Author plan 11 — Phase 2 scrapers").
   - List what's out of scope.
   - Reference this `POST_PHASE_1.md` for testing playbook + monitoring concerns.
4. The agent authors `docs/plans/NN-name.md` per `docs/plans/README.md` conventions. Plan files describe **how** — they do not duplicate ROADMAP's task tables.
5. Review + approve via the plan's approval checklist.
6. Agent authors `docs/prompts/NN-name.md` once the plan is APPROVED.
7. Paste the kickoff prompt into a fresh implementation session.
8. Archive plan + prompt + bump ROADMAP task rows when done (per `AGENTS.md` § Workflow step 7-8).
9. Repeat.

The lifecycle is identical to plans 08–10's. After Phase 1 ships, the source contracts are well-defined in BACKEND.md / DATA_MODEL.md — no design-doc graduation step needed for Phase 2-6, just plan + prompt + execute.

---

## Cross-cutting concerns to monitor post-Phase-1

These are operational concerns, not discrete tasks. Watch them as you ship Phase 2–6; convert to ROADMAP tasks if they materialize as actionable work.

1. **Cost trajectory.** Once real scraping (Phase 2) + auto-apply (Wave 6) run together, watch `ApiUsage` weekly. If a single user costs > $50 / month on AI, the cost-cap defaults need tightening.
2. **Anti-detection drift.** LinkedIn / Workday / Indeed actively detect bots. Each shipped scraper needs a 2-week stability window before considering it production-ready. If the scraper breaks within a week, anti-detection budget needs a rethink.
3. **Email classification accuracy.** Phase 5's classifier should be ≥ 95 % accurate on the 6-class taxonomy. Monitor by user-flagging false positives; retrain prompts via versioning.
4. **n8n decommission.** After Phase 2 ships and runs clean for 1 week, disable the n8n Main Workflow. Don't forget. (See `ROADMAP.md` § n8n Migration Strategy.)
5. **Portfolio site dependency.** `crypticsoul.dev`'s `cv.astro` build-time fetches `/api/portfolio/cv`. Any contract change to that endpoint must coordinate with the portfolio repo (separate codebase). Currently zero versioning — Phase 2+ adds `?version=v1` (tracked in ROADMAP § Phase 1 deferred).
6. **Multi-user readiness.** Every entity already has `user_id`; the multi-tenant cloud tier is unblocked at the model layer. But cron jobs assume single-user (`user_id=1`) — the `applications.auto_apply` cron, `tracking.sync_gmail`, etc. all need a `for user in users` loop wrapping their existing logic. Convert to a ROADMAP task when the cloud tier ships multi-tenant.
7. **Backups.** `~/.naavik/data/snapshots/` daily SQL gzip — but no off-site backup story yet. Document for self-hosters: the vault + snapshots dir together is the full backup; off-site to S3 / Backblaze / etc. is the user's responsibility.
8. **Visual regression as PR gate (CI-side).** Depends on the Pre-Phase-2 paper cut PC.3 landing first (local capture must work on NixOS before CI can run it). Once the local baseline is committed AND snapshots stabilize across 2-3 Phase 2-6 plans, wire a Playwright + pixelmatch (or Percy / similar) diff step into CI: capture per-PR snapshots, compare against `tests/visual/screenshots/` baseline, fail on > 1 % per-screen pixel delta. Convert to a ROADMAP task when PC.3 ships and snapshots stabilize.

---

## When something goes wrong

Each implementation prompt includes a "STOP and post a question" instruction for blockers. Honor it — mid-flight scope creep is the most common way these sessions drift. Common blocker categories:

- **Spec contradicts mockup.** SCREENS.md spec wins (`docs/design/SCREENS.md` says it's the source of truth). Update SCREENS.md if the mockup is correct; update the mockup batch if the spec is correct.
- **Component variant missing.** If a plan needs a component variant the prior plan didn't ship, the implementing agent files an extension to COMPONENTS.md and adds the variant. Catalog count stays at 85; only variants extend.
- **External API surface drift.** Greenhouse / Lever / Ashby / LinkedIn / Anthropic SDK changes between authoring and implementation are likely after Phase 1 ships (3–6 months between waves). When an API breaks, file a small fix-up plan (e.g. `12a-greenhouse-api-update.md`) and ship it before continuing the main wave.
- **Cost cap hits in production.** If a user hits the daily LLM cost cap repeatedly during normal use, the cap default is wrong — adjust in DATA_MODEL.md `Settings.daily_llm_cost_cap_usd` default and ship as a tiny plan.

---

## What success looks like

Naavik v1.0 (post-Phase-6) means:

- A self-hosted user clones the repo, edits `.env`, runs `docker compose up -d`, lands at `localhost:8000`, signs up, uploads a resume, and is auto-applying to relevant jobs by end-of-day.
- A NixOS user adds the flake input, enables the module, sets SOPS secrets, and the same flow works behind their Traefik reverse proxy.
- A cloud-tier user pays $15/mo, brings their own Anthropic key, and gets the identical product.
- The portfolio site at `crypticsoul.dev` reflects the Profile state without manual sync.
- Cost per user per month is < $5 on Claude (target — depends on traffic patterns).
- Self-hosted instances run for 90+ days without intervention.

The product hits the "Sprout for engineers, but you own your data" pitch in the ROADMAP § Vision section.

If Phase 6 ships clean and the above is mostly true, ship the v1.0 release tag, write the launch post, and start on v1.1. The `ROADMAP.md` Phase 6+ ideas (template marketplace, ML scoring calibration from outcomes, multi-region cloud tier, mobile companion app, browser extension for one-click capture) are the v1.1+ frontier.

---

## Realistic timeline

- Phase 1: ~4-6 weeks of agent-driven implementation (plans 08, 09, 09a, 10).
- Phase 2-6: ~9-15 weeks of agent-driven implementation (plans 11, 12, 13, 14, 15).
- v1.0 ship date: 4-5 months from Phase 1 start.

Total post-Phase-1 estimate per `ROADMAP.md` phase headers: 9–15 weeks, plus 1.x deferred items slotted in opportunistically. Each plan is a fresh Claude Code session paste; multiple plans can run in parallel if no shared state.
