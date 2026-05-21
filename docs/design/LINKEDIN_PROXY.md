# LinkedIn proxy support

> **Canonical design reference for the LinkedIn proxy substrate.**
> Graduated 2026-05-21 from `docs/plans/64-0.2.7.11-linkedin-proxy.md`.
> Implements ROADMAP row `0.2.7.11`.

## A · Contract (one paragraph)

Naavik's LinkedIn scraper routes every HTTP request through an operator-supplied HTTP / HTTPS / SOCKS5 proxy when the env var `LINKEDIN_PROXY_URL` is configured. The proxy URL carries Basic-auth credentials in standard `http://user:pass@host:port` form; Naavik never stores it in the database, never logs the credentials, and never silently falls back to a direct connection if the proxy is unreachable (proxy outage → `JobScrapeRun.status = FAILED` → admin alert after 3 consecutive failures per plan 35's existing counter). Sticky session is per-`Crawl4AIClient`-instance — each cron firing constructs a fresh client, which equals one sticky-IP session window. Provider-agnostic by design: operator points the env var at any residential / datacenter provider URL.

## B · Why proxy

LinkedIn fingerprints (a) the residential IP, (b) the TLS-fingerprint, (c) the cookie continuity, (d) the request cadence. Plan 38 shipped layers (b)+(c)+(d) (`enable_stealth=True`, UA rotation, 0.4 rpm rate limit + 429/503 backoff). Without (a), the operator's residential IP is exposed on every LinkedIn request — one CAPTCHA round or 24h rate-limit cooldown stops the entire `discover` pipeline. Research source: `docs/design/research/LINKEDIN_SCRAPING.md § 6` — proxy is the fourth and final anti-detection layer.

Defense-in-depth composition (plan 64 § D.11):

```
1. Stealth        — BrowserConfig(enable_stealth=True)   [plan 29 § G.5]
2. UA rotation    — pick_user_agent() per Crawl4AIClient [plan 38 § G.4]
3. Rate limit     — 0.4 rpm + 429/503 backoff             [plan 38 § G.2 + § G.3]
4. Proxy          — LINKEDIN_PROXY_URL env var            [plan 64 § C-D]  ← THIS DOC
```

## C · Configuration surface

### C.1 — Env var `LINKEDIN_PROXY_URL`

One env var carries the full proxy contract:

```
LINKEDIN_PROXY_URL=http://user:pass@gate.smartproxy.com:7000
```

Parsed by `scraper.proxy.ProxyURLConfig` (Pydantic v2). Validated FAIL LOUD at app boot — invalid URL refuses to start the app per § F.1.

### C.2 — Scheme support

`{http, https, socks5}`. The Crawl4AI 0.8.6 `ProxyConfig.from_string` parser accepts all three; tested in `tests/test_scraper_proxy.py`.

```
http://user:pass@host:port
https://user:pass@host:port
socks5://user:pass@host:port
```

`socks5h://` (DNS-via-proxy) vs `socks5://` (local DNS) defaults to local DNS; tracked as `0.2.7.11b` deferred follow-up for operator-observed behavior.

### C.3 — Provider selection (residential vs datacenter)

LinkedIn's bot detection treats datacenter IPs (AWS / GCP / DigitalOcean exit ranges) as automation. Operators choosing the wrong proxy type silently amputate the anti-detection benefit.

✓ **Residential proxies — recommended:**
- Bright Data: `brd-customer-{id}-zone-{zone}:{password}@brd.superproxy.io:33335`
- Smartproxy (Decodo): `user-{username}-session-{id}:{password}@gate.smartproxy.com:7000`
- IPRoyal: `{username}:{password}@geo.iproyal.com:12321`

✗ **Datacenter proxies — NOT recommended for LinkedIn:**
- AWS / GCP / DO exit IPs. Cheaper ($1-3/GB vs $7-15/GB) but LinkedIn flags them.

Per plan 64 § D.4 we do NOT validate the operator's choice (no outbound IP-classifier API call; preserves self-hosted privacy contract). The trade-off is documented loudly in `.env.example` + this section.

### C.4 — Geo + sticky-session

Operator embeds geo / sticky-window in the URL per their provider's documentation. Naavik does not compose these on the operator's behalf (plan 64 § D.5 — provider-specific URL templates would re-introduce vendor lock-in we ruled out in § D.2).

## D · Wiring

### D.1 — Resolver: `scraper.proxy.resolve_proxy_config(source)`

