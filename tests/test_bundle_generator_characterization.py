"""Plan 91 Phase 3.5 — bundle_generator characterization (sqlite tier).

Pins the two under-tested legs before the Phase-4 split:

- the **typst-failure partial bundle**: when every compile raises, the
  bundle still ships reviewable content — error-carrying resume + cover
  letter documents AND real screener rows — with the trace persisted;
- the **answer_screeners legs** (never exercised through the bundle):
  profile auto-fill (reviewed, no model), LLM draft (unreviewed, model
  stamped), and USER rows preserved untouched;
- the pre-flight cost-cap skip (no LLM spend, full stages_skipped trace).

Same harness as 3.2: fake ONLY `get_provider` + `typst_compile` at the
document_generator boundary; everything else — corpus assembly, hiring-
manager regex, tracker, coverage/ethics validators, trace persistence —
runs for real against seeded sqlite.
"""

from __future__ import annotations

import enum
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlmodel import select

from llm import LLMProviderError
from llm.base import StructuredResult
from models import (
    ApiUsage,
    AppEvent,
    Application,
    ApplicationScreenerAnswer,
    Bullet,
    Certification,
    Education,
    Experience,
    GeneratedDocument,
    Job,
    Profile,
    ProfileAnswer,
    Project,
    Settings,
    Skill,
    User,
)
from models.enums import (
    ApplicationBoard,
    ApplicationStatus,
    DocsState,
    JobSource,
    ScreenerAnswerSource,
    ScreenerQuestionType,
    VisaSponsorship,
)
from services import generation as bundle_generator
from services.generation import question_fingerprint
from tests._sqlite import sqlite_session, strip_pg_checks
from typst.compiler import CompileResult, TypstError

_NOW = datetime(2026, 7, 4, 12, 0, tzinfo=UTC)

_TABLES = strip_pg_checks(
    (
        User,
        Profile,
        Experience,
        Bullet,
        Education,
        Skill,
        Project,
        Certification,
        Job,
        Application,
        GeneratedDocument,
        ApplicationScreenerAnswer,
        ProfileAnswer,
        ApiUsage,
        AppEvent,
        Settings,
    )
)


@pytest.fixture
async def session(tmp_path, monkeypatch):
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "data_dir", str(tmp_path))
    async with sqlite_session(tables=_TABLES) as s:
        s.add(User(id=1, email="owner@t.test", password_hash="x"))
        await s.flush()
        yield s


async def _raw_insert(session, obj) -> int:
    table = type(obj).__table__
    params: dict[str, object] = {}
    for col in table.columns:
        if col.name == "id":
            continue
        v = getattr(obj, col.name, None)
        if isinstance(v, enum.Enum):
            v = v.name
        elif isinstance(v, (list, dict)):
            v = json.dumps(v)
        elif isinstance(v, datetime):
            v = v.isoformat(sep=" ")
        params[col.name] = v
    names = ", ".join(params)
    placeholders = ", ".join(f":{n}" for n in params)
    await session.execute(
        text(f"INSERT INTO {table.name} ({names}) VALUES ({placeholders})"), params
    )
    return int((await session.execute(text("SELECT last_insert_rowid()"))).scalar())


