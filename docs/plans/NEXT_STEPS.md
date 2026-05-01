# Naavik · Post-MVP next steps

> **Last updated:** 2026-05-01
>
> Forward-looking plan you read **after Phase 1 ships** (plan 08 + plan 09 + plan 10 Wave 3 + plan 10 Wave 6 all archived). Use this as the entry point to figure out what to author + ship next.
>
> If Phase 1 isn't done yet, this doc isn't actionable for you yet — go finish ROADMAP.md § Phase 1 first.

---

## What "Phase 1 done" looks like

After the 4 implementation sessions complete (plan 08, plan 09, plan 10 Wave 3, plan 10 Wave 6), the deliverable line in `ROADMAP.md` § Phase 1 is satisfied:

> User uploads resume → AI extracts profile → user edits in UI → Discover queue **(seeded; real scraping is Phase 2)** scored + filtered → tailored resume + cover letter generated for any job → submit application via Greenhouse / Lever / Ashby (semi-auto for the rest) → email-signal-driven Tracking **(stubbed; real Gmail/Outlook is Phase 4)** → outreach drafts **(stubbed; real LinkedIn DM + email is Phase 5)** → portfolio API serves profile + downloadable resume.

Concretely, **end-to-end smoke after Phase 1**:

1. `nix run .#dev` boots Postgres + alembic + FastAPI in one terminal.
2. Visit `http://localhost:8000/login`. Log in as the seeded user (Shyam).
3. Land on Overview. Real KPIs from seeded `Application` rows. Email signal feed shows seeded `EmailThread` rows. Pipeline strip shows 5 stages.
4. Visit `/profile/edit`. Edit a bullet via the modal. Autosave indicator cycles `saving → saved`. Tag picker toggles. Drag a bullet to reorder — Sortable.js fires the reorder API; bullet order persists across reload.
5. Visit `/discover`. The seeded queue is sorted by score. Skip / Save / Auto-apply work via keyboard (←/↑/→). Auto-apply right-swipe creates a DRAFT; the queue advances.
6. Click a swipe card to open `/discover/{id}`. DRAFT auto-creates (or shows lazy CTA per `Settings.eager_review_generation`). Tailored resume + cover letter render with realistic AI output. Cover-letter sections are click-to-edit. Screener questions render with `drafted` / `auto` / `user` chips.
7. Click "Submit application". DRAFT → APPLIED. Real Greenhouse submission against a public board (or mocked in dev). Tracking shows the new APPLIED row.
8. Visit `/tracking`. Drag a card from APPLIED to RECRUITER_SCREEN — Sortable.js fires `/api/v1/applications/move`; status persists.
9. Visit `/outreach`. Pick an application. The recommended-move card shows a real AI draft. Click "Send via LinkedIn" — stubbed in MVP (real LinkedIn is Phase 5).
10. Visit `/settings`. Switch LLM provider. Test connection — real API call, real round-trip latency. Cost cards show this-month aggregates from `ApiUsage`.
11. Visit `/_design/components` (toggle `Settings.debug=True` first via SQL or settings tab). All 85 components render in a single fixture page.
12. `curl http://localhost:8000/api/portfolio/cv` returns Profile JSON filtered for public consumption. The portfolio site at `crypticsoul.dev` builds against this.

---

## Phase 1 testing playbook (post-Wave-5)

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

Every test green. Expected test files:

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

### 2. Visual QA

```bash
uv run python tests/visual/capture.py --all   # 22 snapshots: 11 screens × 2 viewports
```

Diff each snapshot against the committed baseline at `tests/visual/screenshots/`. Per-screen pixel delta should be ≤1% (font rendering tolerance). Anything larger than that is a regression — investigate.

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

Any HIGH/CRITICAL → fix before declaring Phase 1 done.

### 5. Cost telemetry sanity

After running the end-to-end smoke 5-10 times, check `ApiUsage` aggregates:

```sql
SELECT provider, model, COUNT(*) as calls, SUM(cost_usd) as total_cost_usd, AVG(latency_ms) as avg_latency_ms
FROM api_usage
WHERE occurred_at >= now() - interval '7 days'
GROUP BY provider, model;
```

Expected for 10 end-to-end runs against the seeded jobs (~10 DRAFTs × ~3 LLM calls each):

