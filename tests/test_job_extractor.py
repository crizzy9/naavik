"""Tests for `services.job_extractor.enrich_raw_job` (plan 30 / 0.2.0.08).

HTML-fixture-driven. No real LLM calls, no real Chromium. The fake provider
duck-types `LLMProvider` so we can assert tracker-wrap semantics without a
real DB session.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from llm.base import CompletionResult, LLMProvider, LLMProviderError, StructuredResult
from llm.prompts.extract_job import JobExtraction
from models.enums import (
    ApplicationBoard,
    JobSource,
    RemotePolicy,
    SeniorityLevel,
    VisaRestriction,
)
from scraper.types import RawJob
from services import job_extractor
from services.job_extractor import (
    ExtractionSkipped,
    _parse_posted_at,
    _strip_boilerplate,
    enrich_raw_job,
)

pytestmark = pytest.mark.uses_sample_data_shims

FIXTURES = Path(__file__).parent / "fixtures" / "html"


# ── Helpers ──────────────────────────────────────────────────────────


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _seed_raw_job(
    *,
    description_html: str | None = None,
    description_text: str | None = None,
    source: JobSource = JobSource.LINKEDIN,
    board: ApplicationBoard = ApplicationBoard.LINKEDIN,
    remote_policy_hint: RemotePolicy | None = None,
    raw_meta: dict[str, Any] | None = None,
) -> RawJob:
    return RawJob(
        source=source,
        external_id="seed-abc123",
        source_url="https://example.com/jobs/abc123",
        board=board,
        url_type="external",
        company_name="ScraperCo",
        position_title="Software Engineer",
        location_raw="San Francisco, CA",
        description_html=description_html,
        description_text=description_text,
        remote_policy_hint=remote_policy_hint,
        raw_meta=raw_meta or {},
    )


def _canned_extraction(**overrides: Any) -> JobExtraction:
    defaults: dict[str, Any] = {
        "company_name": "Acme Fake",
        "position_title": "Senior Software Engineer",
        "location_raw": "San Francisco, CA",
        "posted_at_text": "Posted 3 days ago",
        "posted_at": "2026-05-16T00:00:00Z",
        "salary_raw": "$220,000 - $280,000",
        "salary_min": 220_000,
        "salary_max": 280_000,
        "remote_policy": RemotePolicy.HYBRID,
        "visa_restrictions": VisaRestriction.SPONSORSHIP_AVAILABLE,
        "seniority_level": SeniorityLevel.SENIOR,
        "description": "Acme Fake is hiring a Senior Software Engineer...",
        "criteria": ["7+ years experience", "Bachelor's degree in CS"],
        "skills_required": ["Python", "Go", "Kubernetes", "PostgreSQL"],
        "tags": ["backend", "platform"],
    }
    defaults.update(overrides)
    return JobExtraction(**defaults)


class _FakeLLMProvider(LLMProvider):
    """In-memory LLMProvider stub. Returns a canned StructuredResult."""

    def __init__(
        self,
        *,
        returns: JobExtraction | dict[str, Any] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self._returns = returns
        self._raises = raises
        self.calls = 0
        self.last_prompt: str | None = None
        self.last_schema: type | None = None
        self.last_max_tokens: int | None = None

    @property
    def provider_id(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return "claude-3-5-sonnet-FAKE"

    async def structured(
        self,
        prompt: str,
        schema: type,
        *,
        max_tokens: int = 1024,
    ) -> StructuredResult:
        self.calls += 1
        self.last_prompt = prompt
        self.last_schema = schema
        self.last_max_tokens = max_tokens
        if self._raises is not None:
            raise self._raises
        if isinstance(self._returns, JobExtraction):
            value = self._returns.model_dump(mode="json")
        elif isinstance(self._returns, dict):
            value = self._returns
        else:
            value = {}
        return StructuredResult(
            text="",
            value=value,
            input_tokens=120,
            output_tokens=480,
            model=self.model_name,
        )

    async def complete(self, prompt: str, *, max_tokens: int = 1024) -> CompletionResult:
        raise NotImplementedError

    async def stream(self, prompt: str, *, max_tokens: int = 1024) -> AsyncIterator[str]:
        raise NotImplementedError
        yield  # pragma: no cover

    def estimate_cost(self, *, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens + output_tokens) * 0.0001


# ── _strip_boilerplate ────────────────────────────────────────────────


def test_strip_boilerplate_removes_drop_tags() -> None:
    html = _load("linkedin-senior-engineer.html")
    stripped = _strip_boilerplate(html)

    # No script / style / nav / footer / iframe / noscript content survives.
    assert "window.__INITIAL_STATE__" not in stripped
    assert "var liFn" not in stripped
    assert "All rights reserved" not in stripped
    assert "JavaScript is required" not in stripped
    # nav links should be gone
    assert "Home" not in stripped
    assert "Messaging" not in stripped
    # button content (Easy Apply) should be gone
    assert "Easy Apply" not in stripped
    # JD body content survives
    assert "Senior Software Engineer" in stripped
    assert "distributed event-processing pipeline" in stripped
    assert "Required" in stripped
    # <aside> content survives (LinkedIn right-rail JD content)
    assert "About this job" in stripped
    assert "Visa sponsorship is available" in stripped
    # Reduction: stripped output is materially smaller than raw HTML
    assert len(stripped) < len(html) * 0.7


# ── _parse_posted_at ──────────────────────────────────────────────────


def test_parse_posted_at_permissive() -> None:
    assert _parse_posted_at("2026-05-19T00:00:00Z") == datetime(2026, 5, 19, 0, 0, 0, tzinfo=UTC)
    assert _parse_posted_at("2026-05-19") == datetime(2026, 5, 19, 0, 0, 0)
    assert _parse_posted_at(None) is None
    assert _parse_posted_at("") is None
    assert _parse_posted_at("not-a-date") is None
    assert _parse_posted_at("Posted 3 days ago") is None


# ── enrich_raw_job — happy path ──────────────────────────────────────


async def test_enrich_raw_job_happy_path() -> None:
    seed = _seed_raw_job(description_html=_load("linkedin-senior-engineer.html"))
    canned = _canned_extraction()
    provider = _FakeLLMProvider(returns=canned)

    enriched = await enrich_raw_job(session=None, user_id=1, provider=provider, raw_job=seed)

    # Scraper-owned identity preserved verbatim
    assert enriched.source == seed.source
    assert enriched.external_id == seed.external_id
    assert enriched.source_url == seed.source_url
    assert enriched.board == seed.board
    assert enriched.url_type == seed.url_type
    # LLM overwrites
    assert enriched.company_name == "Acme Fake"
    assert enriched.position_title == "Senior Software Engineer"
    assert enriched.description_text == canned.description
    assert enriched.remote_policy_hint == RemotePolicy.HYBRID
    assert enriched.visa_restriction_hint == VisaRestriction.SPONSORSHIP_AVAILABLE
    assert enriched.seniority_level_hint == SeniorityLevel.SENIOR
    # posted_at parsed from LLM ISO string
    assert enriched.posted_at == datetime(2026, 5, 16, 0, 0, 0, tzinfo=UTC)
    # raw_meta carries scorer-required arrays
    assert enriched.raw_meta["skills_required"] == ["Python", "Go", "Kubernetes", "PostgreSQL"]
    assert enriched.raw_meta["criteria"] == ["7+ years experience", "Bachelor's degree in CS"]
    assert enriched.raw_meta["tags"] == ["backend", "platform"]
    assert enriched.raw_meta["salary_min"] == 220_000
    assert enriched.raw_meta["salary_max"] == 280_000
    assert enriched.raw_meta["description_extraction_model"] == "claude-3-5-sonnet-FAKE"
    # Provider invoked exactly once
    assert provider.calls == 1


async def test_enrich_raw_job_calls_tracker_with_right_args(monkeypatch) -> None:
    seed = _seed_raw_job(description_html=_load("minimal-valid.html"))
    canned = _canned_extraction()
    provider = _FakeLLMProvider(returns=canned)

    captured: dict[str, Any] = {}

    async def spy_tracked_call(**kwargs: Any) -> StructuredResult:
        captured.update(kwargs)
        # Delegate to the provider so the rest of the pipeline runs.
        return await kwargs["provider"].structured(
            kwargs["prompt"],
            kwargs["schema"],
            max_tokens=kwargs.get("max_tokens", 1024),
        )

    monkeypatch.setattr(job_extractor.llm_tracker, "tracked_call", spy_tracked_call)

    await enrich_raw_job(session=None, user_id=42, provider=provider, raw_job=seed)

    assert captured["session"] is None
    assert captured["user_id"] == 42
    assert captured["provider"] is provider
    assert captured["method"] == "structured"
    assert captured["prompt_name"] == "extract_job"
    assert captured["schema"] is JobExtraction
    assert captured["max_tokens"] == 2048
    assert isinstance(captured["prompt"], str)
    assert "Backend Engineer" in captured["prompt"]


# ── enrich_raw_job — skip path (no html / no text) ────────────────────


async def test_enrich_raw_job_skips_when_no_html_or_text() -> None:
    seed = _seed_raw_job(description_html=None, description_text=None)
    provider = _FakeLLMProvider(returns=_canned_extraction())

    out = await enrich_raw_job(session=None, user_id=1, provider=provider, raw_job=seed)

    # Tracker NEVER called
    assert provider.calls == 0
    # Marker landed in raw_meta
    assert out.raw_meta["extraction_skipped"] == "no_html_or_text"
    # Otherwise unchanged
    assert out.company_name == seed.company_name
    assert out.position_title == seed.position_title
    assert out.description_text is None


async def test_enrich_raw_job_strict_raises_on_no_body() -> None:
    seed = _seed_raw_job(description_html=None, description_text=None)
    provider = _FakeLLMProvider(returns=_canned_extraction())

    with pytest.raises(ExtractionSkipped):
        await enrich_raw_job(
            session=None,
            user_id=1,
            provider=provider,
            raw_job=seed,
            strict=True,
        )
    assert provider.calls == 0


# ── enrich_raw_job — LLM failure paths ───────────────────────────────


async def test_enrich_raw_job_llm_failure_default_marks_skipped() -> None:
    seed = _seed_raw_job(description_html=_load("linkedin-senior-engineer.html"))
    provider = _FakeLLMProvider(
        raises=LLMProviderError("rate limit", kind="rate_limit"),
    )

    out = await enrich_raw_job(session=None, user_id=1, provider=provider, raw_job=seed)

    assert out.raw_meta["extraction_skipped"] == "llm_failure:rate_limit"
    # Original RawJob otherwise preserved
    assert out.source == seed.source
    assert out.description_text is None  # not overwritten


async def test_enrich_raw_job_llm_failure_strict_reraises() -> None:
    seed = _seed_raw_job(description_html=_load("linkedin-senior-engineer.html"))
    provider = _FakeLLMProvider(
        raises=LLMProviderError("upstream 500", kind="provider_error"),
    )

    with pytest.raises(LLMProviderError):
        await enrich_raw_job(
            session=None,
            user_id=1,
            provider=provider,
            raw_job=seed,
            strict=True,
        )


# ── enrich_raw_job — schema invalid ──────────────────────────────────


async def test_enrich_raw_job_schema_invalid_marks_skipped() -> None:
    seed = _seed_raw_job(description_html=_load("minimal-valid.html"))
    # Provider returns a dict missing `description` (which has min_length=1).
    bad_payload: dict[str, Any] = {
        "company_name": "X",
        "position_title": "Y",
        # description omitted -> validation fails
    }
    provider = _FakeLLMProvider(returns=bad_payload)

    out = await enrich_raw_job(session=None, user_id=1, provider=provider, raw_job=seed)

    assert out.raw_meta["extraction_skipped"] == "schema_invalid"


async def test_enrich_raw_job_schema_invalid_strict_reraises() -> None:
    seed = _seed_raw_job(description_html=_load("minimal-valid.html"))
    provider = _FakeLLMProvider(returns={"company_name": "X"})

    with pytest.raises(LLMProviderError) as exc_info:
        await enrich_raw_job(
            session=None,
            user_id=1,
            provider=provider,
            raw_job=seed,
            strict=True,
        )
    assert exc_info.value.kind == "schema_validation"


# ── enrich_raw_job — overwrite + preserve semantics ──────────────────


async def test_enrich_raw_job_overwrites_hint_trio() -> None:
    # Seed says ONSITE; LLM says REMOTE — LLM wins.
    seed = _seed_raw_job(
        description_html=_load("greenhouse-sponsorship.html"),
        remote_policy_hint=RemotePolicy.ONSITE,
    )
    canned = _canned_extraction(
        remote_policy=RemotePolicy.REMOTE,
        visa_restrictions=VisaRestriction.SPONSORSHIP_AVAILABLE,
        seniority_level=SeniorityLevel.STAFF,
    )
    provider = _FakeLLMProvider(returns=canned)

    out = await enrich_raw_job(session=None, user_id=1, provider=provider, raw_job=seed)

    assert out.remote_policy_hint == RemotePolicy.REMOTE
    assert out.visa_restriction_hint == VisaRestriction.SPONSORSHIP_AVAILABLE
    assert out.seniority_level_hint == SeniorityLevel.STAFF


async def test_enrich_raw_job_preserves_scraper_identity() -> None:
    seed = RawJob(
        source=JobSource.GREENHOUSE,
        external_id="gh-9876",
        source_url="https://boards.greenhouse.io/lumino/jobs/9876",
        board=ApplicationBoard.GREENHOUSE,
        url_type="external",
        company_name="Original Company From Listing Card",
        position_title="Original Title",
        description_html=_load("greenhouse-sponsorship.html"),
        raw_meta={"listing_card": "preserved"},
    )
    canned = _canned_extraction(
        company_name="Normalized Company",
        position_title="Normalized Title",
    )
    provider = _FakeLLMProvider(returns=canned)

    out = await enrich_raw_job(session=None, user_id=1, provider=provider, raw_job=seed)

    # Identity quad preserved
    assert out.source == JobSource.GREENHOUSE
    assert out.external_id == "gh-9876"
    assert out.source_url == seed.source_url
    assert out.board == ApplicationBoard.GREENHOUSE
    assert out.url_type == "external"
    # User-visible fields LLM-normalized
    assert out.company_name == "Normalized Company"
    assert out.position_title == "Normalized Title"
    # Existing raw_meta preserved through merge
    assert out.raw_meta["listing_card"] == "preserved"
    assert out.raw_meta["skills_required"]


# ── Integration with to_upsert_payload ───────────────────────────────


async def test_enrich_raw_job_integration_with_upsert_payload() -> None:
    """The enriched RawJob.to_upsert_payload() carries scorer-required arrays
    under raw_meta so job_service._create_payload can lift them onto Job
    columns.
    """
    seed = _seed_raw_job(description_html=_load("greenhouse-sponsorship.html"))
    canned = _canned_extraction(
        skills_required=["python", "fastapi", "postgresql"],
        criteria=["9+ years experience", "Strong Python"],
        tags=["backend", "platform", "genai"],
    )
    provider = _FakeLLMProvider(returns=canned)

    enriched = await enrich_raw_job(session=None, user_id=1, provider=provider, raw_job=seed)
    payload = enriched.to_upsert_payload()

    # Job-column-shaped keys present
    assert payload["company"] == "Acme Fake"
    assert payload["role"] == "Senior Software Engineer"
    assert payload["description"] == canned.description
    assert payload["remote_policy"] == RemotePolicy.HYBRID
    assert payload["visa_restrictions"] == VisaRestriction.SPONSORSHIP_AVAILABLE
    # Scorer-required arrays land in raw_meta for _create_payload to lift
    assert payload["raw_meta"]["skills_required"] == ["python", "fastapi", "postgresql"]
    assert payload["raw_meta"]["criteria"] == ["9+ years experience", "Strong Python"]
    assert payload["raw_meta"]["tags"] == ["backend", "platform", "genai"]
    assert payload["raw_meta"]["description_extraction_model"] == "claude-3-5-sonnet-FAKE"


# ── _strip_boilerplate empty body path ───────────────────────────────


async def test_enrich_raw_job_empty_body_marks_schema_invalid() -> None:
    """HTML with only script/style/nav/footer -> _strip_boilerplate returns
    empty -> LLM input empty -> stub returns empty dict -> Pydantic validation
    fails (description min_length=1) -> default path marks schema_invalid.
    """
    seed = _seed_raw_job(description_html=_load("empty-body.html"))
    # Provider returns a no-description payload (simulates LLM hallucinating
    # blank fields on empty input).
    provider = _FakeLLMProvider(returns={"company_name": "X", "position_title": "Y"})

    out = await enrich_raw_job(session=None, user_id=1, provider=provider, raw_job=seed)

    assert out.raw_meta["extraction_skipped"] == "schema_invalid"


# ── description_text fallback path ───────────────────────────────────


async def test_enrich_raw_job_uses_description_text_when_html_absent() -> None:
    """When description_html is None but description_text is present, the
    service uses the text directly (no bs4 strip) and still calls the LLM.
    """
    seed = _seed_raw_job(
        description_html=None,
        description_text="Backend Engineer. Python, PostgreSQL. Remote.",
    )
    canned = _canned_extraction(
        description="Backend Engineer. Python, PostgreSQL. Remote.",
        skills_required=["python", "postgresql"],
        tags=["backend"],
    )
    provider = _FakeLLMProvider(returns=canned)

    out = await enrich_raw_job(session=None, user_id=1, provider=provider, raw_job=seed)

    assert provider.calls == 1
    assert out.description_text == "Backend Engineer. Python, PostgreSQL. Remote."
    # The LLM input prompt should contain the original text
    assert "Backend Engineer" in provider.last_prompt


# ── JobExtraction.tags Literal vocabulary (plan 46 / 0.2.0.08a) ──────


def test_job_extraction_rejects_off_vocab_tags() -> None:
    """Off-vocab tags fail Pydantic validation at the LLM-output boundary.

    Closes hacker review on PR #106: LLM hallucinations carrying invented
    tag strings now fail-fast rather than slipping through to the scorer
    via raw_meta (where downstream consumers trust the vocabulary without
    re-validation).
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        JobExtraction(
            company_name="Acme",
            position_title="Engineer",
            description="x",
            tags=["invalid-tag"],
        )


def test_job_extraction_accepts_canonical_tags() -> None:
    """All 9 canonical tags accepted; multi-tag mix accepted."""
    out = JobExtraction(
        company_name="Acme",
        position_title="Engineer",
        description="x",
        tags=["ai-ml", "backend", "platform", "genai"],
    )
    assert out.tags == ["ai-ml", "backend", "platform", "genai"]
