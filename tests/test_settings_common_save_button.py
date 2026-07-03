"""Settings common Save button (0.7.0.48 W4 — owner UX consolidation).

Owner directive: all 9 settings tabs should expose a single "Save changes"
button in the page header. Per-tab inputs belong to ONE form via the HTML5
`form="settings-active-form"` attribute; the button at the header submits
that form. Read-only tabs (deployment, submissions, security) hide the
button via `active_save_endpoint=None` in the route ctx.

Coverage:
  - Each writable tab renders `data-testid="settings-save"` + an enclosing
    `<form id="settings-active-form" hx-put="<endpoint>">`.
  - Read-only tabs render no Save button + no `settings-active-form` form.
  - The `#settings-save-result` aria-live region is always present.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app)


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1"}


class _NoopSession:
    async def commit(self):  # pragma: no cover
        return None

    async def rollback(self):  # pragma: no cover
        return None

    async def close(self):  # pragma: no cover
        return None


async def _fake_get_session():
    yield _NoopSession()


@pytest.fixture(autouse=True)
def _patch_db_dependencies(monkeypatch):
    """Stub session + the per-tab view helpers so the settings GET routes
    don't need a live DB. Mirrors the pattern in test_settings_llm_form.py
    + test_settings_sources_route.py."""
    from db.session import get_session
    from main import app
    from services import llm_tracker
    from ui.routes import settings as settings_routes

    async def _fake_today_cost(session, *, user_id):
        return 0.0

    async def _fake_sources_view(session, *, user_id):
        return []

    async def _fake_recent_runs(session, *, user_id):
        return []

    async def _fake_submission_failures(session, *, user_id):
        return []

    async def _fake_security_view(session, *, user_id):
        return {
            "active_key": None,
            "retiring_keys": [],
            "retired_count": 0,
            "rotation_days": 90,
            "rotation_grace_days": 7,
        }

    monkeypatch.setattr(llm_tracker, "today_cost_usd", _fake_today_cost)
    monkeypatch.setattr(settings_routes, "_build_sources_view", _fake_sources_view)
    monkeypatch.setattr(settings_routes, "_recent_scrape_runs_view", _fake_recent_runs)
    monkeypatch.setattr(settings_routes, "_submission_failures_view", _fake_submission_failures)
    monkeypatch.setattr(settings_routes, "_build_security_view", _fake_security_view)
    app.dependency_overrides[get_session] = _fake_get_session
    yield
    app.dependency_overrides.pop(get_session, None)


# Per dispatch: tab-id → expected save endpoint (or None for read-only).
# 2026-07 consolidation: llm-provider / generation / auto-apply / submissions
# are now URL aliases for the merged AI & Automation page — all writable via
# the union endpoint.
_TAB_EXPECTATIONS = [
    ("account", "/api/v1/settings/account"),
    ("ai-automation", "/api/v1/settings/ai-automation"),
    ("llm-provider", "/api/v1/settings/ai-automation"),
    ("generation", "/api/v1/settings/ai-automation"),
    ("auto-apply", "/api/v1/settings/ai-automation"),
    ("submissions", "/api/v1/settings/ai-automation"),
    ("notifications", "/api/v1/settings/notifications"),
    ("sources", None),
    ("security", None),
    ("deployment", None),
]


@pytest.mark.parametrize(
    ("tab", "endpoint"), _TAB_EXPECTATIONS, ids=[t for t, _ in _TAB_EXPECTATIONS]
)
def test_each_tab_renders_common_save_button_iff_writable(
    client: TestClient, auth_cookies, tab: str, endpoint: str | None
):
    """data-testid="settings-save" present iff `active_save_endpoint` is set;
    enclosing `<form id="settings-active-form" hx-put="<endpoint>">` matches.
    """
    url = "/settings" if tab == "llm-provider" else f"/settings/{tab}"
    r = client.get(url, cookies=auth_cookies)
    assert r.status_code == 200, f"{tab}: status {r.status_code}\n{r.text[:500]}"
    body = r.text

    # aria-live save-result region always renders (header is shared).
    assert 'data-testid="settings-save-result"' in body, f"{tab}: aria-live region missing"

    if endpoint is None:
        # Read-only: NO save button + NO form id.
        assert 'data-testid="settings-save"' not in body, (
            f"{tab}: read-only tab should not render Save button"
        )
        assert 'id="settings-active-form"' not in body, (
            f"{tab}: read-only tab should not render settings-active-form"
        )
    else:
        # Writable: BOTH save button AND enclosing form must be present.
        assert 'data-testid="settings-save"' in body, f"{tab}: Save button missing"
        assert 'form="settings-active-form"' in body, (
            f"{tab}: Save button missing form= attr targeting common form"
        )
        assert 'id="settings-active-form"' in body, (
            f"{tab}: enclosing form id=settings-active-form missing"
        )
        assert f'hx-put="{endpoint}"' in body, f"{tab}: expected hx-put={endpoint!r} on common form"
        # Common form targets the shared save-result region.
        assert 'hx-target="#settings-save-result"' in body, (
            f"{tab}: common form should target #settings-save-result"
        )


def test_save_button_uses_form_attr_outside_form(client: TestClient, auth_cookies):
    """The shared Save button lives in the page header (outside the form
    block), wired via HTML5 `form="settings-active-form"` attr."""
    r = client.get("/settings", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    # Lazy assertion: the button block + the form id both exist, and the
    # button declares form= attr (HTML5 lets a submit button outside a form
    # fire that form via this attribute).
    assert 'form="settings-active-form"' in body
    assert 'id="settings-active-form"' in body
