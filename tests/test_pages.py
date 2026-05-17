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
    (
        "profile",
        "/profile",
        ["Shyam Padia", "ARE YOU AUTHORIZED TO WORK IN THE US?", "Built and shipped Intuit"],
        [],
    ),
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
            "discover-skip-btn",
            "discover-save-btn",
            "discover-review-btn",
            "discover-auto-apply-btn",
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


# ── Plan 10b (item 4) — login signup-mode toggle ─────────────────────────


def test_login_default_mode_is_signin(client: TestClient):
    r = client.get("/login")
    assert r.status_code == 200
    body = r.text
    assert "Welcome back" in body
    # Sign-up link still reachable from sign-in mode (plan 10c (10c.2a)
    # promoted it from the footer to a prominent CTA below the Sign-in
    # button — see test_login_signin_has_prominent_signup_link).
    assert "/login?mode=signup" in body
    assert "/login?create=1" not in body
    # Form posts to login, not signup.
    assert 'hx-post="/api/v1/auth/login"' in body


def test_login_signup_mode_renders_signup_form(client: TestClient):
    r = client.get("/login?mode=signup")
    assert r.status_code == 200
    body = r.text
    assert "Create your account" in body
    # Form posts to signup.
    assert 'hx-post="/api/v1/auth/signup"' in body
    # Plan 10c (10c.2a, 2026-05-11): sign-in CTA below the Submit button in
    # signup mode (replaces the old footer "Back to sign in" link).
    assert "Already have an account?" in body
    assert 'data-auth-mode-toggle="signin"' in body


def test_login_invalid_mode_rejected(client: TestClient):
    """Pattern-validated query param rejects garbage modes."""
    r = client.get("/login?mode=hax")
    # FastAPI returns 422 for query-param pattern validation failures.
    assert r.status_code == 422


# ── Plan 10c (10c.2) — signup CTA promotion + signup_disabled gate ───────


def test_login_signin_has_prominent_signup_link(client: TestClient):
    """The "Create account" CTA lives below the Sign-in button, NOT in
    the footer. Plan 10c (10c.2a, 2026-05-11) promotes it out of the
    footer so the operator finds it before scanning past the SSO card.
    """
    r = client.get("/login")
    assert r.status_code == 200
    body = r.text

    # The prominent CTA is a `<p data-auth-mode-toggle="signup">` rendered
    # inside the form (below the submit button), not inside `<footer>`.
    assert 'data-auth-mode-toggle="signup"' in body
    assert "First time?" in body

    # Surgical check: the footer block contains Docs + Source only — NO
    # signup link. Splice the footer out and assert "Create account" is
    # absent from THAT region. The link still appears elsewhere via the
    # prominent CTA above.
    footer_start = body.rfind("<footer")
    footer_end = body.find("</footer>", footer_start)
    assert footer_start > 0 and footer_end > footer_start, "footer block missing"
    footer_html = body[footer_start:footer_end]
    assert "Create account" not in footer_html, (
        "Plan 10c (10c.2a): footer must NOT contain the signup CTA — it "
        "moved to a prominent below-submit affordance."
    )
    assert "/login?mode=signup" not in footer_html


def test_login_signup_mode_renders_form_on_fresh_db(client: TestClient, monkeypatch):
    """On a fresh DB (no users), `/login?mode=signup` renders the signup form.

    Plan 10c (10c.2b, 2026-05-11): server-side `signup_disabled` is False
    when the User table is empty, so the form renders normally.
    """
    from ui.routes import auth as auth_routes

    async def _gate_false(_session):
        return False

    monkeypatch.setattr(auth_routes, "_compute_signup_disabled", _gate_false)

    r = client.get("/login?mode=signup")
    assert r.status_code == 200
    body = r.text
    assert 'hx-post="/api/v1/auth/signup"' in body
    assert "Create your account" in body
    assert 'data-signup-disabled-banner="true"' not in body


