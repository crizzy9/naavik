"""scorer.match_analysis — lazy review-panel analysis (2026-07).

Pins:
- keyword hygiene in the MatchAnalysis schema (trim / dedupe / cap);
- ensure_match_analysis persistence: coverage aligned to criteria, keyword
  strengths/gaps overwrite the judge's prose, fresh-hash no-op, unscored
  no-op, and the failure cooldown stamp.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from llm.prompts.match_analysis import MatchAnalysis
from services.scorer.match_analysis import criteria_hash, ensure_match_analysis


def test_keywordize_trims_dedupes_and_caps():
    m = MatchAnalysis(
        requirements=[],
        strengths=["  distributed systems.  ", "Distributed Systems", "", "x" * 200],
        gaps=["Rust —", "rust"],
    )
    assert m.strengths[0] == "distributed systems"
    assert len(m.strengths) == 2  # dupe + empty dropped
    assert len(m.strengths[1]) <= 60
    assert m.gaps == ["Rust"]


def test_criteria_hash_stable_and_order_sensitive():
    a = criteria_hash(["one", "two"])
    assert a == criteria_hash(["one", "two"])
    assert a != criteria_hash(["two", "one"])


# ── ensure_match_analysis harness ─────────────────────────────────────────


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeSession:
    def __init__(self, *, profile, skills, experiences, bullets):
        self._profile = profile
        self._skills = skills
        self._experiences = experiences
        self._bullets = bullets
        self.added: list = []
        self.commits = 0

    async def exec(self, stmt):
        s = str(stmt)
        if "FROM profile" in s:
            return _FakeResult([self._profile])
        if "FROM skill" in s:
            return _FakeResult(self._skills)
        if "FROM experience" in s:
            return _FakeResult(self._experiences)
        if "FROM bullet" in s:
            return _FakeResult(self._bullets)
        return _FakeResult([])

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


def _job(criteria, breakdown):
    return SimpleNamespace(
        id=73,
        company="Perk",
        role="Senior Software Engineer",
        description="We need a senior engineer.",
        description_html=None,
        criteria=criteria,
        match_breakdown=breakdown,
    )


def _fake_session():
    return _FakeSession(
        profile=SimpleNamespace(id=1, summary_full="Summary.", summary_short=None),
        skills=[SimpleNamespace(category="Testing", items=["Cypress", "pytest"])],
        experiences=[SimpleNamespace(id=1, title="Senior Software Engineer")],
        bullets=[SimpleNamespace(text="Led a team building platforms")],
    )


def _patch_llm(monkeypatch, value):
    from services import llm_tracker
    from services import settings as settings_service
    from services.scorer import match_analysis as ma

    async def _get_or_create(_session, *, user_id):
        return SimpleNamespace(llm_provider=None, llm_model=None)

    async def _tracked_call(**_kwargs):
        return SimpleNamespace(value=value)

    monkeypatch.setattr(settings_service, "get_or_create", _get_or_create)
    monkeypatch.setattr(ma, "get_provider", lambda _s: object())
    monkeypatch.setattr(llm_tracker, "tracked_call", _tracked_call)


@pytest.mark.asyncio
async def test_ensure_persists_coverage_and_keywords(monkeypatch):
    _patch_llm(
        monkeypatch,
        {
            "requirements": [
                {"index": 0, "covered": True},
                {"index": 1, "covered": False},
                {"index": 9, "covered": True},  # out of range — ignored
            ],
            "strengths": ["senior engineering experience"],
            "gaps": ["Rust"],
        },
    )
    criteria = ["Senior software engineering experience", "Rust systems programming"]
    job = _job(criteria, {"score": 0.78, "strengths": ["JD wants X — candidate did Y"]})
    session = _fake_session()

    assert await ensure_match_analysis(session, job=job, user_id=2) is True
    assert session.commits == 1
    bd = job.match_breakdown
    assert bd["strengths"] == ["senior engineering experience"]
    assert bd["gaps"] == ["Rust"]
    cov = bd["requirements_coverage"]
    assert cov["criteria_hash"] == criteria_hash(criteria)
    assert cov["covered"] == [True, False]


@pytest.mark.asyncio
async def test_ensure_noops_when_fresh(monkeypatch):
    criteria = ["Senior software engineering experience"]
    job = _job(
        criteria,
        {
            "score": 0.8,
            "requirements_coverage": {
                "criteria_hash": criteria_hash(criteria),
                "covered": [True],
            },
        },
    )
    session = _fake_session()
    # No LLM patching needed — must return before any provider resolution.
    assert await ensure_match_analysis(session, job=job, user_id=2) is False
    assert session.commits == 0


@pytest.mark.asyncio
async def test_ensure_noops_on_unscored_job():
    job = _job(["anything"], {})
    session = _fake_session()
    assert await ensure_match_analysis(session, job=job, user_id=2) is False


@pytest.mark.asyncio
async def test_ensure_failure_stamps_cooldown(monkeypatch):
    from llm import LLMProviderError
    from services import llm_tracker
    from services import settings as settings_service
    from services.scorer import match_analysis as ma

    async def _get_or_create(_session, *, user_id):
        return SimpleNamespace(llm_provider=None, llm_model=None)

    async def _boom(**_kwargs):
        raise LLMProviderError("down")

    monkeypatch.setattr(settings_service, "get_or_create", _get_or_create)
    monkeypatch.setattr(ma, "get_provider", lambda _s: object())
    monkeypatch.setattr(llm_tracker, "tracked_call", _boom)

    job = _job(["req"], {"score": 0.5})
    session = _fake_session()
    assert await ensure_match_analysis(session, job=job, user_id=2) is False
    assert "analysis_failed_at" in job.match_breakdown
    # Within the cooldown window a second call skips before the LLM.
    assert await ensure_match_analysis(session, job=job, user_id=2) is False


@pytest.mark.asyncio
async def test_ensure_retries_after_cooldown_expires(monkeypatch):
    _patch_llm(monkeypatch, {"requirements": [], "strengths": ["x"], "gaps": []})
    stale = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    job = _job(["req"], {"score": 0.5, "analysis_failed_at": stale})
    session = _fake_session()
    assert await ensure_match_analysis(session, job=job, user_id=2) is True
    assert "analysis_failed_at" not in job.match_breakdown
