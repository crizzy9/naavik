"""Wave 6 — portfolio_sync tests.

Per plan 10 § E. Coverage:
- /api/portfolio/cv filters EEO/visa/salary
- CORS allowlist works (default crypticsoul.dev; configurable)
- Netlify webhook fires (mocked) on Profile-update path
- Generic resume regen + cached path
- Debounced timer coalesces rapid edits
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from services import portfolio_sync as ps
from services.portfolio_sync import (
    assert_no_pii,
    cors_allowed_origins,
    is_cors_allowed,
    portfolio_resume_path,
    public_cv_payload,
    regenerate_generic_resume,
    schedule_debounced_regen,
    trigger_netlify_rebuild,
)


def _profile():
    from datetime import UTC, datetime

    return SimpleNamespace(
        id=1,
        user_id=1,
        full_name="Shyam Padia",
        headline="Senior Software Engineer",
        current_company="Intuit",
        location="Boston, MA",
        portfolio_url="crypticsoul.dev",
        github_handle="crizzy9",
        linkedin_handle="shyampadia",
        email="shyam@example.com",  # filtered
        phone="+1 555 555 0100",  # filtered
        salary_expectation_usd=200000,  # filtered
        veteran_status="not_veteran",  # filtered
        disability_status="no",  # filtered
        race_ethnicity="asian",  # filtered
        gender_identity="male",  # filtered
        work_authorization="h1b",  # filtered
        visa_sponsorship_needed="needed_now",  # filtered
        willing_to_relocate="open",  # filtered
        notice_period_days=14,  # filtered
        earliest_start=datetime(2026, 6, 1, tzinfo=UTC),  # filtered
        summary_full="Long form",
        summary_short="Short form",
        open_to_opportunities=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _settings(**kw):
    base = {
        "portfolio_cors_allowed_origins": ["https://crypticsoul.dev"],
    }
    base.update(kw)
    return SimpleNamespace(**base)


# ── Public CV filtering ─────────────────────────────────────────────


def test_public_cv_filters_pii_and_eeo_and_visa_and_salary():
    payload = public_cv_payload(_profile())
    profile_dict = payload["profile"]
    # PII
    assert "email" not in profile_dict
    assert "phone" not in profile_dict
    # Compensation
    assert "salary_expectation_usd" not in profile_dict
    # EEO
    for k in ("veteran_status", "disability_status", "race_ethnicity", "gender_identity"):
        assert k not in profile_dict
    # Visa
    for k in ("work_authorization", "visa_sponsorship_needed"):
        assert k not in profile_dict
    # Operational
    for k in ("willing_to_relocate", "notice_period_days", "earliest_start"):
        assert k not in profile_dict
    # Public fields preserved
    assert profile_dict["full_name"] == "Shyam Padia"
    assert profile_dict["headline"] == "Senior Software Engineer"
    assert profile_dict["location"] == "Boston, MA"
    assert profile_dict["portfolio_url"] == "crypticsoul.dev"


def test_public_cv_serializes_experiences():
    from datetime import UTC, datetime

    profile = _profile()
    exp = SimpleNamespace(
        company="Intuit",
        title="Senior Engineer",
        team=None,
        location="Mountain View",
        start_date=datetime(2020, 7, 1, tzinfo=UTC),
        end_date=None,
        summary_short="Personalization platform",
    )
    payload = public_cv_payload(profile, experiences=[exp])
    assert len(payload["experiences"]) == 1
    e = payload["experiences"][0]
    assert e["company"] == "Intuit"
    assert e["title"] == "Senior Engineer"
    assert e["start_date"].startswith("2020-07-01")


def test_assert_no_pii_raises_if_filtered_field_leaks():
    with pytest.raises(ValueError):
        assert_no_pii({"profile": {"email": "x@y.com"}})


def test_assert_no_pii_passes_clean_payload():
    assert_no_pii({"profile": {"full_name": "x", "headline": "y"}})


# ── CORS ────────────────────────────────────────────────────────────


def test_cors_allowed_origins_returns_list():
    s = _settings(portfolio_cors_allowed_origins=["https://example.com", "https://crypticsoul.dev"])
    assert cors_allowed_origins(s) == ["https://example.com", "https://crypticsoul.dev"]


def test_cors_allowed_origins_filters_empty_strings():
    s = _settings(portfolio_cors_allowed_origins=["", "https://x.com", ""])
    assert cors_allowed_origins(s) == ["https://x.com"]


def test_is_cors_allowed_default_crypticsoul():
    s = _settings()
    assert is_cors_allowed(s, "https://crypticsoul.dev") is True
    assert is_cors_allowed(s, "https://other-origin.com") is False
    assert is_cors_allowed(s, None) is False


def test_is_cors_allowed_after_self_hoster_edits_origins():
    s = _settings(
        portfolio_cors_allowed_origins=["https://my-portfolio.example", "https://crypticsoul.dev"]
    )
    assert is_cors_allowed(s, "https://my-portfolio.example") is True
    assert is_cors_allowed(s, "https://crypticsoul.dev") is True


# ── Cached portfolio resume path ────────────────────────────────────


def test_portfolio_resume_path_under_data_dir():
    p = portfolio_resume_path()
    assert p.name == "resume.pdf"
    assert p.parent.name == "portfolio"
    assert p.parent.parent.name == "documents"


# ── Generic resume regen ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_regenerate_generic_resume_calls_generator(tmp_path):
    settings = _settings()
    out = tmp_path / "documents" / "portfolio" / "resume.pdf"

    async def fake_gen(session, *, user_id, settings, output_path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"%PDF-fake")
        return SimpleNamespace(byte_size=8, page_count=1)

    with patch(
        "services.portfolio_sync.portfolio_resume_path", return_value=out
    ):
        result = await regenerate_generic_resume(
            settings=settings, generate_fn=fake_gen
        )
    assert result == out
    assert out.exists()


@pytest.mark.asyncio
async def test_regenerate_generic_resume_handles_failure(tmp_path):
    settings = _settings()
    out = tmp_path / "fail.pdf"

    async def failing_gen(*a, **kw):
        raise RuntimeError("compile bombed")

    with patch(
        "services.portfolio_sync.portfolio_resume_path", return_value=out
    ):
        result = await regenerate_generic_resume(
            settings=settings, generate_fn=failing_gen
        )
    assert result is None


# ── Netlify webhook ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trigger_netlify_no_op_when_url_missing():
    with patch("services.portfolio_sync.vault_svc.get", return_value=None):
        ok = await trigger_netlify_rebuild()
    assert ok is False


@pytest.mark.asyncio
async def test_trigger_netlify_posts_when_configured():
    captured = {}

    def _handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = json.loads(req.read())
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    with patch(
        "services.portfolio_sync.vault_svc.get",
        return_value="https://api.netlify.com/build_hooks/abc",
    ):
        ok = await trigger_netlify_rebuild(http_client=client)
    await client.aclose()
    assert ok is True
    assert captured["url"].endswith("/build_hooks/abc")
    assert captured["body"]["trigger"] == "naavik-profile-update"


@pytest.mark.asyncio
async def test_trigger_netlify_returns_false_on_5xx():
    def _handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    with patch(
        "services.portfolio_sync.vault_svc.get",
        return_value="https://hook/x",
    ):
        ok = await trigger_netlify_rebuild(http_client=client)
    await client.aclose()
    assert ok is False


# ── Debounce coalescing ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schedule_debounced_regen_coalesces_rapid_calls():
    """Three rapid calls within the debounce window → one execution."""
    settings = _settings()
    call_count = 0

    async def fake_regen(**kw):
        nonlocal call_count
        call_count += 1

    async def fake_netlify(**kw):
        return True

    # Drain any prior debounce state.
    if ps._debounce_handle is not None:
        ps._debounce_handle.cancel()
        ps._debounce_handle = None

    with (
        patch("services.portfolio_sync.regenerate_generic_resume", new=fake_regen),
        patch("services.portfolio_sync.trigger_netlify_rebuild", new=fake_netlify),
    ):
        # 3 rapid calls; each resets the timer to 0.05s out.
        for _ in range(3):
            schedule_debounced_regen(
                settings=settings,
                delay_seconds=0.05,
                fire_netlify=True,
            )
            await asyncio.sleep(0.01)
        # Wait long enough for the debounce timer to fire.
        await asyncio.sleep(0.2)
        # Wait for the spawned task to finish.
        if ps._debounce_task is not None:
            with contextlib.suppress(Exception):
                await ps._debounce_task
    assert call_count == 1, f"expected 1 regen call, got {call_count}"
