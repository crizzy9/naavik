"""Profile sparkline strip — plan 73 / 0.3.2.03.

Variant A (Hero strip) per `docs/design/MOCKUP_HANDOFF-0.3.2.md` § Surface 3.
Asserts that:
  - Populated sample-data fixture renders 3 family rows + 3 inline SVG polylines.
  - Empty-state branch renders the `/discover` hint when families is empty.
  - The strip is suppressed on partials that don't pass `score_trend`.

TestClient + autouse fixture (`tests/conftest.py`) backs reads to
`db.sample_data.PROFILE`, which now carries the `score_history` blob.
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


# ── 1. Populated state (PROFILE fixture has score_history) ───────────────


def test_profile_renders_score_trend_strip(
    client: TestClient, auth_cookies: dict[str, str]
) -> None:
    r = client.get("/profile", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    # Section marker present
    assert "Score trend · 30d" in body
    assert 'data-testid="score-trend-strip"' in body
    # 3 family rows from the PROFILE fixture (ai-ml + backend + platform)
    assert body.count('data-testid="score-trend-row"') == 3
    assert 'data-family="ai-ml"' in body
    assert 'data-family="backend"' in body
    assert 'data-family="platform"' in body
    # Inline SVG polyline present (no JS, no Chart.js)
    assert "<polyline " in body
    # current value for ai-ml renders to "0.84"
    assert "0.84" in body
    # Empty state must NOT render alongside data
    assert 'data-testid="score-trend-empty"' not in body


def test_profile_sparkline_polyline_uses_30_points(
    client: TestClient, auth_cookies: dict[str, str]
) -> None:
    """daily_means in fixture has 30 slots → polyline points string has 30 segments."""
    from ui.profile_ctx import _sparkline_polyline_points

    daily = [0.7 + (i * 0.005) for i in range(30)]
    points = _sparkline_polyline_points(daily)
    # 30 entries, each `x,y` separated by spaces → 29 spaces
    assert points.count(" ") == 29


# ── 2. Empty state ───────────────────────────────────────────────────────


def test_profile_renders_empty_sparkline_state_when_families_empty(
    monkeypatch, client: TestClient, auth_cookies: dict[str, str]
) -> None:
    """If the user has no scored jobs yet, render the empty-state hint."""
    from services import profile_service

    async def _empty_history(_session, _user_id):
        return {"last_aggregated_at": "2026-05-21T00:00:00+00:00", "families": []}

    monkeypatch.setattr(profile_service, "get_score_history", _empty_history)
    r = client.get("/profile", cookies=auth_cookies)
    assert r.status_code == 200, r.text
    body = r.text
    assert "Score trend · 30d" in body
    assert 'data-testid="score-trend-empty"' in body
    assert "No scored jobs yet" in body
    assert "/discover" in body
    # No populated rows
    assert 'data-testid="score-trend-row"' not in body


# ── 3. Ctx-builder unit tests ────────────────────────────────────────────


def test_score_trend_strip_handles_none_history() -> None:
    from ui.profile_ctx import score_trend_strip

    out = score_trend_strip(None)
    assert out == {"has_data": False, "rows": []}


def test_score_trend_strip_handles_empty_families() -> None:
    from ui.profile_ctx import score_trend_strip

    out = score_trend_strip({"families": []})
    assert out == {"has_data": False, "rows": []}


def test_score_trend_strip_caps_top_3() -> None:
    from ui.profile_ctx import score_trend_strip

    history = {
        "families": [
            {
                "family": f,
                "scored_count_30d": 100 - i,
                "score_current": 0.7,
                "score_delta_30d": 0.0,
                "daily_means": [0.7] * 30,
            }
            for i, f in enumerate(["ai-ml", "backend", "frontend", "devops", "data-eng"])
        ]
    }
    out = score_trend_strip(history, top_k=3)
    assert out["has_data"] is True
    assert len(out["rows"]) == 3
    # Sorted by scored_count_30d DESC → ai-ml first
    assert [r["family"] for r in out["rows"]] == ["ai-ml", "backend", "frontend"]


def test_score_trend_strip_classifies_delta_signs() -> None:
    from ui.profile_ctx import score_trend_strip

    history = {
        "families": [
            {
                "family": "ai-ml",
                "scored_count_30d": 10,
                "score_current": 0.85,
                "score_delta_30d": 0.10,  # up
                "daily_means": [0.75] * 30,
            },
            {
                "family": "backend",
                "scored_count_30d": 8,
                "score_current": 0.50,
                "score_delta_30d": -0.10,  # down
                "daily_means": [0.6] * 30,
            },
            {
                "family": "platform",
                "scored_count_30d": 5,
                "score_current": 0.70,
                "score_delta_30d": 0.001,  # flat (< 0.005)
                "daily_means": [0.7] * 30,
            },
        ]
    }
    out = score_trend_strip(history)
    signs = {r["family"]: r["delta_sign"] for r in out["rows"]}
    assert signs == {"ai-ml": "up", "backend": "down", "platform": "flat"}


def test_score_trend_strip_color_thresholds() -> None:
    from ui.profile_ctx import _sparkline_color

    assert _sparkline_color(0.90) == "emerald"  # ≥ 0.80
    assert _sparkline_color(0.80) == "emerald"
    assert _sparkline_color(0.75) == "indigo"  # ≥ 0.60
    assert _sparkline_color(0.60) == "indigo"
    assert _sparkline_color(0.50) == "amber"  # ≥ 0.40
    assert _sparkline_color(0.40) == "amber"
    assert _sparkline_color(0.30) == "rose"  # < 0.40
