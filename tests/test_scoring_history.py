"""scoring_history service — plan 73 (0.3.2.03).

Covers the heuristic substring classifier (all 9 Tag families + other),
the aggregator (empty input, multi-family, missing days, window
boundaries), and the profile-side update helper round-trip.

Persistence-side tests use a fake `AsyncSession` that returns a fixed
Job list — avoids sqlite ARRAY binding constraints while still exercising
the aggregator's logic + the `update_profile_score_history` write path
against an in-memory Profile row.
"""

from __future__ import annotations

import os

os.environ.setdefault("NAAVIK_DEBUG", "1")

from dataclasses import dataclass, field  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402

from services.scorer.history import (  # noqa: E402
    aggregate_score_history,
    classify_role_family,
)

# ── 1. Classifier coverage ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        ("Senior ML Engineer", "ai-ml"),
        ("Machine Learning Engineer", "ai-ml"),
        ("Applied Scientist", "ai-ml"),
        ("Senior Data Scientist", "ai-ml"),
        ("GenAI Platform Engineer", "genai"),
        ("LLM Application Developer", "genai"),
        ("Prompt Engineer", "genai"),
        ("Senior Frontend Engineer", "frontend"),
        ("Front-End Engineer", "frontend"),
        ("UI Engineer", "frontend"),
        ("Senior Data Engineer", "data-eng"),
        ("Analytics Engineer", "data-eng"),
        ("DevOps Engineer", "devops"),
        ("Senior SRE", "devops"),
        ("Site Reliability Engineer", "devops"),
        ("Infrastructure Engineer", "devops"),
        ("Platform Engineer", "platform"),
        ("Developer Platform Engineer", "platform"),
        ("Engineering Manager", "leadership"),
        ("Staff Engineer", "leadership"),
        ("Principal Engineer", "leadership"),
        ("Tech Lead", "leadership"),
        ("Founding Engineer", "product"),
        ("Product Engineer", "product"),
        ("Senior Backend Engineer", "backend"),
        ("API Engineer", "backend"),
        ("Software Engineer", "backend"),
        ("Senior Software Engineer", "backend"),
    ],
)
def test_classify_role_family_known(role: str, expected: str) -> None:
    assert classify_role_family(role) == expected


@pytest.mark.parametrize(
    "role",
    ["", None, "Underwater Basket Weaver", "Customer Success Manager"],
)
def test_classify_role_family_falls_back_to_other(role: str | None) -> None:
    assert classify_role_family(role) == "other"


def test_classify_role_family_priority_ml_over_swe() -> None:
    """ML engineer must NOT fall through to backend's 'software engineer'."""
    assert classify_role_family("Senior ML Software Engineer") == "ai-ml"


def test_classify_role_family_priority_genai_over_aiml() -> None:
    """GenAI must NOT fall through to ai-ml's 'ai ' substring."""
    assert classify_role_family("GenAI Platform Engineer") == "genai"


# ── 2. Aggregator (fake-session) ─────────────────────────────────────────


@dataclass
class _StubJob:
    """Minimal Job duck-type. Only fields the aggregator reads."""

    user_id: int
    role: str
    match_breakdown: dict
    deleted_at: datetime | None = None


@dataclass
class _FakeResult:
    rows: list[Any]

    def all(self) -> list[Any]:
        return list(self.rows)

    def one_or_none(self) -> Any | None:
        return self.rows[0] if self.rows else None


@dataclass
class _FakeSession:
    """AsyncSession stub that filters by `user_id == ?` in the WHERE clause.

    The aggregator builds: `select(Job).where(user_id == X, deleted_at IS NULL)`.
    This stub inspects the statement's compiled params + filters in-memory.
    """

    jobs: list[_StubJob] = field(default_factory=list)
    profiles: dict[int, Any] = field(default_factory=dict)
    last_added: Any | None = None

    async def exec(self, stmt) -> _FakeResult:
        # Walk the compiled clause to find the `user_id == X` literal.
        # SQLModel's `select(Profile)` and `select(Job)` produce a Select
        # node; we inspect `stmt.whereclause` for BinaryExpression on
        # `user_id` and `deleted_at`.
        from sqlalchemy.sql.elements import BinaryExpression

        target_user_id: int | None = None
        from_clause = stmt.get_final_froms()[0] if stmt.get_final_froms() else None
        target_table = from_clause.name if from_clause is not None else None

        clause = stmt.whereclause
        if clause is not None:
            stack = [clause]
            while stack:
                node = stack.pop()
                if isinstance(node, BinaryExpression):
                    left = getattr(node.left, "key", None) or getattr(node.left, "name", None)
                    right = node.right
                    if left == "user_id" and hasattr(right, "value"):
                        target_user_id = int(right.value)
                # Walk AND/OR children.
                for child in getattr(node, "clauses", []) or []:
                    stack.append(child)

        if target_table == "job":
            rows = [
                j
                for j in self.jobs
                if (target_user_id is None or j.user_id == target_user_id) and j.deleted_at is None
            ]
            return _FakeResult(rows)
        if target_table == "profile":
            row = self.profiles.get(target_user_id) if target_user_id else None
            return _FakeResult([row] if row else [])
        return _FakeResult([])

    def add(self, obj) -> None:
        self.last_added = obj
        # Reflect score_history writes back into the profiles map.
        if hasattr(obj, "user_id") and hasattr(obj, "score_history"):
            self.profiles[int(obj.user_id)] = obj

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None


