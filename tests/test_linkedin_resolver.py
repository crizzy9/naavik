"""LinkedIn apply-target resolver — guest parsing + authenticated extraction.

Tier A (`parse_guest_detail`) and the pure halves of Tier B
(`extract_apply_from_voyager`, `resolved_from_fetch`) are unit-tested here; the
browser session (`resolve_via_auth`) is driven with an injected fetcher, the
way the ATS adapter tests inject a stub Page. No network, no browser.
"""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_DEBUG", "1")

from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402

from services import resolution as asr  # noqa: E402
from services import resolution as lr  # noqa: E402

# ── fixtures ─────────────────────────────────────────────────────────────

_GUEST_OFFSITE = """
<html><body>
  <a href="https://www.linkedin.com/company/catapultsports?trk=public_jobs_topcard_logo"></a>
  <h2 class="top-card-layout__title">Senior Software Engineer (GO)</h2>
  <a class="topcard__link" href="https://www.linkedin.com/jobs/view/senior-software-engineer-go-at-catapult-4422894549?trk=public_jobs_topcard-title">Senior Software Engineer (GO)</a>
  <a href="https://www.linkedin.com/company/catapultsports?trk=public_jobs_topcard-org-name">Catapult</a>
  <button data-tracking-control-name="public_jobs_apply-link-offsite">Apply</button>
  <section class="show-more-less-html">
    <div>Catapult is building the future of sports performance technology.
    You will design and build backend services in Go. This is a long enough
    description to exceed the minimum replacement threshold for enrichment so
    it is treated as a real posting body and not a stub sentence.</div>
  </section>
</body></html>
"""

_GUEST_EASY_APPLY = """
<html><body>
  <a href="https://www.linkedin.com/company/acme?trk=public_jobs_topcard-org-name">Acme</a>
  <button data-tracking-control-name="public_jobs_apply-button">Easy Apply</button>
  <section class="show-more-less-html"><div>Native LinkedIn apply flow.</div></section>
</body></html>
"""


def _voyager_offsite(url="https://job-boards.greenhouse.io/catapultsports/jobs/7960837"):
    return {
        "data": {
            "applyMethod": {
                "com.linkedin.voyager.jobs.OffsiteApply": {
                    "companyApplyUrl": url,
                    "inPageOffsiteApply": False,
                }
            },
            "description": {"text": {"text": "Full authenticated JD for the Go role."}},
        }
    }


def _voyager_easy():
    return {
        "data": {
            "applyMethod": {
                "com.linkedin.voyager.jobs.ComplexOnsiteApply": {"easyApplyUrl": "urn:li:..."}
            },
            "description": {"text": {"text": "Easy apply JD body."}},
        }
    }


def _job():
    return SimpleNamespace(
        id=75,
        external_id="4422894549",
        url="https://www.linkedin.com/jobs/view/4422894549",
    )


# ── Tier A: parse_guest_detail ───────────────────────────────────────────


def test_parse_guest_offsite_extracts_slug_and_marker():
    g = lr.parse_guest_detail(_GUEST_OFFSITE)
    assert g.is_offsite is True
    assert g.company_slug == "catapultsports"
    assert g.posting_title == "Senior Software Engineer (GO)"
    assert g.description_text and "sports performance" in g.description_text


def test_parse_guest_easy_apply_no_offsite_marker():
    g = lr.parse_guest_detail(_GUEST_EASY_APPLY)
    assert g.is_offsite is False
    assert g.company_slug == "acme"


def test_parse_guest_none_is_all_unknown():
    g = lr.parse_guest_detail(None)
    assert g.is_offsite is None
    assert g.company_slug is None
    assert g.description_text is None


def test_parse_guest_ignores_malformed_slug():
    g = lr.parse_guest_detail('<a href="https://www.linkedin.com/company/-bad">x</a>')
    assert g.company_slug is None


# ── Tier B: extract_apply_from_voyager (pure) ────────────────────────────


def test_extract_offsite_apply_url():
    va = lr.extract_apply_from_voyager(_voyager_offsite())
    assert va.apply_url == "https://job-boards.greenhouse.io/catapultsports/jobs/7960837"
    assert va.is_easy_apply is False
    assert va.description_text == "Full authenticated JD for the Go role."


def test_extract_easy_apply_has_no_url():
    va = lr.extract_apply_from_voyager(_voyager_easy())
    assert va.apply_url is None
    assert va.is_easy_apply is True


def test_extract_deep_fallback_finds_company_apply_url():
    payload = {"included": [{"foo": {"companyApplyUrl": "https://jobs.lever.co/acme/abc"}}]}
    va = lr.extract_apply_from_voyager(payload)
    assert va.apply_url == "https://jobs.lever.co/acme/abc"


def test_extract_formatted_description_fallback():
    payload = {"data": {"formattedDescription": "Legacy JD field."}}
    va = lr.extract_apply_from_voyager(payload)
    assert va.description_text == "Legacy JD field."


# ── Tier B: resolved_from_fetch (pure) ───────────────────────────────────


def test_resolved_from_fetch_offsite_greenhouse():
    fetch = lr.AuthFetch(landing_url="…/jobs/view/x", logged_in=True, voyager=_voyager_offsite())
    out = lr.resolved_from_fetch(_job(), fetch)
    assert out is not None
    assert out.kind == "greenhouse"
    assert out.ats_org == "catapultsports"
    assert out.via == "linkedin_auth"
    assert out.apply_url.endswith("/7960837")
    assert out.description_text