```python
def resolve_proxy_config(source: JobSource) -> ProxyURLConfig | None:
    if source is not JobSource.LINKEDIN:
        return None
    if not app_settings.linkedin_proxy_url:
        return None
    return ProxyURLConfig(
        url=app_settings.linkedin_proxy_url,
        provider_hint=app_settings.linkedin_proxy_provider_hint,
    )
```

Plan 64 § D.7: LinkedIn-only this plan. Multi-source generalization to `0.8.0.NN`.

### D.2 — `Crawl4AIClient.__init__(proxy_config=...)`

Optional kwarg threaded into the per-request `CrawlerRunConfig.proxy_config` slot (Crawl4AI 0.8.6 contract; `BrowserConfig.proxy` is deprecated):

```python
self._run_config = CrawlerRunConfig(
    cache_mode=CacheMode.BYPASS,
    page_timeout=page_timeout_ms,
    proxy_config=proxy_config.to_crawl4ai() if proxy_config else None,
)
```

### D.3 — Scheduler integration: `_scrape_one_user`

```python
proxy_config = resolve_proxy_config(source)
client = Crawl4AIClient(
    rate_limit_per_minute=rl_config.rpm,
    random_delay_seconds=(rl_config.delay_lo, rl_config.delay_hi),
    use_undetected_adapter=scraper_cls.use_undetected_adapter,
    proxy_config=proxy_config,
)
```

The scheduler logs INFO per firing when the proxy is on (with redacted host) + WARNING once at first firing when LinkedIn + env unset (per `_LINKEDIN_PROXY_WARNED` global).

## E · Stickiness behavior

**One `Crawl4AIClient` instance = one sticky session.** The scheduler constructs a fresh client per cron firing (`scheduler/scraping.py:_scrape_one_user`). LinkedIn cron schedule is `*/30` (every 30 min) → one firing = one session window. Operators pointing at a residential provider's "sticky-session" URL (e.g. `session-XYZ` in Smartproxy username, `session-id` in Bright Data) get up to N-minute sticky-IP per the provider's contract.

**Why not rotate per-request?** Plan 64 § D.1 Option B is the textbook bot signal — rapid IP cycling within the same LinkedIn session reads as "human typing from different cities". Even with stealth + UA rotation, jumping IPs mid-session triggers immediate challenges. The provider's sticky-session URL is the canonical anti-detection shape.

