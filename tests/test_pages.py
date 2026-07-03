"""Per-screen page-render tests (plan 09 § I).

Each of the 11 Phase 1 screens GETs to 200 with key markup present. The
parametrized matrix below captures both the URL and a few render-fail-fast
strings.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.uses_sample_data_shims


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
        [
            "Edit profile",
            "data-sortable",
            "application-qs",
            "bullet-list-1",
            # 0.7.0.48 fold-in for owner bug #4: explicit Save button replaces
            # the misleading static "Auto-saved · just now" indicator.
            'data-testid="profile-edit-save"',
            'id="profile-edit-form"',
            'hx-put="/api/v1/profile"',
        ],
        # The static "Auto-saved · just now" indicator was a lie — it rendered
        # the same string regardless of whether anything had saved. Gone.
        ["Auto-saved · just now", "Auto-saved"],
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
        # 2026-07 round 2: WHAT THEY WANT restored as the JD-requirements
        # column beside the judge's strengths/gaps verdict.
        [
            "Tailored resume",
            "Cover letter",
            "Submit application",
            "YOUR STRENGTHS",
            "WHAT THEY WANT",
        ],
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
        ["Settings", "Anthropic Claude", "THIS MONTH"],
        # Plan 70 (0.3.3.13): "Active provider" radio surface deleted; the
        # API-key env-presence card section is the single canonical surface.
        ["Active provider"],
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


def test_settings_all_seven_tabs(client: TestClient, auth_cookies, monkeypatch):
    """Plan 54 / 0.2.5 closeout — Settings now ships 7 tabs (adds `submissions`).

    `/settings/sources`, `/settings/submissions`, and `/settings/llm-provider`
    each `Depends(get_session)` (plans 49 + 54). Override + patch service
    layer so the test stays DB-independent.
    """
    from db.session import get_session
    from main import app
    from services import application_service, job_service, llm_tracker, settings_service

    class _NoopSession:
        async def commit(self):
            return None

        async def rollback(self):
            return None

        async def close(self):
            return None

    async def _fake_get_session():
        yield _NoopSession()

    def _fake_sql_settings():
        # Plan 69 (`0.3.3.12`) collapsed every Settings tab through
        # `_ctx_for_tab`, which now reads many more attributes than the
        # original SimpleNamespace covered. Build a real `models.Settings`
        # SQLModel instance from the shadow payload so every attribute
        # access resolves (shadow types lack SQLModel-only fields like
        # `linkedin_keywords`).
        from db import sample_data as sd
        from models import Settings as SQLSettings

        return SQLSettings.model_validate(sd.SETTINGS.model_dump())

    async def _fake_get_or_create(session, *, user_id):
        return _fake_sql_settings()

    async def _fake_runs(session, *, user_id):
        return {}

    async def _fake_recent_runs(session, *, user_id, limit=50):
        return []

    async def _fake_failures(session, *, user_id, since_days=30):
        return []

    async def _fake_today_cost(session, *, user_id):
        return 0.0

    monkeypatch.setattr(settings_service, "get_or_create", _fake_get_or_create)
    monkeypatch.setattr(job_service, "list_recent_scrape_runs_by_source", _fake_runs)
    monkeypatch.setattr(job_service, "list_recent_scrape_runs", _fake_recent_runs)
    monkeypatch.setattr(application_service, "aggregate_submission_failures", _fake_failures)
    monkeypatch.setattr(llm_tracker, "today_cost_usd", _fake_today_cost)

    # 0.7.0.48 fold-in — extending the loop to cover `security` (skipped pre-fix)
    # tripped _NoopSession not having `.exec`. Stub the security panel builder
    # so the route renders to base.html w/ sidebar without hitting the DB.
    from ui.routes import settings as settings_routes

    async def _fake_security_view(session, *, user_id):
        return {
            "active_key": None,
            "retiring_keys": [],
            "retired_count": 0,
            "rotation_days": 90,
            "rotation_grace_days": 7,
        }

    monkeypatch.setattr(settings_routes, "_build_security_view", _fake_security_view)
    app.dependency_overrides[get_session] = _fake_get_session
    try:
        # 0.7.0.48 fold-in (bug #3): every settings tab MUST return the full
        # base.html shell (sidebar included) even under HX-Request, because
        # `hx-boost="true"` on <body> sends every boosted nav with that header
        # and HTMX needs a full body in the response to do its swap. Five
        # routes (sources/submissions/llm-provider/generation/security) used
        # to return a partial when HX-Request: true — that stripped the sidebar
        # on click.
        for tab in (
            "llm-provider",
            "deployment",
            "account",
            "notifications",
            "auto-apply",
            "sources",
            "submissions",
            "generation",
            "security",
        ):
            for headers in ({}, {"HX-Request": "true", "HX-Boosted": "true"}):
                r = client.get(f"/settings/{tab}", cookies=auth_cookies, headers=headers)
                assert r.status_code == 200, (
                    f"/settings/{tab} headers={headers}: HTTP {r.status_code}"
                )
                body = r.text
                assert 'id="sidebar-drawer"' in body, (
                    f"/settings/{tab} headers={headers}: sidebar drawer missing — "
                    "hx-boost click would strip the sidebar"
                )
                assert "Naavik" in body, f"/settings/{tab} headers={headers}: lockup missing"
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_tracking_list_fragment_is_partial_not_full_page(client: TestClient, auth_cookies):
    """0.7.0.48 fold-in (bug #6): /_fragments/tracking/list MUST return the
    list partial only — NOT a full base.html page. view_toggle.html points
    HTMX at /_fragments/tracking/<view> precisely so the swap into
    `#tracking-main` doesn't inject a duplicate sidebar inside the existing
    layout. If this fragment regressed to extending base.html, the toggle
    would render a second sidebar nested in the page.
    """
    for view in ("board", "list"):
        r = client.get(f"/_fragments/tracking/{view}", cookies=auth_cookies)
        assert r.status_code == 200, f"/_fragments/tracking/{view}: HTTP {r.status_code}"
        body = r.text
        assert 'id="sidebar-drawer"' not in body, (
            f"/_fragments/tracking/{view}: sidebar drawer must NOT appear in the "
            "fragment response — it would render a duplicate sidebar when swapped "
            "into #tracking-main"
        )
        # Sanity check that the fragment IS returning the expected payload.
        if view == "list":
            assert "Company" in body, "list fragment missing list-table header"
        else:
            assert "data-column" in body, "board fragment missing column markers"


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


# ── Plan 10c (10c.2a) + 0.7.0.48 — signup CTA promotion ─────────────────


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


def test_login_signup_mode_renders_form(client: TestClient):
    """`/login?mode=signup` renders the signup form unconditionally (plan 0.7.0.48)."""
    r = client.get("/login?mode=signup")
    assert r.status_code == 200
    body = r.text
    assert 'hx-post="/api/v1/auth/signup"' in body
    assert "Create your account" in body
    assert 'data-signup-disabled-banner="true"' not in body


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


# ── Plan 26 (0.2.0.01) — Settings · Deployment vault banner gone ────────


def test_settings_deployment_never_renders_vault_locked_banner(
    client: TestClient,
    auth_cookies,
):
    """Plan 26: vault deleted; the rose vault-locked banner is gone forever."""
    r = client.get("/settings/deployment", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    assert 'data-vault-locked-banner="true"' not in body
    assert "Vault locked" not in body
    assert "SECRET_KEY mismatch" not in body
    assert "naavik vault rotate-key" not in body
    assert "~/.naavik/secrets.enc" not in body


def test_settings_deployment_on_disk_panel_lists_env_not_vault(
    client: TestClient,
    auth_cookies,
):
    """`_ON_DISK` panel surfaces .env instead of ~/.naavik/secrets.enc."""
    r = client.get("/settings/deployment", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    # No SECRETS row referencing the gone vault.
    assert "aes-256-gcm" not in body
    assert "secrets.enc" not in body
    # CONFIG row now points at .env.
    assert "env-loaded" in body


def test_settings_llm_tab_renders_env_indicators_not_api_key_input(
    client: TestClient,
    auth_cookies,
    monkeypatch,
):
    """Plan 26: API-key password input removed; env-presence indicators rendered.

    Plan 54 / 0.2.5.03: `/settings/llm-provider` is now its own route w/
    `Depends(get_session)` so the daily cost-cap widget can query ApiUsage.
    Override session + stub `today_cost_usd` for DB-free render.
    """
    from db.session import get_session
    from main import app
    from services import llm_tracker

    class _NoopSession:
        async def commit(self):
            return None

        async def rollback(self):
            return None

        async def close(self):
            return None

    async def _fake_get_session():
        yield _NoopSession()

    async def _fake_today_cost(session, *, user_id):
        return 0.0

    monkeypatch.setattr(llm_tracker, "today_cost_usd", _fake_today_cost)
    app.dependency_overrides[get_session] = _fake_get_session
    try:
        r = client.get("/settings/llm-provider", cookies=auth_cookies)
        assert r.status_code == 200
        body = r.text
        # No password input or hidden api_key form field.
        assert 'name="api_key"' not in body
        assert 'name="ollama_base_url"' not in body
        # New env indicators present.
        assert 'data-env-indicator="anthropic"' in body
        assert "ANTHROPIC_API_KEY" in body
        assert "OPENAI_API_KEY" in body
        assert "OLLAMA_BASE_URL" in body
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_settings_notifications_tab_renders_env_indicators_not_inputs(
    client: TestClient,
    auth_cookies,
):
    """Plan 26: Discord/Telegram inputs removed; env-presence indicators rendered."""
    r = client.get("/settings/notifications", cookies=auth_cookies)
    assert r.status_code == 200
    body = r.text
    # No password input or text input for the secret values.
    assert 'name="discord_webhook_url"' not in body
    assert 'name="telegram_bot_token"' not in body
    # Indicators + env-var hints present.
    assert 'data-channel="discord"' in body
    assert 'data-channel="telegram"' in body
    assert "DISCORD_WEBHOOK_URL" in body
    assert "TELEGRAM_BOT_TOKEN" in body


# ── 0.7.0.48 fold-in (owner bugs #7 + #8): sign out + favicon ──────────


def test_sidebar_has_signout_button(client: TestClient, auth_cookies):
    """Owner bug #7 — Sign out affordance lives in the sidebar bottom block,
    wired to POST /api/v1/auth/logout. No CSRF wiring needed (the logout
    endpoint is intentionally permissive — it just clears the cookies).
    """
    body = client.get("/", cookies=auth_cookies).text
    assert 'data-testid="sidebar-signout"' in body, (
        "Owner bug #7: sidebar must render a Sign out affordance"
    )
    assert 'hx-post="/api/v1/auth/logout"' in body, (
        "Sign out button must POST to the logout endpoint"
    )
    assert 'data-lucide="log-out"' in body


def test_base_html_links_favicon(client: TestClient, auth_cookies):
    """Owner bug #8 — `<link rel="icon">` must point at /static/favicon.svg
    on every authed page so the browser stops 404'ing /favicon.ico fallback.
    """
    body = client.get("/", cookies=auth_cookies).text
    assert '<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">' in body


def test_favicon_ico_route_returns_svg(client: TestClient):
    """Owner bug #8 — /favicon.ico legacy browser request returns the SVG
    so we don't generate a 404 every page load.
    """
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/svg+xml"
    assert r.text.startswith("<svg")
