# LinkedIn apply-target resolution

**Status:** shipped 2026-07-03 · supersedes the guess-only LinkedIn branch of
`SCRAPER_SITES.md § LinkedIn`. Companion to `LINKEDIN_SCRAPING.md` (discovery)
and `JOB_MODEL.md` (the `apply_*` columns).

## The problem

**The site we scrape is not the site we apply on.** LinkedIn is an aggregator:
most postings hand off to an external ATS (Greenhouse / Lever / Ashby / Workday
/ company page). The scraper honestly stamps `source = LINKEDIN` and
`board = LINKEDIN`, but the *real* apply target has to be resolved separately.

The logged-out **guest** job-detail page (`jobs-guest/jobs/api/jobPosting/<id>`)
structurally **hides the offsite target**: the Apply button only carries an
`apply-link-offsite` marker (a boolean "this is offsite") and a CTA that bounces
to a LinkedIn sign-in page — never the ATS URL. Empirically verified against job
`4422894549` (Naavik job 75): the raw guest HTML contains zero occurrences of
the real `job-boards.greenhouse.io/catapultsports/jobs/7960837`.

So the old resolver *guessed* the ATS board by deriving a slug from the company
display name ("Catapult" → `catapult`) and probing the public board APIs. That
guess failed constantly — the Greenhouse org is `catapultsports`, which no
name-based rule derives, so job 75 resolved to `apply_kind=external`,
`apply_url=NULL`, and Submit dispatched to the LinkedIn stub ("auth required").

## The insight

The guest page hides the apply *target*, but it exposes the org's **LinkedIn
company-page slug** in the topcard links (`/company/catapultsports?trk=…topcard…`).
That slug **is** the Greenhouse board slug far more often than the display name
is. Parsing it and feeding it to the existing public board API resolves the
exact posting — and the board API confirms it by title match, so this is
*precise*, not a guess: "Senior Software Engineer" ⊆ "Senior Software Engineer
(GO)" scores 1.0 against the `catapultsports` board's posting `7960837`.

## Two-tier resolution

Both tiers are stages inside `services/apply_site_resolver.resolve_job`; they
produce the same `ResolvedApply` the resolver already stamps onto `Job`. Order:

1. **Direct** — the listing/posting URL already lives on a known ATS host.
   `via = "direct"`.
2. **Tier A — guest slug → ATS discovery** (`services/linkedin_resolver.parse_guest_detail`
   + `discover_ats_posting(extra_slugs=[…])`). Fetch the guest detail once; from
   it take the offsite marker, the company slug, and the JD. Try the company
   slug *before* the name-derived guesses against the Greenhouse/Lever/Ashby
   boards. A title-matched hit yields the canonical URL + full JD. **No auth.**
   `via = "linkedin_guest_slug"` (or `"ats_discovery"` when the winning slug was
   a name guess, not the guest slug).
3. **Tier B — authenticated LinkedIn** (`linkedin_resolver.resolve_via_auth`).
   Only when Tier A can't (LI slug ≠ ATS slug, or a non-GH/Lever/Ashby ATS) and
   a session is configured. A persistent logged-in Chromium profile reads the
   authenticated Voyager posting API
   (`voyager/api/jobs/jobPostings/<id>?decorationId=…WebFullJobPosting-65`),
   whose `applyMethod.…OffsiteApply.companyApplyUrl` **is** the real external
   apply URL (and `description` the full JD). `via = "linkedin_auth"`.
4. **Unresolved** — known-offsite but no target found. `via = "unresolved"`,
   `apply_kind = external`, but the guest JD is still carried forward so
   enrichment can thicken a thin description.

`Job.apply_resolved_via` (migration `0034`) records which path produced the
result, making "authoritative vs guessed" a queryable row-level property.
Two more values joined the vocabulary in the 2026-07-03 retry rework:
`"manual"` (operator-pasted target — ground truth, never overwritten by
automation) and `"exhausted"` (the retry ladder ran dry — see below).

A resolved kind promotes `Job.board` (`easy_apply`→LINKEDIN,
`greenhouse`→GREENHOUSE, …), so Submit dispatch and `SUPPORTED_AUTO_SUBMIT_BOARDS`
gating follow the truth. Job 75 now resolves to `apply_kind=greenhouse`,
`board=GREENHOUSE`, the real Greenhouse URL, and a full JD — Submit fills the
real Greenhouse form (dry-run) instead of saying "auth required".

## Tier B mechanics — session, security, politeness