@pytest.mark.asyncio
async def test_aggregator_empty_when_no_jobs() -> None:
    session = _FakeSession()
    blob = await aggregate_score_history(session, 1)
    assert blob["families"] == []
    assert "last_aggregated_at" in blob


def _stub(user_id: int, role: str, score: float, scored_at: datetime) -> _StubJob:
    return _StubJob(
        user_id=user_id,
        role=role,
        match_breakdown={"score": score, "scored_at": scored_at.isoformat()},
    )


@pytest.mark.asyncio
async def test_aggregator_multi_family_grouping() -> None:
    now = datetime(2026, 5, 21, 12, 0, tzinfo=UTC)
    yesterday = now - timedelta(days=1)
    session = _FakeSession(
        jobs=[
            _stub(1, "Senior ML Engineer", 0.9, now),
            _stub(1, "Senior Backend Engineer", 0.7, yesterday),
            _stub(1, "Senior Backend Engineer", 0.8, now),
        ]
    )
    blob = await aggregate_score_history(session, 1, now=now)
    families_by_name = {f["family"]: f for f in blob["families"]}
    assert set(families_by_name) == {"ai-ml", "backend"}

    ai_ml = families_by_name["ai-ml"]
    assert ai_ml["scored_count_30d"] == 1
    assert ai_ml["score_current"] == 0.9
    assert ai_ml["score_delta_30d"] == 0.0  # single data point

    backend = families_by_name["backend"]
    assert backend["scored_count_30d"] == 2
    assert backend["score_current"] == 0.8
    assert backend["score_delta_30d"] == pytest.approx(0.1)
    # 30 daily means slots; last two days carry data, earlier days are None
    assert len(backend["daily_means"]) == 30
    assert backend["daily_means"][-1] == 0.8
    assert backend["daily_means"][-2] == 0.7
    assert backend["daily_means"][0] is None


@pytest.mark.asyncio
async def test_aggregator_filters_outside_window() -> None:
    now = datetime(2026, 5, 21, 12, 0, tzinfo=UTC)
    too_old = now - timedelta(days=45)
    in_window = now - timedelta(days=10)
    session = _FakeSession(
        jobs=[
            _stub(1, "ML Engineer", 0.5, too_old),
            _stub(1, "ML Engineer", 0.9, in_window),
        ]
    )
    blob = await aggregate_score_history(session, 1, now=now)
    assert len(blob["families"]) == 1
    family = blob["families"][0]
    assert family["scored_count_30d"] == 1
    assert family["score_current"] == 0.9


@pytest.mark.asyncio
async def test_aggregator_ignores_missing_scored_at() -> None:
    """Job rows whose match_breakdown lacks scored_at are skipped."""
    now = datetime(2026, 5, 21, 12, 0, tzinfo=UTC)
    session = _FakeSession(
        jobs=[
            _StubJob(
                user_id=1,
                role="Backend Engineer",
                match_breakdown={"backend": 0.75},  # legacy flat shape; no scored_at
            )
        ]
    )
    blob = await aggregate_score_history(session, 1, now=now)
    assert blob["families"] == []


@pytest.mark.asyncio
async def test_aggregator_filters_other_user_jobs() -> None:
    """Cross-user isolation: aggregator only sees user_id rows."""
    now = datetime(2026, 5, 21, 12, 0, tzinfo=UTC)
    session = _FakeSession(
        jobs=[
            _stub(1, "ML Engineer", 0.9, now),
            _stub(2, "ML Engineer", 0.1, now),
        ]
    )
    blob_a = await aggregate_score_history(session, 1, now=now)
    blob_b = await aggregate_score_history(session, 2, now=now)
    assert blob_a["families"][0]["score_current"] == 0.9
    assert blob_b["families"][0]["score_current"] == 0.1


