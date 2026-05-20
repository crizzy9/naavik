# Naavik · Site Scrapers Reference

> **Canonical reference** — graduated from `docs/plans/archive/33-0.2.0.07-site-scrapers.md` per `AGENTS.md` § Workflow step 4.
> **Status:** Active. This is the single source for per-source URL patterns, rate-limit overrides, `external_id` derivation, and the parse contract every site scraper inherits from `_BaseSiteScraper`.
> **Last updated:** 2026-05-20 (plan 43 / `0.2.0.07a` — § D.6 `_make_url` slug-validate helper documented; § E.1–§ E.4 per-scraper notes added; closes PR #102 hacker MEDIUM × 2 / Issue #103).
> Earlier line: 2026-05-19 (plan 38 / `0.2.0.13` — § E LinkedIn rpm `1` → `0.4` (int→float fold); § E.4 Indeed adapter column added + cross-ref to `SCRAPER_BASE.md § G`; § H notes the new `scraper_rate_limits` Settings column).
> **Companion docs:** `docs/design/SCRAPER_BASE.md` (substrate; `_BaseSiteScraper` extends `ScraperBase`), `docs/design/JOB_MODEL.md` (`RawJob → Job` upsert contract), `docs/design/research/LINKEDIN_SCRAPING.md` (LinkedIn-specific blueprint that this doc locks).
> **Downstream plans depending on this contract:** `0.2.0.08` (AI extraction wires into `_maybe_enrich`), `0.2.0.10` (APScheduler cron registers per-source from `scrapers` registry), `0.2.0.11` (Discover UI surfaces persisted Jobs), `0.2.0.13` (per-source rate-limit tuning via Settings).

---

## A · One-paragraph contract

Each per-source scraper is a `_BaseSiteScraper` subclass that composes URLs from a `ScrapeQuery` (plus optional `Settings.{source}_companies` env-loaded lists), validates every URL via `is_safe_destination` before fetching via `Crawl4AIClient`, parses listing-card HTML or JSON-API responses into seed `RawJob` instances, fetches detail HTML, calls `self._maybe_enrich(raw_job)` (no-op until `0.2.0.08` lands the LLM service), and yields the enriched `RawJob` to `scraper_service.run_scraper`. Six production sources live in `src/scraper/sites/`: LinkedIn (guest API + Crawl4AI stealth), Workday (per-tenant), Greenhouse / Lever / Ashby (JSON-API ATS adapters), Indeed (anti-bot HTML). `SampleScraper` stays a test fixture and is NEVER registered in `scrapers` for production dispatch.

---

## B · Layering

```
src/scraper/sites/
├── __init__.py            # scrapers: dict[JobSource.value → type[ScraperBase]]
├── _base_site.py          # _BaseSiteScraper(ScraperBase) — adds _maybe_enrich shim
├── sample.py              # SampleScraper — NOT registered
├── linkedin.py
├── workday.py
├── greenhouse.py
├── lever.py
├── ashby.py
└── indeed.py

src/scraper/url_guard.py   # is_safe_destination(url) — userinfo + RFC1918 + IMDS + link-local guard
```

`_BaseSiteScraper` is the inheritance root for every site scraper. `ScraperBase` (the substrate) stays minimal — substrate tests do not transitively import the service layer. The lazy import of `services.job_extractor` inside `_maybe_enrich` is what lets `0.2.0.07` ship before `0.2.0.08`: until the service module exists, `ImportError` is caught + the helper short-circuits to identity.

---

## C · `_BaseSiteScraper` surface

File: `src/scraper/sites/_base_site.py`.

```python
class _BaseSiteScraper(ScraperBase):
    async def _maybe_enrich(self, raw_job: RawJob) -> RawJob:
        if self._provider is None or self._session is None or self._user_id is None:
            return raw_job
        try:
            from services.job_extractor import enrich_raw_job  # lazy: 0.2.0.08
        except ImportError:
            return raw_job
        try:
            return await enrich_raw_job(
                session=self._session,
                user_id=self._user_id,
                provider=self._provider,
                raw_job=raw_job,
            )
        except Exception as exc:
            self._errors.append(
                f"stage=extract url={safe_url(raw_job.source_url)} "
                f"kind=extract_failure msg={safe_exc(exc)}"
            )
            return raw_job
```

`ScraperBase.__init__` accepts `session: AsyncSession | None`, `user_id: int | None`, `provider: LLMProvider | None` (all optional with `None` defaults). The shim's three-way None check is what pre-`0.2.0.08` callers depend on; when the caller (cron orchestrator from `0.2.0.10`, Discover UI from `0.2.0.11`) wires all three, extraction activates automatically.

---

## D · URL guard

File: `src/scraper/url_guard.py`. Closes the 0.2.0.06b forward refs.

`is_safe_destination(url: str) -> tuple[bool, str | None]` returns `(True, None)` on safe URLs; `(False, "<reason>")` on rejected. Five rejection classes:

1. `unparseable_url` — `urlsplit` raised `ValueError`.
2. `scheme_not_allowed:<scheme>` — non-http(s) scheme. Mirrors `Crawl4AIClient`'s `HttpUrl` validation.
3. `userinfo_present` — `https://user:pass@host/...` form rejected before DNS resolution.
4. `invalid_host` — empty hostname.
5. `private_destination:<ip>` — DNS resolved into RFC1918 / IMDS (169.254.0.0/16) / link-local / loopback / `0.0.0.0/8` / IPv6 ULA-or-link-local. Loopback (`localhost` / `127.0.0.1` / `::1`) is allowed when `Settings.debug=True` for dev orchestrator parity.
6. `dns_resolution_failed` — `socket.getaddrinfo` raised; refuse rather than accept.

DNS resolution is `lru_cache(maxsize=256)`. Cron-driven scraping at ~100 listings/hour aggregate doesn't approach cache pressure. Tests stub `_resolve_host` so no real DNS hits.

The guard is called twice on every URL:

- At URL-composition time inside each subclass (rejection logs + skips the listing).
- At `Crawl4AIClient.fetch_html` / `stream_many` boundary (defense-in-depth; a future scraper that forgets to call the guard still gets blocked).

### D.6 `_make_url(template, **slugs)` helper

Plan 43 (`0.2.0.07a`) — closes PR #102 hacker MEDIUM × 2. Slug-validates every operator-supplied URL component (`tenant`, `site`, `company`) BEFORE template substitution. Single chokepoint in `src/scraper/url_guard.py`; per-site wrapper `_BaseSiteScraper._compose_url(template, *, stage="list", **slugs) -> str | None` owns error-append + redaction.

```python
_SLUG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


class InvalidSlugError(ValueError):
    """Raised by `_make_url` when a slug fails `_SLUG_RE`.

    Subclass of `ValueError` for broad-except composition. Carries
    `slug_name` + `value` for log redaction.
    """


def _make_url(template: str, **slugs: str) -> str:
    """Format `template` with slug-validated kwargs.

    Each kwarg matched against `_SLUG_RE` BEFORE substitution; first
    failure raises `InvalidSlugError(slug_name, value)`. Composes with
    `is_safe_destination` — both chokepoints run.
    """
```

**Why one layer up:** `is_safe_destination` runs AFTER URL composition. `tenant="evil.com#"` confuses `urlsplit.hostname` (returns `evil.com`) so the post-composition guard accepts it; the URL never should have composed in the first place. The slug regex closes the composition-bug attack vector; `is_safe_destination` closes the DNS-resolution one. Both layers compose.

**Per-scraper applicability matrix:**

| Scraper | Slug substitution in templates? | `_compose_url` call site | Notes |
|---|---|---|---|
| **Workday** | Yes — `tenant` + `site` | `scrape()` for `_LIST_TEMPLATE` | `_parse_tenant_spec` strips whitespace; `_make_url` rejects fragment / `@` / `/` |
| **Greenhouse** | Yes — `company` | `scrape()` for `_LIST_TEMPLATE` | `_row_detail_url` keeps bare `.format(job_id=...)` — `company` validated one frame up; `job_id` is vendor-trusted |
| **Lever** | Yes — `company` (path position; most dangerous) | `scrape()` for `_LIST_TEMPLATE` | `hostedUrl` (vendor-supplied) stays under `is_safe_destination` only |
| **Ashby** | Yes — `company` | `scrape()` for `_LIST_TEMPLATE` | `jobUrl` (vendor-supplied) stays under `is_safe_destination` only |
| **LinkedIn** | No — `keywords` / `location` use `quote_plus` (query-param shape) | Not called | RSShub fallback uses env-only `Settings.linkedin_*` + `scraper_rsshub_url` — operator-trust boundary |
| **Indeed** | No — `q` / `l` use `quote_plus`; `jk` is vendor-extracted | Not called | Same operator-trust boundary as LinkedIn for query params |

**Slug regex rationale.** Accepts `[a-zA-Z0-9_-]+` with alphanumeric leading char. Rejects all confusable shapes catalogued in plan 43 § D.1: `""` (empty), `"-leading"` / `"_leading"`, `"evil.com#"` (fragment), `"evil.com?"` (query), `"evil.com&for=victim"` (separator injection), `"evil.com@spoof"` (userinfo smuggle), `"acme/../v0/users/{id}"` (path traversal), `"a b"` (whitespace), `"\x00"` (null), `"\n"` (newline), `"x.y"` (dot — vendor slugs don't use), `"https://x"` (URL as slug). No per-vendor relaxation in this row; if a real-world Workday tenant or ATS company fails (e.g. a `.` in the slug), file a follow-up row with carve-out scope.

---

## E · Per-source reference table

All `rate_limit_per_minute` values below are the class-attr fallbacks; operators tune per source via `Settings.scraper_rate_limits` per `SCRAPER_BASE.md § G.1`. All sources ship with `use_undetected_adapter = False`; engagement on Indeed (and possibly LinkedIn) deferred to `0.2.0.13c` per `SCRAPER_BASE.md § G.6`.

| Source | source / board enum | Listing URL | Detail URL | `external_id` rule | rate_limit_per_minute | random_delay_seconds | adapter |
|---|---|---|---|---|---|---|---|
| **LinkedIn** | `LINKEDIN` / `LINKEDIN` | `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={kw}&location={loc}&start=0&f_TPR=r604800` | `https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}` | `urn:li:jobPosting:(\d+)` from card; `/jobs/view/(\d+)` fallback | **0.4** (effective <=24/hr; plan 38 § D.8 int→float fold) | `(3.0, 7.0)` | stealth |
| **Workday** | `WORKDAY` / `WORKDAY` | `https://{tenant}.wd1.myworkdayjobs.com/{site}` | `https://{tenant}.wd1.myworkdayjobs.com/{site}/job/{loc}/{title}_{R-XXXXXX}` | `/job/[^/]+/[^/]+_([A-Z]+[-_]?\d+)` from URL path | **2** | `(20.0, 40.0)` | stealth |
| **Greenhouse** | `GREENHOUSE` / `GREENHOUSE` | `https://boards.greenhouse.io/embed/job_board?for={company}&format=json` (JSON-API) | `https://boards.greenhouse.io/{company}/jobs/{id}` (HTML) | `str(row["id"])` | **20** | `(1.5, 3.0)` | stealth |
| **Lever** | `LEVER` / `LEVER` | `https://api.lever.co/v0/postings/{company}?mode=json` (JSON-API) | `row["hostedUrl"]` (inlined in JSON) | `row["id"]` (UUID) | **20** | `(1.5, 3.0)` | stealth |
| **Ashby** | `ASHBY` / `ASHBY` | `https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true` | `row["jobUrl"]` (inlined) | `row["id"]` (UUID) | **20** | `(1.5, 3.0)` | stealth |
| **Indeed** | `INDEED` / `INDEED` | `https://www.indeed.com/jobs?q={kw}&l={loc}` | `https://www.indeed.com/viewjob?jk={jk}` | `data-jk` attr; `[?&]jk=([a-f0-9]+)` fallback | **2** | `(20.0, 40.0)` | stealth (undetected pending `0.2.0.13c`) |

### E.1 LinkedIn

Per `docs/design/research/LINKEDIN_SCRAPING.md § 5` (Option B — direct guest API + Crawl4AI stealth). Conservative defaults: effective ~24 listings / hour ceiling. RSShub fallback activates ONLY when `Settings.scraper_rsshub_url` is set AND the guest-API call returns zero cards. Cookie-based auth (`Settings.linkedin_session_cookie`) is deferred to Phase 5 task 5.12 — research § 5 Trade-off accepted.

No operator-controlled slug substitution in URL templates (`_LIST_BASE` / `_DETAIL_BASE` / `_FALLBACK_VIEW_BASE` are constants); `keywords` + `location` are `quote_plus`'d query params — structural protection. RSShub fallback inherits the env-only operator-trust boundary for `scraper_rsshub_url` + `Settings.linkedin_*`.

### E.2 Workday

Per-tenant. `Settings.workday_companies: list[str] | None` parsed as CSV from `WORKDAY_COMPANIES` env var; each entry is `"tenant/site"` (e.g. `"salesforce/External"`) or `"tenant"` (site defaults to `"External"`). Cron skips silently when the list is unset.

Plan 43 (`0.2.0.07a`): both `tenant` and `site` are slug-validated (`^[a-zA-Z0-9][a-zA-Z0-9_-]*$`) BEFORE template substitution; entries with `.`, `#`, `?`, `&`, `@`, `/`, whitespace, or control chars are skipped with a `kind=invalid_slug` error append.

### E.3 Greenhouse / Lever / Ashby

Three near-identical JSON-API scrapers. Each reads `Settings.{ats}_companies: list[str] | None` (CSV-parsed) when `ScrapeQuery.company_filter` is empty. Per-company JSON-API endpoint returns a flat array; iterate, build seed `RawJob`, optionally re-fetch the detail HTML for richer description (Lever / Ashby inline description in JSON; Greenhouse needs a second fetch).

Plan 43 (`0.2.0.07a`): `{company}` is slug-validated BEFORE template substitution. Lever's path-position substitution (`https://api.lever.co/v0/postings/{company}`) was the most dangerous variant per PR #102 (slash injection → vendor-API path traversal); slug regex rejects `/` and `.`. Greenhouse `_row_detail_url` keeps bare `.format(job_id=...)` since `company` is validated one stack frame up and `job_id` is vendor-trusted.

### E.4 Indeed

Aggressively anti-bot (Cloudflare WAF + fingerprinting). Crawl4AI `enable_stealth=True` is the front-line defense. Conservative 2/min cap + 20-40s jitter. Plan 38 shipped the `UndetectedAdapter` wiring + telemetry — `IndeedScraper.use_undetected_adapter` stays `False` here; engagement deferred to `0.2.0.13c` after the cron observes real-world 403-rate exceeding ~5% (operator-visible via `JobScrapeRun.raw_meta["rate_limit"]["hits"]` per `SCRAPER_BASE.md § G.7`).

No operator-controlled slug substitution in URL templates; `q` / `l` are `quote_plus`'d query params and `jk` is vendor-extracted from card HTML. Same operator-trust posture as LinkedIn.

---

## F · Registry

`src/scraper/sites/__init__.py`:

```python
scrapers: dict[str, type[ScraperBase]] = {
    JobSource.LINKEDIN.value: LinkedInScraper,
    JobSource.WORKDAY.value: WorkdayScraper,
    JobSource.GREENHOUSE.value: GreenhouseScraper,
    JobSource.LEVER.value: LeverScraper,
    JobSource.ASHBY.value: AshbyScraper,
    JobSource.INDEED.value: IndeedScraper,
}
```

Keyed by `JobSource.value` (the string, lowercase). APScheduler (`0.2.0.10`) reads job IDs from a Postgres job-store; string keys serialize cleanly. `+ Add by URL` dispatch (Phase 6) parses the host out of a URL + maps to a source string via `scraper_service.dispatch_by_url(url)`. The enum is recoverable via `JobSource(scraper_key)` when callers need it.

`SampleScraper` is deliberately absent. Production dispatch must never invoke it.

---

## G · Test strategy

Per-source tests live at `tests/test_scraper_sites/test_<source>.py` (~5-7 tests each). Each suite uses the `FakeClient` helper from `tests/test_scraper_sites/_helpers.py` to stand in for `Crawl4AIClient` — keyed responses by URL prefix. DNS resolution is monkeypatched to return public-looking IPs so the URL guard returns `(True, None)` for non-hostile hosts.

HTML / JSON fixtures live at `tests/fixtures/html/sites/` — hand-crafted (NOT scrubbed-from-live) per plan 33 OQ.3. Fictional companies + fictional URL hosts; structurally accurate to the real DOM as observed 2026-05-19.

Lint guards:
- `tests/test_no_direct_http_imports.py` — rejects `requests` / `httpx` / `urllib.request` / `aiohttp` inside `src/scraper/`.
- `tests/test_scraper_sites/test_registry.py` — confirms the six registered sources + SampleScraper exclusion.
- `tests/test_scraper_sites/test_url_guard.py` — exercises all five rejection classes plus the `Settings.debug` escape hatch + plan 43 § D.6 `_make_url` slug-validate acceptance + rejection matrix.
- `tests/test_scraper_sites/test_base_site.py` — exercises the four-way `_maybe_enrich` decision tree + plan 43 `_compose_url` wrapper (None on hostile / URL on valid / control-char redaction).
- `tests/test_scraper_sites/test_{workday,greenhouse,lever,ashby}.py` — integration tests verify PR #102 attack payloads compose no URL + perform no outbound fetch (`client.fetch_calls == []`).

---

## H · Settings env-var slots + DB-backed dials

All optional. Cron skips a source silently when its company list is unset.

| Env var | Type | Purpose |
|---|---|---|
| `GREENHOUSE_COMPANIES` | CSV → `list[str]` | Greenhouse `{company}` slugs (one per company embed board) |
| `LEVER_COMPANIES` | CSV → `list[str]` | Lever postings-API company slugs |
| `ASHBY_COMPANIES` | CSV → `list[str]` | Ashby posting-API company slugs |
| `WORKDAY_COMPANIES` | CSV → `list[str]` | Workday tenants in `"tenant"` or `"tenant/site"` form |
| `SCRAPER_RSSHUB_URL` | str / URL | Opt-in LinkedIn RSShub fallback base URL |

Per `AGENTS.md § Key Conventions § CLI` — these are env-loaded via `pydantic-settings` in `src/config.py:Settings` (post-vault, post-CLI sunset pattern). No new `naavik` subcommand, no vault scope.

Plan 38 (`0.2.0.13`) added a DB-backed dial: `Settings.scraper_rate_limits: dict[str, dict[str, float]]` (JSONB) keyed by `JobSource.value` with nested `{"rpm", "delay_lo", "delay_hi"}` shape. Operator tunes per source via Settings · Sources UI (Phase 6+); empty `{}` (default) → class-attr fallback per `SCRAPER_BASE.md § G.1`. No new env var — DB column is the per-user knob.

---

## I · Sunset compliance

- No new `naavik` CLI subcommand. ✅
- No `src/services/vault.py` extension. ✅
- No AES-GCM / PBKDF2 / audit-log code. ✅
- Five new env-var slots (`SCRAPER_RSSHUB_URL`, `WORKDAY_COMPANIES`, `GREENHOUSE_COMPANIES`, `LEVER_COMPANIES`, `ASHBY_COMPANIES`) follow the post-`0.2.0.01` env-based pattern via `pydantic-settings`. ✅
- No new on-disk artifact under `~/.naavik/` or `DATA_DIR`. ✅
- No new ports / schedules. ✅

---

## J · Cross-references

- `docs/design/SCRAPER_BASE.md` § C, § E, § F, § H — substrate this doc extends.
- `docs/design/JOB_MODEL.md` § F.1 — `upsert_job` contract that `scraper_service` consumes.
- `docs/design/research/LINKEDIN_SCRAPING.md` § 5 — locked into Option B by this doc.
- `docs/design/BACKEND.md § J.2` — pipeline overview; per-source modules table points here.
- `ROADMAP.md` row `0.2.0.07` — implementation tracking.
