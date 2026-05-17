---
Topic: linkedin-scraping
Aliases: linkedin, scrapers, job feed, RSShub, guest API, voyager, MCP linkedin
First captured: 2026-05-17 (run 2026-05-17T08-40-13_4abef2)
Last referenced: 2026-05-17
Supersedes: none
Confidence: high
---

# linkedin-scraping

## Context

ROADMAP § Phase 2 task 2.2 currently reads "LinkedIn (RSS via RSShub + guest API)". That sentence locked a stack of decisions inherited from the n8n era. The 2026-05-17 architect dispatch on the same run as plan 18 / PC.6 produced a 214-line option matrix at `docs/design/research/LINKEDIN_SCRAPING.md` weighing 5 mechanisms (RSShub feed, direct guest API + Crawl4AI stealth, stickerdaniel/linkedin-mcp-server, HorizonDataWave SaaS, tomquirk/linkedin-api Voyager wrapper) across 7 dimensions.

## Resolution / pattern

Recommended path is **direct guest-API + Crawl4AI stealth**, with RSShub kept as opportunistic enrichment. Rationale: same TOS posture as RSShub (both hit `seeMoreJobPostings/search` against the unauthenticated `jobs-guest` API), one fewer operational hop (no `rsshub.luminolab.net` dependency on our infra), keeps the rate-limit-bearing surface on LinkedIn's side. Decision gate: revisit before authoring `docs/plans/11a-phase-2-scrapers.md`; re-read § 8 (Revisit checklist) of the research doc before folding any option into the plan.

Constraints applied: vault is sunset (2.12) so credentialed options (C/E) cannot land cookies in `services/vault.py`; CLI is sunset (2.11) so `naavik linkedin login` is off the table; APScheduler-driven cron (Phase 2 task 2.5) forces in-process invocation, ruling out long-running MCP daemons without stable IPC.

## Related

- docs/design/research/LINKEDIN_SCRAPING.md — full 214-line option matrix + revisit checklist
- ROADMAP.md § Phase 2 task 2.2 (current "RSShub + guest API" wording awaiting plan 11a update)
- traces/2026-05-17T03-16-16_75a522/architect-linkedin.log — the dispatch that produced the matrix
- docs/design/BACKEND.md § J (scraping architecture, authoritative scope doc)
