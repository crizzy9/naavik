# Naavik · Job Search Preferences

> **Canonical reference** — written BEFORE implementation for the same-day owner-directed redesign that moves job-search intent (target titles / target cities / remote_ok) from `Settings.{linkedin,indeed}_keywords` (per-source, keyword-based) to `Profile.{target_titles,target_cities,remote_ok,title_expansions}` (profile-level, source-agnostic). One profile-level intent record now drives every scraper.
> **Status:** ACTIVE (implementation in progress, same-day).
> **Last updated:** 2026-07-02.
> **Companion docs:** `docs/design/JOB_MODEL.md` (`ScrapeQuery` + `JobScrapeRun` contract downstream of this), `docs/design/SOURCES_UI.md` (Settings · Sources panel — becomes derived + override), `docs/design/SCREENS.md` § 5 (Profile) + § 12 (Discover) + § 11 (Settings), `docs/design/BACKEND.md` § I (scheduler / `_compose_query`), `docs/design/SCRAPER_BASE.md` (rate-limit substrate — multi-title interaction).
> **Downstream:** LinkedIn is the priority source for the first cut of the end-to-end path.

---

## A · Goal / Why

Today each source carries its own keyword + location fields on `Settings` (`linkedin_keywords`, `linkedin_location`, `indeed_keywords`, `indeed_location`). Every new source added would multiply the fanout, and the user's actual job-search intent — "I'm hunting for {Senior Software Engineer, ML Engineer} in {Seattle WA, remote}" — is expressed 2×, 3×, N× times across the panel, one per scraper. That contradicts the mental model ("my search preferences") and blocks the near-term additions of Workday + Indeed intent-based flows.

The redesign: one Profile-level record — `target_titles`, `title_expansions`, `target_cities`, `remote_ok` — is the source of truth. Every scraper reads it. Settings retains per-source **override** slots (existing columns) for the edge case where the operator wants "for LinkedIn only, additionally search 'staff platform engineer'"; empty override = derive from profile. LLM-generated title expansions serve post-fetch matching (scorer signal, Discover ranking) without discarding jobs that don't match.

---

## B · Data model

### B.1 New columns on `Profile` (`src/models/profile.py`)

| Column | Type | Default | Semantics |
|---|---|---|---|
| `target_titles` | `list[str]` (Postgres `ARRAY(String)`, nullable=False, server_default `'{}'`) | `[]` | User-entered target titles, e.g. `["Senior Software Engineer", "ML Engineer"]`. Raw strings — no normalization beyond `.strip()`. Order is preserved; UI lists them in insertion order. |
| `title_expansions` | `dict` (`JSONB`, nullable=False, server_default `'{}'`) | `{}` | LLM-generated equivalence groups. Shape: `{ "<raw title>": { "expanded": ["<equiv 1>", "<equiv 2>", ...], "generated_at": "<iso-ts>", "model": "<provider:model>" } }`. Key set MUST match `target_titles` after every edit (stale keys pruned on write). |
| `target_cities` | `list[str]` (`ARRAY(String)`, nullable=False, server_default `'{}'`) | `[]` | Normalized `"City, ST"` strings (US-only for now). Only values that the autocomplete endpoint accepted may be written — clients that POST arbitrary text still get normalized server-side (title-case city, uppercase 2-letter state; unknown → 400). |
| `remote_ok` | `bool` (`NOT NULL`, server_default `'true'`) | `True` | When True, remote-friendly listings are in-scope even without a target city. When False AND `target_cities` empty, the profile is considered unconfigured for search (Discover empty state fires). |

No index on `target_titles` / `target_cities` — the arrays are small (≤10 typical) and only read alongside the profile row itself. `title_expansions` is JSONB; no GIN index — access pattern is always "load the whole dict, use in-process." Revisit if we start querying by expansion contents.

### B.2 Migration `0027_profile_search_prefs`

- **down_revision:** `0026_enum_label_names`.
- **Schema step:** `ALTER TABLE profile ADD COLUMN target_titles text[] NOT NULL DEFAULT '{}'`, same shape for `target_cities`; `title_expansions jsonb NOT NULL DEFAULT '{}'`; `remote_ok boolean NOT NULL DEFAULT true`.
- **Data migration step (idempotent):** For each `Profile` row whose `target_titles = '{}'`:
  1. Join to the row's `Settings`. If `linkedin_keywords` non-empty → seed `target_titles = linkedin_keywords`; else if `indeed_keywords` non-empty → seed `target_titles = indeed_keywords`.
  2. Seed `target_cities = ['<normalized(linkedin_location)>']` if the string maps to a known US city (else empty).
  3. Clear the migrated Settings source fields: `linkedin_keywords = NULL, linkedin_location = NULL, indeed_keywords = NULL, indeed_location = NULL` — so the derived read-path kicks in without carrying stale duplicates. Comment in migration references this doc + explains that the columns are intentionally kept (they now function as **overrides**; empty = derived).