def test_resolved_from_fetch_company_site_when_non_ats_host():
    # A URL in hand on an unrecognized host is a company careers page —
    # "external" is reserved for offsite-with-no-target.
    url = "https://careers.example.com/apply/123"
    fetch = lr.AuthFetch(landing_url="x", logged_in=True, voyager=_voyager_offsite(url))
    out = lr.resolved_from_fetch(_job(), fetch)
    assert out.kind == "company_site"
    assert out.ats_org is None
    assert out.apply_url == url


def test_resolved_from_fetch_easy_apply():
    fetch = lr.AuthFetch(landing_url="x", logged_in=True, voyager=_voyager_easy())
    out = lr.resolved_from_fetch(_job(), fetch)
    assert out.kind == "easy_apply"
    assert out.via == "linkedin_auth"


def test_resolved_from_fetch_not_logged_in_is_none():
    fetch = lr.AuthFetch(landing_url="…/authwall", logged_in=False, voyager=None)
    assert lr.resolved_from_fetch(_job(), fetch) is None


def test_resolved_from_fetch_no_apply_method_is_none():
    fetch = lr.AuthFetch(landing_url="x", logged_in=True, voyager={"data": {}})
    assert lr.resolved_from_fetch(_job(), fetch) is None


# ── Tier B: resolve_via_auth (injected fetcher) ──────────────────────────


@pytest.mark.asyncio
async def test_resolve_via_auth_uses_fetcher_and_decrements_budget():
    auth = lr.AuthContext(remaining=2, jitter=(0.0, 0.0))

    async def _fetcher(job):
        return lr.AuthFetch(landing_url="x", logged_in=True, voyager=_voyager_offsite())

    out = await lr.resolve_via_auth(_job(), auth, _fetcher=_fetcher)
    assert out is not None and out.kind == "greenhouse"
    assert auth.remaining == 1


@pytest.mark.asyncio
async def test_resolve_via_auth_skips_when_budget_exhausted():
    auth = lr.AuthContext(remaining=0, jitter=(0.0, 0.0))
    called = False

    async def _fetcher(job):
        nonlocal called
        called = True
        return None

    out = await lr.resolve_via_auth(_job(), auth, _fetcher=_fetcher)
    assert out is None
    assert called is False


@pytest.mark.asyncio
async def test_resolve_via_auth_none_context_is_none():
    assert await lr.resolve_via_auth(_job(), None) is None


@pytest.mark.asyncio
async def test_resolve_via_auth_swallows_fetcher_error():
    auth = lr.AuthContext(remaining=1, jitter=(0.0, 0.0))

    async def _fetcher(job):
        raise RuntimeError("browser crashed")

    assert await lr.resolve_via_auth(_job(), auth, _fetcher=_fetcher) is None


# ── helpers ──────────────────────────────────────────────────────────────


def test_cookie_payload_strips_quotes_and_scopes_domain():
    payload = lr.cookie_payload('"AQEDsecret"')
    assert payload[0]["value"] == "AQEDsecret"
    assert payload[0]["domain"] == ".linkedin.com"
    assert payload[0]["httpOnly"] is True


def test_ats_org_from_url():
    assert (
        asr.ats_org_from_url("https://job-boards.greenhouse.io/catapultsports/jobs/1", "greenhouse")
        == "catapultsports"
    )
    assert asr.ats_org_from_url("https://careers.example.com/x", "company_site") is None


# ── Session health recording ──────────────────────────────────────────────


@pytest.fixture
def _tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(lr.settings, "data_dir", str(tmp_path))
    return tmp_path


def test_session_health_roundtrip_and_alert_latch(_tmp_data_dir):
    assert lr.read_session_health() is None  # never attempted
    lr.record_session_health("not_logged_in", landing_url="https://www.linkedin.com/authwall")
    health = lr.read_session_health()
    assert health["status"] == "not_logged_in"
    assert health["alerted"] is False
    lr.mark_health_alerted()
    assert lr.read_session_health()["alerted"] is True
    # A repeat failure keeps the latch (no alert spam)…
    lr.record_session_health("not_logged_in")
    assert lr.read_session_health()["alerted"] is True
    # …and recovery clears it, re-arming the next alert.
    lr.record_session_health("ok", landing_url="https://www.linkedin.com/jobs/view/1/")
    health = lr.read_session_health()
    assert health["status"] == "ok"
    assert health["alerted"] is False


@pytest.mark.asyncio
async def test_resolve_via_auth_records_health(_tmp_data_dir):
    job = _job()
    auth = lr.AuthContext(remaining=2, jitter=(0.0, 0.0))

    async def _ok_fetch(j):
        return lr.AuthFetch(
            landing_url="https://www.linkedin.com/jobs/view/1/",
            logged_in=True,
            voyager=_voyager_offsite(),
        )

    out = await lr.resolve_via_auth(job, auth, _fetcher=_ok_fetch)
    assert out is not None
    assert lr.read_session_health()["status"] == "ok"

    async def _authwall_fetch(j):
        return lr.AuthFetch(
            landing_url="https://www.linkedin.com/authwall", logged_in=False, voyager=None
        )

    out = await lr.resolve_via_auth(job, auth, _fetcher=_authwall_fetch)
    assert out is None
    assert lr.read_session_health()["status"] == "not_logged_in"


@pytest.mark.asyncio
async def test_resolve_via_auth_records_error_health(_tmp_data_dir):
    job = _job()
    auth = lr.AuthContext(remaining=1, jitter=(0.0, 0.0))

    async def _boom(j):
        raise RuntimeError("browser crashed")

    out = await lr.resolve_via_auth(job, auth, _fetcher=_boom)
    assert out is None
    assert lr.read_session_health()["status"] == "error"
