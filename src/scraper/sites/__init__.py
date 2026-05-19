"""Per-source site scraper registry (plan 33 § D.7 + plan 29 § D.5).

`scrapers` maps `JobSource.value` (lowercase) → subclass. Keyed by the
string form so APScheduler cron registration (`0.2.0.10`) + `+ Add by URL`
dispatch (Phase 6) can look up via string keys persisted in DB / job-store.

`SampleScraper` is exported for test reuse but deliberately NOT registered:
production dispatch must never invoke it.
"""

from __future__ import annotations

from models import JobSource

from ..base import ScraperBase
from ..types import RawJob
from .ashby import AshbyScraper
from .greenhouse import GreenhouseScraper
from .indeed import IndeedScraper
from .lever import LeverScraper
from .linkedin import LinkedInScraper
from .sample import SampleScraper
from .workday import WorkdayScraper

scrapers: dict[str, type[ScraperBase]] = {
    JobSource.LINKEDIN.value: LinkedInScraper,
    JobSource.WORKDAY.value: WorkdayScraper,
    JobSource.GREENHOUSE.value: GreenhouseScraper,
    JobSource.LEVER.value: LeverScraper,
    JobSource.ASHBY.value: AshbyScraper,
    JobSource.INDEED.value: IndeedScraper,
}

__all__ = [
    "AshbyScraper",
    "GreenhouseScraper",
    "IndeedScraper",
    "LeverScraper",
    "LinkedInScraper",
    "RawJob",
    "SampleScraper",
    "WorkdayScraper",
    "scrapers",
]