- **Downgrade:** copy `target_titles` back into `linkedin_keywords`, drop the four new columns. Best-effort — the profile-level cities/expansions are lossy on downgrade and that's acceptable.

### B.3 Static US-cities dataset

- File: `src/data/us_cities.json` — array of `{"city": str, "state": str, "population": int}` sorted population-descending. Bundled in the package (add to `pyproject.toml` package-data).
- Source + attribution documented in `src/data/README.md` (SimpleMaps free tier or Census 2020 — attribution and license terms recorded there). No runtime download.
- Loader: `src/services/us_cities.py`, lazy `functools.lru_cache` returns a list + a lowercase-lookup index. Loaded once per process.

---

## C · API surface

| Route | Method | Kind | Purpose |
|---|---|---|---|
| `/api/v1/profile/search-prefs` | `PUT` | JSON | Write `target_titles`, `target_cities`, `remote_ok`. Server prunes `title_expansions` keys not in the new titles set and enqueues title expansion for any newly added title. CSRF-gated. |
| `/api/v1/geo/cities` | `GET` | JSON | Query param `q: str` (min length 1). Returns top-10 US city matches: `{"cities": [{"label": "Seattle, WA", "city": "Seattle", "state": "WA", "population": ...}, ...]}`. Case-insensitive prefix match first, substring match second, population-ranked within each bucket. Public within the authed session — no user data, no rate-limit (small in-memory index; O(cities) per query is fine at N≈30k). |
| `/_fragments/profile/target-cities/suggest` | `GET` | HTMX fragment | HTML fragment: dropdown of matches, each `<button>` swaps a hidden input on click. Wraps `/api/v1/geo/cities` for the UI without leaking the JSON shape to the template. |
| `/_fragments/profile/search-prefs` | `POST` | HTMX fragment | Add / remove a title or city. Server-side rerender of the section. Wraps the JSON PUT for browsers-without-JS resilience. |
| `/_fragments/scrape-status` | `GET` | HTMX fragment | Polling fragment (`hx-trigger="every 3s"` while any active run; stops when idle). Renders the last N `JobScrapeRun` rows for the current user across all sources, plus any "queued" client-known runs seeded by a Run-now trigger. Mounted on Discover (status strip above the queue) AND Settings · Sources (above the 6-row table). |

Unchanged: `PUT /api/v1/settings/sources` continues to accept `linkedin_keywords` / `indeed_keywords` / `linkedin_location` / `indeed_location` — those columns now function as **per-source overrides** (empty = derive from profile). The Settings · Sources UI's editor is relabeled accordingly (see § D.2).

---

## D · UI surfaces

### D.1 Profile edit page (`/profile/edit`) — new "Job search preferences" section

Anchor: `#job-search`. Order: after the identity/contact section, before summary. Fields:

- **Target titles** — chip list + text input. Enter adds a chip. Chip has `×` to remove. Removing prunes the corresponding `title_expansions` entry. Server enqueues LLM expansion for each new chip.
- **Target cities** — chip list + text input with autocomplete dropdown (HTMX `hx-get="/_fragments/profile/target-cities/suggest"` on `keyup changed delay:200ms`). Only chips that came from the dropdown or matched a known US city on server-side normalization are accepted. Chips show `"Seattle, WA"`.
- **Remote OK** — DaisyUI toggle bound to `remote_ok`. Sticky helper text: "When on, remote listings are in-scope even without a target city."
- **Empty state help** — if `target_titles = []`: emerald info banner ("These preferences drive every scraper. Add at least one title to start finding jobs.").

Expansion state is not shown in the primary UI. A collapsible `<details>` labeled "Show equivalent titles the AI will match" reveals the current `title_expansions` (per-title bullet list). Regenerate-per-title button is deferred (out of scope for the same-day cut; call out in Risks).

### D.2 Settings · Sources becomes derived + override

Per-row keyword editor (`_keywords_editor.html`, plan 58) is rewritten for LinkedIn + Indeed:

- Above the input: read-only display of the derived profile values — chip list of `target_titles`, chip list of `target_cities`, "Remote OK: yes/no". Caption: "From profile · [Edit in profile](/profile/edit#job-search)".
- Below: existing keyword + location inputs, retitled "Per-source override (optional)". Placeholder text explains "leave blank to use profile preferences."
- No change to `PUT /api/v1/settings/sources` — the field slots stay the same; only the label + rendering change.

