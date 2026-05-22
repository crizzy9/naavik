"""Plan 57 / 0.2.7.13 — onboarding offline retry buffer.

Closes INTERACTIONS.md § H.3 deferred surface. On `htmx:sendError` for
mutating /api/v1/profile/* or /api/v1/onboarding/* requests, the script
queues the request in IndexedDB and drains on the `online` event /
DOMContentLoaded-after-reconnect.

Tests follow `test_base_js.py` pattern — pull the JS body via TestClient
and grep-assert. Browser-side IndexedDB round-trips (offline toggle →
queue → online → drain) are deferred to a Playwright follow-up
(`0.2.7.13a`); the existing project Playwright surface (`tests/visual/`)
is for screenshot capture, not behavioral DOM tests, and standing up an
IndexedDB driver harness exceeds the LOC budget for this row. The
script contract pinned here is sufficient to catch regression on the
core invariants (path gate, idempotency, listener wiring, queue ops).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims

os.environ.setdefault("NAAVIK_BCRYPT_COST", "4")
os.environ.setdefault("NAAVIK_DEBUG", "1")


@pytest.fixture(scope="module")
def client() -> TestClient:
    from main import app

    return TestClient(app, raise_server_exceptions=True)


def _offline_queue_js(client: TestClient) -> str:
    r = client.get("/static/offline_queue.js")
    assert r.status_code == 200, r.text
    return r.text


# ── script body invariants ────────────────────────────────────────────────


def test_offline_queue_js_served(client: TestClient) -> None:
    """`/static/offline_queue.js` is reachable via the StaticFiles mount."""
    body = _offline_queue_js(client)
    assert len(body) > 0


def test_offline_queue_path_gated_to_onboarding(client: TestClient) -> None:
    """Script exits immediately on non-onboarding pages (IndexedDB cost gate)."""
    body = _offline_queue_js(client)
    assert "window.location.pathname.startsWith('/onboarding')" in body


def test_offline_queue_idempotent_guard(client: TestClient) -> None:
    """Re-execution under hx-boost is a no-op (mirrors base.js guard)."""
    body = _offline_queue_js(client)
    assert "_naavikOfflineQueueLoaded" in body


def test_offline_queue_listens_for_send_error(client: TestClient) -> None:
    """Mutating-request capture wires on `htmx:sendError`."""
    body = _offline_queue_js(client)
    assert "htmx:sendError" in body
    assert "captureSendError" in body


def test_offline_queue_listens_for_online_event(client: TestClient) -> None:
    """Replay triggers on `online` event."""
    body = _offline_queue_js(client)
    assert "addEventListener('online'" in body
    assert "drainQueue" in body


def test_offline_queue_uses_indexeddb(client: TestClient) -> None:
    """Buffer is IndexedDB-backed (NOT localStorage, per plan rationale)."""
    body = _offline_queue_js(client)
    assert "indexedDB.open" in body
    assert "naavik_offline_queue" in body
    assert "localStorage" not in body, "plan rejects localStorage (5MB cap)"


def test_offline_queue_replay_restricted_to_safe_prefixes(client: TestClient) -> None:
    """Replay prefix allowlist — never replay arbitrary user requests."""
    body = _offline_queue_js(client)
    assert "/api/v1/profile" in body
    assert "/api/v1/onboarding" in body


def test_offline_queue_exponential_backoff(client: TestClient) -> None:
    """Backoff schedule 1/2/4/8/16s; max 5 retries."""
    body = _offline_queue_js(client)
    assert "MAX_RETRIES = 5" in body
    assert "[1000, 2000, 4000, 8000, 16000]" in body


def test_offline_queue_dispatches_drop_event(client: TestClient) -> None:
    """Final-drop dispatches `naavik:offline-queue-drop` for page toast hook."""
    body = _offline_queue_js(client)
    assert "naavik:offline-queue-drop" in body
    assert "CustomEvent" in body


def test_offline_queue_no_console_log(client: TestClient) -> None:
    """Shipped JS uses `console.warn` for errors only (matches base.js convention)."""
    body = _offline_queue_js(client)
    assert "console.log" not in body


def test_offline_queue_strict_mode(client: TestClient) -> None:
    """`'use strict'` declared at the top of the IIFE."""
    body = _offline_queue_js(client)
    assert "'use strict'" in body


# ── base.html script-tag gate ────────────────────────────────────────────


def test_offline_queue_loaded_on_onboarding_page(client: TestClient) -> None:
    """Script tag renders inside `/onboarding` page body."""
    r = client.get("/onboarding")
    assert r.status_code == 200, r.text
    assert "/static/offline_queue.js" in r.text


def test_offline_queue_NOT_loaded_on_login_page(client: TestClient) -> None:
    """Script tag is absent from `/login` page (path-gate at server side).

    auth_shell.html is shared between /login + /onboarding; the base.html
    Jinja gate restricts the script tag to the onboarding path.
    """
    r = client.get("/login")
    # /login may render via auth_shell.html (extends base.html); the gate is
    # on request.url.path so /login skips the script tag entirely.
    assert "/static/offline_queue.js" not in r.text


def test_offline_queue_NOT_loaded_on_discover_page(client: TestClient) -> None:
    """Discover page (different sidebar surface) skips the script tag."""
    r = client.get("/discover", follow_redirects=False)
    # /discover requires auth → 401/redirect; body still parseable. The
    # invariant being tested is that the gate applies to non-onboarding paths,
    # so even on the auth-rejected response the script tag must be absent.
    assert "/static/offline_queue.js" not in r.text
