"""ScraperBase ABC — every site scraper inherits this surface.

Per docs/design/SCRAPER_BASE.md § C (graduated from plan 29 § D.1, D.3, D.6,
D.7). Matches `src/llm/base.py:LLMProvider(ABC)` convention: abstract base
with `@abstractmethod`-enforced contract, instance state for counters +
errors, class-level config knobs for rate-limit hooks.

Subclasses declare `source` + `board` as class attributes and implement
`scrape()` as an async generator yielding `RawJob` instances. Per-listing
errors append to `self._errors` and continue; scraper-fatal errors raise
to the service layer (`scraper_service.run_scraper`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from models import ApplicationBoard, JobSource

from .types import RawJob, ScrapeQuery

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from llm.base import LLMProvider

    from .crawl4ai_client import Crawl4AIClient


class ScraperBase(ABC):
    """Abstract base for site scrapers.

    Subclasses MUST set `source` + `board` class attributes and implement
    `scrape()`. Subclasses MAY override `rate_limit_per_minute` /
    `random_delay_seconds` for source-specific tuning; `0.2.0.13` lifts
    these into `Settings` fields.
    """

    # Subclass-declared
    source: JobSource
    board: ApplicationBoard

    # Rate-limit hooks (plan 29 § D.6). `float` per plan 38 § D.8 — LinkedIn's
    # 0.4 req/min (24/hour) is now expressible without int-floor flooring it
    # to 1. Operator overrides live in `Settings.scraper_rate_limits` (plan
    # 38 § D.1); class attrs are the fallback table.
    rate_limit_per_minute: float = 30.0
    random_delay_seconds: tuple[float, float] = (1.0, 3.0)

    # Crawl4AI's `UndetectedAdapter` (more aggressive fingerprint patching
    # than stealth-mode). Engagement deferred to `0.2.0.13c` follow-up gated
    # on observed 403-rate per plan 38 § D.4; wiring + telemetry ship here.
    use_undetected_adapter: bool = False

    def __init__(
        self,
        *,
        client: Crawl4AIClient | None = None,
        session: AsyncSession | None = None,
        user_id: int | None = None,
        provider: LLMProvider | None = None,
    ) -> None:
        if client is None:
            from .crawl4ai_client import Crawl4AIClient

            client = Crawl4AIClient(
                rate_limit_per_minute=self.rate_limit_per_minute,
                random_delay_seconds=self.random_delay_seconds,
                use_undetected_adapter=self.use_undetected_adapter,
            )
        self._client = client
        # AI extraction context (plan 33 § D.3 / D.4). All optional so substrate
        # smoke tests (SampleScraper) and `0.2.0.07` site scrapers running
        # pre-`0.2.0.08` stay constructable without an LLM provider. The
        # `_BaseSiteScraper._maybe_enrich` shim short-circuits when any of the
        # three is None.
        self._session = session
        self._user_id = user_id
        self._provider = provider
        # Per-listing error buffer; service layer aggregates into
        # `JobScrapeRun.errors[]` after the run completes.
        self._errors: list[str] = []

    @property
    def name(self) -> str:
        """Human-readable name for logs + JobScrapeRun.raw_meta."""
        return self.__class__.__name__

    @abstractmethod
    async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
        """Yield `RawJob` instances as they are discovered.

        Subclass contract:
        - MUST yield only valid `RawJob` instances (Pydantic validates at
          construction).
        - SHOULD honor `query.max_listings` as an upper bound.
        - SHOULD catch per-listing errors, append to `self._errors`, and
          continue iterating.
        - MUST raise on a total scraper failure (auth, network unrecoverable,
          target site down) so the service layer marks the run FAILED.
        """
        # `if False: yield` flips the parser into async-generator mode so the
        # return-type annotation `AsyncIterator[RawJob]` matches the subclass
        # override shape (also an async generator).
        if False:  # pragma: no cover
            yield  # type: ignore[unreachable]
