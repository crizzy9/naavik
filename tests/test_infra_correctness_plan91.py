"""Plan 91 Phase 6 — infra correctness pins (6.1 retry ladder, 6.2 cost-cap
day boundary).

6.1: providers wrap raw SDK errors in `LLMProviderError` WITHOUT setting
`kind`, and `_classify_error` trusted `kind` blindly — so a 429 classified
as non-retryable "provider_error" and the retry ladder never fired. The fix
falls through to message sniffing when `kind` is the default.

6.2: `document_generator._today_spend` was a third competing spend
implementation using the operator's LOCAL calendar date mislabelled as UTC
(plus a `succeeded IS TRUE` filter the tracker doesn't apply). It now
delegates to the canonical `llm_tracker.today_cost_usd` (true UTC
midnight), preserved as a wrapper because tests patch it as the cost seam.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import select

from llm.base import LLMProviderError, StructuredResult
from models import ApiUsage, Settings, User
from services import llm_tracker
from services.llm_tracker import _classify_error, tracked_call
from tests._sqlite import sqlite_session, strip_pg_checks

_TABLES = strip_pg_checks((User, ApiUsage, Settings))


@pytest.fixture
async def session():
    async with sqlite_session(tables=_TABLES) as s:
        s.add(User(id=1, email="owner@t.test", password_hash="x"))
        await s.flush()
        yield s


class FlakyProvider:
    """Raises provider-wrapped SDK errors N times, then succeeds."""

    provider_id = "anthropic"
    model_name = "fake-model"

    def __init__(self, failures: int, message: str):
        self.failures = failures
        self.message = message
        self.calls = 0

    def estimate_cost(self, *, input_tokens: int, output_tokens: int, model=None) -> float:
        return 0.001

    async def structured(self, **_kw):
        self.calls += 1
        if self.calls <= self.failures:
            # Exactly how every provider wraps SDK errors: no kind set.
            raise LLMProviderError(self.message)
        value = {"ok": True}
        return StructuredResult(
            text=json.dumps(value),
            input_tokens=10,
            output_tokens=5,
            model="fake-model",
            value=value,
        )


# ── 6.1 — retry ladder ──────────────────────────────────────────────────


def test_classify_error_sniffs_default_kind_provider_errors():
    """Default-kind LLMProviderError falls through to message sniffing."""
    assert (
        _classify_error(LLMProviderError("anthropic structured failed: Error code: 429"))
        == "rate_limit"
    )
    assert (
        _classify_error(LLMProviderError("anthropic complete failed: request timed out"))
        == "timeout"
    )
    # A deliberately-set kind is still trusted verbatim.
    assert _classify_error(LLMProviderError("nope", kind="auth_required")) == "auth_required"
    # Truly unknown provider errors stay non-retryable.
    assert _classify_error(LLMProviderError("something odd happened")) == "provider_error"


@pytest.mark.asyncio
async def test_rate_limited_call_retries_with_backoff_and_succeeds(session):
    """A 429-wrapped provider error retries (with exponential backoff) and
    the call ultimately succeeds; every attempt lands an ApiUsage row."""
    provider = FlakyProvider(2, "anthropic structured failed: Error code: 429 - rate limit")
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    with patch("services.llm_tracker.asyncio.sleep", new=fake_sleep):
        result = await tracked_call(
            session=session,
            user_id=1,
            provider=provider,
            method="structured",
            prompt_name="retry_pin",
            prompt="p",
        )

    assert result.value == {"ok": True}
    assert provider.calls == 3
    assert sleeps == [1.0, 2.0]  # exponential backoff, base 1s

    rows = list((await session.exec(select(ApiUsage))).all())
    assert len(rows) == 3
    assert [r.succeeded for r in rows] == [False, False, True]
    assert {r.error_kind for r in rows[:2]} == {"rate_limit"}


@pytest.mark.asyncio
async def test_rate_limit_exhaustion_still_raises(session):
    """More failures than the ladder allows (3 for rate_limit) → raises."""
    provider = FlakyProvider(10, "anthropic structured failed: Error code: 429")
    with (
        patch("services.llm_tracker.asyncio.sleep", new=AsyncMock()),
        pytest.raises(LLMProviderError),
    ):
        await tracked_call(
            session=session,
            user_id=1,
            provider=provider,
            method="structured",
            prompt_name="retry_pin",
            prompt="p",
        )
    assert provider.calls == 4  # initial + 3 retries


# ── 6.2 — cost-cap day boundary ─────────────────────────────────────────


def _usage_row(*, cost: float, at: datetime, succeeded: bool = True) -> ApiUsage:
    return ApiUsage(
        user_id=1,
        provider="anthropic",
        model="m",
        method="structured",
        input_tokens=1,
        output_tokens=1,
        cost_usd=cost,
        latency_ms=1,
        succeeded=succeeded,
        occurred_at=at,
        created_at=at,
    )


@pytest.mark.asyncio
async def test_today_spend_uses_utc_midnight_boundary(session):
    """Yesterday's spend (UTC) is excluded; today's counts — including
    failed-call rows, matching the canonical tracker accounting."""
    from services import generation as dg

    now = datetime.now(UTC)
    utc_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    session.add(_usage_row(cost=5.0, at=utc_midnight - timedelta(minutes=1)))
    session.add(_usage_row(cost=1.0, at=utc_midnight + timedelta(minutes=1)))
    session.add(_usage_row(cost=0.5, at=now, succeeded=False))  # counted now
    await session.flush()

    spent = await dg._today_spend(session, 1)
    assert spent == pytest.approx(1.5)

    # And is_cost_capped compares against the same number.
    settings = Settings(user_id=1, created_at=now, updated_at=now)
    settings.daily_llm_cost_cap_usd = 1.4
    assert await dg.is_cost_capped(session, 1, settings) is True
    settings.daily_llm_cost_cap_usd = 1.6
    assert await dg.is_cost_capped(session, 1, settings) is False


@pytest.mark.asyncio
async def test_today_spend_delegates_to_canonical_tracker(session):
    """One accounting implementation: _today_spend == today_cost_usd."""
    from services import generation as dg

    now = datetime.now(UTC)
    session.add(_usage_row(cost=2.25, at=now))
    await session.flush()
    assert await dg._today_spend(session, 1) == await llm_tracker.today_cost_usd(session, user_id=1)


# ── 6.3 — stored fallback provider is wired ─────────────────────────────


class DeadProvider(FlakyProvider):
    """Always fails with a 500-flavoured provider error."""

    def __init__(self):
        super().__init__(10**6, "anthropic structured failed: 500 internal error")


@pytest.mark.asyncio
async def test_stored_fallback_provider_rescues_500_failures(session, monkeypatch):
    """Primary exhausts retries on a 500 → tracked_call resolves
    Settings.llm_fallback_provider and completes on the fallback."""
    import enum as _enum
    import json as _json

    from sqlalchemy import text as _text

    # Seed a Settings row with a fallback configured (raw SQL — ARRAY cols).
    now = datetime.now(UTC)
    s = Settings(user_id=1, created_at=now, updated_at=now)
    from models.enums import LLMProvider as LLMProviderEnum

    s.llm_fallback_provider = LLMProviderEnum.OLLAMA
    params = {}
    for col in Settings.__table__.columns:
        v = getattr(s, col.name, None)
        if isinstance(v, _enum.Enum):
            v = v.name
        elif isinstance(v, (list, dict)):
            v = _json.dumps(v)
        elif isinstance(v, datetime):
            v = v.isoformat(sep=" ")
        params[col.name] = v
    names = ", ".join(params)
    ph = ", ".join(f":{n}" for n in params)
    await session.execute(_text(f"INSERT INTO settings ({names}) VALUES ({ph})"), params)

    primary = DeadProvider()
    rescue = FlakyProvider(0, "unused")
    rescue.provider_id = "ollama"

    def fake_get_provider(user_settings, *, fallback=False):
        assert fallback is True
        return rescue

    monkeypatch.setattr("llm.get_provider", fake_get_provider)

    with patch("services.llm_tracker.asyncio.sleep", new=AsyncMock()):
        result = await tracked_call(
            session=session,
            user_id=1,
            provider=primary,
            method="structured",
            prompt_name="fallback_pin",
            prompt="p",
        )

    assert result.value == {"ok": True}
    assert rescue.calls == 1


@pytest.mark.asyncio
async def test_no_fallback_configured_still_raises(session):
    """No Settings row / no fallback set → the primary's error propagates."""
    primary = DeadProvider()
    with (
        patch("services.llm_tracker.asyncio.sleep", new=AsyncMock()),
        pytest.raises(LLMProviderError),
    ):
        await tracked_call(
            session=session,
            user_id=1,
            provider=primary,
            method="structured",
            prompt_name="fallback_pin",
            prompt="p",
        )
