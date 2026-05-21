# Naavik · Scraper Base Contract

> **Canonical reference** — graduated from `docs/plans/archive/29-0.2.0.06-crawl4ai-base.md` per `AGENTS.md` § Workflow step 4.
> **Status:** Active. This is the single source for the `ScraperBase` ABC, the `RawJob` Pydantic DTO, the `Crawl4AIClient` wrapper, the `scraper_service.run_scraper` lifecycle, the rate-limit + anti-detection contract, and the two-tier error model.
> **Last updated:** 2026-05-19 (plan 38 / `0.2.0.13` — rate limiting + anti-detection graduated: § G replaces the "interface only" stub with G.1–G.12 — operator-tunable `Settings.scraper_rate_limits`, `crawl4ai.RateLimiter` integration for 429/503 backoff, curated 8-UA round-robin pool, `UndetectedAdapter` wiring + telemetry deferred to `0.2.0.13c`, robots.txt explicit no-honor policy, `cachetools.TTLCache` DNS-rebind fix folding 0.2.0.13a, `JobScrapeRun.raw_meta` telemetry. `ScraperBase.rate_limit_per_minute: int → float`).
> **Companion docs:** `docs/design/JOB_MODEL.md` (locked input for `RawJob → Job` mapping via `job_service.upsert_job`), `docs/design/BACKEND.md` § J (pipeline overview), `docs/design/research/LINKEDIN_SCRAPING.md` (source-specific blueprint that will subclass `ScraperBase` in `0.2.0.07`), `docs/ARCHITECTURE.md` § 3.8 (scraper layer rules).
> **Downstream plans depending on this contract:** `0.2.0.07` (per-source site scrapers), `0.2.0.08` (AI extraction), `0.2.0.09` (dedup), `0.2.0.10` (APScheduler), `0.2.0.11` (Discover UI), `0.2.0.12` (notifications), `0.2.0.13` (rate limiting + anti-detection), `0.2.0.14` (n8n migration).

---

## A · One-paragraph contract

A `ScraperBase` is the abstract surface every site scraper inherits. Subclasses declare `source` + `board` (which `JobSource` they emit + which `ApplicationBoard` ATS adapter the resulting `Job` routes to), optionally override `rate_limit_per_minute` + `random_delay_seconds`, and implement `async def scrape(query) -> AsyncIterator[RawJob]` as an async generator yielding `RawJob` instances. Per-listing errors append to `self._errors` and continue; scraper-fatal errors raise to `scraper_service.run_scraper`, which opens a `JobScrapeRun` row at `RUNNING`, calls `job_service.upsert_job(...)` per yield, and finalizes the row with status (`SUCCESS` / `PARTIAL` / `FAILED` / `TIMED_OUT`) + counters + errors. The boundary DTO `RawJob` is a 17-field Pydantic v2 model with `extra="forbid"`; scrapers fill what they know from source HTML, and AI extraction (`0.2.0.08`) overwrites `*_hint` enum values from authoritative reads of the JD body.

---

## B · Layering — where this lives

```
src/scraper/
├── __init__.py                    # re-exports RawJob / ScrapeQuery / ScraperBase / Crawl4AIClient
├── types.py                       # RawJob + ScrapeQuery (boundary DTOs)
├── base.py                        # ScraperBase ABC (the contract every site scraper inherits)
├── crawl4ai_client.py             # Crawl4AIClient wrapper around AsyncWebCrawler
└── sites/
    ├── __init__.py                # scrapers: dict[str, type[ScraperBase]] = {} — populated by 0.2.0.07
    ├── sample.py                  # SampleScraper test fixture (NOT for production)
    ├── linkedin.py                # 0.2.0.07 (per docs/design/research/LINKEDIN_SCRAPING.md)
    ├── workday.py                 # 0.2.0.07
    ├── greenhouse.py              # 0.2.0.07
    ├── lever.py                   # 0.2.0.07
    ├── ashby.py                   # 0.2.0.07
    └── indeed.py                  # 0.2.0.07

src/services/
└── scraper_service.py             # run_scraper(scraper) — opens JobScrapeRun, streams + persists
```

Scraper code never touches the DB. `scraper_service.run_scraper` is the only writer; it consumes the streaming generator and calls `job_service.upsert_job` + `job_service.record_scrape_run`.

---

## C · `ScraperBase` ABC reference

File: `src/scraper/base.py`. Matches `src/llm/base.py:LLMProvider(ABC)` convention.

### C.1 Surface

