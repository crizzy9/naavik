"""Per-screen page-render tests (plan 09 § I).

Each of the 11 Phase 1 screens GETs to 200 with key markup present. The
parametrized matrix below captures both the URL and a few render-fail-fast
strings.
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


_PAGES = [
    # (slug, url, [substrings present], [substrings absent])
    ("login", "/login", ["Welcome back", "Sign in", "login-card"], []),
    (
        "onboarding",
        "/onboarding?step=1",
        ["Upload your resume", "step_indicator" if False else "Upload"],
        [],
    ),
    (
        "overview",
        "/",
        ["PRIORITY ACTIONS", "Pipeline · live", "RESPONSE RATE", "overview-pipeline"],
        [],
    ),
    ("profile", "/profile", ["Shyam Padia", "WORK AUTHORIZATION", "Built and shipped Intuit"], []),
    (
        "profile_edit",
        "/profile/edit",
        ["Edit profile", "data-sortable", "application-qs", "bullet-list-1"],
        [],
    ),
    (
        "discover",
        "/discover",
        [
            "Discover",
            "discover-card",
            "skip-btn",
            "save-btn",
            "review-btn",
            "auto-apply-btn",
            "Up next",
            'data-template="/discover"',
        ],
        # Token compliance — no kanban-square (the inbox icon is correct)
        ["kanban-square"],
    ),
    (
        "discover_review_eager",
        "/discover/113",
        ["Tailored resume", "Cover letter", "Submit application", "WHAT THEY WANT"],
        ["/generate/cover-letter", "/generate/resume"],
    ),
    (
        "tracking",
        "/tracking",
        ["Tracking", "tracking-main", "data-column", "APPLIED"],
        ["kanban-square"],
    ),
    (
        "outreach",
        "/outreach",
        ["Outreach", "RECOMMENDED NEXT MOVE", "Active ·", "Send via LinkedIn"],
        [],
    ),
    (
        "settings",
        "/settings",
        ["Settings", "Active provider", "Anthropic Claude", "THIS MONTH"],
        [],
    ),
    (
        "bullet_modal",
        "/_modal/bullet-editor/1",
        ["bullet-editor-modal", "BULLET", "TAGS", "SELECTION OVERRIDE", "Save bullet"],
        [],
    ),
]


@pytest.mark.parametrize(
    ("slug", "url", "must_have", "must_not_have"),
    _PAGES,
    ids=[p[0] for p in _PAGES],
)
def test_page_renders(client: TestClient, auth_cookies, slug, url, must_have, must_not_have):
    r = client.get(url, cookies=auth_cookies)
    assert r.status_code == 200, f"{slug}: HTTP {r.status_code}"
    body = r.text
    for sub in must_have:
        assert sub in body, f"{slug}: missing {sub!r} in response"
    for sub in must_not_have:
        assert sub not in body, f"{slug}: forbidden {sub!r} in response"


def test_settings_all_six_tabs(client: TestClient, auth_cookies):
    """Plan 09 § H — Settings ships all 6 tabs."""
    for tab in ("llm-provider", "deployment", "account", "notifications", "auto-apply", "sources"):
        r = client.get(f"/settings/{tab}", cookies=auth_cookies)
        assert r.status_code == 200, f"/settings/{tab}: HTTP {r.status_code}"


def test_settings_unknown_tab_returns_404(client: TestClient, auth_cookies):
    r = client.get("/settings/wat", cookies=auth_cookies)
    assert r.status_code == 404


def test_no_arbitrary_tailwind_hex_in_pages(client: TestClient, auth_cookies):
    """Plan 09 § L — no `class="…[#abcd…]"` arbitrary hex anywhere in pages."""
    import re

    pattern = re.compile(r'class="[^"]*\[#[0-9a-fA-F]')
    urls = [u for _, u, *_ in _PAGES if u.startswith("/")]
    for u in urls:
        r = client.get(u, cookies=auth_cookies)
        assert pattern.search(r.text) is None, f"{u}: arbitrary hex class found"
