"""RateLimitConfig + resolver tests — plan 38 § D.1.

Validator + fallback + settings round-trip.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from models import JobSource
from scraper.rate_limit import (
    _CLASS_ATTR_FALLBACK,
    _DEFAULT_FALLBACK,
    RateLimitConfig,
    resolve_rate_limit,
)

pytestmark = pytest.mark.uses_sample_data_shims

# ── RateLimitConfig validator ─────────────────────────────────────────────


def test_validates_canonical_shape():
    cfg = RateLimitConfig(rpm=0.4, delay_lo=3.0, delay_hi=7.0)
    assert cfg.rpm == 0.4
    assert cfg.delay_lo == 3.0
    assert cfg.delay_hi == 7.0


def test_rejects_unknown_extra_field():
    """`extra=forbid` keeps the schema closed against typos."""
    with pytest.raises(ValidationError):
        RateLimitConfig.model_validate({"rpm": 1.0, "delay_lo": 1.0, "delay_hi": 3.0, "burst": 5})


def test_rejects_rpm_below_floor():
    with pytest.raises(ValidationError):
        RateLimitConfig(rpm=0.05, delay_lo=1.0, delay_hi=3.0)


def test_rejects_rpm_above_ceiling():
    with pytest.raises(ValidationError):
        RateLimitConfig(rpm=1000.0, delay_lo=1.0, delay_hi=3.0)


def test_rejects_negative_delay():
    with pytest.raises(ValidationError):
        RateLimitConfig(rpm=1.0, delay_lo=-1.0, delay_hi=3.0)


def test_rejects_delay_lo_greater_than_hi():
    with pytest.raises(ValidationError):
        RateLimitConfig(rpm=1.0, delay_lo=5.0, delay_hi=3.0)


def test_accepts_delay_lo_equal_to_hi():
    """Equal lo + hi (no jitter) is a legitimate config."""
    cfg = RateLimitConfig(rpm=1.0, delay_lo=3.0, delay_hi=3.0)
    assert cfg.delay_lo == cfg.delay_hi


# ── _CLASS_ATTR_FALLBACK ──────────────────────────────────────────────────


def test_fallback_table_covers_six_production_sources():
    expected = {
        JobSource.LINKEDIN.value,
        JobSource.WORKDAY.value,
        JobSource.GREENHOUSE.value,
        JobSource.LEVER.value,
        JobSource.ASHBY.value,
        JobSource.INDEED.value,
    }
    assert set(_CLASS_ATTR_FALLBACK.keys()) == expected


def test_linkedin_fallback_is_subhourly():
    """LinkedIn fallback uses 0.4 rpm (research § 5 - <=24/hr)."""
    cfg = _CLASS_ATTR_FALLBACK[JobSource.LINKEDIN.value]
    assert cfg.rpm == 0.4
    assert cfg.delay_lo == 3.0
    assert cfg.delay_hi == 7.0


def test_indeed_fallback_is_conservative():
    cfg = _CLASS_ATTR_FALLBACK[JobSource.INDEED.value]
    assert cfg.rpm == 2.0
    assert cfg.delay_lo == 20.0
    assert cfg.delay_hi == 40.0


# ── resolve_rate_limit ────────────────────────────────────────────────────


def _make_settings(scraper_rate_limits: dict | None = None):
    return SimpleNamespace(scraper_rate_limits=scraper_rate_limits or {})


def test_resolver_falls_back_when_no_override():
    s = _make_settings()
    cfg = resolve_rate_limit(s, JobSource.LINKEDIN)
    assert cfg.rpm == 0.4


def test_resolver_falls_back_when_source_key_missing():
    """Operator configured Indeed but not LinkedIn → LinkedIn uses fallback."""
    s = _make_settings({"indeed": {"rpm": 4.0, "delay_lo": 10.0, "delay_hi": 20.0}})
    cfg = resolve_rate_limit(s, JobSource.LINKEDIN)
    assert cfg.rpm == 0.4


def test_resolver_uses_operator_override_when_valid():
    s = _make_settings({"linkedin": {"rpm": 1.5, "delay_lo": 2.0, "delay_hi": 4.0}})
    cfg = resolve_rate_limit(s, JobSource.LINKEDIN)
    assert cfg.rpm == 1.5
    assert cfg.delay_lo == 2.0
    assert cfg.delay_hi == 4.0


def test_resolver_falls_back_on_invalid_override(caplog):
    """A malformed override logs + returns the fallback, never raises."""
    s = _make_settings({"linkedin": {"rpm": 0.0, "delay_lo": 1.0, "delay_hi": 2.0}})
    with caplog.at_level("WARNING", logger="scraper.rate_limit"):
        cfg = resolve_rate_limit(s, JobSource.LINKEDIN)
    # rpm=0.0 is < 0.1 floor → invalid → fallback.
    assert cfg.rpm == 0.4
    assert any("invalid rate_limit_config" in rec.message for rec in caplog.records)


def test_resolver_falls_back_on_delay_inversion(caplog):
    s = _make_settings({"workday": {"rpm": 2.0, "delay_lo": 30.0, "delay_hi": 5.0}})
    with caplog.at_level("WARNING", logger="scraper.rate_limit"):
        cfg = resolve_rate_limit(s, JobSource.WORKDAY)
    assert cfg.rpm == 2.0
    assert cfg.delay_lo == 20.0  # Falls back to class-attr.
    assert any("invalid rate_limit_config" in rec.message for rec in caplog.records)


def test_resolver_handles_empty_dict_settings():
    """`scraper_rate_limits = {}` (default after migration) returns fallback."""
    s = _make_settings({})
    cfg = resolve_rate_limit(s, JobSource.GREENHOUSE)
    assert cfg.rpm == 20.0


def test_resolver_handles_none_scraper_rate_limits():
    """Defensive: pre-migration row carrying None for the column still resolves."""
    s = SimpleNamespace(scraper_rate_limits=None)
    cfg = resolve_rate_limit(s, JobSource.LEVER)
    assert cfg.rpm == 20.0


def test_resolver_unknown_source_returns_default_fallback():
    """A `JobSource` value not in the fallback table returns sensible defaults."""
    s = _make_settings()
    cfg = resolve_rate_limit(s, JobSource.MANUAL)
    assert cfg.rpm == _DEFAULT_FALLBACK.rpm


@pytest.mark.parametrize(
    "hostile",
    ["not-a-dict", [], ["linkedin"], 42, True],
    ids=["string", "empty-list", "list", "int", "bool"],
)
def test_resolver_handles_non_dict_scraper_rate_limits(hostile):
    """Corrupted JSONB row (non-dict) falls back instead of AttributeError."""
    s = SimpleNamespace(scraper_rate_limits=hostile)
    cfg = resolve_rate_limit(s, JobSource.LINKEDIN)
    assert cfg.rpm == 0.4  # Class-attr fallback, no crash.


# ── Settings round-trip via settings_service.update_sources ──────────────


@pytest.mark.asyncio
async def test_update_sources_validates_and_persists_rate_limits():
    """`update_sources(scraper_rate_limits=...)` validates each entry."""
    from services import settings as settings_service

    class _FakeSession:
        def __init__(self):
            self.added: list = []
            self.flush_count = 0

        def add(self, obj):
            self.added.append(obj)

        async def flush(self):
            self.flush_count += 1

        async def exec(self, _stmt):
            return SimpleNamespace(one_or_none=lambda: None)

    # SQLModel construction inside test avoids the FastAPI app boot path.
    from models import Settings

    session = _FakeSession()
    # Pre-stub get_or_create to skip DB.
    out = Settings(user_id=1)

    async def fake_get_or_create(_s, _u):
        return out

    settings_service.get_or_create = fake_get_or_create  # type: ignore[assignment]
    updated = await settings_service.update_sources(
        session,  # type: ignore[arg-type]
        1,
        scraper_rate_limits={
            "linkedin": {"rpm": 1.0, "delay_lo": 2.0, "delay_hi": 4.0},
            "indeed": {"rpm": 3.0, "delay_lo": 10.0, "delay_hi": 20.0},
        },
    )
    assert updated.scraper_rate_limits["linkedin"]["rpm"] == 1.0
    assert updated.scraper_rate_limits["indeed"]["delay_hi"] == 20.0


@pytest.mark.asyncio
async def test_update_sources_rejects_invalid_rate_limits():
    """Validation surfaces as `ValidationError`; nothing gets persisted."""
    from services import settings as settings_service

    class _FakeSession:
        def add(self, obj):
            pass

        async def flush(self):
            pass

    from models import Settings

    out = Settings(user_id=1)

    async def fake_get_or_create(_s, _u):
        return out

    settings_service.get_or_create = fake_get_or_create  # type: ignore[assignment]
    with pytest.raises(ValidationError):
        await settings_service.update_sources(
            _FakeSession(),  # type: ignore[arg-type]
            1,
            scraper_rate_limits={
                "linkedin": {"rpm": 0.0, "delay_lo": 1.0, "delay_hi": 3.0},
            },
        )
