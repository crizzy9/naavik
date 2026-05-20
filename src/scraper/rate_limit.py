"""Per-source rate-limit configuration resolver.

Per docs/design/SCRAPER_BASE.md § G (graduated from plan 38 § D.1).
`RateLimitConfig` is the Pydantic v2 model that validates the nested-dict
shape of `Settings.scraper_rate_limits`; `resolve_rate_limit(settings,
source)` returns the effective config (operator override > class-attr
fallback).

Shape:
    Settings.scraper_rate_limits: dict[str, dict[str, float]]
        keyed by `JobSource.value`; value is `{"rpm", "delay_lo", "delay_hi"}`.

Fallback table mirrors the class-attr values shipped on each site scraper
in `src/scraper/sites/*.py` at `0.2.0.07`. Keeping the table here keeps the
resolver self-contained — site scrapers can ship without rate-limit logic
leaking into their modules.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from models import JobSource

if TYPE_CHECKING:
    from models import Settings

log = logging.getLogger(__name__)


class RateLimitConfig(BaseModel):
    """Operator-tunable rate-limit knobs for one source.

    `rpm` floor = 0.1 (≤ 1 req per 10min); ceiling = 600 (≤ 10 req/sec, well
    past anything we'd ever set). `delay_*` ceilings = 600s = 10 minutes,
    plenty of headroom for slow sources.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    rpm: float = Field(ge=0.1, le=600.0)
    delay_lo: float = Field(ge=0.0, le=600.0)
    delay_hi: float = Field(ge=0.0, le=600.0)

    @model_validator(mode="after")
    def _delay_order(self) -> RateLimitConfig:
        if self.delay_lo > self.delay_hi:
            raise ValueError("delay_lo must be <= delay_hi")
        return self


# Class-attr fallback table — the conservative-by-design defaults shipped
# with each site scraper. Kept in sync with `src/scraper/sites/*.py` class
# attrs; LinkedIn promoted from `1` (int floor) to `0.4` (effective 24/hr)
# per plan 38 § D.8.
_CLASS_ATTR_FALLBACK: dict[str, RateLimitConfig] = {
    JobSource.LINKEDIN.value: RateLimitConfig(rpm=0.4, delay_lo=3.0, delay_hi=7.0),
    JobSource.WORKDAY.value: RateLimitConfig(rpm=2.0, delay_lo=20.0, delay_hi=40.0),
    JobSource.GREENHOUSE.value: RateLimitConfig(rpm=20.0, delay_lo=1.5, delay_hi=3.0),
    JobSource.LEVER.value: RateLimitConfig(rpm=20.0, delay_lo=1.5, delay_hi=3.0),
    JobSource.ASHBY.value: RateLimitConfig(rpm=20.0, delay_lo=1.5, delay_hi=3.0),
    JobSource.INDEED.value: RateLimitConfig(rpm=2.0, delay_lo=20.0, delay_hi=40.0),
}

# Last-resort default for sources without a fallback entry — keeps the
# resolver total-function for any JobSource value.
_DEFAULT_FALLBACK = RateLimitConfig(rpm=30.0, delay_lo=1.0, delay_hi=3.0)


def resolve_rate_limit(settings: Settings, source: JobSource) -> RateLimitConfig:
    """Return the effective `RateLimitConfig` for one (settings, source).

    Three branches:
    1. Operator override present + valid → return it.
    2. Operator override present + invalid → log warning + fall through to
       the class-attr fallback. Don't let a misconfigured Settings entry
       block the scraper.
    3. No operator override → class-attr fallback.
    """
    overrides = settings.scraper_rate_limits or {}
    if not isinstance(overrides, dict):
        # Corrupted JSONB row or test fixture passing a non-dict — treat as
        # "no overrides" rather than crash the scraper.
        overrides = {}
    raw = overrides.get(source.value)
    if raw is not None:
        try:
            return RateLimitConfig.model_validate(raw)
        except ValidationError as exc:
            log.warning(
                "invalid rate_limit_config for source=%s; falling back: %s",
                source.value,
                exc,
            )
    return _CLASS_ATTR_FALLBACK.get(source.value, _DEFAULT_FALLBACK)


__all__ = ["RateLimitConfig", "resolve_rate_limit"]