```python
class ScraperBase(ABC):
    # Subclass-declared
    source: JobSource           # which JobSource enum value this scraper emits
    board: ApplicationBoard     # which ATS adapter the resulting Jobs route to

    # Rate-limit hooks (plan 38 § D.8 promoted int → float so LinkedIn's
    # 0.4 rpm no longer floors to 1). Operators tune per-source via
    # Settings.scraper_rate_limits (§ G.1); class attrs are the fallback.
    rate_limit_per_minute: float = 30.0
    random_delay_seconds: tuple[float, float] = (1.0, 3.0)

    # UndetectedAdapter engagement toggle; default False — engagement
    # deferred to 0.2.0.13c follow-up (§ G.6).
    use_undetected_adapter: bool = False

    def __init__(
        self,
        *,
        client: Crawl4AIClient | None = None,
        session: AsyncSession | None = None,
        user_id: int | None = None,
        provider: LLMProvider | None = None,
    ) -> None: ...

    @property
    def name(self) -> str: ...

    @abstractmethod
    async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]: ...
```

### C.2 Subclass contract

- **MUST set** `source` + `board` class attributes (e.g. `source = JobSource.LINKEDIN`; `board = ApplicationBoard.LINKEDIN`).
- **MUST implement** `async def scrape(query) -> AsyncIterator[RawJob]` as an async generator (`async def` + `yield`).
- **MAY override** `rate_limit_per_minute` (`float`) + `random_delay_seconds` for source-specific tuning. Operator overrides via `Settings.scraper_rate_limits` (per § G.1) win over the class-attr defaults.
- **MAY override** `use_undetected_adapter: bool = False` for sources where stealth-mode alone is insufficient (no source ships with this `True` today; engagement deferred to `0.2.0.13c` per § G.6).
- **MAY override** `__init__` if the subclass needs source-specific config (LinkedIn cookies, Workday company list, etc.); should call `super().__init__(client=...)` so the rate-limit + error-buffer wiring stays consistent.
- **SHOULD honor** `query.max_listings` as an upper bound on yields per invocation.
- **SHOULD catch** per-listing errors, append to `self._errors`, and continue iterating. The service layer aggregates the buffer into `JobScrapeRun.errors[]` post-stream.
- **MUST raise** on a total scraper failure (auth invalid, DNS unrecoverable, target site fully down) so the service layer marks the run `FAILED`.

### C.3 Why ABC over Protocol / free-function

Locked in plan 29 § D.1. Three options compared:

| Aspect | ABC (chosen) | Protocol | Free-function |
|---|---|---|---|
| `@abstractmethod` enforcement at class creation | ✅ catches "I forgot `scrape()`" at instantiation time | ❌ catches only at `isinstance()` check | ❌ no structural enforcement |
| Convention parity with `src/llm/base.py:LLMProvider(ABC)` | ✅ same pattern | ⚠ diverges | ❌ diverges |
| Per-instance state (`_errors`, `_client`, `requests_made` counter) | ✅ natural instance attrs | ✅ but requires shared interface | ❌ forces global / context dict |

Refactor cost B / C → A: mechanical search-replace if six site scrapers ship and we want to consolidate. Chose ABC up-front; six subclasses incoming.

---

## D · `RawJob` field reference

File: `src/scraper/types.py`. Pydantic v2 BaseModel, `extra="forbid"`, `str_strip_whitespace=True`.

### D.1 The 17 fields

