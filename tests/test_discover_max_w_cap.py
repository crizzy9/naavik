"""Plan 51 · 0.2.2.04 — Discover ultra-wide max-w cap.

Confirms the wrapper carries `2xl:max-w-[1400px]` + `2xl:mx-auto` so the swipe
card clamps to 1400px centered on 4K monitors (>= 1536px viewport). Width-
actual rendering is browser behavior (not unit-testable); template-string
assertion confirms the contract per the no-Playwright-on-NixOS convention.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1"}


def test_discover_carries_2xl_max_width_clamp(
    client: TestClient, auth_cookies: dict[str, str]
) -> None:
    """Wrapper must clamp to 1400px on 2xl+ (>=1536px) so 4K monitors don't sprawl."""
    body = client.get("/discover", cookies=auth_cookies).text
    assert "2xl:max-w-[1400px]" in body, (
        "0.2.2.04 · Discover wrapper must carry 2xl:max-w-[1400px] clamp"
    )


def test_discover_centers_clamp_horizontally(
    client: TestClient, auth_cookies: dict[str, str]
) -> None:
    """`2xl:mx-auto` keeps the clamped column centered, not left-aligned."""
    body = client.get("/discover", cookies=auth_cookies).text
    assert "2xl:mx-auto" in body, (
        "0.2.2.04 · Discover wrapper must carry 2xl:mx-auto to center the clamp"
    )