- ~30 ApiUsage rows total
- ~$1-3 cumulative cost on `claude-3.5-sonnet`
- Avg latency 400-1500ms per `structured` call, 100-400ms per `complete`

If costs blow past $5 / 10 runs, the DRAFT reuse heuristic (plan 10 § C.2) isn't firing — investigate.

### 6. NixOS module integration test

Spin up a NixOS VM with the `nix/module.nix` enabled (`naavik = true`), point at a SOPS secret for `naavik_env`, and verify the systemd service starts cleanly + Traefik routes the subdomain correctly. This is the deployment path for self-hosted users following the Lumino pattern; broken NixOS module = broken self-hosted-first promise.

### 7. Docker Compose integration test

```bash
git clone git@github.com:crizzy9/naavik.git fresh-test && cd fresh-test
cp .env.example .env  # edit SECRET_KEY + ANTHROPIC_API_KEY
docker compose up -d
# Visit http://localhost:8000 — should load without manual setup
```

If a fresh clone + .env edit doesn't bring up a working app in <2 minutes, the self-hosted onboarding is broken.

---

## What to author next (priority order)

Once Phase 1 ships clean, these are the **next plans to author**, in suggested order. Each is its own plan + kickoff prompt cycle (per `AGENTS.md` § Workflow). The numbering picks up where plan 10 left off.

### Tier 1 — unblocks the rest (do these next)

#### Plan 11 — Phase 2: scrapers + cron + auto-apply scoring

**Why first.** The Phase 1 deliverable line says "Discover queue scored + filtered" — but the seeded queue isn't real. Phase 2 makes Discover actually populate from live scraping; auto-apply gets real signal to run against; the cost-tracking + LLM substrate from Wave 6 starts paying for itself.

**Source contract.** `BACKEND.md` § J (scraping architecture), § I.1 (Phase 2 cron catalog), § H.1 (`scraper_service`).

**Scope.**
- `BaseScraper` interface + dispatcher
- 7 site scrapers: LinkedIn (RSShub-fed), Workday, Greenhouse, Lever, Ashby, Indeed, Generic (Playwright fallback)
- Scraping cron per source (every 30–90min)
- AI job extraction (`prompts/extract_job` real implementation)
- Job dedup (URL + fuzzy title/company)
- `notifications.notify_new_high_score` gate at score ≥ `Settings.notify_threshold`
- n8n migration: one-time CSV import via `services/legacy_import.py`
- Anti-detection: per-source rate-limit + jitter, optional UA rotation
- New entity: `ScrapingSource` (DATA_MODEL.md § B Phase 2+ list)

**Risk.** LinkedIn scraping reliability. RSShub feed at `rsshub.luminolab.net` may break — needs alternate path. Workday auto-extracts CV fields from PDFs (the resume-parsing override Greenhouse + Workday adapters in Wave 6 already handle, but extracting JD text from Workday is tougher).

**Estimated effort.** 2-3 weeks. Splits cleanly into 11a (LinkedIn + Greenhouse + Lever + Ashby — the easy ones) and 11b (Workday + Indeed + Generic + n8n migration — the hard ones).

#### Plan 12 — Phase 3: full scoring pipeline

**Why next.** Wave 6's deterministic visa filter zeros out incompatible jobs, but everything else gets a "real but naive" score from `prompts/score_job`. Auto-apply at scale needs the real tag-matching + gap-analysis pipeline so the right jobs surface at the top of Discover.

**Source contract.** `BACKEND.md` § H.1 (`scorer`), § M.3 (`score_job` prompt). `DATA_MODEL.md` § C `Job.match_breakdown`.

**Scope.**
- Tag-based matching: JD → identify tags → match against Profile bullets via embeddings or keyword similarity
- AI scoring (`prompts/score_job`) returning `{score, explanation, matched_tags, gaps, visa_concern}`
- Per-dimension match bars (`ai-ml 0.95`, `platform 0.88`, ...) populating `Job.match_breakdown` JSON
- Score history + analytics surfaces on Overview
- Tailored-resume preview on Discover · review showing which bullets got selected/excluded based on tag relevance
- Score recalibration cron (`jobs.score_pending` every 15min for newly-scraped jobs)
- New: `JobEmbedding` (pgvector) sibling table for semantic match — **optional in Phase 3, full enable in Phase 6**