| Field | Type | Required? | Maps to `Job` field | Filled by scraper? | Refined by AI (`0.2.0.08`)? |
|---|---|---|---|---|---|
| `source` | `JobSource` | YES | `Job.source` | YES (via class attr) | NO |
| `external_id` | `str` (min_length=1) | YES | `Job.external_id` | YES — per-source stable id (LinkedIn `job_id`; Greenhouse `gh_jid`; Lever `posting_id`) | NO |
| `source_url` | `str` (min_length=1) | YES | `Job.url` | YES — canonical URL | NO |
| `board` | `ApplicationBoard` | YES | `Job.board` | YES (via class attr) | NO |
| `url_type` | `str` (default `"external"`) | YES | `Job.url_type` | YES — per-scraper convention (`"ats"` / `"company_direct"` / `"rss"` / `"manual"` / `"external"`) | NO |
| `company_name` | `str` (min_length=1) | YES | `Job.company` | YES | YES — AI normalizes ("Anthropic, PBC" → "Anthropic") |
| `position_title` | `str` (min_length=1) | YES | `Job.role` | YES | YES — AI normalizes ("Sr. SWE - Eng I" → "Senior Software Engineer") |
| `location_raw` | `str \| None` | NO | (input to `Job.location`; AI parses) | YES if scraped | YES — AI maps to "City, State" / "Remote" |
| `description_html` | `str \| None` | NO (but recommended) | `Job.description_html` | YES — from detail fetch | NO (preserved verbatim for re-extraction) |
| `description_text` | `str \| None` | NO | (input to `Job.description`; AI normalizes) | YES if scraper can strip | YES |
| `posted_at_text` | `str \| None` | NO | `Job.posted_at_text` | YES — diagnostics | NO (preserved) |
| `posted_at` | `datetime \| None` | NO | `Job.posted_at` | OPTIONAL — only if scraper parses cleanly | YES — AI normalizes from `posted_at_text` |
| `salary_raw` | `str \| None` | NO | (input to `Job.salary_min/max`; AI parses) | YES if scraped | YES |
| `remote_policy_hint` | `RemotePolicy \| None` | NO | `Job.remote_policy` | OPTIONAL — only when source is unambiguous | YES — AI extracts from description if absent or contradicts |
| `visa_restriction_hint` | `VisaRestriction \| None` | NO | `Job.visa_restrictions` | OPTIONAL — rarely available pre-extraction | YES — AI infers from description |
| `seniority_level_hint` | `SeniorityLevel \| None` | NO | `Job.seniority_level` | OPTIONAL — derivable from title regex sometimes | YES — AI extracts from title + description |
| `raw_meta` | `dict[str, Any]` (default `{}`) | NO | `Job.raw_meta` (merge) | YES — scraper-specific extras | NO (preserved, merged on upsert) |

### D.2 Why `*_hint` enum suffix

Plan 29 § D.13. Three options considered:

- **Structured enum field without suffix** (`RawJob.remote_policy: RemotePolicy`) — rejected. Scrapers that *guess* (LinkedIn listing card shows `"Remote · Hybrid · On-site"` and the scraper picks one) would overwrite AI extraction's later authoritative read.
- **Free-form strings** (`RawJob.remote_policy_hint: str | None`) — rejected. Forces AI to normalize `"hybrid"` / `"Hybrid"` / `"3 days in office"`.
- **Typed enum hints** (chosen) — same enum type as `Job` field; nullable; semantically "scraper's best guess; AI may override". `0.2.0.08` writes the final `Job.remote_policy` from the JD body; the hint is diagnostic-only after extraction lands.

### D.3 `extra="forbid"` rationale

Pydantic v2's `extra="forbid"` raises `ValidationError` at construction time on unknown fields. Two consequences:

1. **Scraper authors can't pass fields that don't map to `Job` silently.** Adding a new structured field forces an explicit `RawJob` schema update + matching `Job` field mapping.
2. **`raw_meta` is the only escape hatch.** Source-specific extras (`{"linkedin_apply_url": "..."}`, `{"workday_req_id": "..."}`) go in `raw_meta` JSONB. Soft cap `< 4KB` per RawJob — runaway growth is a Phase 6 monitoring concern, not a `0.2.0.06` blocker.

### D.4 `RawJob.to_upsert_payload()` is the hand-off shape

`scraper_service.run_scraper` calls `job_service.upsert_job(... raw=raw_job.to_upsert_payload())`. The adapter exists because `RawJob` field names don't all match `Job` column names — `source_url`, `company_name`, `position_title`, `location_raw`, `description_text`, and the `*_hint` enum trio are scraper-side names that map onto `Job.url` / `Job.company` / `Job.role` / `Job.location` / `Job.description` / `Job.remote_policy` / `Job.visa_restrictions` / `Job.seniority_level` per `JOB_MODEL.md § F.1`'s required-keys contract. A bare `model_dump(exclude_unset=True)` would emit `RawJob`-shape keys, every one of which `_create_payload` silently drops (it filters against `_JOB_CREATE_FIELDS` keyed by `Job` column names), leaving the constructed `Job(...)` missing NOT-NULL fields. Postgres catches this on insert; the in-memory test session does not, so the bug only surfaces under live DB. `to_upsert_payload()` does the rename explicitly: hints fill the corresponding `Job` enum columns (and AI extraction in `0.2.0.08` overwrites with authoritative reads), `salary_raw` lands under `raw_meta` for the same AI step to parse, and `_create_payload` supplies typed defaults (`RemotePolicy.UNKNOWN`, `VisaRestriction.NOT_MENTIONED`, etc.) for whatever the hint trio didn't fill.

