"""JD enrichment — canonical ATS descriptions replace thin JDs (2026-07)."""

from __future__ import annotations

import os  # noqa: I001

os.environ.setdefault("NAAVIK_DEBUG", "1")

from types import SimpleNamespace  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

import pytest  # noqa: E402

from models import ApplicationBoard, JobSource  # noqa: E402
from services import jd_enrichment  # noqa: E402
from services.apply_site_resolver import ResolvedApply, _BoardPosting  # noqa: E402


def _job(
    *,
    description="short stub",
    source=JobSource.INDEED,
    apply_kind="greenhouse",
    apply_url="https://job-boards.greenhouse.io/acme/jobs/1",
    raw_meta=None,
):
    return SimpleNamespace(
        id=9,
        source=source,
        board=ApplicationBoard.GREENHOUSE,
        description=description,
        description_html=None,
        description_extracted_at=None,
        description_extraction_model=None,
        apply_url=apply_url,
        apply_kind=apply_kind,
        raw_meta=raw_meta or {},
        match_breakdown={"scored_at": "x"},
        score=0.9,
        score_explanation="old",
        updated_at=None,
        company="Acme",
    )


def test_html_to_text_handles_greenhouse_double_escape():
    escaped = (
        "&lt;p&gt;Build &amp;amp; ship&lt;/p&gt;&lt;ul&gt;&lt;li&gt;Python&lt;/li&gt;&lt;/ul&gt;"
    )
    text = jd_enrichment.html_to_text(escaped)
    assert "Build & ship" in text
    assert "Python" in text
    assert "<" not in text


def test_maybe_apply_replaces_thin_description_and_resets_score():
    job = _job()
    long_text = "A real job description. " * 40  # ~960 chars
    applied = jd_enrichment.maybe_apply_discovered_description(
        job, ResolvedApply(kind="greenhouse", description_text=long_text)
    )
    assert applied is True
    assert job.description == long_text.strip()
    assert job.match_breakdown == {}
    assert job.score == 0.0
    assert job.raw_meta["jd_enriched"] is True
    assert job.description_extraction_model == "ats_board_api"


def test_maybe_apply_never_replaces_rich_jd_with_shorter_text():
    job = _job(description="x" * 2000)
    applied = jd_enrichment.maybe_apply_discovered_description(
        job, ResolvedApply(kind="greenhouse", description_text="y" * 900)
    )
    assert applied is False
    assert job.description == "x" * 2000


def test_maybe_apply_rejects_stub_replacements():
    job = _job()
    applied = jd_enrichment.maybe_apply_discovered_description(
        job, ResolvedApply(kind="greenhouse", description_text="too short")
    )
    assert applied is False


@pytest.mark.asyncio
async def test_fetch_posting_description_matches_url():
    job = _job(raw_meta={"ats_org": "acme"})
    postings = [
        _BoardPosting(
            title="Other role",
            url="https://job-boards.greenhouse.io/acme/jobs/2",
            location="NYC",
            kind="greenhouse",
            org="acme",
            description_html="<p>" + "wrong " * 100 + "</p>",
        ),
        _BoardPosting(
            title="Target",
            url="https://job-boards.greenhouse.io/acme/jobs/1/",
            location="NYC",
            kind="greenhouse",
            org="acme",
            description_html="<p>" + "right " * 100 + "</p>",
        ),
    ]
    with patch(
        "services.apply_site_resolver._greenhouse_postings",
        new=AsyncMock(return_value=postings),
    ):
        out = await jd_enrichment._fetch_posting_description(job)
    assert out is not None
    text, html = out
    assert "right" in text
    assert "wrong" not in text


@pytest.mark.asyncio
async def test_enrich_sweep_marks_attempted_on_miss():
    job = _job()
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.exec = AsyncMock(return_value=MagicMock(all=lambda: [job]))

    with patch.object(
        jd_enrichment, "_fetch_posting_description", new=AsyncMock(return_value=None)
    ):
        n = await jd_enrichment.enrich_thin_descriptions(session)
    assert n == 0
    assert job.raw_meta["jd_enriched"] is False  # attempted, no refetch loop


@pytest.mark.asyncio
async def test_enrich_sweep_applies_fetched_description():
    job = _job()
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.exec = AsyncMock(return_value=MagicMock(all=lambda: [job]))

    long_text = "The full canonical posting text. " * 30
    with patch.object(
        jd_enrichment,
        "_fetch_posting_description",
        new=AsyncMock(return_value=(long_text, "<p>html</p>")),
    ):
        n = await jd_enrichment.enrich_thin_descriptions(session)
    assert n == 1
    assert job.description == long_text
    assert job.match_breakdown == {}
    assert job.score == 0.0


@pytest.mark.asyncio
async def test_reextract_signals_populates_tags_and_clears_flag():
    job = _job(raw_meta={"jd_enriched": True, "jd_tags_pending": True})
    job.user_id = 1
    job.external_id = "x1"
    job.url_type = "external"
    job.role = "Engineer"
    job.location = None
    job.tags = []
    job.skills_required = []
    job.criteria = []
    job.salary_min = None
    job.salary_max = None
    job.visa_restrictions = None
    job.seniority_level = None

    settings_row = SimpleNamespace(user_id=1)
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.exec = AsyncMock(
        side_effect=[
            MagicMock(all=lambda: [job]),
            MagicMock(one_or_none=lambda: settings_row),
        ]
    )

    enriched_raw = SimpleNamespace(
        to_upsert_payload=lambda: {
            "tags": ["backend", "ai-ml"],
            "skills_required": ["python"],
            "criteria": ["5+ years"],
            "salary_min": 150000,
            "salary_max": None,
            "visa_restrictions": None,
            "seniority_level": None,
        }
    )
    with (
        patch("llm.get_provider", return_value=SimpleNamespace(provider_id="openai")),
        patch(
            "services.job_extractor.enrich_raw_job",
            new=AsyncMock(return_value=enriched_raw),
        ),
    ):
        n = await jd_enrichment.reextract_signals(session)
    assert n == 1
    assert job.tags == ["backend", "ai-ml"]
    assert job.salary_min == 150000
    assert job.raw_meta["jd_tags_pending"] is False


@pytest.mark.asyncio
async def test_reextract_signals_waits_for_provider():
    """No provider configured → flag stays pending for the next tick."""
    from llm import LLMProviderError

    job = _job(raw_meta={"jd_enriched": True, "jd_tags_pending": True})
    job.user_id = 1
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.exec = AsyncMock(
        side_effect=[
            MagicMock(all=lambda: [job]),
            MagicMock(one_or_none=lambda: SimpleNamespace(user_id=1)),
        ]
    )
    with patch("llm.get_provider", side_effect=LLMProviderError("none")):
        n = await jd_enrichment.reextract_signals(session)
    assert n == 0
    assert job.raw_meta["jd_tags_pending"] is True
