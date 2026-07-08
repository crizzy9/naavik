"""Thread-pass eval harness — plan 96e (mirrors the 95f classifier harness).

Env-gated (`NAAVIK_EVAL_LLM=1`): renders the LIVE classify_thread prompt over
the owner's real interview conversations and reports what it derives —
process stage, itemized rounds, rejection, needs_scheduling. Read-only
(session rolled back). Run before merging any prompt change:

    NAAVIK_EVAL_LLM=1 NAAVIK_DEBUG=1 \
    DATABASE_URL=postgresql+asyncpg://naavik:password@127.0.0.1:5433/naavik \
    uv run pytest tests/test_eval_thread_pass_llm.py -s
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("NAAVIK_EVAL_LLM") != "1",
    reason="live-LLM eval harness; set NAAVIK_EVAL_LLM=1 to run",
)

_MAX_THREADS = 8


async def test_thread_pass_over_live_conversations():
    from sqlmodel import select

    from db.session import async_session
    from llm import get_provider
    from llm.prompts.classify_thread import PROMPT, ThreadReconcileResult
    from models import Application, EmailMessage, EmailThread, Settings
    from models.enums import EmailClassification
    from services import llm_tracker
    from services.email.reconcile import _render_conversation

    async with async_session() as session:
        threads = (
            await session.exec(
                select(EmailThread, Application)
                .join(Application, Application.id == EmailThread.application_id)  # type: ignore[arg-type]
                .where(
                    EmailThread.classification == EmailClassification.INTERVIEW_REQUEST,
                    EmailThread.message_count >= 2,
                )
                .order_by(EmailThread.latest_message_at.desc())
                .limit(_MAX_THREADS)
            )
        ).all()
        assert threads, "no linked interview threads in this DB"
        settings = (
            await session.exec(select(Settings).where(Settings.user_id == threads[0][1].user_id))
        ).one()
        provider = get_provider(settings)

        parsed_ok = 0
        for thread, application in threads:
            messages = (
                await session.exec(
                    select(EmailMessage)
                    .where(EmailMessage.thread_id == thread.id)
                    .order_by(EmailMessage.received_at.desc())
                    .limit(12)
                )
            ).all()
            role_clause = f" for the role {application.role!r}" if application.role else ""
            rendered = PROMPT.format(
                company=application.company,
                role_clause=role_clause,
                conversation=_render_conversation(list(messages)),
            )
            raw = await llm_tracker.tracked_call(
                session=session,
                user_id=application.user_id,
                provider=provider,
                method="structured",
                prompt_name="classify_thread",
                prompt=rendered,
                schema=ThreadReconcileResult,
            )
            value = getattr(raw, "value", raw)
            parsed = (
                value
                if isinstance(value, ThreadReconcileResult)
                else ThreadReconcileResult.model_validate(value)
            )
            parsed_ok += 1
            print(f"\n=== {application.company} — {thread.subject[:70]}")
            print(
                f"    stage={parsed.process_stage} rejection={parsed.rejection} "
                f"needs_scheduling={parsed.needs_scheduling}"
            )
            for r in parsed.rounds:
                print(f"    · {r.kind} {r.title or ''} {r.date or ''} {r.time or ''} [{r.state}]")
        await session.rollback()

    assert parsed_ok == len(threads)