**Why not an explicit Naavik state machine?** Plan 64 § D.1 Option C — over-engineered for v1. Operators who want longer-running sessions wait for Phase 5 outreach (authenticated cookies) or the `0.2.7.11a` follow-up (Crawl4AI's native `RoundRobinProxyStrategy` for multi-URL rotation).

## F · Failure handling

### F.1 — Boot-time validation (FAIL LOUD)

`config.py`'s `field_validator("linkedin_proxy_url")` calls `ProxyURLConfig(url=v)` which raises on any of: unsupported scheme, missing host, missing port, port-out-of-range, query string present, fragment present, unparseable URL. App boot fails with a Pydantic `ValidationError` listing the offending value (which is fine — the URL is operator-supplied, not a secret to the operator).

### F.2 — Cron-time failure (FAIL LOUD, never degrade)

If the proxy is configured but unreachable at scrape time (`asyncio.TimeoutError`, `ConnectionError`, proxy auth-fail, anything Crawl4AI propagates), `Crawl4AIClient.fetch_html` / `stream_many` propagate the exception. `scraper_service.run_scraper` catches at the top-level + finalizes `JobScrapeRun.status = FAILED` (or PARTIAL if some jobs already yielded). The scheduler's `consecutive_scrape_failures` counter increments — after 3 consecutive FAILED runs, plan 35's Discord admin alert fires.

### F.3 — No degrade-to-direct (the load-bearing rule)

Per plan 64 § D.6: the whole reason an operator configures `LINKEDIN_PROXY_URL` is to hide their residential IP. Silently falling back to a direct connection on proxy failure defeats the purpose AND is the #1 way to lose a LinkedIn account in every public scraping post-mortem (Crawlee, JobSpy, n8n's original setup). Naavik MUST NOT catch the proxy failure and retry without the proxy. Cron firings during a proxy outage produce zero data (not degraded data); operators MUST keep proxy credit topped up.

## G · Secret handling

### G.1 — Basic-auth in URL + `safe_proxy_host` redaction

`LINKEDIN_PROXY_URL` carries `user:pass@host:port` in the URL's authority. The post-plan-26 contract is "secrets live in env, filesystem perms are the defense" — DB-stored credentials are forbidden (would re-open the surface the vault deletion closed).

Two helpers defend the secret-in-URL:

- `scraper.proxy.safe_proxy_host(url) -> str` — strips userinfo + scheme; returns `<host>:<port>` only. Used in every log line + `JobScrapeRun.raw_meta` write.
- `scraper.redaction.safe_url(url) -> str` — strips userinfo + query + fragment for ANY URL (post-plan-64). Pre-plan-64, `safe_url` preserved the netloc verbatim, which would have leaked proxy creds if a proxy-tunneled URL ever flowed through it; plan 64 fixed that.

### G.2 — Lint guard: `tests/test_no_proxy_url_in_logs.py`

A dedicated lint test asserts the sentinels `leakeduser123sentinel` + `leakedpass456sentinel` never appear in log records or `JobScrapeRun.errors[]` after a fake LinkedIn scrape. The test pins the secret-handling contract — a future regression in any logging site will trip it.

## H · Cost telemetry

### H.1 — `JobScrapeRun.raw_meta["proxy"]` sub-key

Per plan 64 § D.9. Five sub-keys:

```json
{
  "proxy": {
    "used": true,
    "host": "gate.smartproxy.com:7000",
    "provider_hint": "smartproxy",
    "request_count": 24,
    "bytes_estimated": 487293
  }
}
```

- `used` (bool) — was the proxy on for this run?
- `host` (str | null) — `safe_proxy_host(url)`; `null` when `used=false`.
- `provider_hint` (str | null) — operator-supplied label from `LINKEDIN_PROXY_PROVIDER_HINT`; cost-tracking aid only.
- `request_count` (int) — exact count of HTTP fetches routed through the proxy.
- `bytes_estimated` (int) — sum of `len(result.html)` across all successful fetches. Upper bound on bytes-over-wire; actual proxy billing is on the provider's dashboard.

### H.2 — Operator UX

The Settings · Sources panel renders a LinkedIn-only `proxy: gate.smartproxy.com:7000` chip when configured, or `no proxy` (amber) when unset. Userinfo never reaches the template context.

### H.3 — Bytes-estimated caveat

`bytes_estimated` is an upper bound on the HTML payload size, not socket bytes. Crawl4AI 0.8.6 does not expose lower-level instrumentation. Operators converting to provider GB-billing should multiply by an empirical compression ratio (~0.4 for typical HTML) to estimate actual provider-side cost.

## I · Multi-source generalization (future)

### I.1 — `0.8.0.NN` deferred follow-up

When multi-tenant cloud lands (per-user proxy config) OR when Indeed / Generic ATS scrapers ship and operators want proxies on those too, the substrate generalizes:

- Replace `LINKEDIN_PROXY_URL` (env) with `Settings.scraper_proxies: dict[str, str]` JSONB (per-source, per-user).
- Extend `resolve_proxy_config(source)` to read from Settings.
- Settings UI grows a per-source proxy input (vault-shaped concern reopens — see plan 64 § D.3).

### I.2 — Why LinkedIn-only first

Per plan 64 § D.7:

1. LinkedIn is the ONLY source with realistic account-ban consequences. Greenhouse / Lever / Ashby / Workday are ATS or job-listing sites — they rate-limit but don't ban accounts (Naavik isn't authenticated to them).
2. Cost: residential proxies are ~$15/GB. Greenhouse / Lever / Ashby scrapes are HTML-heavy (50KB/job); sending all sources through the proxy is $$.
3. Scope: the ROADMAP row is "LinkedIn proxy support". Multi-source proxy infra is its own row.

## J · Cross-references

- `docs/design/SCRAPER_BASE.md § G.11` — substrate composition pointer.
- `docs/design/research/LINKEDIN_SCRAPING.md § 6` — anti-detection research source.
- `docs/plans/archive/64-0.2.7.11-linkedin-proxy.md` — implementation plan (post-archive).
- ROADMAP row `0.2.7.11` — LinkedIn proxy support.
- ROADMAP row `0.8.0.NN` (TBD) — multi-source proxy generalization.
- ROADMAP row `0.2.7.11a` (TBD) — `RoundRobinProxyStrategy` rotation.
- ROADMAP row `0.2.7.11b` (TBD) — `socks5h://` vs `socks5://` decision.
