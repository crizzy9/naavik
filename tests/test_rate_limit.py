"""Per-user rate limiter — plan 75 / 0.3.3.02 + 0.3.3.06.

Unit-tests the `RateLimit` sliding-window primitive + the two module
singletons. FastAPI route integration is covered by the dep wiring tests
at the bottom of the file (no live HTTP — exercises the dep function
directly with a mocked `User`).
"""

from __future__ import annotations

import os

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")

from datetime import UTC, datetime, timedelta  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from services import rate_limit as rl  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_limiters():
    rl.reset_all()
    yield
    rl.reset_all()


# ── RateLimit primitive ──────────────────────────────────────────────────


def test_ratelimit_allows_under_threshold() -> None:
    limiter = rl.RateLimit(window=timedelta(minutes=1), threshold=3)
    for _ in range(2):
        assert limiter.is_limited(1) is False
        limiter.record(1)
    # 2 recorded; still under threshold.
    assert limiter.is_limited(1) is False


def test_ratelimit_blocks_at_threshold() -> None:
    limiter = rl.RateLimit(window=timedelta(minutes=1), threshold=3)
    for _ in range(3):
        limiter.record(1)
    assert limiter.is_limited(1) is True


def test_ratelimit_isolates_users() -> None:
    limiter = rl.RateLimit(window=timedelta(minutes=1), threshold=3)
    for _ in range(3):
        limiter.record(1)
    assert limiter.is_limited(1) is True
    assert limiter.is_limited(2) is False


def test_ratelimit_evicts_expired_entries(monkeypatch) -> None:
    """Sliding window: events older than `window` get popped from the deque."""
    limiter = rl.RateLimit(window=timedelta(minutes=1), threshold=3)

    base = datetime(2026, 5, 21, 10, 0, 0, tzinfo=UTC)

    class _Clock:
        now = base

    def _fake_now(_tz=None):
        return _Clock.now

    monkeypatch.setattr(rl, "datetime", _FakeDatetime(_Clock))

    limiter.record(1)
    limiter.record(1)
    limiter.record(1)
    assert limiter.is_limited(1) is True
    # Advance 65s — all 3 entries fall out of the 1-min window.
    _Clock.now = base + timedelta(seconds=65)
    assert limiter.is_limited(1) is False


class _FakeDatetime:
    """Shim so monkeypatching `rl.datetime.now` works on the bound name."""

    def __init__(self, clock):
        self._clock = clock

    def now(self, tz=None):
        return self._clock.now


def test_ratelimit_reset_specific_user() -> None:
    limiter = rl.RateLimit(window=timedelta(minutes=1), threshold=3)
    for _ in range(3):
        limiter.record(1)
        limiter.record(2)
    limiter.reset(user_id=1)
    assert limiter.is_limited(1) is False
    assert limiter.is_limited(2) is True


def test_ratelimit_reset_all_users() -> None:
    limiter = rl.RateLimit(window=timedelta(minutes=1), threshold=3)
    for _ in range(3):
        limiter.record(1)
        limiter.record(2)
    limiter.reset()
    assert limiter.is_limited(1) is False
    assert limiter.is_limited(2) is False


# ── Dep wiring tests — rescore ──────────────────────────────────────────


class _FakeUser:
    """Stand-in for `models.User` — only `.id` is read by the limiter."""

    def __init__(self, user_id: int):
        self.id = user_id


@pytest.mark.asyncio
async def test_check_rescore_rate_limit_allows_under_threshold() -> None:
    user = _FakeUser(user_id=1)
    # 9 calls under the 10/min cap pass.
    for _ in range(9):
        await rl.check_rescore_rate_limit(_user=user)


@pytest.mark.asyncio
async def test_check_rescore_rate_limit_blocks_at_threshold() -> None:
    user = _FakeUser(user_id=1)
    for _ in range(10):
        await rl.check_rescore_rate_limit(_user=user)
    with pytest.raises(HTTPException) as exc_info:
        await rl.check_rescore_rate_limit(_user=user)
    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == "60"  # 1 min


@pytest.mark.asyncio
async def test_check_rescore_rate_limit_skips_fake_session() -> None:
    """`_user=None` is the fake-session bypass — no limit enforced."""
    for _ in range(50):
        await rl.check_rescore_rate_limit(_user=None)


# ── Dep wiring tests — generate-bundle ───────────────────────────────────


@pytest.mark.asyncio
async def test_check_generate_bundle_rate_limit_blocks_at_threshold() -> None:
    user = _FakeUser(user_id=1)
    for _ in range(10):
        await rl.check_generate_bundle_rate_limit(_user=user)
    with pytest.raises(HTTPException) as exc_info:
        await rl.check_generate_bundle_rate_limit(_user=user)
    assert exc_info.value.status_code == 429
    assert exc_info.value.headers["Retry-After"] == "3600"  # 1 hr


@pytest.mark.asyncio
async def test_rescore_and_generate_bundle_limits_are_isolated() -> None:
    """Hitting the rescore limit does NOT block generate-bundle (different bucket)."""
    user = _FakeUser(user_id=1)
    for _ in range(10):
        await rl.check_rescore_rate_limit(_user=user)
    # Rescore 11th would 429; generate-bundle should still pass.
    with pytest.raises(HTTPException):
        await rl.check_rescore_rate_limit(_user=user)
    await rl.check_generate_bundle_rate_limit(_user=user)


@pytest.mark.asyncio
async def test_generate_bundle_rate_limit_isolates_users() -> None:
    user1 = _FakeUser(user_id=1)
    user2 = _FakeUser(user_id=2)
    for _ in range(10):
        await rl.check_generate_bundle_rate_limit(_user=user1)
    # User 1 is at cap; user 2 should still pass.
    await rl.check_generate_bundle_rate_limit(_user=user2)
    with pytest.raises(HTTPException):
        await rl.check_generate_bundle_rate_limit(_user=user1)