**Estimated effort.** 1-2 weeks.

#### Plan 13 — Phase 4: email integration + auto-classification

**Why next.** Tracking "needs followup" + Overview email-signal feed are stubbed in Phase 1. Without real email, recruiter-state derivation can't run; Tracking auto-classification doesn't surface; the Discord/Telegram interview-invitation notifications never fire.

**Source contract.** `BACKEND.md` § L.1 (Gmail/Outlook OAuth + IMAP), § H.1 (`email_monitor`, `email_classifier`), § I.1 (Phase 4 cron catalog).

**Scope.**
- Gmail OAuth flow + sync cron (every 10min)
- Outlook OAuth (same pattern)
- IMAP fallback for non-Gmail/Outlook
- `email_classifier` real implementation (LLM classifies `INTERVIEW_REQUEST / REJECTION / OFFER / ASSESSMENT / FOLLOW_UP / OTHER`)
- `application_service.derive_recruiter_states` cron (every 30min) — auto-sets `Application.recruiter_state` per DATA_MODEL.md § E
- Priority notifications gate (Discord + Telegram on INTERVIEW_REQUEST + OFFER)
- Email thread tracking on Tracking + Overview email-signal feed (real, not stubbed)

**Estimated effort.** 1-2 weeks.

### Tier 2 — completes the lifecycle

#### Plan 14 — Phase 5: outreach + LinkedIn + Discord/Telegram/Calendar

**Source contract.** `BACKEND.md` § L.2-L.5 (LinkedIn browser, Discord, Telegram, Calendar), § H.1 (`outreach_generator`, `contact_tracker`), § I.1 (Phase 5 cron catalog).

**Scope.**
- `integrations/linkedin_browser.py` — Playwright with user session cookie. DM send + employee search + reply check. Account-ban-risk warning prominent in Settings.
- `outreach_generator` real implementation — AI drafts via `prompts/draft_outreach` (all 5 intents)
- Outreach cron: `outreach.send_linkedin_dms` (every 5min batch, max 50/day), `outreach.check_dm_replies` (every 60min), `outreach.suggest_next_moves` (every 24h)
- Telegram inbound long-poll worker (`/status`, `/today`, `/silent` commands) — separate task, NOT APScheduler
- Google Calendar OAuth + auto-create events on `INTERVIEW_REQUEST` classification
- Warm-intro finder: suggest mutual connections for warm outreach (LinkedIn API)

**Estimated effort.** 2-3 weeks (LinkedIn is the most fragile dep).

#### Plan 15 — Phase 6: observability + light mode + LaTeX + semantic match + ML calibration

**Source contract.** `BACKEND.md` § N (Prometheus, Sentry, OTel), `DATA_MODEL.md` § H (`JobEmbedding` pgvector), `DESIGN.md` (light mode tokens — Phase 6).

**Scope.**
- Prometheus metrics endpoint `/metrics`
- Sentry via `SENTRY_DSN`
- OpenTelemetry tracing for LLM / scraper / ATS submission paths
- `JobEmbedding` pgvector enable + Discover semantic search
- Light mode: DESIGN.md tokens + Tailwind `dark:` flips on every component (the largest item in this phase)
- LaTeX template alongside Typst (`latexmk` / `tectonic`)
- Resume A/B testing + ML scoring calibration from outcomes
- Weekly summary report (`admin.weekly_summary` cron)

**Estimated effort.** 3-4 weeks. Splits into 15a (observability) + 15b (light mode) + 15c (LaTeX + ML calibration).

### Tier 3 — Phase 1.x deferred items (slot in opportunistically)

These are smaller items that can ship between or alongside Tier 1/2 plans. Each can be a small standalone plan or folded into a thematic combo plan. From `ROADMAP.md` § Phase 1 deferred:

| Item | Suggested plan number | Notes |
|---|---|---|
| Workday / LinkedIn / Indeed / Generic ATS adapters | 16 (combo with Phase 2's Workday scraper since both touch the same boards) | Need credentials + Playwright + manual review queue |
| Stale-DRAFT cleanup cron | tiny — can merge into plan 11 (Phase 2 cron infra) | Auto-discard >30-day-idle DRAFTs |
| Postmortem-on-failure (Playwright snapshot + AI summary) | small follow-up to plan 16 | Surfaces in stuck-queue card |
| `Show drafts` UI toggle on Tracking | tiny — can merge into a Settings polish plan | Endpoint already wired in Wave 3 |
| `+ Add manually` full modal on Tracking | tiny | Currently only `+ Add by URL` from Discover |
| Application detail slide-over (`/tracking/:id` in Phase 2 spirit, slide-over now) | small | Phase 2 introduces the route; this is the UI |
| Auto-apply immediate dispatch on right-swipe | small | Refinement; user expectation may grow once Phase 2 ships |
| `Settings.scraper_aggressiveness` rate-limit dial | small | Phase 2+ |
| Portfolio API versioning (`/api/portfolio/cv?version=v1`) | tiny | Phase 2+ |
| `Settings.daily_llm_cost_cap_usd` dashboard widget | tiny | Wave 6 ships the enforcement; visible cap progress UI is a Settings polish item |
| `ProfileAnswer` reuse cache (screener answer memory) | small | Phase 2+; new entity |
| OIDC for self-hosted (Authentik / Keycloak / Okta) | medium | Phase 2+ |
| Submission-result observability dashboard | small | Phase 6 polish — Failure-kind aggregates per board |
| Argon2id vault upgrade | small | Phase 6 if security review flags PBKDF2 |
| JWT signing-key rotation (multi-tenant cloud) | medium | Phase 2+ if cloud tier ships multi-tenant |
| LinkedIn proxy support | small | Phase 6+ |

---

## Suggested authoring sequence

```
[Phase 1 ships]
  ↓
Plan 11 (Phase 2 scrapers) — 2-3 weeks
  ↓
Plan 12 (Phase 3 scoring) — 1-2 weeks
  ↓
Plan 13 (Phase 4 email) — 1-2 weeks
  ↓
[Phase 1.x deferred — slot in 1-2 small plans here for breathing room]
  ↓
Plan 14 (Phase 5 outreach) — 2-3 weeks
  ↓
Plan 15 (Phase 6 polish) — 3-4 weeks
  ↓
[Naavik v1.0 — full end-to-end automation]
```

Total post-Phase-1 estimate: 9-15 weeks of agent-driven implementation (each plan is a fresh session paste; you can run multiple plans in parallel if no shared state).

---

## How to author the next plan (operational)

1. Pick the next plan from the priority list above (start with **Plan 11 — Phase 2 scrapers**).
2. Open a fresh Claude Code session at the repo root.
3. Paste a session-continue prompt similar to `docs/prompts/00-session-continue.md` but pointed at the new plan number. The prompt should:
   - List required reading (AGENTS.md, ROADMAP.md, BACKEND.md, DATA_MODEL.md, etc.)
   - State the plan being authored (e.g. "Author plan 11 — Phase 2 scrapers")
   - List what's out of scope
   - Reference this NEXT_STEPS.md for the post-plan-10 forward arc
4. The agent authors `docs/plans/11-phase-2-scrapers.md`.
5. Review + approve.
6. Agent authors `docs/prompts/11-phase-2-scrapers.md` once plan 11 is APPROVED.
7. Paste the kickoff prompt into yet another fresh session for implementation.
8. Archive plan + prompt + bump ROADMAP when done.
9. Repeat for plan 12, 13, etc.

The lifecycle is identical to plans 08-10's. The only difference is the source contract is already well-defined in BACKEND.md / DATA_MODEL.md — no design doc graduation step needed for Phase 2-6, just plan + prompt + execute.

---

## Cross-cutting concerns to track post-Phase-1

These aren't plan-shaped but worth a tracked TODO list as you ship Phase 2-6:

1. **Cost trajectory.** Once real scraping (Phase 2) + auto-apply (Wave 6) run together, watch `ApiUsage` weekly. If a single user costs >$50/month on AI, the cost-cap defaults need tightening.
2. **Anti-detection drift.** LinkedIn / Workday / Indeed actively detect bots. Each shipped scraper needs a 2-week stability window before considering it production-ready. If the scraper breaks within a week, anti-detection budget needs a rethink.
3. **Email classification accuracy.** Phase 4's classifier should be ≥95% accurate on the 6-class taxonomy. Monitor by user-flagging false positives; retrain prompts via versioning.
4. **n8n decommission.** After Phase 2 ships and runs clean for 1 week, disable the n8n Main Workflow. Don't forget. (See `ROADMAP.md` § n8n Migration Strategy.)
5. **Portfolio site dependency.** `crypticsoul.dev`'s `cv.astro` build-time fetches `/api/portfolio/cv`. Any contract change to that endpoint must coordinate with the portfolio repo (separate codebase). Currently zero versioning — Phase 2+ adds `?version=v1`.
6. **Multi-user readiness.** Every entity already has `user_id`; the multi-tenant cloud tier is unblocked at the model layer. But cron jobs assume single-user (`user_id=1`) — the `applications.auto_apply` cron, `tracking.sync_gmail`, etc. all need a `for user in users` loop wrapping their existing logic. Track as a Phase 2+ item.
7. **Backups.** `~/.naavik/data/snapshots/` daily SQL gzip — but no off-site backup story yet. Document for self-hosters: the vault + snapshots dir together is the full backup; off-site to S3 / Backblaze / etc. is the user's responsibility.
8. **Visual regression as PR gate.** Once snapshots stabilize (probably after 2-3 of Phase 2-6 plans ship without breaking visual parity), wire Playwright diff into CI. A plan dedicated to the CI integration around then.

---

## When something goes wrong

Each implementation prompt includes a "STOP and post a question" instruction for blockers. Honor it — mid-flight scope creep is the most common way these sessions drift. Common blocker categories:

- **Spec contradicts mockup.** SCREENS.md spec wins (`docs/design/SCREENS.md` says it's the source of truth). Update SCREENS.md if mockup is correct; update mockup batch if spec is correct.
- **Component variant missing.** If plan 09 needs a component variant plan 08 didn't ship, the implementing agent files an extension to COMPONENTS.md and adds the variant. Catalog count stays at 85; only variants extend.
- **External API surface drift.** Greenhouse / Lever / Ashby / LinkedIn / Anthropic SDK changes between authoring and implementation are likely after Phase 1 ships (3-6 months between waves). When an API breaks, file a small fix-up plan (e.g. `12a-greenhouse-api-update.md`) and ship before continuing the main wave.
- **Cost cap hits in production.** If a user hits the daily LLM cost cap repeatedly during normal use, the cap default is wrong — adjust in DATA_MODEL.md `Settings.daily_llm_cost_cap_usd` default and ship as a tiny plan.

---

## What success looks like

Naavik v1.0 (post-Phase-6) means:

- A self-hosted user clones the repo, edits `.env`, runs `docker compose up -d`, lands at `localhost:8000`, signs up, uploads a resume, and is auto-applying to relevant jobs by end-of-day.
- A NixOS user adds the flake input, enables the module, sets SOPS secrets, and the same flow works behind their Traefik reverse proxy.
- A cloud-tier user pays $15/mo, brings their own Anthropic key, and gets the identical product.
- The portfolio site at `crypticsoul.dev` reflects the Profile state without manual sync.
- Cost per user per month is <$5 on Claude (target — depends on traffic patterns).
- Self-hosted instances run for 90+ days without intervention.

The product hits the "Sprout for engineers, but you own your data" pitch in the ROADMAP § Vision section.

If Phase 6 ships clean and the above is mostly true, ship the v1.0 release tag, write the launch post, and start on v1.1. The `ROADMAP.md` Phase 6+ ideas (template marketplace, ML scoring calibration from outcomes, multi-region cloud tier, mobile companion app, browser extension for one-click capture) are the v1.1+ frontier.

---

## TL;DR

After Phase 1 ships:
1. Run the testing playbook (§ above).
2. Author plan 11 (Phase 2 scrapers) next.
3. Then plans 12 → 13 → 14 → 15 in order.
4. Slot in Phase 1.x deferred items where they fit.
5. Track cost trajectory + anti-detection drift + email classification accuracy + multi-user readiness as cross-cutting concerns.
6. v1.0 ships when Phase 6 lands.

Phase 1's contract was tight — it'll take 4-6 weeks of agent work to ship cleanly. Phase 2-6 is another 9-15 weeks. Realistic v1.0 ship date: 4-5 months from Phase 1 start. That's the timeline you should plan against.
