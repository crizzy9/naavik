# Naavik · Scraper Base Contract

> **Canonical reference** — graduated from `docs/plans/archive/29-0.2.0.06-crawl4ai-base.md` per `AGENTS.md` § Workflow step 4.
> **Status:** Active. This is the single source for the `ScraperBase` ABC, the `RawJob` Pydantic DTO, the `Crawl4AIClient` wrapper, the `scraper_service.run_scraper` lifecycle, the rate-limit + anti-detection interface, and the two-tier error model.
> **Last updated:** 2026-05-19 (plan 29 / `0.2.0.06` shipped).
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

    # Rate-limit hooks (interface only; impl in 0.2.0.13)
    rate_limit_per_minute: int = 30
    random_delay_seconds: tuple[float, float] = (1.0, 3.0)

    def __init__(self, client: Crawl4AIClient | None = None) -> None: ...

    @property
    def name(self) -> str: ...

    @abstractmethod
    async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]: ...
```

### C.2 Subclass contract

- **MUST set** `source` + `board` class attributes (e.g. `source = JobSource.LINKEDIN`; `board = ApplicationBoard.LINKEDIN`).
- **MUST implement** `async def scrape(query) -> AsyncIterator[RawJob]` as an async generator (`async def` + `yield`).
- **MAY override** `rate_limit_per_minute` and `random_delay_seconds` for source-specific tuning. `0.2.0.13` lifts these into `Settings` fields with per-source defaults.
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

### D.4 `model_dump(exclude_unset=True)` is the hand-off shape

`scraper_service.run_scraper` calls `job_service.upsert_job(... raw=raw_job.model_dump(exclude_unset=True))`. Pydantic's `exclude_unset=True` omits defaults the scraper didn't touch; `_create_payload` in `job_service` projects onto Job-creatable fields and supplies typed defaults (`RemotePolicy.UNKNOWN`, `VisaRestriction.NOT_MENTIONED`, etc.) per `JOB_MODEL.md § F.2`.

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
        rate_limit_per_minute: int = 30,
        random_delay_seconds: tuple[float, float] = (1.0, 3.0),
    ) -> None: ...

    async def fetch_html(self, url: str) -> str | None:
        """Fetch one URL; return HTML on success, None on non-fatal failure."""

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

`_respect_rate_limit()` enforces `min_interval = 60 / rate_limit_per_minute` between requests then adds `random.uniform(*random_delay_seconds)` jitter. Per-process token-bucket; no shared state across workers. Source-specific tuning (LinkedIn ≤24/hr) ships with `0.2.0.07` subclasses.

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
   - Try `job_service.upsert_job(session, user_id, source=raw_job.source, external_id=raw_job.external_id, raw=raw_job.model_dump(exclude_unset=True), scrape_run_id=run.id)`.
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

## G · Rate limiting + anti-detection (interface only; impl in `0.2.0.13`)

Plan 29 ships defaults conservative-by-design. Per `docs/design/research/LINKEDIN_SCRAPING.md` § 5: LinkedIn-specific recommendation is 2.5s mean delay + max 4 search calls/hour. The class default (30/min, 1-3s) is conservative enough for any source; LinkedIn's subclass overrides to (≤24/hour) when `0.2.0.07` ships.

What's reserved for `0.2.0.13`:

- Per-source `Settings` field (`Settings.linkedin_rate_limit_per_minute`, etc.) so operators tune without code changes.
- Burst tolerance + exponential backoff on HTTP 429 (Crawl4AI's `RateLimiter` lift into the wrapper).
- IP rotation / proxy support (per `Settings.scraper_proxy_url`; Phase 6+ per ROADMAP `0.2.3.03`).
- `UndetectedAdapter` engagement for sources measured at high 403-rate.

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