async def _seed_world(session):
    profile_id = await _raw_insert(
        session,
        Profile(
            user_id=1,
            full_name="Owner Person",
            headline="Senior Engineer",
            email="owner@t.test",
            summary_short="Profile summary fallback.",
            visa_sponsorship_needed=VisaSponsorship.NEEDED_NOW,
            created_at=_NOW,
            updated_at=_NOW,
        ),
    )
    exp = Experience(
        profile_id=profile_id,
        company="Acme",
        title="Senior Engineer",
        start_date=_NOW,
        created_at=_NOW,
        updated_at=_NOW,
    )
    session.add(exp)
    await session.flush()
    bullet_ids = []
    for i, txt in enumerate(
        (
            "Built the billing pipeline handling 2M events/day.",
            "Cut p99 latency 40% by rewriting the cache layer.",
        )
    ):
        bullet_ids.append(
            await _raw_insert(
                session,
                Bullet(
                    experience_id=exp.id,
                    text=txt,
                    order=i,
                    created_at=_NOW,
                    updated_at=_NOW,
                ),
            )
        )
    job_id = await _raw_insert(
        session,
        Job(
            user_id=1,
            source=JobSource.MANUAL,
            external_id="bundle-1",
            board=ApplicationBoard.MANUAL,
            url="https://example.com/job",
            url_type="direct",
            company="Initech",
            role="Staff Engineer",
            description="Short JD.",  # <200 chars: hiring-manager stays regex-only
            found_at=_NOW,
            created_at=_NOW,
            updated_at=_NOW,
        ),
    )
    job = (await session.exec(select(Job).where(Job.id == job_id))).one()
    app = Application(
        user_id=1,
        job_id=job_id,
        company="Initech",
        role="Staff Engineer",
        status=ApplicationStatus.DRAFT,
        docs_state=DocsState.NONE,
        board=ApplicationBoard.MANUAL,
        created_at=_NOW,
        updated_at=_NOW,
    )
    session.add(app)
    await session.flush()
    return app, job, bullet_ids


def _screener_row(app_id: int, question: str, *, source, answer="", order=0, reviewed_at=None):
    return ApplicationScreenerAnswer(
        application_id=app_id,
        question_text=question,
        question_fingerprint=question_fingerprint(question),
        question_type=ScreenerQuestionType.TEXTAREA,
        required=True,
        order_index=order,
        answer=answer,
        source=source,
        reviewed_at=reviewed_at,
        created_at=_NOW,
        updated_at=_NOW,
    )


def _settings(**overrides) -> Settings:
    s = Settings(user_id=1, created_at=_NOW, updated_at=_NOW)
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


class FakeProvider:
    provider_id = "anthropic"
    model_name = "fake-model"

    def __init__(self):
        self.calls: list[str] = []

    def estimate_cost(self, *, input_tokens: int, output_tokens: int, model=None) -> float:
        return 0.001

    async def structured(self, *, prompt, schema, **_kw):
        self.calls.append(schema.__name__)
        by_schema = {
            "BulletSelection": {"selected_ids": []},
            "RefinedBullet": {"refined": "Refined against the JD, one printed line."},
            "TailoredSummary": {"summary": "Tailored summary pitch."},
            "ScreenerAnswer": {"answer": "Drafted screener answer."},
            "CoverLetterSota": {
                "format_chosen": "standard",
                "hook": "Hook paragraph.",
                "match": "Match paragraph.",
                "why_company": "Why Initech.",
                "close": "Close paragraph.",
                "hiring_manager_used": {"name": None, "source": None},
                "verbatim_phrases": [],
            },
        }
        value = by_schema.get(schema.__name__, {})
        return StructuredResult(
            text=json.dumps(value),
            input_tokens=100,
            output_tokens=20,
            model="fake-model",
            value=value,
        )

    async def complete(self, *, prompt, **_kw):  # generation_eval judge fallback
        raise LLMProviderError("no completion in fake")


def _typst_ok():
    async def compile_(template_name, data, out_pdf, *, pdf_standard=None):
        return CompileResult(
            output_path=Path(out_pdf),
            page_count=1,
            byte_size=2048,
            compiled_at=datetime.now(UTC),
        )

    return compile_


def _typst_broken():
    async def compile_(*_a, **_kw):
        raise TypstError("fontconfig exploded")

    return compile_