`env_secrets.scraper_source_configured` for LinkedIn / Indeed becomes:

```python
def scraper_source_configured(source, settings, profile):
    if source is JobSource.LINKEDIN:
        return bool(settings.linkedin_keywords) or bool(profile.target_titles)
    if source is JobSource.INDEED:
        return bool(settings.indeed_keywords) or bool(profile.target_titles)
    ...
```

Signature gains `profile` — call sites in the Settings · Sources route + scheduler pass it through. Profile is guaranteed to exist for any authed user (created at signup).

### D.3 Discover — status strip + empty state

- **Status strip** — thin band above the queue rendering the `_fragments/scrape-status` fragment. When active runs exist, the fragment shows one chip per active source (`LinkedIn · queued → running → found 12` etc.) and polls every 3s. When idle, the strip shows "Last checked: Nm ago · [ Run now ]" and stops polling.
- **Empty state CTA** — if `Job` queryset is empty AND `profile.target_titles = []`, replace the existing empty-state with: "Set up your job search — we'll start finding jobs as soon as you tell us what you're looking for," CTA button → `/profile/edit#job-search`.

---

## E · Scraper read-path contract

The single chokepoint is `_compose_query` in `src/scheduler/scraping.py`. It goes from returning **one** `ScrapeQuery` per (user, source) to returning **a list** of `ScrapeQuery` — one per target title. `_scrape_one_user` iterates the list, opening a separate `JobScrapeRun` per query, recording the source title into `JobScrapeRun.raw_meta["target_title"]`.

Before (§ B.1 of BACKEND.md § I):

```python
def _compose_query(source, settings) -> ScrapeQuery:
    if source is JobSource.LINKEDIN:
        return ScrapeQuery(
            keywords=list(settings.linkedin_keywords or []),
            location=settings.linkedin_location,
        )
    ...
```

After:

```python
def _compose_queries(source, settings, profile) -> list[ScrapeQuery]:
    # Per-source override wins if any field is set.
    if source is JobSource.LINKEDIN and settings.linkedin_keywords:
        return [ScrapeQuery(
            keywords=list(settings.linkedin_keywords),
            location=settings.linkedin_location,
            raw_meta={"query_source": "override"},
        )]
    # Derive from profile.
    titles = list(profile.target_titles or [])
    if not titles:
        return []  # Unconfigured — caller already skipped via scraper_source_configured
    location = (profile.target_cities[0] if profile.target_cities
                else ("" if profile.remote_ok else None))
    return [
        ScrapeQuery(
            keywords=[title],           # raw title as the LinkedIn/Indeed keyword param
            location=location,
            raw_meta={"query_source": "profile", "target_title": title},
        )
        for title in titles
    ]
```

