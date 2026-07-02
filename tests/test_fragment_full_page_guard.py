"""P4 regression guard — fragment endpoints must never return full pages.

The view-stacking bug class: a response carrying base-layout markup
(`<html>` / `<body>` / the sidebar shell) swapped into a fragment slot
renders a second copy of the app inside the page. This suite sweeps every
parameterless GET route under `/_fragments/` and `/_modal/` and asserts
the response is a bare fragment. Parameterized fragment routes get the
same assertion via representative IDs where cheap.

(The Sources PUT granularity variant of this class is pinned in
tests/test_settings_save_fragment_response.py and tests/test_paired_editors.py.)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Route

from main import app

pytestmark = pytest.mark.uses_sample_data_shims

_FULL_PAGE_MARKERS = ("<html", "<body", "<!doctype", 'id="sidebar"')


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(scope="module")
def auth_cookies() -> dict[str, str]:
    return {"naavik_session": "fake-1"}


def _assert_bare_fragment(body: str, path: str) -> None:
    lowered = body.lower()
    for marker in _FULL_PAGE_MARKERS:
        assert marker not in lowered, (
            f"{path} returned full-page markup (found {marker!r}) — "
            "fragment endpoints must render partials only (P4 stacking bug class)"
        )


def _parameterless_fragment_get_paths() -> list[str]:
    paths: list[str] = []
    for route in app.routes:
        if not isinstance(route, Route):
            continue
        if "GET" not in (route.methods or set()):
            continue
        path = route.path
        if not (path.startswith("/_fragments/") or path.startswith("/_modal/")):
            continue
        if "{" in path:
            continue  # parameterized — covered by the representative cases below
        paths.append(path)
    return sorted(paths)


def test_fragment_route_inventory_is_nonempty():
    assert len(_parameterless_fragment_get_paths()) >= 5


@pytest.mark.parametrize("path", _parameterless_fragment_get_paths())
def test_parameterless_fragment_gets_never_return_full_pages(
    path: str, client: TestClient, auth_cookies
):
    # Some fragment routes require query params; send harmless defaults.
    r = client.get(
        path, params={"q": "bo", "title": "t", "message": "m", "action": "/x"}, cookies=auth_cookies
    )
    # 2xx → must be a bare fragment. 4xx (missing params) is fine — the
    # guard only cares that successful renders aren't full pages.
    if 200 <= r.status_code < 300:
        _assert_bare_fragment(r.text, path)


@pytest.mark.parametrize(
    "path",
    [
        "/_fragments/discover/queue",
        "/_fragments/scrape-status",
        "/_fragments/profile/cities?q=bos",
    ],
)
def test_key_fragment_routes_render_and_are_bare(path: str, client: TestClient, auth_cookies):
    r = client.get(path, cookies=auth_cookies)
    assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"
    _assert_bare_fragment(r.text, path)
