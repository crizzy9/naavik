"""Naavik scraper substrate (plan 29 / 0.2.0.06).

Public surface:
- `RawJob` / `ScrapeQuery` (boundary DTOs)
- `ScraperBase` (ABC every site scraper inherits)
- `Crawl4AIClient` (testable wrapper around AsyncWebCrawler)
"""

from __future__ import annotations

from .base import ScraperBase
from .crawl4ai_client import Crawl4AIClient
from .types import RawJob, ScrapeQuery

__all__ = ["Crawl4AIClient", "RawJob", "ScrapeQuery", "ScraperBase"]
