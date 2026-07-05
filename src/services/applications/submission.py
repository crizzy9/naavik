"""Submission — validation gates, bundle assembly, ATS dispatch, failure/success recording, retry.

Split out of services/application_service.py in plan 91 Phase 4.2;
behaviour unchanged. Internal calls to shimmed/patched seams go through
`svc()` (the facade) so test interception keeps working.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    AppEventKind,
    Application,
    ApplicationScreenerAnswer,
    ApplicationStatus,
    DocsState,
    GeneratedDocument,
    GeneratedDocumentKind,
    Job,
    JobQueueState,
    ScreenerAnswerSource,
    Settings,
    StatusChangeTrigger,
)
from services import ats_postmortem
from services.applications.auto_apply import _stamp_auto_apply_artifacts
from services.applications.common import (
    ApplicationServiceError,
    IllegalStateTransition,
    ValidationError,
    _emit_event,
    svc,
)
from services.ats import ATSError
from services.ats.base import ApplicationBundle, SubmissionResult

log = logging.getLogger(__name__)


async def validate_submittable(session: AsyncSession, application: Application) -> None:
    """Raise `ValidationError` if the DRAFT can't be submitted yet.

    Rules per plan 10 § C.3 + plan 76 § D.1:
    - status must be DRAFT
    - docs_state must be READY
    - all required DRAFTED screener answers must have reviewed_at NOT NULL
    - sponsorship-gate: profile.NEEDED_NOW × job.{US_CITIZEN_ONLY, GREEN_CARD_REQUIRED}
      blocks submission (belt-and-suspenders over the scorer's visa filter;
      protects race / manual-bypass / stale-extraction scenarios).
    """
    if application.status != ApplicationStatus.DRAFT:
        raise ValidationError(f"application {application.id} not in DRAFT", code="not_draft")
    if application.docs_state != DocsState.READY:
        raise ValidationError(
            "documents not ready (regen the resume first)",
            code="docs_not_ready",
        )
    unreviewed = await _unreviewed_required_screener_count(session, application.id)
    if unreviewed > 0:
        raise ValidationError(
            f"{unreviewed} required screener answers awaiting review",
            code="screeners_unreviewed",
        )
    await _enforce_sponsorship_gate(session, application)


async def _enforce_sponsorship_gate(session: AsyncSession, application: Application) -> None:
    """Plan 76 § D.1 — block submit when job requires citizenship/GC and profile needs sponsorship.

    Reuses `scorer.visa.needs_visa_zero_out` (one source of truth for the predicate).
    Only fires when `application.job_id IS NOT NULL` — manual entries with no Job
    context bypass intentionally.
    """
    if application.job_id is None:
        return

    # Lazy import to avoid services.scorer ↔ services.application_service circular dep risk.
    from models import Profile
    from services.scorer.visa import needs_visa_zero_out

    profile = (
        await session.exec(select(Profile).where(Profile.user_id == application.user_id))
    ).one_or_none()
    if profile is None:
        return
    job = (await session.exec(select(Job).where(Job.id == application.job_id))).one_or_none()
    if job is None:
        return
    if needs_visa_zero_out(profile, job):
        raise ValidationError(
            "Job requires sponsorship Naavik can't provide. "
            "Submission blocked. Update Profile.visa_sponsorship_needed "
            "if you have a valid work authorization for this role.",
            code="visa_incompatible",
        )


async def _unreviewed_required_screener_count(session: AsyncSession, application_id: int) -> int:
    stmt = select(func.count(ApplicationScreenerAnswer.id)).where(
        ApplicationScreenerAnswer.application_id == application_id,
        ApplicationScreenerAnswer.required.is_(True),
        ApplicationScreenerAnswer.source == ScreenerAnswerSource.DRAFTED,
        ApplicationScreenerAnswer.reviewed_at.is_(None),
    )
    result = (await session.exec(stmt)).one()
    if isinstance(result, tuple):
        result = result[0]
    return int(result or 0)


async def _build_bundle(session: AsyncSession, application: Application) -> ApplicationBundle:
    resume = (
        await session.exec(
            select(GeneratedDocument)
            .where(
                GeneratedDocument.application_id == application.id,
                GeneratedDocument.kind == GeneratedDocumentKind.RESUME,
                GeneratedDocument.error.is_(None),
            )
            .order_by(GeneratedDocument.compiled_at.desc())
            .limit(1)
        )
    ).one_or_none()
    cover = (
        await session.exec(
            select(GeneratedDocument)
            .where(
                GeneratedDocument.application_id == application.id,
                GeneratedDocument.kind == GeneratedDocumentKind.COVER_LETTER,
                GeneratedDocument.error.is_(None),
            )
            .order_by(GeneratedDocument.compiled_at.desc())
            .limit(1)
        )
    ).one_or_none()
    screeners = (
        await session.exec(
            select(ApplicationScreenerAnswer).where(
                ApplicationScreenerAnswer.application_id == application.id
            )
        )
    ).all()
    from services import profile_service

    return ApplicationBundle(
        application=application,
        resume=resume,
        cover_letter=cover,
        screener_answers=list(screeners),
        # Item 7 — form fillers take identity from the Profile, never from
        # the board's PDF parsing.
        profile=await profile_service.get_profile(session, application.user_id),
    )


async def _record_failure(
    session: AsyncSession,
    application: Application,
    *,
    kind: str,
    message: str,
    raw: dict | None = None,
    settings: Settings | None = None,
) -> None:
    postmortem_path: str | None = None
    if raw is not None and settings is not None:
        try:
            postmortem_path = await ats_postmortem.capture_postmortem(
                session=session,
                application=application,
                failure_kind=kind,
                failure_message=message,
                raw=raw,
                settings=settings,
            )
        except Exception as exc:  # noqa: BLE001 — postmortem is diagnostic; never block failure
            log.warning("postmortem capture failed for application %s: %s", application.id, exc)

    artifacts = dict(application.submission_artifacts or {})
    artifacts["last_failure"] = {
        "kind": kind,
        "message": message,
        "captured_at": datetime.now(UTC).isoformat(),
        "postmortem_path": postmortem_path,
    }
    artifacts["retry_count"] = int(artifacts.get("retry_count", 0)) + 1
    application.submission_artifacts = artifacts
    application.updated_at = datetime.now(UTC)
    session.add(application)
    await session.flush()


async def _record_success(
    session: AsyncSession,
    application: Application,
    *,
    board_application_id: str | None,
) -> None:
    artifacts = dict(application.submission_artifacts or {})
    if board_application_id:
        artifacts["board_application_id"] = board_application_id
    artifacts.pop("last_failure", None)  # clear on success
    application.submission_artifacts = artifacts


def _default_notify_fn(settings: Settings | None):
    """Plan 77 / 0.4.0.17 — wired `notify_application_submitted` closure.

    Returns `None` when no Settings row exists (no user to scope channels to)
    so manual submissions silently skip notification rather than raising.
    """
    if settings is None:
        return None
    from services.notifications import notify_application_submitted

    async def _notify(application: Application) -> None:
        await notify_application_submitted(settings=settings, application=application)

    return _notify


async def submit_draft(
    session: AsyncSession,
    application_id: int,
    *,
    triggered_by: StatusChangeTrigger = StatusChangeTrigger.DRAFT_SUBMITTED,
    notify_fn=None,
    dry_run: bool = False,
) -> Application:
    """DRAFT → APPLIED. Validates, dispatches via ATS, flips state.

    On persistent failure (CAPTCHA / auth_required / etc.), keeps DRAFT and
    writes `submission_artifacts.last_failure`. Caller (cron or HTTP handler)
    treats the return as a tuple `(application, ok=bool)` via `application.status`.

    Plan 77 / 0.4.0.17 — when `notify_fn is None`, default to a wired
    `notify_application_submitted` closure built from the user's Settings.
    Auto-apply cron continues to pass `notify_fn` explicitly (unchanged); HTTP
    submit-draft now gets Discord/Telegram echo on success without callers
    threading the helper themselves.
    """
    application = await svc().get_application(session, application_id)
    if application is None:
        raise ApplicationServiceError(f"application {application_id} not found")

    await svc().validate_submittable(session, application)

    if application.board is None:
        raise ValidationError("application has no board; cannot dispatch", code="no_board")

    user_settings = (
        await session.exec(select(Settings).where(Settings.user_id == application.user_id))
    ).one_or_none()

    bundle = await _build_bundle(session, application)
    adapter = svc().ats_dispatch(application.board)

    try:
        result: SubmissionResult = await adapter.submit(application, bundle, dry_run=dry_run)
    except ATSError as exc:
        await _record_failure(
            session,
            application,
            kind="unknown",
            message=str(exc),
            raw=getattr(exc, "raw", None),
            settings=user_settings,
        )
        await _emit_event(
            session,
            user_id=application.user_id,
            application_id=application.id,
            kind=AppEventKind.DOCS_FAILED,
            payload={"kind": "unknown", "message": str(exc)},
        )
        return application

    if not result.ok:
        kind = result.error or "unknown"
        message = result.error_message or kind
        await _record_failure(
            session,
            application,
            kind=kind,
            message=message,
            raw=result.raw,
            settings=user_settings,
        )
        if result.artifacts:
            _stamp_auto_apply_artifacts(application, result.artifacts, key="failure_artifacts")
            session.add(application)
        await _emit_event(
            session,
            user_id=application.user_id,
            application_id=application.id,
            kind=AppEventKind.DOCS_FAILED,
            payload={"kind": kind, "message": message},
        )
        return application

    # Item 7 — dry-run outcome: the adapter filled the REAL form and
    # screenshotted it, then stopped short of the submit click. Keep DRAFT,
    # stamp the evidence, and let the caller hand the job to the user.
    if result.dry_run:
        artifacts = dict(application.submission_artifacts or {})
        auto = dict(artifacts.get("auto_apply") or {})
        auto["dry_run_at"] = datetime.now(UTC).isoformat()
        auto["dry_run_artifacts"] = [Path(p).name for p in result.artifacts if p]
        artifacts["auto_apply"] = auto
        artifacts["dry_run_at"] = auto["dry_run_at"]  # legacy key some views read
        application.submission_artifacts = artifacts
        application.updated_at = datetime.now(UTC)
        session.add(application)
        await _emit_event(
            session,
            user_id=application.user_id,
            application_id=application.id,
            kind=AppEventKind.AUTO_APPLY_DRY_RUN,
            payload={
                "board": application.board.value if application.board else None,
                "artifacts": auto["dry_run_artifacts"],
                "fields_filled": (result.raw or {}).get("fields_filled"),
                "captcha_present": (result.raw or {}).get("captcha_present"),
            },
        )
        await session.flush()
        return application

    # Plan 78 § D.2 — adapter-confidence gate. HTTP adapters always emit
    # confidence=1.0 (passes any threshold); Generic LLM-form-fill adapter
    # may emit lower. Below threshold → revert to DRAFT + record as failure
    # so the operator reviews. Defense in depth over the adapter's `ok` flag.
    if (
        result.confidence is not None
        and user_settings is not None
        and result.confidence < float(user_settings.auto_apply_adapter_confidence_threshold)
    ):
        threshold_str = f"{float(user_settings.auto_apply_adapter_confidence_threshold):.2f}"
        confidence_str = f"{float(result.confidence):.2f}"
        await _record_failure(
            session,
            application,
            kind="low_confidence",
            message=(f"adapter confidence {confidence_str} < threshold {threshold_str}"),
            raw={"confidence": result.confidence, **(result.raw or {})},
            settings=user_settings,
        )
        await _emit_event(
            session,
            user_id=application.user_id,
            application_id=application.id,
            kind=AppEventKind.DOCS_FAILED,
            payload={
                "kind": "low_confidence",
                "message": f"confidence {confidence_str} below threshold {threshold_str}",
            },
        )
        return application

    # Success — flip state in one transaction.
    now = datetime.now(UTC)
    application.status = ApplicationStatus.APPLIED
    application.applied_at = now
    application.updated_at = now
    await _record_success(session, application, board_application_id=result.board_application_id)
    if result.artifacts or (result.raw or {}).get("confirmation_text"):
        artifacts = dict(application.submission_artifacts or {})
        auto = dict(artifacts.get("auto_apply") or {})
        if result.artifacts:
            auto["submission_artifacts_files"] = [Path(p).name for p in result.artifacts if p]
        confirmation = (result.raw or {}).get("confirmation_text")
        if confirmation:
            auto["confirmation_text"] = confirmation
        artifacts["auto_apply"] = auto
        application.submission_artifacts = artifacts
    session.add(application)

    if application.job_id:
        job = (await session.exec(select(Job).where(Job.id == application.job_id))).one_or_none()
        if job is not None:
            job.queue_state = JobQueueState.APPLIED
            job.updated_at = now
            session.add(job)

    await _emit_event(
        session,
        user_id=application.user_id,
        application_id=application.id,
        kind=AppEventKind.STATUS_CHANGE,
        payload={
            "from": ApplicationStatus.DRAFT.value,
            "to": ApplicationStatus.APPLIED.value,
            "trigger": triggered_by.value,
            "board_application_id": result.board_application_id,
        },
    )
    await session.flush()

    # Plan 61 (0.2.7.14) — persist reusable screener answers AFTER successful
    # submission. Iterates only DRAFTED + reviewed rows with a non-empty answer;
    # last-write-wins on fingerprint collision. Best-effort — failures here
    # never block submission ack.
    try:
        await _persist_reusable_screener_answers(session, application)
    except Exception as exc:  # noqa: BLE001
        log.warning("profile_answer upsert post-submit failed: %s", exc)

    effective_notify_fn = notify_fn or _default_notify_fn(user_settings)
    if effective_notify_fn is not None:
        try:
            await effective_notify_fn(application)
        except Exception as exc:  # noqa: BLE001 — notification failures are non-fatal
            log.warning("notify_application_submitted failed: %s", exc)

    return application


async def _persist_reusable_screener_answers(
    session: AsyncSession, application: Application
) -> None:
    """Upsert ProfileAnswer rows from this application's reviewed DRAFTED screeners.

    Plan 61 (0.2.7.14). Only rows whose `source == DRAFTED`, `reviewed_at IS
    NOT NULL`, and `answer` non-empty are eligible — user-edited (`USER`)
    answers are already personal; AUTO-filled rows are profile-field reuse
    and don't need a separate cache.
    """
    from services import profile_answer_service

    stmt = select(ApplicationScreenerAnswer).where(
        ApplicationScreenerAnswer.application_id == application.id,
        ApplicationScreenerAnswer.source == ScreenerAnswerSource.DRAFTED,
        ApplicationScreenerAnswer.reviewed_at.is_not(None),
    )
    rows = (await session.exec(stmt)).all()
    for row in rows:
        if not row.answer or not row.answer.strip():
            continue
        await profile_answer_service.upsert_from_screener_answer(
            session,
            user_id=application.user_id,
            screener_answer=row,
            company_name=application.company,
        )


async def retry_failed(
    session: AsyncSession,
    application_id: int,
    *,
    user_id: int,
) -> Application:
    """Plan 79 / 0.4.0.11 — clear `submission_artifacts.last_failure` + re-queue.

    Returns the updated Application. Raises `ApplicationServiceError` when the
    application doesn't exist or belongs to a different user (route swallows
    to 404). Raises `IllegalStateTransition` when the application isn't a
    DRAFT, or when it has no `last_failure` to retry (route maps to 409).

    Idempotent over re-runs in the no-failure path (raises 409, never mutates).
    Job re-queue is gated on `Settings.auto_apply_enabled`; with auto-apply OFF,
    the DRAFT is cleaned + left for manual submit (Job stays SAVED).
    """
    application = await svc().get_application(session, application_id)
    if application is None or application.user_id != user_id:
        raise ApplicationServiceError(f"application {application_id} not found")
    if application.status != ApplicationStatus.DRAFT:
        raise IllegalStateTransition(f"can only retry DRAFTs (was {application.status.value})")
    if (
        application.submission_artifacts is None
        or "last_failure" not in application.submission_artifacts
    ):
        raise IllegalStateTransition("no last_failure to retry")

    artifacts = dict(application.submission_artifacts)
    previous_retry_count = int(artifacts.get("retry_count", 0))
    artifacts.pop("last_failure", None)
    application.submission_artifacts = artifacts
    application.updated_at = datetime.now(UTC)
    session.add(application)

    if application.job_id:
        job = (await session.exec(select(Job).where(Job.id == application.job_id))).one_or_none()
        if job is not None and job.queue_state == JobQueueState.SAVED:
            settings = (
                await session.exec(select(Settings).where(Settings.user_id == user_id))
            ).one_or_none()
            if settings is not None and settings.auto_apply_enabled:
                job.queue_state = JobQueueState.QUEUED_FOR_AUTO_APPLY
                job.updated_at = datetime.now(UTC)
                session.add(job)

    await _emit_event(
        session,
        user_id=user_id,
        application_id=application_id,
        kind=AppEventKind.AUTO_APPLY_QUEUED,
        payload={
            "trigger": "retry_requested",
            "previous_retry_count": previous_retry_count,
        },
    )
    await session.flush()
    return application