---

## E · `Crawl4AIClient` reference

File: `src/scraper/crawl4ai_client.py`. Wraps Crawl4AI's `AsyncWebCrawler`. Matches `src/llm/anthropic.py:AnthropicProvider` wrap-the-SDK convention so test injection points exist and Crawl4AI upgrades land in one place.

### E.1 Surface

```python
class Crawl4AIClient:
    def __init__(
        self,
        *,
        enable_stealth: bool = True,
        headless: bool = True,
        page_timeout_ms: int = 30_000,
        rate_limit_per_minute: float = 30.0,
        random_delay_seconds: tuple[float, float] = (1.0, 3.0),
        user_agent: str | None = None,
        use_undetected_adapter: bool = False,
    ) -> None: ...

    async def fetch_html(self, url: str) -> str | None:
        """Fetch one URL; return HTML on success, None on non-fatal failure.

        URL validates through `pydantic.HttpUrl` (rejects file/ftp/gopher/
        data/javascript schemes) before invoking Crawl4AI. Per plan 31 D.1.
        """

    async def stream_many(self, urls: list[str]) -> AsyncIterator[tuple[str, str | None]]:
        """Fetch many URLs concurrently; yield (url, html|None) per result."""
```

### E.2 Why a wrapper class (not direct import)

Plan 29 § D.4 Option B vs A vs C:

- **Direct import** in `ScraperBase` — rejected. Six site scrapers would each patch any Crawl4AI breaking change. Crawl4AI's 0.7 → 0.8 rename (`proxy` → `proxy_config`) is the canonical cautionary example.
- **Wrapper class** (chosen) — Crawl4AI breaks land in `crawl4ai_client.py` only; scrapers + tests untouched. Matches `AnthropicProvider`/`OpenAIProvider`/`OllamaProvider` wrap-the-SDK pattern.
- **Hexagonal `IBrowser` protocol** — rejected (YAGNI). Right answer eventually when a second `IBrowser` impl ships (Playwright generic scraper, debug-mode headless-off). Refactor cost when needed: search-replace ~5 method-call sites.

### E.3 `enable_stealth=True` default

Confirmed via Crawl4AI 0.8.6 `BrowserConfig` signature (`enable_stealth: bool = False` in the upstream default; we flip to `True` at our wrapper layer). Patches `navigator.webdriver`, modifies browser fingerprints, emulates realistic plugin behavior. First-line defense against Cloudflare / WAF challenges per `docs/design/research/LINKEDIN_SCRAPING.md` § 6 risk #3. `UndetectedAdapter` is a separate, more advanced feature reserved for `0.2.0.13` (rate limiting + anti-detection) if measured 403-rate exceeds threshold.

### E.4 Rate-limit math

Plan 38 split the rate-limit surface across two layers — see § G.2 + G.3 for the full contract:

- `_enforce_min_interval()` (renamed from `_respect_rate_limit` in plan 38): per-process token-bucket + jitter, fires before every `arun` in `fetch_html`. `min_interval = 60.0 / max(0.1, rate_limit_per_minute)`. The `max(0.1, ...)` floor caps wait time at 600s so a misconfigured Settings entry can't deadlock the cron.
- `crawl4ai.RateLimiter(...)` (constructed in `__init__`, threaded into `MemoryAdaptiveDispatcher(rate_limiter=...)` in `stream_many`): exponential backoff on 429 / 503. `base_delay=random_delay_seconds`, `max_delay=60.0`, `max_retries=2`, `rate_limit_codes=[429, 503]`.

Per-process; no shared state across workers. Source-specific tuning lives in `Settings.scraper_rate_limits` per § G.1; class-attr fallbacks per `_CLASS_ATTR_FALLBACK`.

### E.5 `CrawlerRunConfig.clone(stream=True)` (deviation from plan)

Plan 29 § D.4 sample code used `self._run_config.model_copy(update={"stream": True})`. Reality on shipped wheel: Crawl4AI 0.8.6's `CrawlerRunConfig` is a plain class (not Pydantic), so `model_copy` does not exist. The supported API is `CrawlerRunConfig.clone(**kwargs)`. `Crawl4AIClient.stream_many` uses `.clone(stream=True)`. Site scrapers in `0.2.0.07` that copy this pattern should call `.clone()` too.

---

## F · `scraper_service.run_scraper` lifecycle

File: `src/services/scraper_service.py`.

