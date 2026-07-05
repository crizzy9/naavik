"""`_BaseSiteScraper` shim tests — plan 33 § D.4.

Exercises the `_maybe_enrich` decision tree:

- Provider/session/user_id missing → identity pass-through.
- `services.jobs.extractor` not importable → identity pass-through w/ debug log.
- `enrich_raw_job` raises → tier-1 error logged, identity pass-through.
- All wired + service returns enriched RawJob → enriched RawJob returned.
"""

from __future__ import annotations

import sys
import types
from collections.abc import AsyncIterator

import pytest

from models import ApplicationBoard, JobSource
from scraper.sites._base_site import _BaseSiteScraper
from scraper.types import RawJob, ScrapeQuery


class _FakeProvider:
    """LLMProvider stand-in; never actually called by the shim."""


class _FakeSession:
    """AsyncSession stand-in; never actually called by the shim."""


class _StubSiteScraper(_BaseSiteScraper):
    source = JobSource.GREENHOUSE
    board = ApplicationBoard.GREENHOUSE

    async def scrape(self, query: ScrapeQuery) -> AsyncIterator[RawJob]:
        return
        yield  # pragma: no cover


def _make_seed() -> RawJob:
    return RawJob(
        source=JobSource.GREENHOUSE,
        external_id="seed-1",
        source_url="https://boards.greenhouse.io/acme/jobs/seed-1",
        board=ApplicationBoard.GREENHOUSE,
        company_name="Acme",
        position_title="Engineer",
    )


@pytest.fixture
def _wipe_job_extractor():
    """Make sure `services.jobs.extractor` is NOT cached in sys.modules."""
    sys.modules.pop("services.jobs.extractor", None)
    yield
    sys.modules.pop("services.jobs.extractor", None)


@pytest.mark.asyncio
async def test_maybe_enrich_passthrough_when_provider_missing(_wipe_job_extractor):
    """No provider → identity. `services.jobs.extractor` is NOT imported."""
    scraper = _StubSiteScraper(client=object())  # type: ignore[arg-type]
    seed = _make_seed()

    result = await scraper._maybe_enrich(seed)

    assert result is seed
    assert "services.jobs.extractor" not in sys.modules


@pytest.mark.asyncio
async def test_maybe_enrich_passthrough_when_session_missing(_wipe_job_extractor):
    """Provider set but no session → identity (constructor partial-state guard)."""
    scraper = _StubSiteScraper(
        client=object(),  # type: ignore[arg-type]
        provider=_FakeProvider(),  # type: ignore[arg-type]
        user_id=1,
    )
    seed = _make_seed()

    result = await scraper._maybe_enrich(seed)

    assert result is seed
    assert "services.jobs.extractor" not in sys.modules


@pytest.mark.asyncio
async def test_maybe_enrich_handles_missing_service_module(_wipe_job_extractor, monkeypatch):
    """If `services.jobs.extractor` isn't installed (pre-0.2.0.08), return identity."""
    # Force the lazy import to fail. Two-step: ensure no real module is
    # cached, then make the import raise.
    monkeypatch.setitem(sys.modules, "services.jobs.extractor", None)

    scraper = _StubSiteScraper(
        client=object(),  # type: ignore[arg-type]
        session=_FakeSession(),  # type: ignore[arg-type]
        user_id=1,
        provider=_FakeProvider(),  # type: ignore[arg-type]
    )
    seed = _make_seed()

    result = await scraper._maybe_enrich(seed)

    assert result is seed
    assert scraper._errors == []  # ImportError path does NOT append to errors


@pytest.mark.asyncio
async def test_maybe_enrich_calls_service_when_wired(_wipe_job_extractor, monkeypatch):
    """When `enrich_raw_job` exists, the shim awaits it and returns the result."""
    fake_module = types.ModuleType("services.jobs.extractor")
    calls: list[dict] = []

    async def _fake_enrich(*, session, user_id, provider, raw_job):
        calls.append({"session": session, "user_id": user_id, "provider": provider})
        # Return a *different* RawJob so the test can assert it propagated.
        return raw_job.model_copy(update={"company_name": "Acme (enriched)"})

    fake_module.enrich_raw_job = _fake_enrich
    monkeypatch.setitem(sys.modules, "services.jobs.extractor", fake_module)

    session = _FakeSession()
    provider = _FakeProvider()
    scraper = _StubSiteScraper(
        client=object(),  # type: ignore[arg-type]
        session=session,  # type: ignore[arg-type]
        user_id=42,
        provider=provider,  # type: ignore[arg-type]
    )
    seed = _make_seed()

    result = await scraper._maybe_enrich(seed)

    assert result is not seed
    assert result.company_name == "Acme (enriched)"
    assert len(calls) == 1
    assert calls[0] == {"session": session, "user_id": 42, "provider": provider}


@pytest.mark.asyncio
async def test_maybe_enrich_catches_service_exception(_wipe_job_extractor, monkeypatch):
    """A raised enrichment becomes a tier-1 error and we return the seed unchanged."""
    fake_module = types.ModuleType("services.jobs.extractor")

    async def _broken_enrich(*, session, user_id, provider, raw_job):
        raise RuntimeError("LLM unavailable")

    fake_module.enrich_raw_job = _broken_enrich
    monkeypatch.setitem(sys.modules, "services.jobs.extractor", fake_module)

    scraper = _StubSiteScraper(
        client=object(),  # type: ignore[arg-type]
        session=_FakeSession(),  # type: ignore[arg-type]
        user_id=1,
        provider=_FakeProvider(),  # type: ignore[arg-type]
    )
    seed = _make_seed()

    result = await scraper._maybe_enrich(seed)

    assert result is seed
    assert len(scraper._errors) == 1
    assert "kind=extract_failure" in scraper._errors[0]
    assert "RuntimeError" in scraper._errors[0]


# ── Plan 43 § D.5.2 — `_compose_url` slug-validate wrapper ────────────────


def test_compose_url_returns_none_and_logs_on_hostile_slug():
    """Hostile slug → None + tier-1 error append + redaction (no smuggled controls)."""
    scraper = _StubSiteScraper(client=object())  # type: ignore[arg-type]
    result = scraper._compose_url("https://{x}.test/", stage="list", x="evil.com#")
    assert result is None
    assert len(scraper._errors) == 1
    assert "kind=invalid_slug" in scraper._errors[0]
    assert "msg=x=" in scraper._errors[0]
    # No smuggled control chars / newlines from a hostile slug value.
    assert "\x00" not in scraper._errors[0]
    assert "\n" not in scraper._errors[0]


def test_compose_url_returns_url_on_valid_slug():
    """Valid slug → composed URL + no error."""
    scraper = _StubSiteScraper(client=object())  # type: ignore[arg-type]
    result = scraper._compose_url("https://{x}.test/", stage="list", x="acme-corp")
    assert result == "https://acme-corp.test/"
    assert scraper._errors == []


def test_compose_url_redacts_control_chars_in_error_msg():
    """Slug with null + newline gets `_strip_control_chars`'d before logging."""
    scraper = _StubSiteScraper(client=object())  # type: ignore[arg-type]
    result = scraper._compose_url("https://{x}.test/", stage="detail", x="x\x00\nrebind")
    assert result is None
    assert len(scraper._errors) == 1
    assert "stage=detail" in scraper._errors[0]
    assert "\x00" not in scraper._errors[0]
    assert "\n" not in scraper._errors[0]
