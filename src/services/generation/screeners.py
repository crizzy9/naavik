"""Screener answering — auto-fill fingerprints, reuse cache, LLM draft.

Split out of the former services/document_generator.py in plan 91 Phase 4.3;
behaviour unchanged. Internal calls to patched seams go through `svc()`
(the facade) so test interception keeps working.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from llm import LLMProvider, LLMProviderError
from models import (
    Application,
    ApplicationScreenerAnswer,
    Job,
    Profile,
    ScreenerAnswerSource,
    ScreenerQuestionType,
    Settings,
)
from services.generation.common import svc
from services.generation.cost_cap import CostCapExceededError

log = logging.getLogger(__name__)


_AUTO_FILL_FINGERPRINTS: dict[str, str] = {
    # Lowercased keyword tokens → Profile field name.
    "earliest start": "earliest_start",
    "start date": "earliest_start",
    "salary expectation": "salary_expectation_usd",
    "salary requirement": "salary_expectation_usd",
    "work authorization": "work_authorization",
    "authorized to work": "work_authorization",
    "visa sponsorship": "visa_sponsorship_needed",
    "require sponsorship": "visa_sponsorship_needed",
    "willing to relocate": "willing_to_relocate",
    "relocate": "willing_to_relocate",
    "veteran": "veteran_status",
    "disability": "disability_status",
    "race": "race_ethnicity",
    "ethnicity": "race_ethnicity",
    "gender": "gender_identity",
}


def question_fingerprint(question_text: str) -> str:
    """Lowercase + strip punctuation + remove company name (best-effort)."""
    s = (question_text or "").lower()
    out = "".join(c if c.isalnum() or c.isspace() else " " for c in s)
    return " ".join(out.split())


def _auto_field_for_question(question_text: str) -> str | None:
    fp = question_fingerprint(question_text)
    for keyword, field_name in _AUTO_FILL_FINGERPRINTS.items():
        if keyword in fp:
            return field_name
    return None


def _profile_value_for_field(profile: Profile, field: str) -> str | None:
    raw = getattr(profile, field, None)
    if raw is None:
        return None
    if isinstance(raw, datetime | date):
        return raw.isoformat()
    return str(raw.value if hasattr(raw, "value") else raw)


async def answer_screeners(
    session: AsyncSession,
    application: Application,
    *,
    settings: Settings,
    job: Job | None = None,
    questions: Iterable[dict[str, Any]] | None = None,
    system: str | None = None,
    cache_system: bool = False,
) -> list[ApplicationScreenerAnswer]:
    """Populate / refresh ApplicationScreenerAnswer rows for `application`.

    `questions` is the ordered list of `{question_text, question_type,
    choices?, required?}` dicts extracted by the scraper. If omitted, the
    function works with whatever `ApplicationScreenerAnswer` rows already
    exist on the application (auto-fill / draft loop).

    Each row carries `source` + `drafted_by_model` + `reviewed_at` per
    DATA_MODEL.md § J. Auto-fills set `reviewed_at = utcnow()`; AI-drafts
    leave it null until user reviews.
    """
    user_id = application.user_id
    if await svc().is_cost_capped(session, user_id, settings):
        raise CostCapExceededError("daily_llm_cost_cap_usd reached")

    profile_row = (
        await session.exec(
            select(Profile).where(Profile.user_id == user_id, Profile.deleted_at.is_(None))
        )
    ).one_or_none()
    if profile_row is None:
        raise ValueError(f"no profile for user_id={user_id}")
    if job is None and application.job_id is not None:
        job = (await session.exec(select(Job).where(Job.id == application.job_id))).one_or_none()

    # Pull existing rows so we can update in-place where appropriate.
    existing = (
        await session.exec(
            select(ApplicationScreenerAnswer).where(
                ApplicationScreenerAnswer.application_id == application.id
            )
        )
    ).all()
    by_fp = {row.question_fingerprint: row for row in existing}

    questions_list: list[dict[str, Any]] = list(questions or [])
    if not questions_list:
        # Use existing rows as the question list.
        for row in existing:
            questions_list.append(
                {
                    "question_text": row.question_text,
                    "question_type": row.question_type,
                    "choices": row.choices,
                    "required": row.required,
                    "order_index": row.order_index,
                }
            )

    out_rows: list[ApplicationScreenerAnswer] = []
    provider: LLMProvider | None = None  # Lazy — only instantiate if drafting needed.
    now = datetime.now(UTC)

    def _ensure_provider() -> LLMProvider:
        nonlocal provider
        if provider is None:
            provider = svc().get_provider(settings)
        return provider

    for idx, q in enumerate(questions_list):
        text = q["question_text"]
        fp = question_fingerprint(text)
        qtype = q.get("question_type") or ScreenerQuestionType.TEXTAREA
        if isinstance(qtype, str):
            try:
                qtype = ScreenerQuestionType(qtype)
            except ValueError:
                qtype = ScreenerQuestionType.TEXTAREA
        choices = q.get("choices") or None
        required = bool(q.get("required", True))
        order_index = int(q.get("order_index", idx))

        row = by_fp.get(fp)
        # If existing row is USER-edited, preserve untouched.
        if row is not None and row.source == ScreenerAnswerSource.USER:
            out_rows.append(row)
            continue
        # Decide source: AUTO if a Profile field matches; DRAFTED otherwise.
        auto_field = _auto_field_for_question(text)
        if auto_field:
            answer_value = _profile_value_for_field(profile_row, auto_field)
            source = ScreenerAnswerSource.AUTO
            reviewed_at = now
            drafted_by_model = None
        else:
            # Plan 61 (0.2.7.14) — check the per-user reuse cache before
            # spending LLM tokens. A hit prefills the suggestion but never
            # auto-submits (decision D7); the row's `drafted_by_model` carries
            # a `reuse:<id>` marker so the UI swaps in the diff component.
            from services import profile_answer_service as _pas

            reuse_hit = None
            try:
                reuse_hit = await _pas.get_suggestion(
                    session,
                    user_id=user_id,
                    question_text=text,
                    company_name=application.company,
                )
            except Exception as exc:  # noqa: BLE001 — reuse lookup is best-effort
                log.debug("profile_answer reuse lookup failed: %s", exc)

            if reuse_hit is not None:
                answer_value = reuse_hit.answer
                source = ScreenerAnswerSource.DRAFTED
                reviewed_at = None
                drafted_by_model = f"reuse:{reuse_hit.id}"
            else:
                try:
                    p = _ensure_provider()
                    result = await svc().llm_tracker.tracked_call(
                        session=session,
                        user_id=user_id,
                        provider=p,
                        method="structured",
                        prompt_name="answer_screener",
                        application_id=application.id,
                        prompt=_render_screener_prompt(
                            profile_row, job, text, qtype.value, choices
                        ),
                        schema=__import__(
                            "llm.prompts.answer_screener", fromlist=["ScreenerAnswer"]
                        ).ScreenerAnswer,
                        system=system,
                        cache_system=cache_system,
                    )
                    answer_value = str(result.value.get("answer") or "")
                except LLMProviderError as exc:
                    log.warning("answer_screener LLM failed for %r: %s", text, exc)
                    answer_value = ""
                source = ScreenerAnswerSource.DRAFTED
                reviewed_at = None
                drafted_by_model = provider.model_name if provider else None

        if row is None:
            row = ApplicationScreenerAnswer(
                application_id=application.id,
                question_text=text,
                question_fingerprint=fp,
                question_type=qtype,
                choices=list(choices) if choices else None,
                required=required,
                order_index=order_index,
                answer=answer_value,
                source=source,
                drafted_by_model=drafted_by_model,
                reviewed_at=reviewed_at,
            )
        else:
            row.question_text = text
            row.question_type = qtype
            row.choices = list(choices) if choices else None
            row.required = required
            row.order_index = order_index
            row.answer = answer_value
            row.source = source
            row.drafted_by_model = drafted_by_model
            row.reviewed_at = reviewed_at
            row.updated_at = now
        session.add(row)
        out_rows.append(row)

    await session.flush()
    return out_rows


def _render_screener_prompt(
    profile: Profile,
    job: Job | None,
    question_text: str,
    question_type: str,
    choices: list[str] | None,
) -> str:
    job_str = f"{job.company} — {job.role}" if job is not None else "(no job context)"
    choices_str = f"Choices: {choices}" if choices else ""
    return (
        f"Draft an answer for this screener question.\n\n"
        f"Candidate: {profile.full_name}\n"
        f"{profile.summary_short or ''}\n\n"
        f"Job: {job_str}\n\n"
        f"Question: {question_text}\n"
        f"Question type: {question_type}\n"
        f"{choices_str}\n\n"
        "Return ScreenerAnswer with answer + confidence."
    )