def test_login_signup_mode_renders_banner_on_seeded_db(client: TestClient, monkeypatch):
    """When `signup_disabled` is True (seeded single-user DB),
    `/login?mode=signup` renders an explanatory banner instead of the
    form so the operator doesn't submit a request that comes back 403.

    Plan 10c (10c.2b, 2026-05-11).
    """
    from ui.routes import auth as auth_routes

    async def _gate_true(_session):
        return True

    monkeypatch.setattr(auth_routes, "_compute_signup_disabled", _gate_true)

    r = client.get("/login?mode=signup")
    assert r.status_code == 200
    body = r.text

    assert 'data-signup-disabled-banner="true"' in body
    assert "This instance already has an account." in body
    assert "Settings · Deployment" in body
    # Form is suppressed.
    assert 'hx-post="/api/v1/auth/signup"' not in body
    # Lucide lock icon, stroke width 1.5 (DESIGN.md § Iconography).
    assert 'data-lucide="lock"' in body
    assert 'stroke-width="1.5"' in body


# ── Plan 18 (PC.6) — /auth/change-password page ─────────────────────────


def _fake_flagged_user():
    """Return an in-memory User flagged must_change_password=True. Used by
    `app.dependency_overrides[get_current_user]` to bypass DB lookup.
    """
    from models import User

    return User(
        id=1,
        email="dev@local",
        password_hash="$2b$04$placeholder.hash.for.test.only",
        is_active=True,
        is_admin=True,
        must_change_password=True,
    )


def _fake_unflagged_user():
    from models import User

    return User(
        id=1,
        email="dev@local",
        password_hash="$2b$04$placeholder.hash.for.test.only",
        is_active=True,
        is_admin=True,
        must_change_password=False,
    )


def test_change_password_page_renders_with_banner_when_flagged(client: TestClient):
    """Plan 18 (PC.6): when must_change_password=True, the amber banner +
    "Set a new password" heading + HTMX form wire show up.
    """
    from main import app
    from services.auth import get_current_user

    app.dependency_overrides[get_current_user] = _fake_flagged_user
    try:
        r = client.get("/auth/change-password")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert r.status_code == 200
    body = r.text
    assert "Change your password to continue" in body
    assert "Set a new password" in body
    assert 'hx-post="/api/v1/auth/change-password"' in body
    assert 'data-lucide="key-round"' in body
    assert 'data-must-change-banner="true"' in body


def test_change_password_page_no_banner_when_not_flagged(client: TestClient):
    """Voluntary change-password mode: no banner, "Change password" heading,
    "Back to Overview" affordance present.
    """
    from main import app
    from services.auth import get_current_user

    app.dependency_overrides[get_current_user] = _fake_unflagged_user
    try:
        r = client.get("/auth/change-password")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert r.status_code == 200
    body = r.text
    assert "Change your password to continue" not in body
    assert "← Back to Overview" in body
    assert 'data-must-change-banner="true"' not in body


# ── Plan 10b (item 7) — Settings · Deployment vault-locked banner ────────


def test_settings_deployment_no_banner_when_vault_unlocked(
    client: TestClient,
    auth_cookies,
    monkeypatch,
):
    """Banner stays hidden when the on-disk vault matches SECRET_KEY."""
    from services import vault as vault_svc

    monkeypatch.setattr(vault_svc, "is_locked", lambda: False)
    monkeypatch.setattr(vault_svc, "fingerprint", lambda: "deadbeef" * 4)
    monkeypatch.setattr(vault_svc, "expected_fingerprint", lambda: "deadbeef" * 4)

    r = client.get("/settings/deployment", cookies=auth_cookies)
    assert r.status_code == 200
    assert 'data-vault-locked-banner="true"' not in r.text
    assert "Vault locked" not in r.text


def test_settings_deployment_renders_vault_locked_banner(
    client: TestClient,
    auth_cookies,
    monkeypatch,
):
    """Banner shows fingerprints when SECRET_KEY no longer matches the vault."""
    from services import vault as vault_svc

    monkeypatch.setattr(vault_svc, "is_locked", lambda: True)
    monkeypatch.setattr(vault_svc, "fingerprint", lambda: "1111aaaa" * 4)
    monkeypatch.setattr(vault_svc, "expected_fingerprint", lambda: "2222bbbb" * 4)

    r = client.get("/settings/deployment", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    assert 'data-vault-locked-banner="true"' in body
    assert "Vault locked — SECRET_KEY mismatch" in body
    assert "1111aaaa" * 4 in body
    assert "2222bbbb" * 4 in body
    assert "naavik vault rotate-key" in body
