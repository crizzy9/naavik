---
Status: ACTIVE
Type: research
Authored: 2026-05-17
Last updated: 2026-05-17
Decision gate: revisit when authoring `docs/plans/NN-phase-2-scrapers.md` (after 2.12 + 2.11 sunset clear; current ROADMAP estimate: 3–5 dev-days from 2026-05-17). Re-read the Revisit checklist (§ 8) before folding any option into plan 11a.
Implements: ROADMAP § Phase 2 task 2.2 (LinkedIn portion). Touches 2.1 (Crawl4AI base), 2.3 (AI extraction), 2.4 (dedup), 2.5 (APScheduler), 2.9 (rate limit + anti-detection) — see § 7 for per-task impact.
Authoritative-scope-doc: `docs/design/BACKEND.md` § J (scraping architecture). This doc weighs options before plan 11a freezes the choice into a file-by-file plan.
---

# LinkedIn Job-Discovery Mechanisms — Research

> **Purpose.** ROADMAP § Phase 2 task 2.2 currently reads "LinkedIn (RSS via RSShub + guest API)". That sentence locked in a sequence of decisions that haven't been re-examined since the n8n era. This doc names the 5 viable mechanisms, scores them against the 7 dimensions that matter for self-hosted Naavik, recommends one, and surfaces the trigger condition that forces a revisit.
> **Not a plan.** No file-by-file edits, no tests, no migrations. Plan 11a authoritatively encodes the chosen path.

---

## 1. Executive summary

