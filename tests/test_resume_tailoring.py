"""Resume tailoring guarantees (plan: UX-quality session).

Pins the fixes for the real-PDF audit findings:
- every experience keeps ≥1 bullet — no job silently vanishes;
- the page-fit loop never empties an experience while other experiences
  still have bullets to give;
- `_build_resume_data` renders all experiences, orders kept bullets by
  selection priority, carries project dates/links, and omits empty
  contact fields without blank separators;
- the resume parser schema extracts linkedin/github/portfolio.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from services import document_generator as dg


def _bullet(bid: int, exp_id: int, text: str = "Did a thing with numbers 42%"):
    return SimpleNamespace(
        id=bid,
        experience_id=exp_id,
        order_index=bid,
        text=text,
        tags=["backend"],
        selection_override=None,
        edited_at=None,
        deleted_at=None,
    )


def _experience(eid: int):
    return SimpleNamespace(
        id=eid,
        profile_id=1,
        company=f"Co{eid}",
        title="Engineer",
        team=None,
        location="City",
        start_date=datetime(2020, 1, 1, tzinfo=UTC),
        end_date=None,
        order_index=eid,
        summary_short=None,
        deleted_at=None,
    )


def _snap(bullets_by_exp: dict[int, list]):
    return dg.ProfileSnapshot(
        profile=SimpleNamespace(
            full_name="Test",
            headline="Engineer",
            email="t@example.com",
            phone=None,
            location=None,
            portfolio_url=None,
            linkedin_handle=None,
            github_handle=None,
            summary_short="Short summary.",
            summary_full=None,
        ),
        experiences=[_experience(eid) for eid in sorted(bullets_by_exp)],
        bullets_by_experience=bullets_by_exp,
        skills=[],
        education=[],
        projects=[],
    )


def test_min_one_per_experience_rescues_starved_experiences():
    """A top-N cut that starves an experience gets that experience's best
    ranked bullet appended."""
    by_exp = {1: [_bullet(1, 1), _bullet(2, 1)], 2: [_bullet(3, 2)], 3: [_bullet(4, 3)]}
    snap = _snap(by_exp)
    ranked = [1, 2, 3, 4]
    candidates = dg._ensure_min_one_per_experience([1, 2], ranked, snap)
    assert 3 in candidates and 4 in candidates


def test_drop_lowest_priority_never_empties_an_experience():
    by_exp = {1: [_bullet(1, 1), _bullet(2, 1)], 2: [_bullet(3, 2)]}
    snap = _snap(by_exp)
    # Priority order: 1 > 3 > 2. Bullet 3 is exp 2's ONLY bullet — dropping
    # from the tail must skip it and drop bullet 2 (exp 1 keeps bullet 1).
    remaining, dropped = dg._drop_lowest_priority([1, 3, 2], snap)
    assert dropped == 2
    assert remaining == [1, 3]


def test_drop_lowest_priority_falls_back_when_all_experiences_at_one():
    by_exp = {1: [_bullet(1, 1)], 2: [_bullet(2, 2)]}
    snap = _snap(by_exp)
    remaining, dropped = dg._drop_lowest_priority([1, 2], snap)
    assert dropped == 2
    assert remaining == [1]


@pytest.mark.asyncio
async def test_build_resume_data_renders_every_experience():
    by_exp = {1: [_bullet(1, 1)], 2: [_bullet(2, 2)], 3: [_bullet(3, 3)]}
    snap = _snap(by_exp)
    # Only exp 1's bullet selected — exps 2 and 3 must still render.
    data = await dg._build_resume_data(snap=snap, selected_bullet_ids=[1], trimmed={})
    assert len(data["experiences"]) == 3
    assert data["experiences"][0]["bullets"] == [by_exp[1][0].text]
    assert data["experiences"][1]["bullets"] == []


@pytest.mark.asyncio
async def test_build_resume_data_orders_bullets_by_selection_priority():
    b1, b2, b3 = _bullet(1, 1, "first"), _bullet(2, 1, "second"), _bullet(3, 1, "third")
    snap = _snap({1: [b1, b2, b3]})
    data = await dg._build_resume_data(snap=snap, selected_bullet_ids=[3, 1, 2], trimmed={})
    assert data["experiences"][0]["bullets"] == ["third", "first", "second"]


@pytest.mark.asyncio
async def test_build_resume_data_contact_links_omit_empty_fields():
    snap = _snap({1: [_bullet(1, 1)]})
    data = await dg._build_resume_data(snap=snap, selected_bullet_ids=[1], trimmed={})
    texts = [c["text"] for c in data["contact_links"]]
    assert texts == ["t@example.com"]  # phone/location/handles absent, no separators


@pytest.mark.asyncio
async def test_build_resume_data_normalizes_pasted_profile_urls():
    snap = _snap({1: [_bullet(1, 1)]})
    snap.profile.linkedin_handle = "https://www.linkedin.com/in/shyampadia/"
    snap.profile.github_handle = "github.com/crizzy9"
    snap.profile.portfolio_url = "https://crypticsoul.dev/"
    data = await dg._build_resume_data(snap=snap, selected_bullet_ids=[1], trimmed={})
    by_text = {c["text"]: c["href"] for c in data["contact_links"]}
    assert by_text["linkedin.com/in/shyampadia"] == "https://linkedin.com/in/shyampadia"
    assert by_text["github.com/crizzy9"] == "https://github.com/crizzy9"
    assert by_text["crypticsoul.dev"] == "https://crypticsoul.dev"


@pytest.mark.asyncio
async def test_build_resume_data_projects_carry_dates_and_links():
    snap = _snap({1: [_bullet(1, 1)]})
    snap.projects = [
        SimpleNamespace(
            title="Naavik",
            date=datetime(2026, 2, 1, tzinfo=UTC),
            text="Career automation platform",
            tags=[],
            link="github.com/crizzy9/naavik",
            order_index=0,
        )
    ]
    data = await dg._build_resume_data(snap=snap, selected_bullet_ids=[1], trimmed={})
    p = data["projects"][0]
    assert p["date"] == "Feb 2026"
    assert p["link"] == "https://github.com/crizzy9/naavik"


def test_extract_resume_schema_carries_profile_links():
    from llm.prompts.extract_resume import ExtractedResume

    fields = ExtractedResume.model_fields
    for name in ("linkedin_handle", "github_handle", "portfolio_url"):
        assert name in fields
