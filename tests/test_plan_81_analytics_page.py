"""Plan 81 § D.4 — analytics page route tests.

These ride on the conftest autouse `_patch_services_to_sample_data` fixture,
which patches `application_analytics.compute_kpis` to a controlled return
value — see `_patch_analytics` below. Separated from
`test_plan_81_application_analytics.py` (which uses real sqlite) so the
two test surfaces don't fight over conftest scope.
"""

from __future__ import annotations

import os

os.environ.setdefault("NAAVIK_DEBUG", "1")
os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

pytestmark = pytest.mark.uses_sample_data_shims

_CSRF_TOKEN = "csrf-cookie-token-plan-81-anpage-eeeeeeee"


@pytest.fixture
def patched_client(monkeypatch) -> TestClient:
    """Patch the analytics service to return a deterministic KPI digest."""
    from services.applications import analytics as svc

    async def _fake_kpis(_session, *, user_id, window_days=90):
        return svc.ApplicationKpis(
            window_days=window_days,
            applied_in_window=12,
            response_rate=0.5,
            onsite_rate=0.25,
            offer_rate=0.083,
            funnel=svc.FunnelCounts(applied=12, recruiter=6, onsite=3, offer=1),
        )

    async def _fake_by_company(_session, *, user_id, window_days=90, limit=10):
        return [
            svc.CompanyKpi(
                company="Acme",
                applied=5,
                response_rate=0.6,
                onsite_rate=0.4,
                offer_rate=0.2,
            ),
            svc.CompanyKpi(
                company="Beta",
                applied=3,
                response_rate=0.33,
                onsite_rate=0.0,
                offer_rate=0.0,
            ),
        ]

    async def _fake_by_role_family(_session, *, user_id, window_days=90):
        return {
            "backend": {
                "applied": 8,
                "response_rate": 0.5,
                "onsite_rate": 0.25,
                "offer_rate": 0.0,
            },
            "ai-ml": {
                "applied": 4,
                "response_rate": 0.5,
                "onsite_rate": 0.25,
                "offer_rate": 0.25,
            },
        }

    async def _fake_by_tag(_session, *, user_id, window_days=90):
        return {
            "platform": {
                "applied": 6,
                "response_rate": 0.33,
                "onsite_rate": 0.16,
                "offer_rate": 0.0,
            },
        }

    monkeypatch.setattr(svc, "compute_kpis", _fake_kpis)
    monkeypatch.setattr(svc, "kpis_by_company", _fake_by_company)
    monkeypatch.setattr(svc, "kpis_by_role_family", _fake_by_role_family)
    monkeypatch.setattr(svc, "kpis_by_tag", _fake_by_tag)

    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    c.cookies.set("naavik_session", "fake-1")
    c.cookies.set("naavik_csrf", _CSRF_TOKEN)
    return c


def test_tracking_analytics_page_renders(patched_client: TestClient) -> None:
    """GET /tracking/analytics renders 4-KPI strip + funnel + company table +
    role-family + tag breakdowns (plan 86 R3 round 2)."""
    r = patched_client.get("/tracking/analytics")
    assert r.status_code == 200
    body = r.text
    assert 'data-testid="analytics-kpi-strip"' in body
    assert 'data-testid="analytics-funnel-card"' in body
    assert 'data-testid="analytics-company-table"' in body
    # Plan 86 R3 round 2 — role-family + tag breakdown sections.
    assert 'data-testid="analytics-role-family-table"' in body
    assert 'data-testid="analytics-tag-table"' in body
    assert "Tracking · Analytics" in body
    # The mocked applied count surfaces in the strip
    assert ">12<" in body
    # Top company surfaces in the table
    assert "Acme" in body
    assert "Beta" in body
    # Role-family + tag bucket labels surface from the fixtures.
    assert "backend" in body
    assert "ai-ml" in body
    assert "platform" in body


def test_tracking_analytics_route_order_precedence(patched_client: TestClient) -> None:
    """`/tracking/analytics` (literal) MUST resolve before `/tracking/{id}`.

    If the int-coerced dynamic route shadowed it, FastAPI would 404 with
    "Application not found" instead of rendering the analytics page.
    """
    r = patched_client.get("/tracking/analytics")
    assert r.status_code == 200, (
        "If this hits the dynamic /tracking/{application_id} route it'll 404. Route order matters."
    )
    assert "analytics-kpi-strip" in r.text


def test_tracking_analytics_unauth_redirects_to_login() -> None:
    """No session cookie → 307 + Location: /login (same as other tracking routes)."""
    from main import app

    c = TestClient(app, raise_server_exceptions=True)
    r = c.get("/tracking/analytics", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers.get("location") == "/login"


def test_tracking_main_links_to_analytics(patched_client: TestClient) -> None:
    """The /tracking page surfaces the Analytics nav link."""
    r = patched_client.get("/tracking")
    assert r.status_code == 200
    assert 'data-testid="tracking-analytics-link"' in r.text
    assert 'href="/tracking/analytics"' in r.text
