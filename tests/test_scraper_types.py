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
from services.job_service import _JOB_CREATE_FIELDS, _create_payload


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


# ── to_upsert_payload adapter ────────────────────────────────────────────


def test_to_upsert_payload_renames_to_job_column_names():
    """RawJob field names rename to Job column names per SCRAPER_BASE.md § D.4."""
    kwargs = _minimal_rawjob_kwargs()
    kwargs["location_raw"] = "Remote — US"
    kwargs["description_text"] = "Train foundation models."
    kwargs["description_html"] = "<p>Train foundation models.</p>"
    kwargs["posted_at"] = datetime(2026, 5, 19, tzinfo=UTC)
    kwargs["posted_at_text"] = "Posted 2 days ago"
    job = RawJob(**kwargs)

    payload = job.to_upsert_payload()

    # source_url -> url, company_name -> company, position_title -> role,
    # location_raw -> location, description_text -> description.
    assert payload["url"] == "https://boards.greenhouse.io/example/jobs/123"
    assert payload["company"] == "Anthropic"
    assert payload["role"] == "Senior ML Engineer"
    assert payload["location"] == "Remote — US"
    assert payload["description"] == "Train foundation models."
    assert payload["description_html"] == "<p>Train foundation models.</p>"
    assert payload["posted_at"].tzinfo is UTC
    assert payload["posted_at_text"] == "Posted 2 days ago"
    # RawJob-shape names must NOT leak through.
    for raw_name in (
        "source_url",
        "company_name",
        "position_title",
        "location_raw",
        "description_text",
        "remote_policy_hint",
        "visa_restriction_hint",
        "seniority_level_hint",
        "salary_raw",
        "external_id",  # passed positionally to upsert_job, not via raw dict
        "source",  # ditto
    ):
        assert raw_name not in payload, f"adapter leaked RawJob name {raw_name!r}"


def test_to_upsert_payload_hint_trio_maps_to_job_columns():
    """`*_hint` enums map onto the corresponding `Job` enum column verbatim.

    AI extraction (`0.2.0.08`) overwrites later from the authoritative read
    of the JD body, but the scraper's hint seeds the column at insert time.
    """
    kwargs = _minimal_rawjob_kwargs()
    kwargs["remote_policy_hint"] = RemotePolicy.HYBRID
    kwargs["visa_restriction_hint"] = VisaRestriction.SPONSORSHIP_AVAILABLE
    kwargs["seniority_level_hint"] = SeniorityLevel.STAFF
    job = RawJob(**kwargs)

    payload = job.to_upsert_payload()

    assert payload["remote_policy"] is RemotePolicy.HYBRID
    assert payload["visa_restrictions"] is VisaRestriction.SPONSORSHIP_AVAILABLE
    assert payload["seniority_level"] is SeniorityLevel.STAFF


def test_to_upsert_payload_omits_hints_when_unset():
    """Unset hints stay absent so `_create_payload` supplies typed defaults."""
    payload = RawJob(**_minimal_rawjob_kwargs()).to_upsert_payload()
    assert "remote_policy" not in payload
    assert "visa_restrictions" not in payload
    assert "seniority_level" not in payload


def test_to_upsert_payload_salary_raw_lands_in_raw_meta():
    """`salary_raw` has no `Job` column; AI extraction (0.2.0.08) parses it
    out of `raw_meta` into typed `salary_min` / `salary_max` later."""
    kwargs = _minimal_rawjob_kwargs()
    kwargs["salary_raw"] = "$180k–$240k + equity"
    kwargs["raw_meta"] = {"gh_jid": "abc-123"}
    payload = RawJob(**kwargs).to_upsert_payload()

    assert "salary_raw" not in payload
    assert payload["raw_meta"]["salary_raw"] == "$180k–$240k + equity"
    # Scraper-supplied raw_meta entries are preserved alongside.
    assert payload["raw_meta"]["gh_jid"] == "abc-123"


def test_to_upsert_payload_description_text_none_becomes_empty_string():
    """`Job.description` is NOT NULL; `to_upsert_payload` substitutes "" when
    the scraper omits description_text so the insert doesn't trip the
    NOT-NULL constraint at the DB."""
    payload = RawJob(**_minimal_rawjob_kwargs()).to_upsert_payload()
    assert payload["description"] == ""


def test_to_upsert_payload_keys_are_subset_of_job_create_allowlist():
    """Every key the adapter emits must live in `_JOB_CREATE_FIELDS`; otherwise
    `_create_payload` would silently drop it (the bug that motivated the
    adapter). This is the canonical contract assertion."""
    kwargs = _minimal_rawjob_kwargs()
    kwargs["location_raw"] = "Remote"
    kwargs["description_text"] = "x"
    kwargs["description_html"] = "<p>x</p>"
    kwargs["posted_at"] = datetime(2026, 5, 19, tzinfo=UTC)
    kwargs["posted_at_text"] = "Posted today"
    kwargs["remote_policy_hint"] = RemotePolicy.REMOTE
    kwargs["visa_restriction_hint"] = VisaRestriction.NOT_MENTIONED
    kwargs["seniority_level_hint"] = SeniorityLevel.SENIOR
    kwargs["salary_raw"] = "$100k"
    kwargs["raw_meta"] = {"k": "v"}
    payload = RawJob(**kwargs).to_upsert_payload()

    assert set(payload).issubset(_JOB_CREATE_FIELDS)
    # And `_create_payload` keeps every key the adapter emitted.
    projected = _create_payload(payload)
    for key in payload:
        assert key in projected, f"_create_payload dropped adapter-emitted key {key!r}"


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


def test_scrapequery_max_listings_bounds():
    """`max_listings` is capped at 10_000 (10× LinkedIn-typical headroom);
    `ge=1` prevents silent no-op + negative values. Plan 31 D.5."""
    assert ScrapeQuery(max_listings=10_000).max_listings == 10_000
    assert ScrapeQuery(max_listings=1).max_listings == 1
    with pytest.raises(ValidationError):
        ScrapeQuery(max_listings=10_001)
    with pytest.raises(ValidationError):
        ScrapeQuery(max_listings=0)
    with pytest.raises(ValidationError):
        ScrapeQuery(max_listings=-1)