@pytest.mark.asyncio
async def test_bundle_survives_typst_failure_with_partial_output(session):
    """Every compile raises → the bundle still returns error-carrying resume
    + cover-letter docs AND real screener rows, trace persisted, not
    silently degraded."""
    app, job, _ = await _seed_world(session)
    session.add(
        _screener_row(app.id, "Why do you want to work here?", source=ScreenerAnswerSource.DRAFTED)
    )
    await session.flush()
    provider = FakeProvider()

    with (
        patch("services.generation.get_provider", return_value=provider),
        patch("services.generation.typst_compile", new=_typst_broken()),
    ):
        result = await bundle_generator.generate_bundle(session, app, settings=_settings(), job=job)

    # Partial-but-honest: both documents exist carrying the compile error.
    assert result.resume is not None and "fontconfig" in (result.resume.error or "")
    assert result.cover_letter is not None and "fontconfig" in (result.cover_letter.error or "")
    assert app.docs_state == DocsState.FAILED  # the resume stage marked it
    # The LLM-only stage still delivered.
    assert result.screeners and result.screeners[0].answer == "Drafted screener answer."
    # Typst failure is NOT a degrade/skip — current contract records the
    # stages as run and persists the trace.
    assert result.degraded is False and result.skipped_reason is None
    trace = app.generation_trace
    assert trace is not None
    for stage in ("corpus", "hiring_manager", "resume", "cover_letter", "screeners"):
        assert stage in trace["stages_run"]


@pytest.mark.asyncio
async def test_bundle_answer_screener_legs(session):
    """AUTO leg fills from Profile (reviewed, no model), DRAFTED leg goes
    through the LLM (unreviewed, model stamped), USER rows are untouched."""
    app, job, _ = await _seed_world(session)
    session.add(
        _screener_row(
            app.id,
            "Do you require visa sponsorship?",
            source=ScreenerAnswerSource.DRAFTED,
            order=0,
        )
    )
    session.add(
        _screener_row(
            app.id,
            "Why do you want to work here?",
            source=ScreenerAnswerSource.DRAFTED,
            order=1,
        )
    )
    session.add(
        _screener_row(
            app.id,
            "Tell us about a project you led.",
            source=ScreenerAnswerSource.USER,
            answer="My own words, hands off.",
            order=2,
            reviewed_at=_NOW,
        )
    )
    await session.flush()
    provider = FakeProvider()

    with (
        patch("services.generation.get_provider", return_value=provider),
        patch("services.generation.typst_compile", new=_typst_ok()),
    ):
        result = await bundle_generator.generate_bundle(session, app, settings=_settings(), job=job)

    by_q = {r.question_text: r for r in result.screeners}

    auto = by_q["Do you require visa sponsorship?"]
    assert auto.source == ScreenerAnswerSource.AUTO
    assert auto.answer == VisaSponsorship.NEEDED_NOW.value  # straight off the Profile
    assert auto.reviewed_at is not None  # auto-fills are pre-reviewed
    assert auto.drafted_by_model is None

    drafted = by_q["Why do you want to work here?"]
    assert drafted.source == ScreenerAnswerSource.DRAFTED
    assert drafted.answer == "Drafted screener answer."
    assert drafted.reviewed_at is None  # AI drafts wait for human review
    assert drafted.drafted_by_model == "fake-model"

    user = by_q["Tell us about a project you led."]
    assert user.source == ScreenerAnswerSource.USER
    assert user.answer == "My own words, hands off."

    # Exactly one ScreenerAnswer LLM call — AUTO + USER legs spend nothing.
    assert provider.calls.count("ScreenerAnswer") == 1


@pytest.mark.asyncio
async def test_bundle_cost_cap_preflight_skips_all_stages(session):
    app, job, _ = await _seed_world(session)
    session.add(
        ApiUsage(
            user_id=1,
            provider="anthropic",
            model="m",
            method="structured",
            input_tokens=1,
            output_tokens=1,
            cost_usd=1.0,
            latency_ms=1,
            succeeded=True,
            occurred_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
    )
    await session.flush()
    provider = FakeProvider()

    with (
        patch("services.generation.get_provider", return_value=provider),
        patch("services.generation.typst_compile", new=_typst_ok()),
    ):
        result = await bundle_generator.generate_bundle(
            session, app, settings=_settings(daily_llm_cost_cap_usd=0.5), job=job
        )

    assert result.skipped_reason == "cost_cap_reached"
    assert result.degraded is True
    assert result.resume is None and result.cover_letter is None
    assert provider.calls == []
    trace = app.generation_trace
    assert trace["degraded_mode"] is True
    assert "resume" in trace["stages_skipped"] and "screeners" in trace["stages_skipped"]
