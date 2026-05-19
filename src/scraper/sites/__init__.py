"""Per-source site scraper registry (plan 29 § D.5).

`0.2.0.07` populates `scrapers` with one entry per real source
(`JobSource.LINKEDIN -> LinkedInScraper`, etc.). Plan 29 ships the stub +
`SampleScraper` (which is a test fixture and is NOT registered for production
dispatch — see `docs/design/SCRAPER_BASE.md § J`).
"""

from __future__ import annotations

from ..base import ScraperBase
from ..types import RawJob
from .sample import SampleScraper

# Populated by 0.2.0.07 site scrapers. Empty here on purpose.
scrapers: dict[str, type[ScraperBase]] = {}

__all__ = ["RawJob", "SampleScraper", "scrapers"]