@pytest.mark.asyncio
async def test_aggregator_skips_soft_deleted_jobs() -> None:
    """`deleted_at IS NOT NULL` rows are filtered."""
    now = datetime(2026, 5, 21, 12, 0, tzinfo=UTC)
    session = _FakeSession(
        jobs=[
            _StubJob(
                user_id=1,
                role="ML Engineer",
                match_breakdown={"score": 0.9, "scored_at": now.isoformat()},
                deleted_at=now - timedelta(days=1),
            )
        ]
    )
    blob = await aggregate_score_history(session, 1, now=now)
    assert blob["families"] == []


# ── 3. Service helper round-trip ─────────────────────────────────────────


class _StubProfile:
    """Plain Python stand-in for Profile (no SQLModel validators)."""

    def __init__(self, user_id: int, score_history: dict | None = None) -> None:
        self.user_id = user_id
        self.deleted_at = None
        self.score_history = score_history or {}
        self.updated_at = datetime.now(UTC)


@pytest.mark.asyncio
async def test_update_profile_score_history_round_trip() -> None:
    from services.scorer import history as scoring_history

    now = datetime(2026, 5, 21, 12, 0, tzinfo=UTC)
    profile = _StubProfile(user_id=1)
    session = _FakeSession(
        jobs=[_stub(1, "ML Engineer", 0.84, now)],
        profiles={1: profile},
    )
    blob = await scoring_history.update_profile_score_history(session, 1, now=now)
    assert blob is not None
    assert blob["families"][0]["family"] == "ai-ml"
    assert profile.score_history == blob


@pytest.mark.asyncio
async def test_update_profile_score_history_missing_profile() -> None:
    """Helper returns None when the user has no Profile."""
    from services.scorer import history as scoring_history

    session = _FakeSession(jobs=[], profiles={})
    result = await scoring_history.update_profile_score_history(session, 99)
    assert result is None


# ── 4. get_score_history accessor ────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_score_history_returns_empty_when_profile_missing() -> None:
    from services.profile import get_score_history

    session = _FakeSession()
    assert await get_score_history(session, 99) == {}


@pytest.mark.asyncio
async def test_get_score_history_returns_blob_when_present() -> None:
    from services.profile import get_score_history

    blob = {"last_aggregated_at": "2026-05-21T00:00:00+00:00", "families": []}
    profile = _StubProfile(user_id=1, score_history=blob)
    session = _FakeSession(profiles={1: profile})
    assert await get_score_history(session, 1) == blob


# ── 5. Plan 75 / 0.3.3.18 — _parse_scored_at defensive parsing ───────────


def test_parse_scored_at_rejects_epoch_int_string() -> None:
    """Epoch ints look numeric but aren't ISO 8601 — return None."""
    from services.scorer.history import _parse_scored_at

    assert _parse_scored_at("1716285600") is None


def test_parse_scored_at_rejects_natural_language() -> None:
    """Non-digit start fails the early rejection check."""
    from services.scorer.history import _parse_scored_at

    assert _parse_scored_at("yesterday") is None
    assert _parse_scored_at("today") is None
    assert _parse_scored_at("now") is None


def test_parse_scored_at_accepts_naive_iso() -> None:
    """Naive ISO timestamps get UTC attached (preserves existing tolerance)."""
    from services.scorer.history import _parse_scored_at

    out = _parse_scored_at("2026-05-21T10:00:00")
    assert out is not None
    assert out.tzinfo is not None
    assert out.year == 2026
    assert out.hour == 10


def test_parse_scored_at_accepts_zulu_suffix() -> None:
    """Zulu (`Z`) suffix is converted to `+00:00`."""
    from services.scorer.history import _parse_scored_at

    out = _parse_scored_at("2026-05-21T10:00:00Z")
    assert out is not None
    assert out.utcoffset().total_seconds() == 0


def test_parse_scored_at_accepts_bare_date() -> None:
    """Bare YYYY-MM-DD is valid ISO 8601 — accept it."""
    from services.scorer.history import _parse_scored_at

    out = _parse_scored_at("2026-05-21")
    assert out is not None
    assert out.year == 2026


def test_parse_scored_at_empty_string_returns_none() -> None:
    from services.scorer.history import _parse_scored_at

    assert _parse_scored_at("") is None
    assert _parse_scored_at("   ") is None
