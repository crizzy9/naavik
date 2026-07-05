"""Plan 91 Phase 3.2 — document_generator end-to-end characterization.

The existing `test_document_generator.py` suite pins the module's PRIVATE
call graph (21 `patch("services.generation._x")` targets) — it would
break on the Phase-4 split without proving behaviour preservation. This file
is the test that survives the split: it fakes ONLY the process boundaries
(`get_provider` → a scripted provider, `typst_compile` → a scripted
CompileResult) and lets `load_profile_snapshot`, the cost-cap query, the
prompt modules, the page-fit loop, and the GeneratedDocument persistence run
for real against a seeded sqlite session.
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
    Application,
    Bullet,
    Certification,
    Education,
    Experience,
    GeneratedDocument,
    Job,
    Profile,
    Project,
    Settings,
    Skill,
    User,
)
from models.enums import (
    ApplicationBoard,
    ApplicationStatus,
    DocsState,
    GeneratedDocumentKind,
    JobSource,
)
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
        ApiUsage,
    )
)


@pytest.fixture
async def session(tmp_path, monkeypatch):
    # Keep generated PDFs (paths only — typst is faked) out of the repo.
    from config import settings as app_settings

    monkeypatch.setattr(app_settings, "data_dir", str(tmp_path))
    async with sqlite_session(tables=_TABLES) as s:
        s.add(User(id=1, email="owner@t.test", password_hash="x"))
        await s.flush()
        yield s


# ── Seed helpers (raw SQL for ARRAY-bearing rows, same as 3.1) ──────────


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
    """One profile, two experiences with 2+1 bullets, a job, and a DRAFT."""
    profile_id = await _raw_insert(
        session,
        Profile(
            user_id=1,
            full_name="Owner Person",
            headline="Senior Engineer",
            email="owner@t.test",
            summary_short="Profile summary fallback.",
            created_at=_NOW,
            updated_at=_NOW,
        ),
    )
    exp1 = Experience(
        profile_id=profile_id,
        company="Acme",
        title="Senior Engineer",
        start_date=_NOW,
        created_at=_NOW,
        updated_at=_NOW,
    )
    exp2 = Experience(
        profile_id=profile_id,
        company="Globex",
        title="Engineer",
        start_date=_NOW,
        created_at=_NOW,
        updated_at=_NOW,
    )
    session.add(exp1)
    session.add(exp2)
    await session.flush()
    bullet_ids = []
    for exp, txt in (
        (exp1, "Built the billing pipeline handling 2M events/day."),
        (exp1, "Cut p99 latency 40% by rewriting the cache layer."),
        (exp2, "Shipped the onboarding flow used by 100k users."),
    ):
        bullet_ids.append(
            await _raw_insert(
                session,
                Bullet(
                    experience_id=exp.id,
                    text=txt,
                    order=len(bullet_ids),
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
            external_id="e2e-1",
            board=ApplicationBoard.MANUAL,
            url="https://example.com/job",
            url_type="direct",
            company="Initech",
            role="Staff Engineer",
            description="We need someone who has built billing pipelines at scale.",
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


def _settings(**overrides) -> Settings:
    s = Settings(user_id=1, created_at=_NOW, updated_at=_NOW)
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


class FakeProvider:
    """Scripted provider — dispatches on the structured-output schema."""

    provider_id = "anthropic"
    model_name = "fake-model"

    def __init__(self, *, selected_ids=None, fail=False):
        self.selected_ids = selected_ids or []
        self.fail = fail
        self.calls: list[str] = []

    def estimate_cost(self, *, input_tokens: int, output_tokens: int, model=None) -> float:
        return 0.001

    async def structured(self, *, prompt, schema, **_kw):
        self.calls.append(schema.__name__)
        if self.fail:
            raise LLMProviderError("provider down")
        if schema.__name__ == "BulletSelection":
            value = {"selected_ids": self.selected_ids}
        elif schema.__name__ == "RefinedBullet":
            value = {"refined": "Refined against the JD, one printed line."}
        elif schema.__name__ == "TailoredSummary":
            value = {"summary": "Tailored summary pitch for Initech."}
        else:  # pragma: no cover — new prompt schema reached this path
            value = {}
        return StructuredResult(
            text=json.dumps(value),
            input_tokens=100,
            output_tokens=20,
            model="fake-model",
            value=value,
        )


def _fake_typst(page_counts: list[int]):
    """Async typst stand-in yielding the scripted page counts (last repeats)."""
    seq = list(page_counts)

    async def compile_(template_name, data, out_pdf, *, pdf_standard=None):
        pc = seq.pop(0) if len(seq) > 1 else seq[0]
        return CompileResult(
            output_path=Path(out_pdf),
            page_count=pc,
            byte_size=2048,
            compiled_at=datetime.now(UTC),
        )

    return compile_


async def _usage_rows(session) -> list[ApiUsage]:
    return list((await session.exec(select(ApiUsage))).all())


# ── End-to-end paths ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_resume_end_to_end(session):
    """Happy path: rank → refine every bullet → tailor summary → compile →
    GeneratedDocument row with the full selection blob; every LLM call lands
    an ApiUsage row through the real tracker."""
    from services import generation as dg

    app, job, bullet_ids = await _seed_world(session)
    provider = FakeProvider(selected_ids=list(reversed(bullet_ids)))

    with (
        patch("services.generation.get_provider", return_value=provider),
        patch("services.generation.typst_compile", new=_fake_typst([1])),
    ):
        doc = await dg.generate_resume(session, app, settings=_settings(), job=job)

    assert doc.kind == GeneratedDocumentKind.RESUME
    assert doc.page_count == 1
    assert doc.error is None
    assert app.docs_state == DocsState.READY

    blob = doc.bullet_selection
    # All three bullets fit (page never overflowed) and every experience kept ≥1.
    assert sorted(blob["selected_ids"]) == sorted(bullet_ids)
    assert blob["ranked_ids"] == list(reversed(bullet_ids))  # provider's order won
    assert blob["dropped_for_fit"] == []
    assert blob["summary"] == "Tailored summary pitch for Initech."
    assert set(blob["trimmed_lines"]) == {str(b) for b in bullet_ids}
    for line in blob["trimmed_lines"].values():
        assert line == "Refined against the JD, one printed line."
    assert blob["jd_hash"] and blob["template_version"]

    # 1 rank + 3 refines + 1 summary through the real tracker.
    rows = await _usage_rows(session)
    assert len(rows) == 5
    assert all(r.succeeded for r in rows)
    assert {r.model for r in rows} == {"fake-model"}


@pytest.mark.asyncio
async def test_generate_resume_page_fit_drops_lowest_priority(session):
    """First compile overflows → the fit loop drops the lowest-ranked bullet
    and converges to one page; the drop is recorded in the selection blob."""
    from services import generation as dg

    app, job, bullet_ids = await _seed_world(session)
    provider = FakeProvider(selected_ids=bullet_ids)

    with (
        patch("services.generation.get_provider", return_value=provider),
        patch("services.generation.typst_compile", new=_fake_typst([2, 1])),
    ):
        doc = await dg.generate_resume(session, app, settings=_settings(), job=job)

    assert doc.page_count == 1
    blob = doc.bullet_selection
    assert len(blob["dropped_for_fit"]) == 1
    assert len(blob["selected_ids"]) == len(bullet_ids) - 1
    # Every experience still holds at least one bullet.
    assert app.docs_state == DocsState.READY


@pytest.mark.asyncio
async def test_generate_resume_cost_cap_short_circuits(session):
    """Today's real ApiUsage spend ≥ cap → CostCapExceededError before any
    provider call (exercises the real spend query)."""
    from services import generation as dg

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
        patch("services.generation.typst_compile", new=_fake_typst([1])),
        pytest.raises(dg.CostCapExceededError),
    ):
        await dg.generate_resume(
            session, app, settings=_settings(daily_llm_cost_cap_usd=0.5), job=job
        )
    assert provider.calls == []
    assert app.docs_state == DocsState.NONE  # never flipped to GENERATING


@pytest.mark.asyncio
async def test_generate_resume_degrades_without_provider(session):
    """Provider hard-fails every call → rank falls back to profile order,
    refine falls back to the original text, summary falls back to the profile
    summary — the document still ships."""
    from services import generation as dg

    app, job, bullet_ids = await _seed_world(session)
    provider = FakeProvider(fail=True)

    with (
        patch("services.generation.get_provider", return_value=provider),
        patch("services.generation.typst_compile", new=_fake_typst([1])),
    ):
        doc = await dg.generate_resume(session, app, settings=_settings(), job=job)

    assert doc.error is None
    assert app.docs_state == DocsState.READY
    blob = doc.bullet_selection
    assert blob["ranked_ids"] == bullet_ids  # profile order fallback
    assert blob["summary"] == "Profile summary fallback."
    # Short originals pass through untouched by the truncation fallback.
    originals = {
        "Built the billing pipeline handling 2M events/day.",
        "Cut p99 latency 40% by rewriting the cache layer.",
        "Shipped the onboarding flow used by 100k users.",
    }
    assert set(blob["trimmed_lines"].values()) == originals
    # The tracker recorded the failures.
    rows = await _usage_rows(session)
    assert rows and all(not r.succeeded for r in rows)


@pytest.mark.asyncio
async def test_generate_resume_typst_error_marks_failed(session):
    """TypstError → docs_state FAILED + an error-carrying GeneratedDocument."""
    from services import generation as dg

    app, job, _ = await _seed_world(session)
    provider = FakeProvider()

    async def broken_compile(*_a, **_kw):
        raise TypstError("missing font")

    with (
        patch("services.generation.get_provider", return_value=provider),
        patch("services.generation.typst_compile", new=broken_compile),
    ):
        doc = await dg.generate_resume(session, app, settings=_settings(), job=job)

    assert app.docs_state == DocsState.FAILED
    assert doc.error and "missing font" in doc.error
    assert doc.page_count is None
