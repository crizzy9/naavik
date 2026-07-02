"""Job-search preferences service tests (docs/design/JOB_SEARCH_PREFERENCES.md).

Covers title matching/normalization, per-source derivation with override
precedence, expansion refresh (LLM + graceful no-provider degrade), and
resume-parse prefill.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from llm.base import LLMProviderError
from models.enums import JobSource
from services import search_prefs

pytestmark = pytest.mark.uses_sample_data_shims


class _FakeSession:
    def __init__(self) -> None:
        self.added: list = []
        self.exec_queue: list = []
        self.flush_count = 0

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flush_count += 1

    async def exec(self, _stmt):
        if not self.exec_queue:
            return SimpleNamespace(one_or_none=lambda: None, all=lambda: [], first=lambda: None)
        return self.exec_queue.pop(0)


def _profile(**kw):
    base = {
        "id": 1,
        "user_id": 1,
        "headline": "Senior Software Engineer at Intuit",
        "location": None,
        "target_titles": [],
        "title_expansions": {},
        "target_cities": [],
        "remote_ok": True,
        "updated_at": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _settings(**kw):
    base = {
        "user_id": 1,
        "linkedin_keywords": None,
        "linkedin_location": None,
        "indeed_keywords": None,
        "indeed_location": None,
        "llm_provider": None,
        "llm_model": "m",
        "llm_fallback_provider": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


# ── title matching ────────────────────────────────────────────────────


def test_title_matches_normalizes_roman_numerals_and_containment():
    p = _profile(
        target_titles=["Senior Software Engineer"],
        title_expansions={
            "Senior Software Engineer": {
                "expanded": ["Senior Software Engineer", "Software Engineer III", "SDE 3"],
                "model": "test",
            }
        },
    )
    assert search_prefs.title_matches("Software Engineer 3", p)
    assert search_prefs.title_matches("Senior Software Engineer, Payments", p)
    assert search_prefs.title_matches("SDE 3", p)
    assert not search_prefs.title_matches("Product Designer", p)


def test_title_matches_everything_when_no_prefs():
    assert search_prefs.title_matches("Anything At All", _profile())


def test_expanded_title_set_includes_raw_titles():
    p = _profile(target_titles=["ML Engineer"], title_expansions={})
    assert "ml engineer" in search_prefs.expanded_title_set(p)


# ── derivation + override precedence ─────────────────────────────────


def test_derive_source_inputs_override_wins():
    s = _settings(linkedin_keywords=["staff engineer"], linkedin_location="NYC")
    p = _profile(target_titles=["SRE"], target_cities=["Austin, TX"])
    kw, loc, is_override = search_prefs.derive_source_inputs(p, s, JobSource.LINKEDIN)
    assert (kw, loc, is_override) == (["staff engineer"], "NYC", True)


def test_derive_source_inputs_derives_from_profile():
    s = _settings()
    p = _profile(target_titles=["SRE", "Platform Engineer"], target_cities=["Austin, TX"])
    kw, loc, is_override = search_prefs.derive_source_inputs(p, s, JobSource.INDEED)
    assert kw == ["SRE", "Platform Engineer"]
    assert loc == "Austin, TX"
    assert is_override is False


def test_derive_source_inputs_no_profile_no_override_is_empty():
    kw, loc, is_override = search_prefs.derive_source_inputs(None, _settings(), JobSource.LINKEDIN)
    assert (kw, loc, is_override) == ([], None, False)


# ── expansion refresh ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_title_expansions_degrades_without_provider(monkeypatch):
    def _raise(_settings_row):
        raise LLMProviderError("no provider", kind="auth_required")

    monkeypatch.setattr(search_prefs, "get_provider", _raise)
    p = _profile(target_titles=["ML Engineer"])
    session = _FakeSession()
    changed = await search_prefs.refresh_title_expansions(
        session, profile=p, settings=_settings()
    )
    assert changed is True
    entry = p.title_expansions["ML Engineer"]
    assert entry["expanded"] == ["ML Engineer"]
    assert entry["model"] == "none"


@pytest.mark.asyncio
async def test_refresh_title_expansions_stores_llm_output(monkeypatch):
    provider = SimpleNamespace(model_name="test-model")
    monkeypatch.setattr(search_prefs, "get_provider", lambda _s: provider)
    tracked = AsyncMock(
        return_value=SimpleNamespace(
            value={
                "expansions": [
                    {
                        "title": "ML Engineer",
                        "expanded": ["ML Engineer", "Machine Learning Engineer", "MLE"],
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(search_prefs.llm_tracker, "tracked_call", tracked)

    p = _profile(target_titles=["ML Engineer"])
    session = _FakeSession()
    changed = await search_prefs.refresh_title_expansions(
        session, profile=p, settings=_settings()
    )
    assert changed is True
    entry = p.title_expansions["ML Engineer"]
    assert "Machine Learning Engineer" in entry["expanded"]
    assert entry["model"] == "test-model"
    tracked.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_title_expansions_prunes_removed_titles_and_skips_fresh(monkeypatch):
    monkeypatch.setattr(
        search_prefs.llm_tracker, "tracked_call", AsyncMock(side_effect=AssertionError)
    )
    p = _profile(
        target_titles=["Kept Title"],
        title_expansions={
            "Kept Title": {"expanded": ["Kept Title", "KT II"], "model": "test"},
            "Removed Title": {"expanded": ["Removed Title"], "model": "test"},
        },
    )
    session = _FakeSession()
    changed = await search_prefs.refresh_title_expansions(
        session, profile=p, settings=_settings()
    )
    assert changed is True  # pruning counts as change
    assert "Removed Title" not in p.title_expansions
    assert p.title_expansions["Kept Title"]["expanded"] == ["Kept Title", "KT II"]


# ── prefill from resume parse ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_prefill_seeds_title_from_latest_experience_and_city():
    latest = SimpleNamespace(title="Staff Software Engineer")
    session = _FakeSession()
    session.exec_queue = [SimpleNamespace(first=lambda: latest)]
    p = _profile(location="Boston, MA")
    changed = await search_prefs.prefill_search_prefs(session, profile=p)
    assert changed is True
    assert p.target_titles == ["Staff Software Engineer"]
    assert p.target_cities == ["Boston, MA"]


@pytest.mark.asyncio
async def test_prefill_falls_back_to_headline_and_never_overwrites():
    session = _FakeSession()
    p = _profile(headline="ML Engineer at Foo Corp")
    changed = await search_prefs.prefill_search_prefs(session, profile=p)
    assert changed and p.target_titles == ["ML Engineer"]

    session2 = _FakeSession()
    p2 = _profile(target_titles=["Existing"], target_cities=["Austin, TX"])
    assert await search_prefs.prefill_search_prefs(session2, profile=p2) is False
    assert p2.target_titles == ["Existing"]
