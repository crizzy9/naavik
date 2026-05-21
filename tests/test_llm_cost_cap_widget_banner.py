"""Tests for `_llm_cost_cap_widget.html` severity-gated banner (plan 74 / 0.3.2.04).

Goal: verify the cost-cap widget's new judge-skipped fallback banner —
- `judge_skipped_count_today == 0` → no banner.
- `judge_skipped_count_today` in 1-3 → Variant A inline treatment.
- `judge_skipped_count_today >= 4` → Variant B prominent strip + SPENT /
  CAP / RESUMES stat grid + CTAs.

Render path: Settings · LLM Provider tab via the FastAPI TestClient.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app)


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1"}


def _patch_widget_ctx(
    monkeypatch,
    *,
    count: int,
    reasons: dict[str, int],
    today_cost: float = 0.0,
) -> None:
    """Stub `llm_tracker` helpers + the per-request session for the LLM tab.

    The conftest autouse fixture already overrides `get_session` to yield a
    `_NoopSession`; we layer per-test stubs on top.
    """
    from services import llm_tracker

    async def _today(session, *, user_id):
        return today_cost

    async def _count(session, *, user_id):
        return count

    async def _reasons(session, *, user_id):
        return dict(reasons)

    monkeypatch.setattr(llm_tracker, "today_cost_usd", _today)
    monkeypatch.setattr(llm_tracker, "judge_skipped_count_today", _count)
    monkeypatch.setattr(llm_tracker, "judge_skipped_reasons_today", _reasons)


def test_zero_count_renders_no_banner(
    client: TestClient,
    auth_cookies,
    monkeypatch,
) -> None:
    _patch_widget_ctx(monkeypatch, count=0, reasons={})
    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    assert 'data-judge-paused="none"' in body
    assert 'data-judge-paused-banner="inline"' not in body
    assert 'data-judge-paused-banner="prominent"' not in body
    assert "LLM judge paused" not in body


def test_low_count_renders_inline_variant_a(
    client: TestClient,
    auth_cookies,
    monkeypatch,
) -> None:
    _patch_widget_ctx(
        monkeypatch,
        count=2,
        reasons={"cost_cap_exhausted": 2},
    )
    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    assert 'data-judge-paused="inline"' in body
    assert 'data-judge-paused-banner="inline"' in body
    # Prominent banner must NOT render at count=2.
    assert 'data-judge-paused-banner="prominent"' not in body
    assert "LLM judge paused" in body
    assert "2" in body
    assert "cost cap exhausted" in body


def test_low_count_singular_copy(
    client: TestClient,
    auth_cookies,
    monkeypatch,
) -> None:
    _patch_widget_ctx(
        monkeypatch,
        count=1,
        reasons={"no_provider_configured": 1},
    )
    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    assert 'data-judge-paused="inline"' in body
    # "1 job" singular form.
    assert "job scored without LLM tier today" in body
    assert "no provider configured" in body


def test_high_count_renders_prominent_variant_b(
    client: TestClient,
    auth_cookies,
    monkeypatch,
) -> None:
    _patch_widget_ctx(
        monkeypatch,
        count=7,
        reasons={"cost_cap_exhausted": 7},
        today_cost=0.50,
    )
    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    assert 'data-judge-paused="prominent"' in body
    assert 'data-judge-paused-banner="prominent"' in body
    # Inline variant should NOT also render at count>=4.
    assert 'data-judge-paused-banner="inline"' not in body
    assert "LLM judge paused" in body
    # Stat grid cells present.
    assert ">SPENT<" in body
    assert ">CAP<" in body
    assert ">RESUMES<" in body
    # CTA to raise the cap.
    assert "Raise cap in .env" in body
    assert 'data-judge-paused-cta="raise-cap"' in body


def test_high_count_mixed_reasons_copy(
    client: TestClient,
    auth_cookies,
    monkeypatch,
) -> None:
    _patch_widget_ctx(
        monkeypatch,
        count=8,
        reasons={"cost_cap_exhausted": 5, "no_provider_configured": 3},
    )
    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    assert 'data-judge-paused="prominent"' in body
    # Mixed reasons surface both counts.
    assert "5" in body
    assert "3" in body
    assert "Daily cost cap exhausted" in body
    assert "no provider configured" in body


def test_four_count_promotes_to_prominent(
    client: TestClient,
    auth_cookies,
    monkeypatch,
) -> None:
    """Severity-gating boundary — count == 4 promotes to Variant B."""
    _patch_widget_ctx(
        monkeypatch,
        count=4,
        reasons={"cost_cap_exhausted": 4},
    )
    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    assert 'data-judge-paused="prominent"' in body
    assert 'data-judge-paused-banner="prominent"' in body


def test_three_count_stays_inline(
    client: TestClient,
    auth_cookies,
    monkeypatch,
) -> None:
    """Severity-gating boundary — count == 3 stays Variant A inline."""
    _patch_widget_ctx(
        monkeypatch,
        count=3,
        reasons={"cost_cap_exhausted": 3},
    )
    r = client.get("/settings/llm-provider", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    assert 'data-judge-paused="inline"' in body
    assert 'data-judge-paused-banner="prominent"' not in body
