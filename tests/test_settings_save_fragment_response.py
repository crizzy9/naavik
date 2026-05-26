"""Settings PUT handlers return a tiny `#settings-save-result` fragment
(0.7.0.48 W4 — owner UX consolidation).

Before this change, LLM + Generation PUTs re-rendered the full tab partial
on the form path. The common Save button targets `#settings-save-result`
(an aria-live region in the page header), so each writable settings PUT
returns a small emerald `Saved · …` fragment instead — the form re-render
is no longer needed because the page DOM stays static.

Coverage: each writable settings PUT returns a 200 with the saved fragment
and does NOT contain the full-partial markers (`<form`, `<aside`, etc.).
The Account PUT path now goes through the real handler (replacing the
`ui/routes/settings.py:put_account` stub that returned `{"ok": True}`).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app)


_CSRF = "x" * 48


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1", "naavik_csrf": _CSRF}


@pytest.fixture(scope="module")
def csrf_headers() -> dict[str, str]:
    return {"X-CSRF-Token": _CSRF}


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
def _patch_services(monkeypatch):
    """Stub the settings + profile services so each PUT path hits the
    fragment-return branch without touching the DB."""
    from db import sample_data as sd
    from db.session import get_session
    from main import app
    from services import profile_service, settings_service

    async def _stub_update_llm(session, **kwargs):
        return sd.SETTINGS

    async def _stub_update_generation(session, **kwargs):
        return sd.SETTINGS

    async def _stub_update_auto_apply(session, **kwargs):
        return sd.SETTINGS

    async def _stub_update_notifications(session, **kwargs):
        return sd.SETTINGS

    async def _stub_update_sources(session, **kwargs):
        return sd.SETTINGS

    async def _stub_get_or_create(session, *, user_id):
        return sd.SETTINGS

    async def _stub_update_field(session, *, user_id, field, value):
        return None

    monkeypatch.setattr(settings_service, "update_llm", _stub_update_llm)
    monkeypatch.setattr(settings_service, "update_generation", _stub_update_generation)
    monkeypatch.setattr(settings_service, "update_auto_apply", _stub_update_auto_apply)
    monkeypatch.setattr(settings_service, "update_notifications", _stub_update_notifications)
    monkeypatch.setattr(settings_service, "update_sources", _stub_update_sources)
    monkeypatch.setattr(settings_service, "get_or_create", _stub_get_or_create)
    monkeypatch.setattr(profile_service, "update_field", _stub_update_field)
    # Plan 0.7.0.48 W4 (2026-05-26): `put_llm` / `put_notifications` /
    # `put_account` now enforce `require_csrf` (defense-in-depth fold-in
    # per round-5 reviewer pair). Override so the existing tests don't
    # need to craft a double-submit token roundtrip per request.
    from api.auth import require_csrf

    def _csrf_pass() -> None:
        return None

    app.dependency_overrides[get_session] = _fake_get_session
    app.dependency_overrides[require_csrf] = _csrf_pass
    yield
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(require_csrf, None)


def _assert_fragment(text: str, *, must_have_savedness: bool = True):
    """Common assertions for every save-fragment response: emerald color,
    'Saved' wording, NO full-partial sentinel markers."""
    if must_have_savedness:
        assert "text-emerald-300" in text, f"missing saved color class:\n{text[:200]}"
        assert "Saved" in text, f"missing 'Saved' wording:\n{text[:200]}"
    # The fragment must NOT carry full-partial markers — its job is to
    # update the tiny `#settings-save-result` aria-live region only.
    assert "<form" not in text, f"fragment leaked <form (full partial?):\n{text[:300]}"
    assert "<aside" not in text, f"fragment leaked <aside (full partial?):\n{text[:300]}"


def test_put_llm_form_returns_save_fragment(client: TestClient, auth_cookies):
    r = client.put(
        "/api/v1/settings/llm",
        data={"llm_provider": "ollama", "llm_model": "llama3.1:8b"},
        cookies=auth_cookies,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text[:300]
    _assert_fragment(r.text)


def test_put_generation_form_returns_save_fragment(client: TestClient, auth_cookies, csrf_headers):
    r = client.put(
        "/api/v1/settings/generation",
        data={"generation_tier": "free"},
        cookies=auth_cookies,
        headers={**csrf_headers, "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text[:300]
    _assert_fragment(r.text)


def test_put_auto_apply_form_returns_save_fragment(client: TestClient, auth_cookies, csrf_headers):
    r = client.put(
        "/api/v1/settings/auto-apply",
        data={"auto_apply_score_threshold": "0.85"},
        cookies=auth_cookies,
        headers={**csrf_headers, "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text[:300]
    _assert_fragment(r.text)


def test_put_notifications_form_returns_save_fragment(client: TestClient, auth_cookies):
    # notifications endpoint has no CSRF dep (pre-existing pattern).
    r = client.put(
        "/api/v1/settings/notifications",
        data={"notify_threshold": "0.75"},
        cookies=auth_cookies,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text[:300]
    _assert_fragment(r.text)


def test_put_sources_form_returns_full_partial_not_fragment(
    client: TestClient, auth_cookies, csrf_headers, monkeypatch
):
    """Sources tab is an exception to the fragment-response pattern: it
    has no common Save button (active_save_endpoint=None) + the per-source
    rate-limit + keywords popover editors each swap `_settings_sources.html`
    via `hx-target="closest [data-source-editor]"`. Returning a fragment
    here would break the popover re-render (regression caught by
    test_paired_editors.py)."""
    from ui.routes import settings as settings_routes

    async def _fake_sources_view(session, *, user_id):
        return []

    async def _fake_recent_runs(session, *, user_id):
        return []

    monkeypatch.setattr(settings_routes, "_build_sources_view", _fake_sources_view)
    monkeypatch.setattr(settings_routes, "_recent_scrape_runs_view", _fake_recent_runs)

    r = client.put(
        "/api/v1/settings/sources",
        data={"source": "linkedin", "linkedin": "on"},
        cookies=auth_cookies,
        headers={**csrf_headers, "Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text[:300]
    # Full partial returns include the section heading.
    assert "Job sources" in r.text or "Recent scraper runs" in r.text


def test_put_account_form_returns_save_fragment_replacing_stub(client: TestClient, auth_cookies):
    """Pre-0.7.0.48 W4 the account-PUT was a stub returning `{"ok": True}`
    without persisting. The new handler walks the form, routes whitelisted
    fields through profile_service.update_field, returns the fragment.
    """
    r = client.put(
        "/api/v1/settings/account",
        data={"full_name": "Engineer Test", "email": "engineer@test.example"},
        cookies=auth_cookies,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text[:300]
    _assert_fragment(r.text)
    # Bulk-PUT contract: report saved field count.
    assert "2 fields" in r.text


def test_put_account_json_still_returns_json(client: TestClient, auth_cookies):
    """JSON callers (non-HTMX) get a JSON envelope, not the HTML fragment."""
    r = client.put(
        "/api/v1/settings/account",
        json={"full_name": "Engineer Test"},
        cookies=auth_cookies,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body.get("ok") is True
    assert body.get("saved") == ["full_name"]


def test_put_account_rejects_unknown_field(client: TestClient, auth_cookies):
    """Unknown fields are silently skipped (not 422'd) — mirrors the
    `put_profile_bulk` whitelist filter pattern."""
    r = client.put(
        "/api/v1/settings/account",
        data={"full_name": "Engineer", "rogue_field": "ignored"},
        cookies=auth_cookies,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200
    _assert_fragment(r.text)
    # Only the whitelisted field counted.
    assert "1 field" in r.text and "fields" not in r.text.replace("field</span>", "")


# ── CSRF enforcement regression — plan 0.7.0.48 W4 reviewer fold-in 2026-05-26 ──


def _without_csrf_override(test_fn):
    """Decorator: temporarily pop the autouse fixture's `require_csrf`
    override so the wrapped test exercises the real gate. Restored after
    the test runs (the autouse cleanup re-pops anyway, so this is safe).
    """
    import functools

    @functools.wraps(test_fn)
    def wrapper(*args, **kwargs):
        from api.auth import require_csrf
        from main import app

        saved = app.dependency_overrides.pop(require_csrf, None)
        try:
            return test_fn(*args, **kwargs)
        finally:
            if saved is not None:
                app.dependency_overrides[require_csrf] = saved

    return wrapper


@_without_csrf_override
def test_put_llm_csrf_enforced(client: TestClient):
    """Regression: `put_llm` MUST gate on `require_csrf`. Pre-W4-reviewer
    fold-in this route was missing the dep (architect + hacker LOW). Test
    asserts the gate fires when the CSRF dep is NOT overridden.
    """
    r = client.put(
        "/api/v1/settings/llm",
        data={"llm_provider": "anthropic"},
        cookies={"naavik_session": "fake-1"},
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"
    assert "CSRF" in r.text


@_without_csrf_override
def test_put_notifications_csrf_enforced(client: TestClient):
    """Regression: `put_notifications` MUST gate on `require_csrf`."""
    r = client.put(
        "/api/v1/settings/notifications",
        data={"notify_threshold": "80"},
        cookies={"naavik_session": "fake-1"},
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"
    assert "CSRF" in r.text


@_without_csrf_override
def test_put_account_csrf_enforced(client: TestClient):
    """Regression: `put_account` (new in W4) MUST gate on `require_csrf`."""
    r = client.put(
        "/api/v1/settings/account",
        data={"full_name": "Anything"},
        cookies={"naavik_session": "fake-1"},
    )
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"
    assert "CSRF" in r.text
