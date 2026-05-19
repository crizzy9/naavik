"""Naavik scraper substrate (plan 29 / 0.2.0.06).

Public surface:
- `RawJob` / `ScrapeQuery` (boundary DTOs)
- `ScraperBase` (ABC every site scraper inherits)
- `Crawl4AIClient` (testable wrapper around AsyncWebCrawler; W2)
"""

from __future__ import annotations

from .base import ScraperBase
from .types import RawJob, ScrapeQuery

__all__ = ["RawJob", "ScrapeQuery", "ScraperBase"]