- **Current ROADMAP plan (2.2):** RSShub at `rsshub.luminolab.net/linkedin/jobs/...` as the listing feed, LinkedIn guest API (`/jobs-guest/jobs/api/jobPosting/{id}` and `/seeMoreJobPostings/search`) for detail/refresh, Crawl4AI as a fallback for whatever the guest API doesn't expose.
- **Top alternative:** Direct guest-API consumption (skip RSShub; hit `seeMoreJobPostings/search` ourselves from `scraper/linkedin.py` with Crawl4AI's stealth mode). One fewer hop, same TOS posture, removes the operational dependency on `rsshub.luminolab.net`.
- **Recommendation:** **Direct guest-API + Crawl4AI stealth, with RSShub kept as an opportunistic enrichment source.** Rationale in § 5.

---

## 2. Context — why this research now

Phase 2 task 2.2's wording was inherited from the n8n workflow (`PQAGv5qUajzBP5wm` Job Page Parser + RSShub feed at `rsshub.luminolab.net`). That stack predates Naavik's `scraper/` substrate and ships with assumptions we haven't validated:

1. **RSShub's LinkedIn route is uninstrumented for anti-detection.** Source: `DIYgod/RSSHub/lib/routes/linkedin/jobs.ts` — `antiCrawler: false`, no header manipulation, plain `ofetch`. It's a thin wrapper over the same guest-API endpoint we'd hit directly. Self-hosting `rsshub.luminolab.net` puts the rate-limit-bearing surface on *our* infrastructure, not LinkedIn's.
2. **The guest API is alive in 2026 and undocumented.** Public dev.to write-ups + the LinkedIn jobs API gist (Diegiwg) confirm `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=...&location=...&start=N&f_TPR=r86400&f_E=4&f_JT=F&f_WT=2&f_C=companyId` works without auth as of May 2026.
3. **MCP-server ecosystem matured.** Three production-grade LinkedIn MCP options exist (stickerdaniel, HDW, adhikasp). None existed when 2.2 was written. They change the cost / risk / capability calculus enough to warrant inclusion.
4. **TOS + legal context changed.** *hiQ Labs v. LinkedIn* settled Dec 2022 with hiQ paying $500K + agreeing to delete scraped data — even though the Ninth Circuit had ruled CFAA doesn't bar public scraping. The CFAA defence survives; the state-law / TOS / common-law-trespass theories don't. LinkedIn has since aggressively pursued *individual* scrapers — Proxycurl was sued into shutdown July 2025; Apollo.io + Seamless.AI had their LinkedIn company pages removed March 2025.
5. **Naavik's vault is sunset.** Any option requiring persistent credentials (session cookies, OAuth tokens) lands in `.env` (post-2.12) or a per-user encrypted column — NOT `services/vault.py`. This narrows the credential-bearing options' viability.

The decision-relevant constraints from AGENTS.md + ROADMAP are:

| Constraint | Source | Bearing on this decision |
| --- | --- | --- |
| Self-host first; Docker Compose stack | DEPLOYMENT.md § 2 | Out-of-stack services (paid SaaS, third-party MCP servers) add operational complexity. Not disqualifying, must be flagged. |
| No new vault scopes / `services/vault.py` extension | AGENTS.md § Key Conventions § CLI | LinkedIn session cookies cannot live in vault. Forces options-3-and-4 to lean on `.env` or per-user encrypted column. |
| No new `naavik` CLI subcommand | AGENTS.md § Key Conventions § CLI | "`naavik linkedin login`" is not on the table. Cookie capture must be Settings UI or env var. |
| Track all LLM calls via `services/llm_tracker.tracked_call` | ARCHITECTURE.md § 4.4 | Any option that proxies AI extraction (MCP servers that do "AI parse this profile") loses our cost-cap enforcement. |
| Scraping cron is APScheduler-driven (Phase 2 task 2.5) | BACKEND.md § I | The chosen mechanism must be invocable from an APScheduler job in our Python process. Out-of-process daemons (MCP servers as long-running services) need a stable IPC. |

---

## 3. Options inventory

Five mechanisms are viable. The "rejected for cause" appendix § 9 covers six more.

| # | Mechanism | One-line shape |
| --- | --- | --- |
| **A** | **RSShub feed (current ROADMAP)** | Self-hosted `rsshub.luminolab.net/linkedin/jobs/...` → JSON-ified RSS → Naavik pulls every 30min. |
| **B** | **Direct guest API + Crawl4AI stealth** | `scraper/linkedin.py` calls `seeMoreJobPostings/search` + `jobPosting/{id}` directly with Crawl4AI's stealth mode. No external dependency beyond LinkedIn itself. |
| **C** | **stickerdaniel/linkedin-mcp-server (authenticated session via Patchright)** | Local MCP server with per-user LinkedIn cookies. Naavik calls it as a sidecar via stdio or HTTP. |
| **D** | **HorizonDataWave (paid SaaS API)** | Bring-your-own API key to a hosted LinkedIn data service. $0.02/req, 100 free/month. Same shape as Apify actor alternatives. |
| **E** | **tomquirk/linkedin-api (unofficial Voyager wrapper)** | Python lib that authenticates as a logged-in LinkedIn user via email + password, hits the internal Voyager API. |

---

## 4. Options matrix

Dimensions: **Capability**, **Financial cost**, **Maintenance cost**, **Risk (TOS + breakage)**, **Supply-chain (third-party dep)**, **Self-host compat**, **Integration burden**. Scores: ✅ good · ⚠ caveat · ❌ blocker.

| | A — RSShub | B — Direct guest API + Crawl4AI | C — stickerdaniel MCP | D — HDW paid SaaS | E — tomquirk Voyager |
| --- | --- | --- | --- | --- | --- |
| **Capability** (job search) | ⚠ Listings only (title + company + location + URL + pubDate). Detail JD requires a second hit to `jobPosting/{id}`. | ✅ Listings via `seeMoreJobPostings/search` + full detail HTML via `jobPosting/{id}`. Filters supported: `f_TPR` (time), `f_E` (seniority), `f_JT` (type), `f_WT` (remote), `f_C` (company), `geoId` (location). | ✅ 19 tools: jobs search, job detail, profiles, companies, employee listings, messaging, inbox — same shape as a logged-in browser. Far broader than we need today but useful for Phase 5 (5.9–5.14 recruiter/employee outreach). | ✅ Comparable to C; tools across LinkedIn + Instagram + Reddit + Twitter (65+). |⚠  Logged-in account access: jobs search, profile view, message send. Volume capped by single-user account → ban risk. |
| **Capability** (extraction shape) | ⚠ RSS items are pre-shaped — title, description, link, pubDate. JD body needs a second fetch + parse. Phase 2 task 2.3 (AI extraction) is still required for full JobInfo. | ⚠ HTML cards from `seeMoreJobPostings/search` + HTML body from `jobPosting/{id}`. Phase 2 task 2.3 still required for AI extraction of visa / salary / skills. | ✅ Structured fields (title, company, location, JD, posted time, applicants count) returned by the tool call. Reduces task 2.3 scope for LinkedIn jobs only. | ✅ Structured JSON. Same task-2.3 reduction. | ⚠ Structured but field set varies; the lib's `search_jobs` returns IDs + basic metadata; detail is a separate call. |
| **Financial cost** | ✅ Free. RSShub is self-hosted (already on `n8n.luminolab.net`'s neighbour). | ✅ Free. | ✅ Free OSS (Apache-2.0). No cloud cost. | ❌ $0.02/req. 100 jobs/day across user base = ~3000/mo = $60/mo on top of $15/mo cloud tier. Self-hosters pay extra; cloud tier eats the cost or charges through. | ✅ Free OSS (MIT). |
| **Maintenance cost** | ⚠ Two surfaces to maintain: the RSShub fork/instance AND our parser. When LinkedIn changes the guest-API HTML, RSShub breaks AND we must wait for upstream (`DIYgod/RSSHub`) PRs to land. Or fork. | ✅ One surface (`scraper/linkedin.py`). When LinkedIn HTML changes, we patch one file. Our maintenance, our cadence. | ⚠ Patchright + browser ChromeDriver to keep current. When LinkedIn ships UI changes, stickerdaniel's repo lags — historically 1-3 weeks per the upstream issue tracker. We can fork, but Patchright is JavaScript-heavy. | ✅ Vendor maintains; we don't. But we're locked to their schema + their bugs. | ❌ Library breaks every time LinkedIn changes Voyager (multiple per year per upstream commit history). Maintainer responsiveness mixed. |
| **Risk — TOS / legal** | ⚠ TOS § 8.2.2 prohibits scraping "the Services, including profiles and other data" via "any means or processes". RSShub IS scraping. The CFAA argument from *hiQ* is favorable (public, no auth, no protected-page access), but state-law claims (CA Penal Code 502, common-law trespass) survived the settlement. Lowest-risk option in this set because access is unauthenticated + read-only + low-volume. | ⚠ Same posture as A (unauthenticated, public guest API). LinkedIn cannot distinguish our requests from RSShub's at the wire. Same legal surface, one fewer hop. | ❌ Authenticated scraping with a real user account. LinkedIn detects automation patterns (`navigator.webdriver`, canvas fingerprint, WebGL hashes) — Patchright patches ~20 of these but not all. Account ban risk is real: upstream stickerdaniel docs warn "use a secondary account, < 20-30 daily lookups". For a single-user self-host this is barely tolerable; for the cloud tier with N users it doesn't scale. | ⚠ Vendor absorbs the legal exposure on the wire side. We hold their API key. They IP-rotate + manage compliant accounts. TOS risk shifts to them — but data-use TOS still applies to us. | ❌ Credential-stuffing risk + account ban + clear TOS violation. The library README itself warns "use at your own risk". Worst-of-all-worlds: we hold the user's LinkedIn password (vault-sunset blocker) + their account dies under load. |
| **Risk — breakage cadence** | ⚠ Two breakage surfaces (LinkedIn → RSShub upstream → us). 2024-2026 RSShub repo issues show LinkedIn routes flagged broken a few times/year, fixes lag 1-4 weeks. | ⚠ One breakage surface. LinkedIn changes its guest-API HTML shape ~quarterly. We patch in hours, not weeks. | ⚠ Upstream-tracked. stickerdaniel actively migrated to Patchright in late 2025 when Playwright broke; he's responsive, but version lag is real (cf. CI workflow runs). | ✅ Vendor SLA. They handle breakage. | ❌ Constant. Voyager is LinkedIn's internal API; they change it without notice + frequently. |
| **Supply-chain / third-party dep** | ⚠ External service: `rsshub.luminolab.net` must stay alive. Self-hosters who *don't* run RSShub get a broken default scraper unless we ship a Docker `rsshub` sidecar in `docker-compose.yml`. | ✅ No third-party dep. Crawl4AI is already in 2.1; this option re-uses it. | ⚠ MCP server is a sidecar process. Docker Compose can host it. Adds `~500MB Chromium` to the container set. License Apache 2.0 (compatible with AGPL). | ❌ Hard dependency on `app.horizondatawave.ai`. If they go down or change pricing, our LinkedIn scraping is broken. Vendor lock-in for *self-hosters* is a fundamental conflict with project values. | ✅ Pure Python library, no service. |
| **Self-host compat** (`docker compose up -d`) | ⚠ Requires adding `rsshub` service to compose stack OR documenting "BYO RSShub". The Lumino-pattern `rsshub.luminolab.net` is fine for the owner; not transferable. | ✅ Ships inside `naavik` container. No new service. | ⚠ Adds MCP-server sidecar service. Possible, but per-user state (cookies) lives in a mounted volume — multi-user cloud tier needs per-tenant volume slicing. | ❌ Cloud-dependent. Self-hosters who want to be air-gapped (which is half the audience) can't use it. | ✅ Ships inside `naavik` container. But credential management blows up: per-user LinkedIn email + password in DB or env. |
| **Integration burden** (lines + new tasks) | Medium. New `scraper/linkedin.py` + RSShub sidecar in compose + `Settings.scraper_rsshub_url` env var. ~400 LOC. | Low. Drop-in `scraper/linkedin.py` using existing Crawl4AI base. ~300 LOC. | High. MCP client wiring (stdio or HTTP), per-user cookie capture flow (Settings UI: "Connect LinkedIn" → headless browser sign-in → cookie extraction → encrypted column), tool-call schema mapping. ~800 LOC + UI surface. | Medium. SDK wrapper + API-key field in Settings · LLM Provider (since it's the same "configured via env" pattern). ~200 LOC. | High. Login flow + cookie persistence + per-user credential storage (sunset-vault blocker) + retry-on-401 — same complexity as C without the structured output. ~700 LOC. |
| **Removes work from task 2.3 (AI extraction)?** | ❌ No — RSS items are stub-shaped; full JD still needs AI parse. | ❌ No — guest API HTML still needs AI parse for visa / salary / skills. | ✅ Partial — `get_job_details` returns title/company/location/JD/posted time as structured fields. AI parse reduced to visa + salary inference. | ✅ Partial — same shape. | ⚠ Partial — depends on the lib's job-detail shape. |

---

## 5. Recommendation

**Pick Option B — Direct guest API + Crawl4AI stealth.** Keep Option A (RSShub) as an opportunistic enrichment source if `rsshub.luminolab.net` is already running, but do not gate Naavik's LinkedIn scraping on it.

### Why

1. **Self-host compat is the hard constraint.** Naavik's brand promise is "Docker Compose up, jobs in minutes". A self-hoster shouldn't have to also run RSShub, sign up for a paid SaaS, or surrender a LinkedIn password. B ships in-container with zero new services.
2. **One breakage surface beats two.** When LinkedIn changes the guest-API HTML, A means waiting on `DIYgod/RSSHub`. B means we patch one file in our repo. The TOS / legal surface is identical (both hit the same guest endpoint unauthenticated) but the operational responsiveness differs by weeks.
3. **Crawl4AI is already in 2.1.** Option B is purely "use the tool we're already adopting". No new dependency, no new pattern to teach future contributors.
4. **The CFAA / TOS posture is best at the guest-API tier.** Unauthenticated, no protected pages, no credentials → CFAA falls under the *hiQ* precedent. State-law / TOS risk is non-zero but every guest-API consumer (RSShub, Apify, every dev.to tutorial) operates here and LinkedIn hasn't pursued individual non-commercial scrapers at this tier. Note: this is not legal advice; § 6 risk #1 covers the residual.
5. **Doesn't preclude Phase 5 LinkedIn DM/outreach.** Option C (stickerdaniel MCP) is still the right answer for Phase 5 task 5.12 (sending connection requests + DMs) where authenticated session is unavoidable. This research scopes only Phase 2 *discovery*; Phase 5 outreach revisits MCP for the auth-required surface. We can adopt B now without precluding C later.

### Trade-off accepted

- **We carry the breakage maintenance.** When LinkedIn changes the guest API's HTML shape, `scraper/linkedin.py` needs a same-day patch. Mitigation: a daily synthetic-monitor cron (`scraping.linkedin_health_check`) that hits the search endpoint with a known-good query + alerts if the parse fails. Cron lives next to `scraping.linkedin` per BACKEND.md § I.
- **No "structured-field shortcut" for task 2.3.** AI extraction still needed per LinkedIn job to pull visa / salary / sponsorship signals from the JD body. This is fine; we'd need 2.3 anyway for every other source.
- **Low rate ceiling.** Guest API tolerates ~one query per 2-3 seconds, ~400-500 listings/hour before 429s appear (per dev.to + iproyal write-ups). Sufficient for a single user's discovery cadence + a small cloud tier; insufficient for a SaaS-scale aggregator (out of scope).

### Stack-ranked rejected options

1. **A — RSShub** (close 2nd). Reject because of dual-surface maintenance + the operational burden of shipping `rsshub` in Docker Compose. Keep it as an opt-in enrichment source for users who already run RSShub — code in `scraper/linkedin.py` reads `Settings.scraper_rsshub_url` if set, prefers it over the direct call, falls back on parse error.
2. **C — stickerdaniel MCP** (right answer for Phase 5, wrong for 2.2). Reject *now* on account-ban risk + cookie-management complexity. Re-evaluate for plan 14 (Phase 5 outreach).
3. **D — HDW paid SaaS**. Reject for self-host conflict + vendor lock-in. Would only become attractive if Naavik moved to "cloud-tier-first with optional self-host"; current direction is the inverse.
4. **E — tomquirk/linkedin-api**. Reject. Credential storage in DB + breakage cadence + account ban risk. Strictly worse than C for the same risk profile.

---

## 6. Top 3 risks (across all options)

| # | Risk | Likelihood | Impact | Affects which options | Mitigation if recommendation (B) chosen |
| --- | --- | --- | --- | --- | --- |
| 1 | **LinkedIn TOS enforcement action.** Even though CFAA is favorable post-*hiQ*, LinkedIn has aggressively pursued individual scrapers (Proxycurl shutdown 2025, Apollo + Seamless company-page takedowns 2025). State-law / contract / common-law theories survive. Naavik is open-source + non-commercial + single-user — lowest profile in the enforcement target set, but not zero. | LOW for non-commercial self-hosted single-user. MEDIUM if Naavik's cloud tier serves >100 users from a single IP. | HIGH (cease-and-desist, takedown). | All options that touch LinkedIn. D shifts the wire-side exposure to vendor; data-use TOS still applies to us. | (a) Documented user-facing notice in Settings · Integrations explaining the legal posture + telling cloud users to BYO scraping if scale is a concern. (b) Conservative rate-limits (`Settings.scraper_aggressiveness` per ROADMAP § Phase 1.x deferred). (c) Honor `robots.txt` (informational; LinkedIn's `/jobs-guest/` paths are crawl-permitted in their robots). |
| 2 | **Silent breakage.** LinkedIn ships a UI change, the parser breaks, the discover queue goes empty without a loud failure. User assumes "no jobs match", not "scraper is down". | HIGH (quarterly cadence per industry reports). | HIGH (user loses trust in Naavik's job-finding capability). | All scraping options. SaaS (D) absorbs this; everyone else carries it. | Synthetic-monitor cron `scraping.linkedin_health_check` (BACKEND.md § I cron catalog). On parse failure → Discord webhook alert + `Settings.linkedin_scraper_status: DEGRADED` flag → Discover screen shows banner. |
| 3 | **Cloudflare / WAF challenge.** LinkedIn fronted by Cloudflare on some paths (Voyager); 2026 reports document occasional 403s on datacenter IPs without TLS-fingerprint matching. Crawl4AI's stealth mode patches `navigator.webdriver` etc. but doesn't rewrite TLS fingerprints (JA4+). | MEDIUM. Guest API paths (`/jobs-guest/...`) currently appear less aggressively defended than Voyager, but this could shift. | MEDIUM (scraper falls back to authenticated session or service degrades). | B, A (both wire to the same endpoint). | (a) Crawl4AI's `enable_stealth=True` + `UndetectedAdapter` as the bypass ladder (BACKEND.md § J should canonicalize this pattern across scrapers). (b) If 403 rate exceeds threshold → emit `linkedin_blocked` AppEvent → manual review path (notify owner, suggest cookie fallback per Phase 5). (c) Residential proxy support is a Phase 6+ deferred item — not in 2.2 scope. |

---

## 7. Integration notes (under recommended option B)

Per-task impact for Phase 2 tasks the recommended option touches. Plan 11a should encode these as concrete file edits.

| ROADMAP task | Status under option B | Notes |
| --- | --- | --- |
| **2.1 Crawl4AI setup + generic scraper base class** | ✅ No change. LinkedIn is a vanilla `Scraper` subclass that calls `crawler.arun(url, ...)`. Confirms 2.1 needs `enable_stealth` + `UndetectedAdapter` exposed in the base config (already in Crawl4AI 0.8.x). | The `scraper/base.py` interface (already designed in BACKEND.md § J) is sufficient; `linkedin.py` is just an implementation. |
| **2.2 Site scrapers — LinkedIn portion** | New shape: `scraper/linkedin.py` calls `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=&location=&start=&f_TPR=r604800` for listings, then `/jobs-guest/jobs/api/jobPosting/{job_id}` per result for detail HTML. Parse with `bs4` (already in Crawl4AI's transitive deps). | Drop "RSS via RSShub" from the ROADMAP cell when 11a is authored. Edit ROADMAP row 2.2 to read "LinkedIn (guest API, Crawl4AI stealth)". |
| **2.3 AI job extraction** | ✅ No change. The HTML body from `jobPosting/{id}` still needs LLM structured extraction for visa / salary / skills / sponsorship. | The shape of `JobInfo` doesn't change. |
| **2.4 Deduplication** | ✅ No change. LinkedIn job IDs are stable, unique, and embedded in every URL — primary dedup key. Fuzzy title/company is the secondary key for cross-board duplicates. | |
| **2.5 APScheduler cron** | ✅ No change. `scraping.linkedin` per BACKEND.md § I (every 30min). Add `scraping.linkedin_health_check` per § 6 risk #2 mitigation. | |
| **2.9 Rate limiting + anti-detection** | ⚠ Critical for B's viability. Settings: 2.5s mean delay + jitter; max 20 listings/page; max 4 search calls/hour from a single IP. Crawl4AI's stealth mode + `UndetectedAdapter` engaged for LinkedIn specifically. | This becomes the LOAD-BEARING task for option B's viability. Plan 11a should call out LinkedIn-specific limits separately from Workday/Greenhouse/Lever (which are friendlier). |

**New ROADMAP rows to add when authoring 11a:**

- (none — the existing 2.1-2.10 + 2.12-2.11 set covers it.)

**Tasks that become moot or different under option B:**

- The "RSS via RSShub" wording in 2.2 is replaced with "guest API + Crawl4AI stealth (RSShub kept as opt-in fallback)".
- The deferred backlog row "LinkedIn proxy support → Phase 6+" stays Phase 6 — option B works without it for single-user self-host.

**Files plan 11a will create / touch (preview, not authoritative — plan 11a finalizes):**

- `src/scraper/linkedin.py` (new, ~300 LOC)
- `src/scraper/base.py` (already exists post-2.1; minor — add stealth-mode flag if not yet present)
- `src/scheduler/jobs.py` (extend with `scraping.linkedin` + `scraping.linkedin_health_check`)
- `src/services/job_scraper.py` (orchestration; already designed in BACKEND.md § J)
- `src/config.py` (add `scraper_rsshub_url: str | None = None` — opt-in RSShub fallback)
- `.env.example` (document the optional `SCRAPER_RSSHUB_URL`)
- `tests/test_scraper_linkedin.py` (mock-HTTP tests against captured fixtures from `seeMoreJobPostings/search` + `jobPosting/{id}`)
- `docs/RUNBOOK.md` § "LinkedIn scraper returns 0 jobs" (new failure-mode entry per option B's silent-breakage risk)

---

## 8. Revisit checklist (before 11a is authored)

Manager / architect MUST re-verify each before option B locks into plan 11a. If any of these has shifted, this doc is stale; re-open the matrix.

- [ ] **stickerdaniel/linkedin-mcp-server** — is the project still actively maintained (commit in last 60 days)? If yes, the option-C rationale is unchanged. If abandoned, drop C from the rejection list to avoid confusing future architects.
- [ ] **`seeMoreJobPostings/search` endpoint** — still responding to unauthenticated requests in May 2026? Quick check: `curl 'https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=python&location=United+States&start=0'` returns HTML containing `<li class="result-card">` (or equivalent) and HTTP 200. If LinkedIn has gated this behind auth, **option B collapses** and the matrix re-opens — A might survive if RSShub adapts, but C becomes the new front-runner.
- [ ] **`jobPosting/{job_id}` endpoint** — same auth check. If gated, option B falls back to scraping the public job-detail HTML page (`https://www.linkedin.com/jobs/view/{job_id}`), which is a different surface and warrants a re-think.
- [ ] **`DIYgod/RSSHub/lib/routes/linkedin/jobs.ts`** — still tracks the guest-API endpoint? Check for `antiCrawler` flag changes — if RSShub starts inserting cookies / TLS-fingerprint manipulation, our direct-call posture might need to match.
- [ ] **LinkedIn TOS § 8.2** — re-read for material changes. If LinkedIn adds an explicit "no scraping public data" clause (currently the prohibition is general "scrape the Services" — guest API access is contested), the legal posture for ALL non-MCP options worsens.
- [ ] **Crawl4AI undetected_browser_adapter** — confirm LinkedIn isn't on the documented "known broken" list (currently not mentioned either way; v0.8.x docs are silent on LinkedIn specifically).
- [ ] **`scraper_aggressiveness` Settings field** — is the Phase 1.x deferred row for `Settings.scraper_aggressiveness` (rate-limit dial) still deferred, or has it been moved to 2.9? If unchanged, 11a's defaults need to be conservative-by-default and conservatively-configurable.

If 3+ of these have shifted, the matrix is stale enough that 11a's architect should re-author this doc before proceeding.

---

## 9. Appendix — rejected options (single-line dismissals)

| # | Mechanism | Reject because |
| --- | --- | --- |
| F | LinkedIn official Talent Solutions Jobs API | Restricted to vetted Talent Solutions partners; <10% approval rate; 3–6 month onboarding; new Apply-with-LinkedIn partners frozen Oct 2025. Not an option for an open-source project. |
| G | OAuth Sign-In With LinkedIn (`r_liteprofile`, `r_emailaddress`) | Member-data scope only. No jobs read. Useful for Phase 5 outreach contact import, irrelevant for 2.2 discovery. |
| H | `joeyism/linkedin_scraper`, `drissbri/linkedin-scraper` (Selenium-based) | Same risk profile as E (authenticated scraping, ban risk, credential storage) without the structured-output benefit of MCP-server options. Worse than C. |
| I | Apify LinkedIn-jobs-scraper actor | Same shape as D (paid SaaS). $0.4/1000 records is cheaper than HDW but the self-host conflict + vendor lock-in apply identically. |
| J | LinkedIn RSS-feed widgets (the user-configurable share buttons) | Not job search. Promotes LinkedIn POSTS, not job listings. Misnomer in older guides. |
| K | `southleft/linkedin-mcp` (analytics-focused MCP) | Targets content creators (post analytics, engagement automation). No jobs surface. |

---

## 10. References

### MCP servers + scraping libraries
- `stickerdaniel/linkedin-mcp-server` (1.9k stars, Apache-2.0, Patchright-based, active May 2026) — <https://github.com/stickerdaniel/linkedin-mcp-server>
- `horizondatawave/hdw-mcp-server` (61 stars, MIT, paid `$0.02/req` API) — <https://github.com/horizondatawave/hdw-mcp-server>
- `adhikasp/mcp-linkedin` (201 stars, Unlicense, email+password unofficial-API) — <https://github.com/adhikasp/mcp-linkedin>
- `alinaqi/mcp-linkedin-server` (53 stars, MIT, FastMCP, low-activity) — <https://github.com/alinaqi/mcp-linkedin-server>
- `tomquirk/linkedin-api` (PyPI: `linkedin-api`, Voyager wrapper, unofficial) — <https://pypi.org/project/linkedin-api/>
- `DIYgod/RSSHub/lib/routes/linkedin/jobs.ts` — <https://github.com/DIYgod/RSSHub/blob/master/lib/routes/linkedin/jobs.ts>

### LinkedIn API surface
- "LinkedIn Jobs API Documentation" gist (Diegiwg, guest-API endpoint catalog) — <https://gist.github.com/Diegiwg/51c22fa7ec9d92ed9b5d1f537b9e1107>
- LinkedIn Job Posting API (official, partner-only) — <https://learn.microsoft.com/en-us/linkedin/talent/job-postings/api/overview>
- Voyager API context + security disclosure (Idehen, Medium) — <https://medium.com/@Scofield_Idehen/vulnerabilities-exposed-in-linkedins-voyager-api-721755365fbb>

### 2026 scraping landscape + ban risk
- "How to Scrape LinkedIn Job Listings in 2026" (dev.to / agenthustler) — <https://dev.to/agenthustler/how-to-scrape-linkedin-job-listings-in-2026-python-public-api-no-login-required-5bin>
- "LinkedIn Scraping in 2026" (Vayne) — <https://www.vayne.io/en/blog/linkedin-scraping-guide-2026>
- "Scrape LinkedIn Without Getting Blocked 2026" (AlterLab) — <https://alterlab.io/blog/how-to-scrape-linkedin-profiles-and-company-data-without-getting-blocked-in-2026>
- "How to Scrape LinkedIn" (Scrapfly) — <https://scrapfly.io/blog/posts/how-to-scrape-linkedin>
- "LinkedIn MCP Server: Setup, Tools & API Limitations 2026" (Morph) — <https://www.morphllm.com/linkedin-mcp-server>

### Legal context
- *hiQ Labs v. LinkedIn* — case overview (Ninth Circuit + 2022 settlement) — <https://en.wikipedia.org/wiki/HiQ_Labs_v._LinkedIn>
- Jenner & Block client alert on the Ninth Circuit ruling — <https://www.jenner.com/en/news-insights/publications/client-alert-data-scraping-in-hiq-v-linkedin-the-ninth-circuit-reaffirms-narrow-interpretation-of-cfaa>
- LinkedIn User Agreement § 8.2 (current scraping prohibitions) — <https://www.linkedin.com/legal/user-agreement>

### Naavik internal context
- `ROADMAP.md` § Phase 2 task 2.2 (LinkedIn portion)
- `docs/design/BACKEND.md` § J (scraping architecture), § I (cron catalog), § L.2 (LinkedIn browser, Phase 5)
- `docs/ARCHITECTURE.md` § 3.8 (scraper layer), § 4.7 (n8n migration)
- `AGENTS.md` § Key Conventions § CLI (vault + CLI sunset constraints)
- Crawl4AI undetected browser docs (v0.8.x) — <https://docs.crawl4ai.com/advanced/undetected-browser/>