- **Backend.** Prefer **Patchright** (stealth Chromium fork) pointed at the
  Nix-pinned browser via `executable_path` (Patchright's own bundled revision
  1217 isn't in the read-only Nix store, which ships 1208). Falls back to plain
  **Playwright** with stealth launch args when Patchright is unavailable — the
  persistent-profile + real-cookie approach is the main anti-detection lever
  either way.
- **Session as a profile, not credentials.** The logged-in session persists as
  a Chromium profile under `DATA_DIR/linkedin/profile` (`chmod 0700`,
  gitignored via `.naavik/`). No `li_at` or password is ever written to the DB.
- **Bootstrap.** The `LINKEDIN_SESSION_COOKIE` env slot (an `li_at` value) seeds
  the profile; after the first authenticated navigation LinkedIn sets and the
  profile keeps its own `JSESSIONID`/`bcookie`, so later runs rely on the
  profile. See **Authentication** below.
- **Serialized + jittered.** A module-level `asyncio.Lock` guarantees one
  authenticated session at a time (requests queue). Each session sleeps a
  jittered `Settings.scraper_rate_limits`-derived interval. The sweep budgets
  Tier B to `remaining=3` attempts so one cron tick never opens a long train of
  tabs. Unconfigured deployments skip Tier B entirely (`auth_available()`
  false).

## Authentication — how the operator logs in / refreshes

`scripts/linkedin_login.py` (standalone; not a `naavik` CLI subcommand):

```bash
# Import the li_at from the env slot and verify (headless — SSH/CI friendly):
NAAVIK_DEBUG=1 LINKEDIN_SESSION_COOKIE='AQED…' \
    uv run python scripts/linkedin_login.py --import-cookie

# Or pull li_at from a locally logged-in Firefox/Zen (plaintext cookies.sqlite):
NAAVIK_DEBUG=1 uv run python scripts/linkedin_login.py \
    --from-firefox ~/.config/zen/default/cookies.sqlite

# Or one-time interactive login in a real window (needs a display; persists 2FA):
NAAVIK_DEBUG=1 uv run python scripts/linkedin_login.py --headed

# Check whether the existing profile is still logged in:
NAAVIK_DEBUG=1 uv run python scripts/linkedin_login.py --check
```

`--from-firefox` is the most reliable bootstrap: it imports the **full**
LinkedIn cookie set (not just `li_at`), including the load-balancer cookies
(`lidc`, `bcookie`, `JSESSIONID`). `li_at` alone makes LinkedIn's www↔apex
redirect bounce forever (`ERR_TOO_MANY_REDIRECTS`); the balancer cookies fix it.

Session cookies expire (~months) and LinkedIn invalidates them on password
change / suspicious activity. When the resolver logs *"session not logged in —
refresh the profile"*, re-run `--from-firefox` (or `--import-cookie` with a
fresh `li_at`, or `--headed`).

**Rate-limit hygiene.** LinkedIn soft-blocks automated sessions that hit it too
fast (serving an authwall or a self-redirect tarpit). The resolver defends
against this by design — one serialized session, jittered, budgeted to 3
authenticated fetches per sweep, on the 20-minute cron. Do **not** loop the
verification scripts rapidly; a burst of headless hits will trip the block even
with a valid cookie (it clears after a cooldown).

## Retry regime — no silent dead ends (2026-07-03)

Resolution used to run exactly once per job: the sweep selected
`apply_kind IS NULL`, so anything stamped `external`/`unknown` with no
`apply_url` (every pre-two-tier row — 46% of LinkedIn jobs at the time)
stayed a dead end forever. Now (`migration 0035`):

- `Job.apply_resolve_attempts` counts attempts; `Job.apply_next_resolve_at`
  non-NULL schedules the next retry (partial index `ix_job_apply_retry_due`).
- **Backoff ladder** (`apply_site_resolver.MAX_RESOLVE_ATTEMPTS = 5`):
  attempt 1 → +1h, 2 → +4h, 3 → +24h, 4 → +72h; the 5th failed attempt
  terminalizes as `via="exhausted"` (≈4.2 days total). A crashed attempt
  (`note_failed_attempt`) walks the same ladder — a persistently-failing job
  can't eat sweep budget forever.
- `resolve_pending` drains **fresh first** (`apply_kind IS NULL`, newest
  first — those are what the operator is swiping) minus a 2-slot reserve for
  due retries, so heavy scrape days can't starve the retry queue. Tier B
  stays budgeted at 3 authenticated fetches/sweep regardless.
- The invariant lives in `apply_resolution`: any stamp that leaves
  `external`/`unknown` with no URL either schedules the next rung or
  terminalizes — never a silent dead end. Migration 0035 backfilled the
  existing dead ends as due-now.
- Tier-B URLs get **normalized** before classification
  (`normalize_apply_url`): tracking wrappers unwrap (`?url=` families),
  redirect chains are followed (SSRF-guarded, early-exit on the first hop
  that classifies), so `careers.x.com → x.wdX.myworkdayjobs.com` upgrades
  `company_site` → `workday`. The pre-normalization URL persists in
  `raw_meta["apply_url_original"]`. An unrecognized host **with a URL in
  hand** is `company_site`; `external` strictly means "offsite, target
  unknown".

**Operator surfaces.** The Job-detail right rail (`_apply_target_card.html`)
shows kind + URL + via/attempts/next-retry, a "Re-resolve now" button
(`POST /api/v1/jobs/{id}/resolve-apply`, Tier-B budget of one, serialized
behind the module auth lock), and — while unresolved — a paste-URL form
(`POST /api/v1/jobs/{id}/apply-url`, stamped `via="manual"`, doesn't count
as an attempt). Settings · AI & Automation (`_apply_resolver_card.html`)
shows session health + pipeline counts (`resolver_stats`).

**Session health.** Every Tier-B attempt records its outcome
(`ok` / `not_logged_in` / `error`) to `DATA_DIR/linkedin/session_health.json`
(atomic write, colocated with the profile it describes). The
`resolve_apply_sites` cron sends ONE Discord admin alert when the session
goes not-logged-in (edge-triggered via the file's `alerted` latch; recovery
to `ok` re-arms it).

## Extending to other sites

The `source → resolve → enrich` seam is site-agnostic:

- `parse_guest_detail`-style HTML parsing generalizes to any aggregator whose
  listing page leaks a company slug / website.
- `discover_ats_posting(extra_slugs=…)` already accepts caller-supplied slug
  candidates — an Indeed resolver would parse the company URL and pass its slug
  the same way.
- Tier B (authenticated browser session) is the pattern for any site that gates
  the apply target behind login; give it a site-specific `_open_and_fetch` and
  reuse the serialized-lock + provenance plumbing.

Do the other scrapers one at a time; LinkedIn is solved first and only.
