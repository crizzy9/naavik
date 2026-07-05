"""Shared base for production site scrapers.

Per docs/design/SCRAPER_SITES.md § D.4 (graduated from plan 33). Extends
`ScraperBase` with the `_maybe_enrich(raw_job)` shim that calls
`services.jobs.extractor.enrich_raw_job` only when the constructor was passed
a non-None `session` + `user_id` + `provider`.

Why a shared helper between `ScraperBase` and the six subclasses:

1. The `_maybe_enrich` body is identical for all six sites; duplicating six
   times would invite drift.
2. `ScraperBase` (the substrate) MUST stay free of `services.jobs.extractor`
   knowledge — substrate tests should not transitively import the service
   layer. Putting the shim in a sites-package-internal class keeps the
   import-graph clean: `scraper.base` doesn't depend on `services.*`;
   `scraper.sites.*` does.
3. `SampleScraper` keeps inheriting `ScraperBase` directly — the substrate
   smoke tests don't need extraction wiring.

The lazy import of `services.jobs.extractor` inside `_maybe_enrich` is what
lets plan 33 ship BEFORE plan 30 (per § D.4): until `0.2.0.08` lands the
`enrich_raw_job` function, the `ImportError` is caught and the helper
short-circuits to identity.
"""

from __future__ import annotations

import logging

from scraper.base import ScraperBase
from scraper.redaction import _strip_control_chars, safe_exc, safe_url
from scraper.types import RawJob
from scraper.url_guard import InvalidSlugError, _make_url

log = logging.getLogger(__name__)


class _BaseSiteScraper(ScraperBase):
    """Substrate + optional-LLM enrichment shim used by the six production sites.

    Leading underscore = sites-package-internal. Not exported from
    `src/scraper/__init__.py`. Sub-package callers import via the concrete
    subclass (e.g. `LinkedInScraper`); registry lookups go through
    `scraper.sites:scrapers`.
    """

    async def _maybe_enrich(self, raw_job: RawJob) -> RawJob:
        """Pass-through unless the constructor was given a provider+session+user_id.

        Three guarded paths:

        - Any of `_provider` / `_session` / `_user_id` is None → return as-is.
          This is the pre-`0.2.0.08` default path (every test in this PR).
        - `services.jobs.extractor` not importable (because `0.2.0.08` has not
          yet landed) → log at DEBUG, return as-is. Lets the subclass code be
          written today against the future contract without coupling to it.
        - `enrich_raw_job` raises → append to `self._errors` (tier-1 per
          `SCRAPER_BASE.md § H.1`), return the unmodified `raw_job`.

        On success, return the enriched `RawJob` produced by the service.
        """
        if self._provider is None or self._session is None or self._user_id is None:
            return raw_job
        try:
            from services.jobs.extractor import enrich_raw_job  # lazy: 0.2.0.08
        except ImportError:
            log.debug(
                "services.jobs.extractor unavailable (0.2.0.08 not yet shipped); "
                "skipping enrichment for url=%s",
                safe_url(raw_job.source_url),
            )
            return raw_job
        try:
            return await enrich_raw_job(
                session=self._session,
                user_id=self._user_id,
                provider=self._provider,
                raw_job=raw_job,
            )
        except Exception as exc:  # noqa: BLE001 — tier-1 per SCRAPER_BASE.md § H.1
            self._errors.append(
                f"stage=extract url={safe_url(raw_job.source_url)} "
                f"kind=extract_failure msg={safe_exc(exc)}"
            )
            return raw_job

    def _compose_url(
        self,
        template: str,
        *,
        stage: str = "list",
        **slugs: str,
    ) -> str | None:
        """Slug-validate + format `template` with `**slugs`.

        Returns the composed URL on success; on `InvalidSlugError`, appends a
        tier-1 error to `self._errors` (mirrors the existing
        `is_safe_destination` rejection shape) and returns `None`. Caller MUST
        check `if url is None: continue`.

        Plan 43 (`0.2.0.07a`). Mirrors `_maybe_enrich` precedent — one wrapper
        owns the error-append + redaction; sites pass-through.
        """
        try:
            return _make_url(template, **slugs)
        except InvalidSlugError as exc:
            redacted_value = _strip_control_chars(exc.value)[:64]
            self._errors.append(
                f"stage={stage} url=<unmade:{template[:80]}> "
                f"kind=invalid_slug msg={exc.slug_name}={redacted_value!r}"
            )
            return None
