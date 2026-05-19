"""RawJob + ScrapeQuery validation tests — plan 29 § D.2 / D.9.

Pure model tests; no DB, no Crawl4AI. Verifies `extra="forbid"` rejects
unknown fields, required-field enforcement, enum coercion of `source` /
`board` / `*_hint` fields, default values.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from models import (
    ApplicationBoard,
    JobSource,
    RemotePolicy,
    SeniorityLevel,
    VisaRestriction,
)
from scraper.types import RawJob, ScrapeQuery


def _minimal_rawjob_kwargs() -> dict:
    return {
        "source": JobSource.GREENHOUSE,
        "external_id": "gh-abc-123",
        "source_url": "https://boards.greenhouse.io/example/jobs/123",
        "board": ApplicationBoard.GREENHOUSE,
        "company_name": "Anthropic",
        "position_title": "Senior ML Engineer",
    }


# ── Required-field coverage ──────────────────────────────────────────────


def test_rawjob_builds_from_minimal_kwargs():
    job = RawJob(**_minimal_rawjob_kwargs())
    assert job.source == JobSource.GREENHOUSE
    assert job.external_id == "gh-abc-123"
    assert job.url_type == "external"  # default
    assert job.raw_meta == {}


@pytest.mark.parametrize(
    "missing",
    ["source", "external_id", "source_url", "board", "company_name", "position_title"],
)
def test_rawjob_rejects_missing_required(missing: str):
    kwargs = _minimal_rawjob_kwargs()
    kwargs.pop(missing)
    with pytest.raises(ValidationError):
        RawJob(**kwargs)


def test_rawjob_rejects_empty_external_id():
    kwargs = _minimal_rawjob_kwargs()
    kwargs["external_id"] = ""
    with pytest.raises(ValidationError):
        RawJob(**kwargs)


def test_rawjob_rejects_empty_company_name():
    kwargs = _minimal_rawjob_kwargs()
    kwargs["company_name"] = ""
    with pytest.raises(ValidationError):
        RawJob(**kwargs)


# ── extra="forbid" enforcement ───────────────────────────────────────────


def test_rawjob_rejects_unknown_field():
    kwargs = _minimal_rawjob_kwargs()
    kwargs["this_field_does_not_exist"] = "oops"
    with pytest.raises(ValidationError):
        RawJob(**kwargs)


# ── Enum coercion ────────────────────────────────────────────────────────


def test_rawjob_coerces_string_to_jobsource_enum():
    kwargs = _minimal_rawjob_kwargs()
    kwargs["source"] = "lever"
    job = RawJob(**kwargs)
    assert job.source is JobSource.LEVER


def test_rawjob_coerces_string_to_hint_enums():
    kwargs = _minimal_rawjob_kwargs()
    kwargs["remote_policy_hint"] = "remote"
    kwargs["visa_restriction_hint"] = "sponsorship_available"
    kwargs["seniority_level_hint"] = "senior"
    job = RawJob(**kwargs)
    assert job.remote_policy_hint is RemotePolicy.REMOTE
    assert job.visa_restriction_hint is VisaRestriction.SPONSORSHIP_AVAILABLE
    assert job.seniority_level_hint is SeniorityLevel.SENIOR


def test_rawjob_rejects_invalid_hint_value():
    kwargs = _minimal_rawjob_kwargs()
    kwargs["remote_policy_hint"] = "definitely-not-an-enum"
    with pytest.raises(ValidationError):
        RawJob(**kwargs)


# ── Optional + default field shape ───────────────────────────────────────


def test_rawjob_optional_fields_default_none():
    job = RawJob(**_minimal_rawjob_kwargs())
    assert job.location_raw is None
    assert job.description_html is None
    assert job.description_text is None
    assert job.posted_at is None
    assert job.posted_at_text is None
    assert job.salary_raw is None
    assert job.remote_policy_hint is None
    assert job.visa_restriction_hint is None
    assert job.seniority_level_hint is None


def test_rawjob_str_strip_whitespace_applies_to_all_strings():
    kwargs = _minimal_rawjob_kwargs()
    kwargs["company_name"] = "  Stripe  "
    kwargs["position_title"] = "\tInfra Engineer\n"
    job = RawJob(**kwargs)
    assert job.company_name == "Stripe"
    assert job.position_title == "Infra Engineer"


def test_rawjob_model_dump_round_trip_into_upsert_payload():
    """The model_dump output is what scraper_service hands to job_service.upsert_job."""
    kwargs = _minimal_rawjob_kwargs()
    kwargs["description_html"] = "<p>Build things.</p>"
    kwargs["posted_at"] = datetime(2026, 5, 19, tzinfo=UTC)
    job = RawJob(**kwargs)
    payload = job.model_dump(exclude_unset=True)
    assert payload["company_name"] == "Anthropic"
    assert "description_html" in payload
    assert payload["posted_at"].tzinfo is UTC
    # exclude_unset omits the defaults the scraper didn't touch.
    assert "remote_policy_hint" not in payload


# ── ScrapeQuery defaults ─────────────────────────────────────────────────


def test_scrapequery_bare_construct_has_conservative_defaults():
    q = ScrapeQuery()
    assert q.keywords == []
    assert q.location is None
    assert q.company_filter is None
    assert q.max_listings == 200
    assert q.raw_meta == {}


def test_scrapequery_accepts_keyword_list():
    q = ScrapeQuery(keywords=["python", "platform"], location="Remote")
    assert q.keywords == ["python", "platform"]
    assert q.location == "Remote"