Non-intent sources (Workday / Greenhouse / Lever / Ashby) are unchanged — they still return a single `ScrapeQuery(company_filter=...)`. `_scrape_one_user` calls the resolver, iterates whatever list comes back, and shares the same `client` / `rate_limit` config across the loop (see Risks § H.4 — one client-level bucket rate-limits all queries in the loop together, which is what LinkedIn's 0.4 rpm sustained budget requires).

---

## F · Title-expansion prompt

Module: `src/llm/prompts/expand_titles.py`. Wrapped by `services.llm_tracker.tracked_call` at the call site inside the write-path handler for `/api/v1/profile/search-prefs`.

Input:

- `titles: list[str]` — the newly-added or edited titles (not the full set — we only expand the diff).
- `headline: str | None` — `profile.headline`, provides seniority + domain context ("Senior Software Engineer @ Intuit — GenAI, martech" tells the model this is a real senior IC, not "Senior Software Engineer intern").

Output schema (`pydantic` BaseModel):

```python
class TitleExpansions(BaseModel):
    expansions: list[TitleExpansion]

class TitleExpansion(BaseModel):
    title: str        # echoes the input title verbatim
    expanded: list[str]  # cap 12, deduped, excludes exact title, excludes the input list
```

Prompt sketch: "Given the headline and a target title, list up to 12 equivalent titles, senior/staff variants, and closely related roles a recruiter might post the same job under. Exclude obvious mismatches (director/VP if the seeker is IC-level). Return `TitleExpansions` where each `title` matches an input exactly." `max_tokens=768`, structured output via `provider.structured`.

Graceful degrade — no LLM configured (`llm_get_provider` raises `LLMProviderError`): write `{title: {"expanded": [title], "generated_at": now, "model": "none"}}` for each title. Downstream matching still works (self-match).

Cap: 12 expansions per title, guarded server-side (truncate `.expanded[:12]`). Rate: expansions are enqueued on write, not on read; write path awaits inline (single small call, ≤2s typical). Failure of expansion doesn't fail the write — the row lands with `expanded = [title]` and `model = "fallback"`.

### F.1 `title_matches` helper

`src/services/title_match.py`:

```python
def title_matches(job_role: str, expansions: dict) -> bool:
    """True iff any expanded string is a normalized substring of job_role
    OR vice versa. Case + punctuation-insensitive."""
```

Used by (a) the scorer as a title-relevance signal folded into the existing match breakdown (as a boost, not a gate — jobs that don't match are stored + shown, just ranked lower), and (b) Discover ordering (secondary sort key after score). Never a filter — we never drop a job for failing title match.

---

## G · Prefill from resume parse

After `extract_resume` persists the profile (in `src/services/profile_intake.py` or equivalent):

- If `profile.target_titles == []`: seed to `[experiences[0].title]` (most recent) or, if experience list empty, `[profile.headline.split(" @ ")[0].strip()]`. Never seed with more than one — user adds more manually.
- If `profile.target_cities == []` and `profile.location` normalizes to a known US city: seed `[normalized]`.
- Always seed `remote_ok = True` on first parse — cheap default matching the "open to opportunities" flag.
- Enqueue title expansion for the seeded title (same write path as § F).

Prefill runs once, inside the same DB transaction as the resume-derived profile write. Idempotent: re-uploading a resume never overwrites non-empty preferences.

---

## H · Risks / edge cases

| # | Risk | Mitigation |
|---|---|---|
| H.1 | LLM unavailable at write time → expansions fall back to self-only, degrading match quality permanently. | Store `model = "fallback"` on fallback writes. Add a nightly cron (out-of-scope for same-day; ROADMAP note) that retries `model = "fallback"` rows against the currently configured provider. Not blocking for MVP because scoring still works — expansion is a boost, not a gate. |
| H.2 | Empty prefs after migration for users who had no `linkedin_keywords` / `indeed_keywords` set. | Discover empty state renders the "Set up your job search" CTA. `scraper_source_configured` returns False; the scheduler skips silently. No noisy zero-hit `JobScrapeRun` rows. |
| H.3 | Override precedence confusion — user edits profile expecting change to take effect but has an old per-source override still set. | Sources UI shows the override AND the derived value side-by-side, with an explicit "Per-source override (optional)" label + placeholder. Migration step § B.2 clears the pre-migration keyword fields, so no user carries over a stale override by accident. |
| H.4 | Multi-title queries interact with LinkedIn's 0.4 rpm sustained budget — 3 titles at 0.4 rpm means one full cycle takes ~7.5 minutes minimum. | `_scrape_one_user` shares one `Crawl4AIClient` (single rate-limit bucket) across all queries in the loop, and queries run **sequentially** through the existing rate limiter. This means the profile-level 30-minute LinkedIn cron may not clear a 3-title backlog in one firing — that's acceptable; the next firing picks up where the last left off (each query is its own `JobScrapeRun`). Manual Run-now still applies the `_MANUAL_RUN_MIN_RPM` floor per query, so an operator verifying the config isn't waiting hours. |
| H.5 | Autocomplete dataset stale (a city renamed or a new state's town missing). | Dataset attribution + refresh cadence documented in `src/data/README.md`. Fallback: server-side normalization accepts any `"<City>, <STATE>"` shape that matches the case-insensitive index; unknown → 400 with actionable message. The static file can be regenerated any time without a code change. |
| H.6 | JSONB `title_expansions` grows unbounded if the user churns titles. | On every write to `target_titles`, prune keys not in the new set. Cap enforced at 12 expansions per title inside the prompt handler. |
| H.7 | Scorer weight for title-relevance not yet defined — folding into match breakdown risks over/under-weighting. | Ship as a small additive boost (e.g. +5 pts on match) inside the existing breakdown. Deferred: tune weight in a follow-up plan after 1 week of production data. |
| H.8 | Regenerate-per-title button deferred. | Users can force-regenerate by removing + re-adding a title. Add explicit UI in a follow-up. |

---

## I · Non-goals (this doc)

- Non-US cities. Autocomplete dataset is US-only; the `remote_ok` flag is the escape hatch for international remote work until Phase 5+ adds locale.
- Boolean-search expressions in target titles ("(Senior OR Staff) AND Backend"). Titles are raw strings; LLM expansion is the substitute for boolean search.
- Multi-title fan-out to non-intent sources (Workday / Greenhouse / Lever / Ashby). Those remain company-list driven; the intent record does not synthesize per-title company filters. Post-fetch `title_matches` still applies to their results.
- Live regeneration of expansions on model swap. If the user changes their default LLM provider, existing expansions stay; the retry cron in H.1 catches this.