```python
async def run_scraper(
    session: AsyncSession,
    *,
    scraper: ScraperBase,
    user_id: int,
    query: ScrapeQuery | None = None,
    triggered_by: str = "manual",
) -> JobScrapeRun: ...
```

### F.1 Sequence

1. **Open the run.** `job_service.record_scrape_run(... status=RUNNING, triggered_by, raw_meta={"scraper_name": scraper.name, "query": query.model_dump()})` writes a JobScrapeRun row + returns it.
2. **Stream RawJobs.** `async for raw_job in scraper.scrape(query):`
   - `listings_returned += 1`
   - Try `job_service.upsert_job(session, user_id, source=raw_job.source, external_id=raw_job.external_id, raw=raw_job.to_upsert_payload(), scrape_run_id=run.id)` (see § D.4 for the adapter rationale).
   - On `(_, True)` (created) → `new_jobs += 1`. On `(_, False)` (existing) → `updated_jobs += 1`.
   - On per-listing exception → append `stage=upsert url=<source_url> kind=upsert_failure msg=<exc>` to `errors`; continue.
3. **Drain scraper-internal errors.** Post-stream: `errors.extend(getattr(scraper, '_errors', []))` so per-listing errors collected during `scrape()` propagate to the run row.
4. **Derive status** (table below). Mutate `run.status` / `run.finished_at` / `run.duration_ms` / counters / errors in-place; `session.add(run)` + `session.flush()` in `finally`.

### F.2 Status derivation table

| Outcome | `JobScrapeRun.status` |
|---|---|
| Generator completes; `errors == []` | `SUCCESS` |
| Generator completes; `errors != []`; ≥1 RawJob yielded | `PARTIAL` |
| Generator completes; `errors != []`; 0 RawJobs yielded | `FAILED` |
| Generator raises; ≥1 RawJob already yielded | `PARTIAL` |
| Generator raises; 0 RawJobs yielded | `FAILED` |
| `asyncio.CancelledError` | `TIMED_OUT` (re-raised so scheduler reacts) |

### F.3 Caller responsibility

`run_scraper` calls `session.flush()` only — never `session.commit()`. Caller (APScheduler cron job in `0.2.0.10`, manual ops, test) commits at its boundary. This is the merged Naavik service-layer pattern; matches `job_service` per `JOB_MODEL.md § F`.

### F.4 Single JobScrapeRun row per invocation

`record_scrape_run` writes the row once at `status=RUNNING`. The `finally` block updates the same row in-place via `session.add(run)`. Rows are NOT append-only — one row per scraper invocation, transitioning through statuses.

---

## G · Rate limiting + anti-detection

Plan 38 / `0.2.0.13` graduated the rate-limit + anti-detection contract from "interface only" to fully wired. Six layered controls; operators tune the top layer via Settings, the rest stay in code.

### G.1 — Settings locus: `Settings.scraper_rate_limits`

Single JSONB column on `settings`, keyed by `JobSource.value`, nested per-source dict shape:

```json
{
  "linkedin": {"rpm": 0.4, "delay_lo": 3.0, "delay_hi": 7.0},
  "workday":  {"rpm": 2.0, "delay_lo": 20.0, "delay_hi": 40.0}
}
```

`scraper.rate_limit.RateLimitConfig` (Pydantic v2, `extra="forbid"`) validates each per-source entry. `scraper.rate_limit.resolve_rate_limit(settings, source)` returns the operator override when present + valid, else falls back to the class-attr defaults in `_CLASS_ATTR_FALLBACK`. Empty `{}` (post-migration default) → fallback. Misconfigured entry → log + fallback (never raise). Adding a new source = a new key, no migration.

Alembic 0008 `scraper_rate_limits JSONB NOT NULL DEFAULT '{}'`.

`Settings.scraper_proxy_url` (IP rotation; Phase 6+ per ROADMAP `0.2.3.03`) is NOT yet introduced — proxy support waits for that row.

### G.2 — Per-request pacing: `Crawl4AIClient._enforce_min_interval`

Per-process token-bucket with jitter, fires before every `arun` in `fetch_html`. `_min_interval_s = 60.0 / max(0.1, rate_limit_per_minute)`. `random.uniform(*random_delay_seconds)` jitter on top.

