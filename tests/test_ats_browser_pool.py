"""ATSBrowserPool lifecycle + Semaphore bounds (plan 63 / 0.2.7.10 § C.3).

Real Playwright instances are NOT booted here — Chromium is not always
available in CI / pre-merge. We test the surface that doesn't need the
Browser: constructor validation, lifecycle idempotency, and the Semaphore
bound by patching `_browser` with a fake context-factory.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import pytest

from services.ats._browser_pool import ATSBrowserPool


class _FakeBrowser:
    """Stub `Browser` — `new_context()` returns a `_FakeContext` with a close hook."""

    def __init__(self) -> None:
        self.contexts_opened = 0
        self.contexts_closed = 0
        self.closed = False

    async def new_context(self, **kwargs: Any) -> _FakeContext:
        self.contexts_opened += 1
        return _FakeContext(self, kwargs)

    async def close(self) -> None:
        self.closed = True


class _FakeContext:
    def __init__(self, browser: _FakeBrowser, kwargs: dict[str, Any]) -> None:
        self._browser = browser
        self.kwargs = kwargs
        self.closed = False

    async def close(self) -> None:
        self._browser.contexts_closed += 1
        self.closed = True


@asynccontextmanager
async def _patched_pool(pool: ATSBrowserPool):
    """Replace `start()` with a no-op that just installs a `_FakeBrowser`."""
    fake = _FakeBrowser()

    async def fake_start() -> None:
        pool._started = True
        pool._browser = fake  # type: ignore[assignment]

    pool.start = fake_start  # type: ignore[assignment]
    try:
        yield fake
    finally:
        # `stop()` close()s the browser; ours just flips closed=True.
        await pool.stop()


def test_constructor_rejects_zero_concurrency():
    with pytest.raises(ValueError):
        ATSBrowserPool(max_concurrent_contexts=0)


def test_constructor_rejects_negative_concurrency():
    with pytest.raises(ValueError):
        ATSBrowserPool(max_concurrent_contexts=-1)


def test_constructor_default_concurrency_is_four():
    pool = ATSBrowserPool()
    # Semaphore's `_value` starts at the cap when no acquires in flight.
    assert pool._sem._value == 4  # type: ignore[attr-defined]


def test_constructor_custom_concurrency():
    pool = ATSBrowserPool(max_concurrent_contexts=2)
    assert pool._sem._value == 2  # type: ignore[attr-defined]


def test_pool_not_started_initially():
    pool = ATSBrowserPool()
    assert pool.started is False


@pytest.mark.asyncio
async def test_pool_idempotent_start():
    pool = ATSBrowserPool()
    async with _patched_pool(pool):
        await pool.start()
        first = pool._started
        await pool.start()  # idempotent — no re-launch
        assert first is True
        assert pool._started is True


@pytest.mark.asyncio
async def test_pool_stop_is_idempotent():
    pool = ATSBrowserPool()
    async with _patched_pool(pool):
        await pool.start()
    # Second stop() after the context-manager already called it — must not raise.
    await pool.stop()
    assert pool.started is False


@pytest.mark.asyncio
async def test_acquire_yields_fresh_context_each_call():
    pool = ATSBrowserPool()
    async with _patched_pool(pool) as fake:
        async with pool.acquire(board="workday"):
            pass
        async with pool.acquire(board="workday"):
            pass
        assert fake.contexts_opened == 2
        assert fake.contexts_closed == 2


@pytest.mark.asyncio
async def test_acquire_passes_user_agent_to_context():
    pool = ATSBrowserPool()
    async with _patched_pool(pool) as fake:
        async with pool.acquire(board="linkedin", user_agent="custom-UA/1.0") as ctx:
            assert ctx.kwargs["user_agent"] == "custom-UA/1.0"  # type: ignore[union-attr]
        # Default path picks from pool — never empty.
        async with pool.acquire(board="linkedin") as ctx:
            assert ctx.kwargs["user_agent"]  # type: ignore[union-attr]
        assert fake.contexts_opened == 2


@pytest.mark.asyncio
async def test_acquire_passes_default_viewport_to_context():
    pool = ATSBrowserPool()
    async with _patched_pool(pool), pool.acquire(board="indeed") as ctx:
        assert ctx.kwargs["viewport"] == {"width": 1440, "height": 900}  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_concurrent_acquires_respect_semaphore_cap():
    """Semaphore(2) — 3rd acquire blocks until one of the first two releases."""
    pool = ATSBrowserPool(max_concurrent_contexts=2)
    async with _patched_pool(pool):
        started = asyncio.Event()
        release_first_two = asyncio.Event()
        third_started = False

        async def hold(idx: int) -> None:
            nonlocal third_started
            async with pool.acquire(board=f"b{idx}"):
                if idx in (1, 2):
                    started.set() if idx == 1 else None
                    await release_first_two.wait()
                else:
                    third_started = True

        t1 = asyncio.create_task(hold(1))
        t2 = asyncio.create_task(hold(2))
        await started.wait()
        t3 = asyncio.create_task(hold(3))
        # Give the third task a chance to attempt entry — it must NOT have entered.
        await asyncio.sleep(0.05)
        assert third_started is False
        release_first_two.set()
        await asyncio.gather(t1, t2, t3)
        assert third_started is True


@pytest.mark.asyncio
async def test_acquire_closes_context_even_on_exception():
    pool = ATSBrowserPool()
    async with _patched_pool(pool) as fake:
        with pytest.raises(RuntimeError):
            async with pool.acquire(board="workday"):
                raise RuntimeError("boom")
        assert fake.contexts_closed == 1
