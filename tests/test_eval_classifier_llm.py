"""Correction-replay eval harness — plan 95 § 3.4.3 (slice 95f).

Env-gated (`NAAVIK_EVAL_LLM=1`): replays the owner's ClassificationCorrection
set against the LIVE classify prompt + provider and reports accuracy. Run
before merging any prompt change so "improvements" can't silently regress on
exactly the emails the owner already had to fix once.

Read-only against DATABASE_URL: renders prompts and calls the provider, but
never mutates rows (the session is rolled back). Skipped in normal CI.

    NAAVIK_EVAL_LLM=1 NAAVIK_DEBUG=1 \
    DATABASE_URL=postgresql+asyncpg://naavik:password@127.0.0.1:5433/naavik \
    uv run pytest tests/test_eval_classifier_llm.py -s
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("NAAVIK_EVAL_LLM") != "1",
    reason="live-LLM eval harness; set NAAVIK_EVAL_LLM=1 to run",
)

_MIN_ACCURACY = 0.5  # smoke floor — the report matters more than the gate


async def test_replay_corrections_against_live_prompt():
    from sqlmodel import select

    from db.session import async_session
    from llm import get_provider
    from llm.prompts.classify_email import PROMPT as CLASSIFY_PROMPT
    from llm.prompts.classify_email import EmailClassificationResult
    from models import ClassificationCorrection, EmailMessage, Settings
    from services import llm_tracker
    from services.email import few_shot

    async with async_session() as session:
        rows = (
            await session.exec(
                select(ClassificationCorrection, EmailMessage)
                .join(EmailMessage, EmailMessage.id == ClassificationCorrection.message_id)  # type: ignore[arg-type]
                .where(
                    ClassificationCorrection.kind == "reclassify",
                    ClassificationCorrection.to_classification.is_not(None),  # type: ignore[union-attr]
                )
                .order_by(ClassificationCorrection.corrected_at.desc())
                .limit(50)
            )
        ).all()
        if not rows:
            pytest.skip("no corrections recorded yet — nothing to replay")

        settings = (await session.exec(select(Settings))).first()
        assert settings is not None, "no Settings row — configure a provider first"
        provider = get_provider(settings)

        correct = 0
        results: list[tuple[int, str, str]] = []
        for correction, msg in rows:
            block = await few_shot.build_few_shot_block(
                session,
                user_id=msg.user_id,
                sender_email=msg.sender_email,
                subject=msg.subject,
            )
            # PII invariant: no raw address anywhere in the exemplar block.
            few_shot.assert_no_addresses(block)
            rendered = CLASSIFY_PROMPT.format(
                sender=msg.sender_email,
                subject=msg.subject,
                body=msg.snippet,
                owner_corrections=block,
            )
            result = await llm_tracker.tracked_call(
                session=session,
                user_id=msg.user_id,
                provider=provider,
                method="structured",
                prompt_name="classify_email_eval",
                prompt=rendered,
                schema=EmailClassificationResult,
            )
            value = getattr(result, "value", result)
            got = (
                value.get("classification", "")
                if isinstance(value, dict)
                else getattr(value, "classification", "")
            )
            got = str(got).strip().lower()
            want = str(correction.to_classification).strip().lower()
            if got == want:
                correct += 1
            results.append((msg.id or 0, want, got))

        await session.rollback()  # read-only: drop the ApiUsage rows too

    accuracy = correct / len(results)
    print(f"\ncorrection-replay accuracy: {correct}/{len(results)} = {accuracy:.0%}")
    for mid, want, got in results:
        marker = "✓" if want == got else "✗"
        print(f"  {marker} message={mid} expected={want} got={got}")
    assert accuracy >= _MIN_ACCURACY, (
        f"prompt regressed on the owner's corrected set: {accuracy:.0%} < {_MIN_ACCURACY:.0%}"
    )