Why we keep this layer (rather than delegating entirely to Crawl4AI's `RateLimiter`): in 0.8.6, `AsyncWebCrawler.arun()` does not accept a `rate_limiter=` kwarg — only `MemoryAdaptiveDispatcher` does, and the dispatcher only fires inside `arun_many`. Sub-1-rpm sources (LinkedIn = 0.4 → 150s between requests) need the floor even on single-URL fetches.

### G.3 — 429 / 503 backoff: `crawl4ai.RateLimiter`

`Crawl4AIClient.__init__` constructs `RateLimiter(base_delay=random_delay_seconds, max_delay=60.0, max_retries=2, rate_limit_codes=[429, 503])` and threads it into `MemoryAdaptiveDispatcher(rate_limiter=...)` for `stream_many`. Crawl4AI's exponential backoff fires on 429 / 503 — base_delay × 2^attempt, capped at 60s, up to 2 retries.

Worst-case URL time = base + 2 × 60s. For LinkedIn at 0.4 rpm: 150s base + 120s retries = 270s, within the APScheduler `misfire_grace_time=300`.

### G.4 — User-Agent rotation: `scraper.user_agents.pick_user_agent`

Curated module-level tuple of 8 modern desktop UAs (Chrome / Firefox / Safari / Edge across Windows / macOS / Linux). Round-robin via module-level counter under a `threading.Lock`. `Crawl4AIClient.__init__` calls `pick_user_agent()` when `user_agent=None` (the default).

Per-firing rotation: scheduler constructs a fresh `Crawl4AIClient` per `_scrape_one_user` call; six firings in one sweep see six different UAs.

Pool refresh ~quarterly. `tests/test_user_agents.py` asserts a `# Last refreshed: YYYY-MM-DD` comment exists + is within 365 days (CI forcing function).

Mobile UAs deliberately excluded — LinkedIn / Indeed serve different HTML to mobile clients, which would diverge listing-card selectors.

### G.5 — Stealth: `BrowserConfig(enable_stealth=True)` (default)

Crawl4AI's `enable_stealth=True` patches `navigator.webdriver` + canvas / WebGL / plugin enumeration. Wrapper-level default; subclasses don't override.

### G.6 — `UndetectedAdapter` (engagement deferred to `0.2.0.13c`)

`ScraperBase.use_undetected_adapter: bool = False` is the class-attr toggle. `Crawl4AIClient(use_undetected_adapter=True)` routes via `AsyncWebCrawler(crawler_strategy=AsyncPlaywrightCrawlerStrategy(browser_config=..., browser_adapter=UndetectedAdapter()))`.

Plan 38 ships the wiring + telemetry only; no source flips the flag yet. The follow-up `0.2.0.13c` will engage UndetectedAdapter on Indeed (and possibly LinkedIn) after the cron observes real-world 403-rate exceeding ~5%. Engagement criterion: 403-rate over a 7-day rolling window.

### G.7 — Telemetry: `JobScrapeRun.raw_meta`

`scraper_service.run_scraper` writes two fields into `JobScrapeRun.raw_meta` in the `finally` block:

```json
{
  "rate_limit": {
    "hits": 2,
    "backoff_total_s": 4.5,
    "ua": "Mozilla/5.0 ... Chrome/130.0.0.0 ..."
  },
  "adapter_used": "stealth"
}
```

- `hits` — count of 429 / 503 responses during the run (incremented in `Crawl4AIClient.fetch_html` + `stream_many`).
- `backoff_total_s` — best-effort upper bound on time spent in retries (wall-clock of `stream_many` batches).
- `ua` — the UA string this `Crawl4AIClient` instance pinned.
- `adapter_used` — `"undetected"` if `scraper.use_undetected_adapter`, else `"stealth"`.

Operators surface this via the Discover UI's "View scrape run" detail page (`0.2.0.11`).

### G.8 — DNS-rebind defense: `cachetools.TTLCache`

`scraper.url_guard._DNS_CACHE` is a `cachetools.TTLCache(maxsize=256, ttl=60.0)`. Bounds the DNS-rebind TOCTOU window to ≤60s — a host that resolves to a public IP at URL-composition time can rebind to RFC1918 within 60s and the next `_resolve_host` call re-queries DNS.

Closes Issue #105 (`0.2.0.13a`). Single-process + single-asyncio-loop usage today; if multi-process workers ship in Phase 2+, add a `threading.Lock` around get/set.

### G.9 — Connection between layers

```
Settings.scraper_rate_limits  ──┐
                                │ resolve_rate_limit(settings, source)
                                ▼
                       RateLimitConfig(rpm, delay_lo, delay_hi)
                                │
                                ▼
                      Crawl4AIClient(
                          rate_limit_per_minute=rpm,
                          random_delay_seconds=(delay_lo, delay_hi),
                          use_undetected_adapter=scraper_cls.use_undetected_adapter,
                          user_agent=None,  # picks from pool
                      )
                                │
                ┌───────────────┴────────────────┐
                ▼                                ▼
       _enforce_min_interval()         RateLimiter(base_delay,
       (per-request floor)              max_delay=60, max_retries=2,
                                        rate_limit_codes=[429, 503])
                                                │
                                                ▼
                                MemoryAdaptiveDispatcher
                                (used by stream_many only)
```

### G.10 — `robots.txt` policy

Naavik does NOT honor `robots.txt`. Industry precedent for job-discovery tools (Crawlee `JobSpy`, `JobFunnel`, the legacy n8n LinkedIn workflow, Crawl4AI's own LinkedIn demo) is to skip it; LinkedIn / Workday / Indeed all `Disallow: /jobs` in their robots files, and honoring them would ship zero listings for three of six sources. Operating contract: CFAA + the research § 5 trade-off accepted at plan 33. If LinkedIn shifts posture toward unauthenticated-scraping suit, the architectural response is to swap to Phase 5 task 5.12's MCP-based authenticated session, not flip a robots flag.

### G.11 — IP rotation / proxy

LinkedIn-specific proxy support shipped in `0.2.7.11` (plan 64). Canonical reference: `docs/design/LINKEDIN_PROXY.md`. Single env var `LINKEDIN_PROXY_URL` (basic-auth-in-URL); `Crawl4AIClient(proxy_config=...)` threads it via `CrawlerRunConfig.proxy_config` per the Crawl4AI 0.8.6 contract. Sticky-per-`Crawl4AIClient`-instance (natural per-cron-firing window); FAIL LOUDLY on proxy failure (never degrade to direct — the silent-fallback-to-residential-IP path is what gets LinkedIn accounts banned). Multi-source proxy infra (Indeed / generic) is deferred to `0.8.0.NN`.

### G.12 — `consecutive_scrape_failures` interaction

Plan 38 § D.9: counter semantics unchanged from plan 35. SUCCESS / PARTIAL resets the counter regardless of cause (including RL-induced PARTIAL); FAILED increments. If operators want RL-specific alerting in the future, that's a `0.5.0.NN` observability row, not this layer.

---

## H · Error handling pattern (two tiers)

### H.1 Tier 1 — per-listing (recoverable; scrape continues)

The scraper subclass's `scrape()` catches per-URL parse failures, per-URL 429s, per-URL timeouts. Appends to `self._errors[]` and continues iterating.

Format: `"stage=<list|detail|extract> url=<...> kind=<rate_limit|captcha|timeout|parse_failure|other> msg=<...>"`. Per-listing errors do NOT raise.

```python
# Example in a future LinkedInScraper.scrape():
try:
    html = await self._client.fetch_html(detail_url)
except Crawl4AIRateLimitError as e:
    self._errors.append(f"stage=detail url={detail_url} kind=rate_limit msg={e}")
    continue
```

### H.2 Tier 2 — scraper-fatal (raise to service layer)

Auth invalid, DNS unrecoverable, target site fully down, scraper subclass bug. `scrape()` raises; `run_scraper` catches at top level, finalizes `status=FAILED` (or `PARTIAL` if some jobs already yielded), logs the exception. The error is appended to `JobScrapeRun.errors` for operator diagnosis.

```python
# scraper_service.run_scraper:
except Exception as exc:  # noqa: BLE001 — top-level scraper failure
    status = JobScrapeStatus.PARTIAL if listings_returned > 0 else JobScrapeStatus.FAILED
    errors.append(f"stage=invocation kind=fatal msg={type(exc).__name__}: {exc!s}")
    log.exception("scraper %s failed", scraper.name)
```

### H.3 `asyncio.CancelledError` (TIMED_OUT path)

Scheduler-level time budget elapses → `asyncio.CancelledError` raised into the running coroutine. `run_scraper` catches separately, marks `status=TIMED_OUT`, appends `stage=invocation kind=cancelled msg=asyncio.CancelledError` to errors, then re-raises. Structured concurrency demands re-raise so the scheduler can react.

### H.4 Redaction (`safe_url` + `safe_exc` + `safe_msg`)

Both writer paths — `scraper_service.run_scraper` building `JobScrapeRun.errors[]` strings and `crawl4ai_client.{fetch_html, stream_many}` `log.warning` calls — route URL + exception material through `safe_url` (strips query string + fragment; preserves scheme + host + path; blocks non-http(s) schemes inline) and `safe_exc` (`<ClassName>: <message[:200]>`). Pure functions in `src/scraper/redaction.py`, importable from any scraper-layer or service-layer module. Shipped `0.2.0.06a` per plan 31. Plan 32 (`0.2.0.06b`) added `safe_msg(s)` for raw upstream-message strings (Crawl4AI's `result.error_message`); same 200-char cap + ANSI / C0 / DEL strip as `safe_exc` but without the `<ClassName>:` prefix. Subclasses in `0.2.0.07` building their own error strings MUST use these helpers; `JobScrapeRun.errors[]` is the operator-UI surface and the full traceback still lands in app logs via the existing `log.exception(...)` calls in `scraper_service.py`.

---

## I · How to add a new site scraper (`0.2.0.07` checklist)

1. **File path:** `src/scraper/sites/<source>.py` (lowercase, matching `JobSource` value).
2. **Class:**
   ```python
   class <Source>Scraper(ScraperBase):
       source = JobSource.<SOURCE>
       board = ApplicationBoard.<BOARD>
       rate_limit_per_minute = <source-specific>  # if more conservative than 30 default
       random_delay_seconds = (<lo>, <hi>)        # if different from (1.0, 3.0)

       async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
           # 1. Build listing URLs from query.
           # 2. async for url, html in self._client.stream_many(urls): yield RawJob(...)
           # 3. Per-listing exceptions → self._errors.append(...) + continue.
           # 4. Tier-2 fatal → raise (service layer catches).
   ```
3. **Register:** `src/scraper/sites/__init__.py` → `scrapers[JobSource.<SOURCE>] = <Source>Scraper`.
4. **Tests:** `tests/test_scraper_<source>.py` — mock Crawl4AIClient via `_FakeAsyncCrawler` pattern from `tests/test_crawl4ai_client.py`. Cover at minimum: listing URL composition, RawJob field mapping, per-listing 429 handling, tier-2 fatal propagation.
5. **Cron (`0.2.0.10`):** add `scraping.<source>` APScheduler job calling `scraper_service.run_scraper(scrapers[JobSource.<SOURCE>]())`.
6. **Settings UI (`0.2.0.13`):** surface `<source>_rate_limit_per_minute` field.

---

## J · `SampleScraper` — what it is, what it isn't

File: `src/scraper/sites/sample.py`. Yields 3 hard-coded `RawJob` instances exercising distinct `RemotePolicy` + `SeniorityLevel` hints.

**It IS:**

- A contract smoke test (`tests/test_scraper_base.py` + `tests/test_scraper_sample.py` materialize the stream + assert shape).
- A service-layer smoke test (`tests/test_scraper_service.py` runs `run_scraper(SampleScraper())` end-to-end with an in-memory fake session).
- A manual diagnostic — instantiate + iterate in a REPL to verify the substrate works without spawning Chromium.

**It IS NOT:**

- Registered in `src/scraper/sites/__init__.py:scrapers` for production dispatch.
- Wired into any APScheduler cron job.
- Suitable as a "manual seed-job upload" surface — if `0.2.0.14` (n8n migration) or a future plan needs that, add a `ManualUploadScraper(ScraperBase)` subclass; do NOT reuse `SampleScraper`.

**Source value:** `JobSource.MANUAL`. External IDs use `manual-sample-NNN` synthetic ids — distinct from `create_manual_job`'s `manual-<uuid12>` pattern so the two don't collide if a sample run happens to land in the DB during integration testing.

---

## K · Cross-references

- `docs/design/JOB_MODEL.md` § F — `job_service.upsert_job(... raw=...) → tuple[Job, bool]` contract that `scraper_service.run_scraper` consumes.
- `docs/design/JOB_MODEL.md` § D.2 — `JobScrapeRun` row shape (counters + status + errors + duration_ms).
- `docs/design/BACKEND.md` § J — pipeline overview. § J.1 references this doc for the canonical `ScraperBase` + `RawJob` shape.
- `docs/design/research/LINKEDIN_SCRAPING.md` § 7 — blueprint for the first `0.2.0.07` site scraper subclass.
- `docs/ARCHITECTURE.md` § 3.8 — scraper-layer rules (no DB writes from scraper code; service layer owns persistence).
- `docs/RUNBOOK.md` — failure-mode entries land alongside the first real scraper in `0.2.0.07`.
