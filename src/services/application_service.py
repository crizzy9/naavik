"""Application service — full DRAFT lifecycle + state-transition enforcement.

Per BACKEND.md § K + plan 10 § C.3 + DATA_MODEL.md § E.

Owns:

- DRAFT lifecycle (`get_or_create_draft`, `queue_auto_apply`, `submit_draft`,
  `discard_draft`, `process_auto_apply_queue`).
- Forward-only `Application.status` transitions.
- Service-layer computed state: `_roll_up_referral_state`,
  `compute_outreach_engagement`, `Job.queue_state` flip on submit.
- Failed-DRAFT surface — writes `submission_artifacts.last_failure` so the
  Discover stuck-queue card can read it.

Submission goes through `services/ats/__init__.py:dispatch(board)` for
Greenhouse / Lever / Ashby. Workday / LinkedIn / Indeed / Generic are
Phase 1.x (separate sub-prompt).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    AppEvent,
    AppEventKind,
    Application,
    ApplicationScreenerAnswer,
    ApplicationStatus,
    ClosedReason,
    ContactApplicationLink,
    DocsState,
    GeneratedDocument,
    GeneratedDocumentKind,
    Job,
    JobQueueState,
    OutreachMessage,
    OutreachStatus,
    RecruiterState,
    ReferralState,
    ScreenerAnswerSource,
    Settings,
    StatusChangeTrigger,
)
from services import ats_postmortem
from services.ats import ATSError
from services.ats import dispatch as ats_dispatch
from services.ats.base import ApplicationBundle, SubmissionResult

log = logging.getLogger(__name__)


class ApplicationServiceError(Exception):
    """Generic service-layer failure."""


class ValidationError(ApplicationServiceError):
    """`validate_submittable` rejected the application."""

    def __init__(self, message: str, *, code: str = "validation_failed") -> None:
        super().__init__(message)
        self.code = code


class IllegalStateTransition(ApplicationServiceError):
    """Backwards / forbidden status transition."""


# ── CSV formula-injection defang (plan 85 / 0.4.0.23) ───────────────────

# OWASP A03:2021 — Injection. Excel / LibreOffice / Numbers treat any cell
# whose first character is one of these as a formula expression. Operator-
# typed fields (company / role / team / location / external_url) can be
# trivially weaponized via `=cmd|'/c calc'!A1`. Defang by prefixing a
# single-quote leader — CSV-RFC-4180 quote semantics are unaffected.
_CSV_FORMULA_LEADERS = ("=", "+", "-", "@", "\t", "\r")


def _defang_csv_cell(value: object) -> str:
    """Return `value` as a CSV-injection-safe string.

    Prefixes a single-quote to any value whose first character is a known
    formula leader (`=` / `+` / `-` / `@` / tab / CR). Applied to every
    operator-controllable cell in `list_for_export`; also applied (defense-
    in-depth) to typed / enum cells so future schema additions can't leak.

    None → empty string. Non-string values are coerced via `str()` first.
    """
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in _CSV_FORMULA_LEADERS:
        return "'" + s
    return s


# ── Status-transition rules ─────────────────────────────────────────────


_FORWARD_FROM: dict[ApplicationStatus, set[ApplicationStatus]] = {
    ApplicationStatus.DRAFT: {ApplicationStatus.APPLIED, ApplicationStatus.CLOSED},
    ApplicationStatus.APPLIED: {
        ApplicationStatus.RECRUITER_SCREEN,
        ApplicationStatus.CLOSED,
    },
    ApplicationStatus.RECRUITER_SCREEN: {
        ApplicationStatus.ONSITE_LOOP,
        ApplicationStatus.CLOSED,
    },
    ApplicationStatus.ONSITE_LOOP: {
        ApplicationStatus.OFFER,
        ApplicationStatus.CLOSED,
    },
    ApplicationStatus.OFFER: {ApplicationStatus.CLOSED},
    ApplicationStatus.CLOSED: set(),
}


def _is_forward_transition(current: ApplicationStatus, target: ApplicationStatus) -> bool:
    return target in _FORWARD_FROM.get(current, set())


# ── Get / load helpers ──────────────────────────────────────────────────


async def get_application(session: AsyncSession, application_id: int) -> Application | None:
    return (
        await session.exec(select(Application).where(Application.id == application_id))
    ).one_or_none()


async def get_latest_cover_sections(
    session: AsyncSession, application_id: int
) -> dict[str, str] | None:
    """Return the most recent generated cover-letter's section text, or None.

    Reads the `sections` blob persisted on the latest error-free COVER_LETTER
    `GeneratedDocument`. Powers the Discover review workspace so it shows the
    real generated letter instead of a hardcoded placeholder. Returns None
    when nothing has been generated yet (the caller renders an empty state).
    """
    doc = (
        await session.exec(
            select(GeneratedDocument)
            .where(
                GeneratedDocument.application_id == application_id,
                GeneratedDocument.kind == GeneratedDocumentKind.COVER_LETTER,
                GeneratedDocument.error.is_(None),
            )
            .order_by(GeneratedDocument.compiled_at.desc())
            .limit(1)
        )
    ).one_or_none()
    if doc is None or not doc.bullet_selection:
        return None
    sections = doc.bullet_selection.get("sections")
    if not isinstance(sections, dict):
        return None
    return {k: str(v) for k, v in sections.items()}


async def latest_documents(session: AsyncSession, application_id: int) -> list[GeneratedDocument]:
    """Return the latest error-free GeneratedDocument per kind for an application.

    Used by the bundle-download endpoint to zip the REAL generated PDFs
    (resume + cover letter) instead of placeholder bytes.
    """
    docs = (
        await session.exec(
            select(GeneratedDocument)
            .where(
                GeneratedDocument.application_id == application_id,
                GeneratedDocument.error.is_(None),
            )
            .order_by(GeneratedDocument.compiled_at.desc())
        )
    ).all()
    seen: set = set()
    latest: list[GeneratedDocument] = []
    for d in docs:
        if d.kind in seen:
            continue
        seen.add(d.kind)
        latest.append(d)
    return latest


async def update_cover_section(
    session: AsyncSession,
    *,
    application_id: int,
    user_id: int,
    section: str,
    text: str,
) -> bool:
    """Persist an edited cover-letter `section` for `application_id`.

    IDOR-checked (the application must belong to `user_id`). Writes onto the
    latest error-free COVER_LETTER `GeneratedDocument`'s `sections` blob so
    edits survive restarts and stay per-application/per-user. Returns False
    when the app isn't owned or no cover document exists yet.

    Replaces the previous process-global `discover_review_ctx.COVER_SECTION_TEXT`
    dict, which lost edits on restart and leaked them across all users.
    """
    if section not in {"intro", "body", "why_company", "close"}:
        return False
    app = (
        await session.exec(select(Application).where(Application.id == application_id))
    ).one_or_none()
    if app is None or app.user_id != user_id or getattr(app, "deleted_at", None) is not None:
        return False
    doc = (
        await session.exec(
            select(GeneratedDocument)
            .where(
                GeneratedDocument.application_id == application_id,
                GeneratedDocument.kind == GeneratedDocumentKind.COVER_LETTER,
                GeneratedDocument.error.is_(None),
            )
            .order_by(GeneratedDocument.compiled_at.desc())
            .limit(1)
        )
    ).one_or_none()
    if doc is None:
        return False
    blob = dict(doc.bullet_selection or {})
    sections = dict(blob.get("sections") or {})
    sections[section] = text
    blob["sections"] = sections
    doc.bullet_selection = blob
    session.add(doc)
    await session.flush()
    return True


async def get_application_for_job(
    session: AsyncSession, *, user_id: int, job_id: int
) -> Application | None:
    return (
        await session.exec(
            select(Application).where(
                Application.user_id == user_id,
                Application.job_id == job_id,
                Application.deleted_at.is_(None),
            )
        )
    ).one_or_none()


async def _emit_event(
    session: AsyncSession,
    *,
    user_id: int,
    application_id: int | None,
    kind: AppEventKind,
    payload: dict[str, Any] | None = None,
    actor: str | None = None,
) -> AppEvent:
    ev = AppEvent(
        user_id=user_id,
        application_id=application_id,
        kind=kind,
        payload=payload or {},
        actor=actor,
        occurred_at=datetime.now(UTC),
    )
    session.add(ev)
    await session.flush()
    return ev


# ── DRAFT creation ──────────────────────────────────────────────────────


async def get_or_create_draft(
    session: AsyncSession,
    *,
    user_id: int,
    job_id: int,
    settings: Settings,
) -> Application:
    """Used by `GET /discover/{job_id}`. Creates a DRAFT row if none exists.

    Never generates documents inline — a GET must not block on LLM + Typst
    (~13s on the dev box). Callers that want eager generation dispatch it
    asynchronously via `services.generation_dispatch` after committing.
    """
    del settings  # signature kept uniform; generation moved out of this path
    existing = await get_application_for_job(session, user_id=user_id, job_id=job_id)
    if existing is not None:
        return existing

    job = (await session.exec(select(Job).where(Job.id == job_id))).one_or_none()
    if job is None:
        raise ApplicationServiceError(f"job {job_id} not found")

    now = datetime.now(UTC)
    draft = Application(
        user_id=user_id,
        job_id=job.id,
        company=job.company,
        role=job.role,
        team=job.team,
        location=job.location,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        equity_pct=job.equity_pct,
        board=job.board,
        # Resolved apply target when known — adapters build their form URL
        # from external_url, and an aggregator listing can't take a form.
        external_url=job.apply_url or job.url,
        status=ApplicationStatus.DRAFT,
        docs_state=DocsState.NONE,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        applied_at=None,
        created_at=now,
        updated_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(draft)
            await session.flush()
    except IntegrityError:
        # Lost the SELECT→INSERT race on ix_application_user_job_alive_unique
        # (e.g. double-fired HTMX requests for the same card). The savepoint
        # rollback discards our row; reuse the winner's live row instead of
        # surfacing a UniqueViolation.
        existing = await get_application_for_job(session, user_id=user_id, job_id=job_id)
        if existing is None:
            raise
        return existing

    await _emit_event(
        session,
        user_id=user_id,
        application_id=draft.id,
        kind=AppEventKind.STATUS_CHANGE,
        payload={
            "from": None,
            "to": ApplicationStatus.DRAFT.value,
            "trigger": StatusChangeTrigger.DRAFT_CREATION.value,
        },
    )
    return draft


async def resync_draft_apply_target(session: AsyncSession, job: Job) -> int:
    """Re-point a job's DRAFT applications at its freshly resolved apply target.

    `get_or_create_draft` snapshots `board` + `external_url` from the Job at
    creation. Apply-site resolution can promote `job.board` (LinkedIn →
    Greenhouse) and set `job.apply_url` AFTER a draft exists — without this,
    the draft keeps the aggregator board and Submit refuses ("auth required")
    even though the real target is now known. Only DRAFT rows are touched; a
    submitted application is history and must never be rewritten. Returns the
    number of applications updated (caller flushes/commits).
    """
    stmt = select(Application).where(
        Application.job_id == job.id,
        Application.status == ApplicationStatus.DRAFT,
        Application.deleted_at.is_(None),
    )
    apps = (await session.exec(stmt)).all()
    target_url = job.apply_url or job.url
    changed = 0
    for app in apps:
        if app.board != job.board or app.external_url != target_url:
            app.board = job.board
            app.external_url = target_url
            # A submit failure recorded against the OLD target ("auth required"
            # on the aggregator board) is stale once we re-point — drop it so
            # the review UI doesn't show a contradictory banner. New dict so
            # SQLAlchemy flags the JSON column dirty.
            artifacts = app.submission_artifacts
            if isinstance(artifacts, dict) and "last_failure" in artifacts:
                app.submission_artifacts = {
                    k: v for k, v in artifacts.items() if k != "last_failure"
                } or None
            app.updated_at = datetime.now(UTC)
            session.add(app)
            changed += 1
    return changed


async def queue_auto_apply(
    session: AsyncSession,
    *,
    user_id: int,
    job_id: int,
    settings: Settings,
) -> Application:
    """Right-swipe: create DRAFT (if missing) + flip Job.queue_state."""
    draft = await get_or_create_draft(
        session,
        user_id=user_id,
        job_id=job_id,
        settings=settings,
    )
    job = (await session.exec(select(Job).where(Job.id == job_id))).one_or_none()
    if job is not None:
        job.queue_state = JobQueueState.QUEUED_FOR_AUTO_APPLY
        job.updated_at = datetime.now(UTC)
        session.add(job)
    _stamp_auto_apply(draft, queued_at=datetime.now(UTC).isoformat())
    session.add(draft)

    await _emit_event(
        session,
        user_id=user_id,
        application_id=draft.id,
        kind=AppEventKind.STATUS_CHANGE,
        payload={
            "from": ApplicationStatus.DRAFT.value,
            "to": ApplicationStatus.DRAFT.value,
            "trigger": StatusChangeTrigger.AUTO_APPLY_QUEUED.value,
        },
    )
    await session.flush()
    return draft


# ── Submission (validate + ATS dispatch + state flip) ───────────────────


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
    application = await get_application(session, application_id)
    if application is None:
        raise ApplicationServiceError(f"application {application_id} not found")

    await validate_submittable(session, application)

    if application.board is None:
        raise ValidationError("application has no board; cannot dispatch", code="no_board")

    user_settings = (
        await session.exec(select(Settings).where(Settings.user_id == application.user_id))
    ).one_or_none()

    bundle = await _build_bundle(session, application)
    adapter = ats_dispatch(application.board)

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


async def cleanup_stale_drafts(
    session: AsyncSession,
    *,
    older_than_days: int = 30,
) -> int:
    """Archive DRAFTs idle > N days. Returns count archived.

    Plan 53 § A.2 / 0.2.4.01. Mirrors `discard_draft` semantics
    (CLOSED + withdrawn_by_me + soft-delete) but emits a CLEANUP_STALE
    AppEvent so audit trail distinguishes system archival from user
    withdrawal.
    """
    threshold = datetime.now(UTC) - timedelta(days=older_than_days)
    stmt = select(Application).where(
        Application.status == ApplicationStatus.DRAFT,
        Application.deleted_at.is_(None),
        Application.updated_at < threshold,
    )
    rows = (await session.exec(stmt)).all()
    archived = 0
    for app in rows:
        now = datetime.now(UTC)
        app.status = ApplicationStatus.CLOSED
        app.closed_reason = ClosedReason.WITHDRAWN_BY_ME
        app.deleted_at = now
        app.updated_at = now
        session.add(app)
        await _emit_event(
            session,
            user_id=app.user_id,
            application_id=app.id,
            kind=AppEventKind.STATUS_CHANGE,
            payload={
                "from": ApplicationStatus.DRAFT.value,
                "to": ApplicationStatus.CLOSED.value,
                "trigger": StatusChangeTrigger.CLEANUP_STALE.value,
            },
        )
        archived += 1
    if archived:
        await session.flush()
    return archived


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
    application = await get_application(session, application_id)
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


async def discard_draft(session: AsyncSession, application_id: int) -> Application:
    """DRAFT → CLOSED `withdrawn_by_me` + soft-delete."""
    application = await get_application(session, application_id)
    if application is None:
        raise ApplicationServiceError(f"application {application_id} not found")
    if application.status != ApplicationStatus.DRAFT:
        raise IllegalStateTransition(f"can only discard DRAFTs (was {application.status.value})")
    now = datetime.now(UTC)
    application.status = ApplicationStatus.CLOSED
    application.closed_reason = ClosedReason.WITHDRAWN_BY_ME
    application.deleted_at = now
    application.updated_at = now
    session.add(application)

    if application.job_id:
        job = (await session.exec(select(Job).where(Job.id == application.job_id))).one_or_none()
        if job is not None and job.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY:
            job.queue_state = JobQueueState.SAVED
            job.updated_at = now
            session.add(job)

    await _emit_event(
        session,
        user_id=application.user_id,
        application_id=application.id,
        kind=AppEventKind.STATUS_CHANGE,
        payload={
            "from": ApplicationStatus.DRAFT.value,
            "to": ApplicationStatus.CLOSED.value,
            "trigger": StatusChangeTrigger.DISCARD.value,
            "closed_reason": ClosedReason.WITHDRAWN_BY_ME.value,
        },
    )
    await session.flush()
    return application


# ── Auto-apply queue cron ───────────────────────────────────────────────


@dataclass(slots=True)
class AutoApplyResult:
    processed: int = 0
    submitted: int = 0
    failed: int = 0
    skipped_by_cap: int = 0
    docs_generated: int = 0
    handed_to_user: int = 0


def _stamp_auto_apply(application: Application, **fields: Any) -> None:
    """Merge timestamped state fields into `submission_artifacts["auto_apply"]`.

    The auto-apply pipeline's visible-state contract: every transition writes
    a timestamped marker here (queued_at / docs_ready_at / needs_you_at +
    needs_you_reason / dry_run_at / submitted_at) so Discover and Tracking
    can show WHERE a queued job actually is instead of a silent queue.
    """
    artifacts = dict(application.submission_artifacts or {})
    blob = dict(artifacts.get("auto_apply") or {})
    blob.update(fields)
    artifacts["auto_apply"] = blob
    application.submission_artifacts = artifacts
    application.updated_at = datetime.now(UTC)


def _stamp_auto_apply_artifacts(application: Application, paths: list[str], *, key: str) -> None:
    """Record adapter screenshot evidence (filenames only — served via the
    guarded artifacts route) under `submission_artifacts.auto_apply.<key>`."""
    names = [Path(p).name for p in paths if p]
    if names:
        _stamp_auto_apply(application, **{key: names})


async def _hand_to_user(
    session: AsyncSession,
    application: Application,
    job: Job,
    *,
    reason: str,
) -> None:
    """Flip a queued job to READY_TO_SUBMIT — docs are prepared, but this
    application needs the human (unsupported board, auto-apply off, dry-run,
    screener review, adapter wall). Emits an AppEvent with the reason."""
    now = datetime.now(UTC)
    job.queue_state = JobQueueState.READY_TO_SUBMIT
    job.updated_at = now
    session.add(job)
    _stamp_auto_apply(application, needs_you_at=now.isoformat(), needs_you_reason=reason)
    session.add(application)
    await _emit_event(
        session,
        user_id=application.user_id,
        application_id=application.id,
        kind=AppEventKind.AUTO_APPLY_QUEUED,
        payload={"trigger": "handed_to_user", "reason": reason},
    )
    await session.flush()


def auto_apply_phase(application: Application | None, job: Job | None) -> dict[str, Any] | None:
    """Computed pipeline phase for UI chips.

    Returns `{phase, label, reason, at}` or None when the pair isn't in the
    auto-apply pipeline at all. Phases: queued / generating / docs_ready /
    submitted / needs_you.
    """
    if application is None or job is None:
        return None
    blob = (application.submission_artifacts or {}).get("auto_apply") or {}
    if application.status == ApplicationStatus.APPLIED or (
        job.queue_state == JobQueueState.APPLIED
    ):
        applied_at = application.applied_at.isoformat() if application.applied_at else None
        return {
            "phase": "submitted",
            "label": "submitted",
            "reason": None,
            "at": applied_at or blob.get("submitted_at"),
        }
    if job.queue_state == JobQueueState.READY_TO_SUBMIT:
        return {
            "phase": "needs_you",
            "label": "ready for you",
            "reason": blob.get("needs_you_reason"),
            "at": blob.get("needs_you_at"),
        }
    if job.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY:
        if application.docs_state == DocsState.GENERATING:
            return {
                "phase": "generating",
                "label": "docs generating",
                "reason": None,
                "at": blob.get("queued_at"),
            }
        if application.docs_state == DocsState.READY:
            return {
                "phase": "docs_ready",
                "label": "docs ready — submitting next tick",
                "reason": None,
                "at": blob.get("docs_ready_at") or blob.get("queued_at"),
            }
        return {
            "phase": "queued",
            "label": "queued",
            "reason": None,
            "at": blob.get("queued_at"),
        }
    return None


async def process_auto_apply_queue(
    session: AsyncSession,
    *,
    user_id: int | None = None,
    notify_fn=None,
) -> AutoApplyResult:
    """Process queued DRAFTs. Returns a per-run summary.

    For each `Application` in DRAFT with `Job.queue_state=QUEUED_FOR_AUTO_APPLY`:
    1. Validate submittable; if not, leave queued.
    2. Dispatch via ATS.
    3. On failure with `kind ∈ {auth_required, captcha, unknown}`, the cron
       reverts `Job.queue_state` to `SAVED` so it doesn't keep retrying without
       human attention. The DRAFT stays DRAFT and surfaces in the stuck queue.
    """
    out = AutoApplyResult()

    stmt = (
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(
            Application.status == ApplicationStatus.DRAFT,
            Application.deleted_at.is_(None),
            Job.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY,
        )
    )
    if user_id is not None:
        stmt = stmt.where(Application.user_id == user_id)

    rows = (await session.exec(stmt)).all()

    # Pull settings per-user once for cap enforcement.
    settings_cache: dict[int, Settings] = {}

    async def _settings_for(uid: int) -> Settings:
        if uid in settings_cache:
            return settings_cache[uid]
        s = (await session.exec(select(Settings).where(Settings.user_id == uid))).one_or_none()
        if s is None:
            s = Settings(user_id=uid)
        settings_cache[uid] = s
        return s

    today_count: dict[int, int] = {}

    async def _today_submitted_count(uid: int) -> int:
        if uid in today_count:
            return today_count[uid]
        today_start = datetime.combine(datetime.now(UTC).date(), datetime.min.time(), tzinfo=UTC)
        c = (
            await session.exec(
                select(func.count(Application.id)).where(
                    Application.user_id == uid,
                    Application.status != ApplicationStatus.DRAFT,
                    Application.applied_at >= today_start,
                )
            )
        ).one()
        if isinstance(c, tuple):
            c = c[0]
        today_count[uid] = int(c or 0)
        return today_count[uid]

    # Plan 78 § D.3 — per-board daily counter cache. Keyed by (uid, board.value)
    # so concurrent multi-board submissions count independently. Cron lifetime
    # only — re-queries each cron run.
    today_count_per_board: dict[tuple[int, str], int] = {}

    async def _today_submitted_per_board(uid: int, board_value: str) -> int:
        key = (uid, board_value)
        if key in today_count_per_board:
            return today_count_per_board[key]
        from models import ApplicationBoard

        today_start = datetime.combine(datetime.now(UTC).date(), datetime.min.time(), tzinfo=UTC)
        try:
            board_enum = ApplicationBoard(board_value)
        except ValueError:
            today_count_per_board[key] = 0
            return 0
        c = (
            await session.exec(
                select(func.count(Application.id)).where(
                    Application.user_id == uid,
                    Application.board == board_enum,
                    Application.status != ApplicationStatus.DRAFT,
                    Application.applied_at >= today_start,
                )
            )
        ).one()
        if isinstance(c, tuple):
            c = c[0]
        today_count_per_board[key] = int(c or 0)
        return today_count_per_board[key]

    from services.ats import board_supports_auto_submit

    for application, job in rows:
        out.processed += 1
        s = await _settings_for(application.user_id)

        # Stage 1 — documents. The queue OWNS doc generation now: a queued
        # job with no docs used to fail `validate_submittable` silently on
        # every tick, forever. Generate here (cost-capped); if a background
        # generation is already in flight, wait for the next tick.
        if application.docs_state == DocsState.GENERATING:
            continue
        if application.docs_state in {DocsState.NONE, DocsState.STALE, DocsState.FAILED}:
            from services.bundle_generator import generate_bundle

            try:
                bundle = await generate_bundle(session, application, settings=s, job=job)
            except Exception as exc:  # noqa: BLE001 — one bad row must not kill the cron
                log.warning("auto-apply doc generation failed for %s: %s", application.id, exc)
                out.failed += 1
                continue
            if bundle.skipped_reason == "cost_cap_reached":
                out.skipped_by_cap += 1
                continue
            out.docs_generated += 1
            _stamp_auto_apply(application, docs_ready_at=datetime.now(UTC).isoformat())
            session.add(application)
            await session.flush()
        if application.docs_state != DocsState.READY:
            continue

        # Stage 2 — honest handoffs. The user queued this job explicitly, so
        # docs get prepared either way; but if WE can't submit it, say so and
        # hand it over instead of sitting silent.
        if not s.auto_apply_enabled:
            await _hand_to_user(
                session,
                application,
                job,
                reason=(
                    "auto-apply is off in Settings — documents are prepared "
                    "for you to submit manually"
                ),
            )
            out.handed_to_user += 1
            continue
        if not board_supports_auto_submit(application.board):
            board_label = application.board.value if application.board else "manual"
            await _hand_to_user(
                session,
                application,
                job,
                reason=(
                    f"{board_label} has no auto-submit adapter — open the "
                    "posting and apply with the prepared documents"
                ),
            )
            out.handed_to_user += 1
            continue

        # Plan 78 § D.1 — belt-and-suspenders score gate. Right-swipe in
        # Discover already gates upstream, but the score may have drifted
        # between queue + dispatch (re-scoring cron, profile change, etc.).
        # Re-check here against the live threshold; below → pull out of queue.
        threshold = getattr(s, "auto_apply_score_threshold", None)
        job_score = getattr(job, "score", None)
        if threshold is not None and job_score is not None and float(job_score) < float(threshold):
            log.info(
                "auto-apply skipped application %s: score %s below threshold %s",
                application.id,
                job_score,
                threshold,
            )
            job.queue_state = JobQueueState.SAVED
            job.updated_at = datetime.now(UTC)
            session.add(job)
            continue
        if s.auto_apply_daily_cap is not None:
            already = await _today_submitted_count(application.user_id)
            if already >= s.auto_apply_daily_cap:
                out.skipped_by_cap += 1
                continue

        try:
            await validate_submittable(session, application)
        except ValidationError as exc:
            log.info("auto-apply skipped application %s: %s", application.id, exc)
            # Plan 78 § fold-in (0.4.0.22) — visa-incompatible DRAFTs in the
            # queue tight-loop on every cron tick. Pull out of queue + emit
            # AUTO_APPLY_VISA_BLOCKED so the operator can re-evaluate.
            if exc.code == "visa_incompatible":
                job.queue_state = JobQueueState.SAVED
                job.updated_at = datetime.now(UTC)
                session.add(job)
                await _emit_event(
                    session,
                    user_id=application.user_id,
                    application_id=application.id,
                    kind=AppEventKind.AUTO_APPLY_VISA_BLOCKED,
                    payload={"message": str(exc)},
                )
            elif exc.code == "screeners_unreviewed":
                # AI-drafted answers can't review themselves — hand over.
                await _hand_to_user(
                    session,
                    application,
                    job,
                    reason="screener answers need your review before submitting",
                )
                out.handed_to_user += 1
            continue

        # Plan 78 § D.5, rebuilt by item 7 (2026-07): dry-run now produces
        # REAL evidence — `submit_draft(dry_run=True)` drives the actual
        # apply form (navigate + fill + upload + screenshot) and stops
        # short of the final submit click. The stamp-only short-circuit
        # proved nothing about field correctness.
        if getattr(s, "auto_apply_dry_run", False):
            try:
                await submit_draft(
                    session,
                    application.id,
                    triggered_by=StatusChangeTrigger.AUTO_APPLY_SUBMITTED,
                    notify_fn=None,
                    dry_run=True,
                )
            except ApplicationServiceError as exc:
                log.warning("dry-run fill errored on %s: %s", application.id, exc)
            await _hand_to_user(
                session,
                application,
                job,
                reason=(
                    "dry-run — the form was filled and screenshotted but NOT "
                    "submitted; inspect the artifacts, then submit manually or "
                    "turn dry-run off"
                ),
            )
            out.handed_to_user += 1
            continue

        # Plan 78 § D.3 — per-board daily cap check. Operator-configurable
        # JSONB on Settings keyed by ApplicationBoard.value. Empty dict /
        # missing board key = no per-board limit (global cap still applies).
        per_board_caps = getattr(s, "auto_apply_per_board_daily_caps", None) or {}
        if application.board is not None:
            board_cap = per_board_caps.get(application.board.value)
            if board_cap is not None:
                already_board = await _today_submitted_per_board(
                    application.user_id, application.board.value
                )
                if already_board >= int(board_cap):
                    out.skipped_by_cap += 1
                    continue

        try:
            after = await submit_draft(
                session,
                application.id,
                triggered_by=StatusChangeTrigger.AUTO_APPLY_SUBMITTED,
                notify_fn=notify_fn,
            )
        except ApplicationServiceError as exc:
            log.warning("auto-apply errored on %s: %s", application.id, exc)
            out.failed += 1
            continue

        if after.status == ApplicationStatus.APPLIED:
            out.submitted += 1
            _stamp_auto_apply(application, submitted_at=datetime.now(UTC).isoformat())
            session.add(application)
            today_count[application.user_id] = today_count.get(application.user_id, 0) + 1
            # Plan 78 § D.3 — bump per-board counter for in-cron-lifetime caps.
            if application.board is not None:
                key = (application.user_id, application.board.value)
                today_count_per_board[key] = today_count_per_board.get(key, 0) + 1
        else:
            out.failed += 1
            # Persistent failure (CAPTCHA / auth wall / field mismatch) —
            # the docs are good; the submission needs a human. Hand over
            # with the failure message instead of burying it in SAVED.
            failure = (application.submission_artifacts or {}).get("last_failure") or {}
            await _hand_to_user(
                session,
                application,
                job,
                reason=f"submission failed: {failure.get('message', 'unknown error')}",
            )
            out.handed_to_user += 1
    return out


# ── Status transitions (manual override) ────────────────────────────────


async def drain_auto_apply_queue(
    session: AsyncSession,
    *,
    user_id: int,
    reason: str | None = None,
) -> int:
    """Plan 78 § D.4 — global drain: flip every QUEUED_FOR_AUTO_APPLY Job back
    to SAVED for the given user; emit one `AUTO_APPLY_DRAINED` AppEvent per
    drained Application. Returns the count drained.

    Use case: operator flips `Settings.auto_apply_enabled = False` and wants
    to clear the queued backlog so the queue doesn't auto-process if they
    later flip it back ON.
    """
    stmt = (
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(
            Application.user_id == user_id,
            Application.status == ApplicationStatus.DRAFT,
            Application.deleted_at.is_(None),
            Job.queue_state == JobQueueState.QUEUED_FOR_AUTO_APPLY,
        )
    )
    rows = (await session.exec(stmt)).all()
    drained = 0
    now = datetime.now(UTC)
    for application, job in rows:
        job.queue_state = JobQueueState.SAVED
        job.updated_at = now
        session.add(job)
        await _emit_event(
            session,
            user_id=user_id,
            application_id=application.id,
            kind=AppEventKind.AUTO_APPLY_DRAINED,
            payload={"reason": reason},
        )
        drained += 1
    if drained:
        await session.flush()
    return drained


async def pause_auto_apply_for_job(
    session: AsyncSession,
    *,
    user_id: int,
    job_id: int,
) -> Job | None:
    """Plan 78 § D.4 — per-job pause: flip Job.queue_state QUEUED_FOR_AUTO_APPLY
    → SAVED if the Job is owned by `user_id` and currently queued. Returns the
    updated Job, or None if not found / not queued.
    """
    job = (
        await session.exec(
            select(Job).where(
                Job.id == job_id,
                Job.user_id == user_id,
                Job.deleted_at.is_(None),
            )
        )
    ).one_or_none()
    if job is None:
        return None
    if job.queue_state != JobQueueState.QUEUED_FOR_AUTO_APPLY:
        return job
    job.queue_state = JobQueueState.SAVED
    job.updated_at = datetime.now(UTC)
    session.add(job)
    await session.flush()
    return job


async def update_status(
    session: AsyncSession,
    application_id: int,
    new_status: ApplicationStatus,
    *,
    closed_reason: ClosedReason | None = None,
    notes: str | None = None,
    trigger: StatusChangeTrigger = StatusChangeTrigger.MANUAL,
) -> Application:
    """User-driven (or email-confirmed) status flip.

    Plan 90 / 0.5.0.03 added the `trigger` kwarg so email-suggestion flows can
    record `AUTO_FROM_EMAIL` in the AppEvent payload while reusing the same
    transition + validation path. Default stays MANUAL so existing call sites
    are unchanged.

    Forward transitions are enforced; a backwards transition is allowed but
    logged as `MANUAL_OVERRIDE` AppEvent so audit history is preserved.
    """
    application = await get_application(session, application_id)
    if application is None:
        raise ApplicationServiceError(f"application {application_id} not found")
    current = application.status
    is_forward = _is_forward_transition(current, new_status)
    if not is_forward and current != new_status:
        # Allow but mark explicitly as a manual override.
        log.info(
            "manual override: application %s %s → %s",
            application_id,
            current.value,
            new_status.value,
        )
    if new_status == ApplicationStatus.CLOSED and closed_reason is None:
        raise ValidationError(
            "closed_reason required when status=CLOSED",
            code="closed_reason_missing",
        )

    now = datetime.now(UTC)
    application.status = new_status
    if new_status == ApplicationStatus.CLOSED:
        application.closed_reason = closed_reason
    if new_status != ApplicationStatus.DRAFT and application.applied_at is None:
        # Forward-only: applied_at must be set when leaving DRAFT.
        application.applied_at = now
    if notes:
        application.notes = notes
    application.updated_at = now
    session.add(application)

    await _emit_event(
        session,
        user_id=application.user_id,
        application_id=application.id,
        kind=AppEventKind.STATUS_CHANGE,
        payload={
            "from": current.value,
            "to": new_status.value,
            "trigger": trigger.value,
            "is_forward": is_forward,
            "notes": notes,
        },
    )
    await session.flush()
    return application


# ── Email-suggestion human-confirm seam (plan 90 / 0.5.0.03) ────────────


async def apply_email_suggestion(
    session: AsyncSession,
    *,
    application_id: int,
    message_id: int,
    user_id: int,
) -> Application:
    """Apply the pending email-classification suggestion onto the Application.

    IDOR-guarded — verifies the suggesting EmailMessage belongs to `user_id`
    AND targets `application_id`. Raises ApplicationServiceError on any
    mismatch (mapped to 404 by the route handler).
    """
    from models import EmailMessage

    msg = (
        await session.exec(
            select(EmailMessage).where(
                EmailMessage.id == message_id,
                EmailMessage.user_id == user_id,
                EmailMessage.application_id == application_id,
            )
        )
    ).one_or_none()
    if msg is None:
        raise ApplicationServiceError("suggestion not found")
    if msg.suggested_status is None:
        raise ValidationError(
            "no pending suggestion",
            code="suggestion_missing",
        )
    if msg.suggestion_applied_at is not None or msg.suggestion_dismissed_at is not None:
        raise ValidationError(
            "suggestion already resolved",
            code="suggestion_already_resolved",
        )

    suggested = msg.suggested_status
    closed_reason: ClosedReason | None = None
    if suggested == ApplicationStatus.CLOSED:
        closed_reason = ClosedReason.REJECTED_BY_THEM

    application = await update_status(
        session,
        application_id,
        suggested,
        closed_reason=closed_reason,
        trigger=StatusChangeTrigger.AUTO_FROM_EMAIL,
    )

    now = datetime.now(UTC)
    msg.suggestion_applied_at = now
    session.add(msg)
    await session.flush()
    return application


async def dismiss_email_suggestion(
    session: AsyncSession,
    *,
    application_id: int,
    message_id: int,
    user_id: int,
) -> None:
    """Mark a pending email suggestion as dismissed by the operator."""
    from models import EmailMessage

    msg = (
        await session.exec(
            select(EmailMessage).where(
                EmailMessage.id == message_id,
                EmailMessage.user_id == user_id,
                EmailMessage.application_id == application_id,
            )
        )
    ).one_or_none()
    if msg is None:
        raise ApplicationServiceError("suggestion not found")
    if msg.suggestion_applied_at is not None or msg.suggestion_dismissed_at is not None:
        raise ValidationError(
            "suggestion already resolved",
            code="suggestion_already_resolved",
        )
    msg.suggestion_dismissed_at = datetime.now(UTC)
    session.add(msg)
    await session.flush()


# ── Computed state — referral + outreach ────────────────────────────────


_REFERRAL_PRIORITY = {
    ReferralState.PROVIDED: 4,
    ReferralState.IN_FLIGHT: 3,
    ReferralState.REQUESTED: 2,
    ReferralState.DECLINED: 1,
    ReferralState.NONE: 0,
}


async def _roll_up_referral_state(session: AsyncSession, application_id: int) -> ReferralState:
    """Application.referral_state = max-priority across all links."""
    links = (
        await session.exec(
            select(ContactApplicationLink).where(
                ContactApplicationLink.application_id == application_id
            )
        )
    ).all()
    if not links:
        new_state = ReferralState.NONE
    else:
        new_state = max(
            (link.referral_state for link in links),
            key=lambda s: _REFERRAL_PRIORITY.get(s, 0),
        )
    application = await get_application(session, application_id)
    if application is None:
        return new_state
    if application.referral_state != new_state:
        application.referral_state = new_state
        application.updated_at = datetime.now(UTC)
        session.add(application)
        await session.flush()
    return new_state


async def compute_outreach_engagement(session: AsyncSession, application_id: int) -> str:
    """Pure function over OutreachMessage[] + ContactApplicationLink[].

    Returns one of `referred / awaiting_reply / cold / active`.
    Phase 1 computed on demand; Phase 4+ may cache.
    """
    links = (
        await session.exec(
            select(ContactApplicationLink).where(
                ContactApplicationLink.application_id == application_id
            )
        )
    ).all()
    if any(link.referral_state == ReferralState.PROVIDED for link in links):
        return "referred"

    msgs = (
        await session.exec(
            select(OutreachMessage).where(OutreachMessage.application_id == application_id)
        )
    ).all()
    if not msgs and not links:
        return "cold"
    threshold = datetime.now(UTC) - timedelta(days=14)
    awaiting = any(
        m.sent_at is not None
        and m.sent_at >= threshold
        and m.replied_at is None
        and m.status == OutreachStatus.SENT
        for m in msgs
    )
    if awaiting:
        return "awaiting_reply"
    if msgs or links:
        return "active"
    return "cold"


# ── Stuck-queue surface ────────────────────────────────────────────────


async def stuck_drafts(session: AsyncSession, *, user_id: int) -> list[Application]:
    """DRAFTs with `submission_artifacts.last_failure` populated.

    Surfaces in Discover right rail "Stuck in queue · {N}" card. Filtered to
    the current user — vault boundary applies (we never leak another user's
    failures across the API).
    """
    apps = (
        await session.exec(
            select(Application).where(
                Application.user_id == user_id,
                Application.status == ApplicationStatus.DRAFT,
                Application.deleted_at.is_(None),
                Application.submission_artifacts.is_not(None),
            )
        )
    ).all()
    return [
        a for a in apps if a.submission_artifacts and a.submission_artifacts.get("last_failure")
    ]


# ── List accessors (plan 60 / 0.2.7.17) ────────────────────────────────


_TRACKING_VISIBLE_STATUSES: set[ApplicationStatus] = {
    ApplicationStatus.APPLIED,
    ApplicationStatus.RECRUITER_SCREEN,
    ApplicationStatus.ONSITE_LOOP,
    ApplicationStatus.OFFER,
}


async def list_applications(
    session: AsyncSession,
    *,
    user_id: int,
    statuses: set[ApplicationStatus] | None = None,
    include_deleted: bool = False,
) -> list[Application]:
    """Soft-delete-aware list of Applications for `user_id`."""
    stmt = select(Application).where(Application.user_id == user_id)
    if not include_deleted:
        stmt = stmt.where(Application.deleted_at.is_(None))
    if statuses is not None:
        stmt = stmt.where(Application.status.in_(statuses))
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def list_visible_in_tracking(session: AsyncSession, user_id: int) -> list[Application]:
    """Default Tracking view — APPLIED through OFFER. Hides DRAFT + CLOSED."""
    return await list_applications(session, user_id=user_id, statuses=_TRACKING_VISIBLE_STATUSES)


async def list_by_status(
    session: AsyncSession, user_id: int, status: ApplicationStatus
) -> list[Application]:
    return await list_applications(session, user_id=user_id, statuses={status})


async def list_in_followup(session: AsyncSession, user_id: int) -> list[Application]:
    """Recruiter SILENT / STALLED on live (non-DRAFT, non-CLOSED) apps."""
    stmt = select(Application).where(
        Application.user_id == user_id,
        Application.deleted_at.is_(None),
        Application.recruiter_state.in_([RecruiterState.SILENT, RecruiterState.STALLED]),
        Application.status.not_in([ApplicationStatus.DRAFT, ApplicationStatus.CLOSED]),
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def list_closed(session: AsyncSession, user_id: int) -> list[Application]:
    return await list_by_status(session, user_id, ApplicationStatus.CLOSED)


async def list_drafts(session: AsyncSession, user_id: int) -> list[Application]:
    return await list_by_status(session, user_id, ApplicationStatus.DRAFT)


async def list_documents_for(session: AsyncSession, application_id: int) -> list[GeneratedDocument]:
    """All compiled (error IS NULL) GeneratedDocuments for an Application."""
    stmt = (
        select(GeneratedDocument)
        .where(
            GeneratedDocument.application_id == application_id,
            GeneratedDocument.error.is_(None),
        )
        .order_by(GeneratedDocument.compiled_at.desc())
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def list_screener_answers_for(
    session: AsyncSession, application_id: int
) -> list[ApplicationScreenerAnswer]:
    """All screener answers for an Application, ordered by `order_index`."""
    stmt = (
        select(ApplicationScreenerAnswer)
        .where(ApplicationScreenerAnswer.application_id == application_id)
        .order_by(ApplicationScreenerAnswer.order_index)
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


async def get_screener_answer(
    session: AsyncSession,
    answer_id: int,
    *,
    owner_user_id: int | None = None,
) -> ApplicationScreenerAnswer | None:
    """Single ApplicationScreenerAnswer by id, used by `/_fragments/apply/screener/`.

    Plan 75 / 0.3.3.15. `owner_user_id` enforces the IDOR boundary —
    when set, JOINs to `Application` and returns None if the answer's
    parent application belongs to a different user. `None` preserves
    the fake-session bypass for legacy fixtures.
    """
    if owner_user_id is None:
        stmt = select(ApplicationScreenerAnswer).where(ApplicationScreenerAnswer.id == answer_id)
        return (await session.exec(stmt)).one_or_none()
    stmt = (
        select(ApplicationScreenerAnswer)
        .join(Application, ApplicationScreenerAnswer.application_id == Application.id)
        .where(
            ApplicationScreenerAnswer.id == answer_id,
            Application.user_id == owner_user_id,
        )
    )
    return (await session.exec(stmt)).one_or_none()


async def count_unreviewed_required_screeners(session: AsyncSession, application_id: int) -> int:
    """Count of required screener answers that are still unreviewed."""
    stmt = select(func.count(ApplicationScreenerAnswer.id)).where(
        ApplicationScreenerAnswer.application_id == application_id,
        ApplicationScreenerAnswer.required.is_(True),
        ApplicationScreenerAnswer.reviewed_at.is_(None),
    )
    result = (await session.exec(stmt)).one()
    if isinstance(result, tuple):
        result = result[0]
    return int(result or 0)


async def list_events_for(
    session: AsyncSession,
    application_id: int,
    *,
    limit: int = 50,
) -> list[AppEvent]:
    """Most-recent AppEvents for an Application."""
    stmt = (
        select(AppEvent)
        .where(AppEvent.application_id == application_id)
        .order_by(AppEvent.occurred_at.desc())
        .limit(limit)
    )
    rows = (await session.exec(stmt)).all()
    return list(rows)


# ── Mutation helpers (plan 60 / 0.2.7.17) ──────────────────────────────


async def record_draft_failure(
    session: AsyncSession,
    application_id: int,
    kind: str,
    message: str,
) -> Application | None:
    """Write `submission_artifacts.last_failure` to a DRAFT Application."""
    a = await get_application(session, application_id)
    if a is None:
        return None
    artifacts = dict(a.submission_artifacts or {})
    artifacts["last_failure"] = {
        "kind": kind,
        "message": message,
        "captured_at": datetime.now(UTC).isoformat(),
    }
    artifacts["retry_count"] = int(artifacts.get("retry_count") or 0) + 1
    a.submission_artifacts = artifacts
    a.updated_at = datetime.now(UTC)
    session.add(a)
    await session.flush()
    return a


async def create_manual(
    session: AsyncSession,
    *,
    user_id: int,
    company: str,
    role: str,
    team: str | None = None,
    location: str | None = None,
    salary_min: int | None = None,
    salary_max: int | None = None,
    notes: str | None = None,
) -> Application:
    """Create an APPLIED Application from the manual-entry form.

    Uses `board = ApplicationBoard.MANUAL` and stamps `applied_at = now`.
    Emits a STATUS_CHANGE AppEvent so the Tracking timeline carries the
    transition.
    """
    from models import ApplicationBoard  # local import to avoid circular

    now = datetime.now(UTC)
    a = Application(
        user_id=user_id,
        job_id=None,
        company=company,
        role=role,
        team=team,
        location=location,
        salary_min=salary_min,
        salary_max=salary_max,
        applied_at=now,
        board=ApplicationBoard.MANUAL,
        external_url=None,
        status=ApplicationStatus.APPLIED,
        docs_state=DocsState.NONE,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        submission_artifacts={"board_application_id": None, "manual": True},
        notes=notes,
        created_at=now,
        updated_at=now,
    )
    session.add(a)
    await session.flush()
    await _emit_event(
        session,
        user_id=user_id,
        application_id=a.id,
        kind=AppEventKind.STATUS_CHANGE,
        payload={
            "from": None,
            "to": ApplicationStatus.APPLIED.value,
            "trigger": "manual",
        },
    )
    return a


async def record_screener_answer(
    session: AsyncSession,
    answer_id: int,
    body: str,
    *,
    owner_user_id: int | None = None,
) -> ApplicationScreenerAnswer | None:
    """Update an ApplicationScreenerAnswer body + stamp reviewed_at.

    Plan 75 / 0.3.3.15. `owner_user_id` enforces the IDOR boundary on
    writes — when set, returns None for cross-user attempts so the route
    surfaces a clean 404. `None` preserves fake-session bypass.
    """
    if owner_user_id is None:
        stmt = select(ApplicationScreenerAnswer).where(ApplicationScreenerAnswer.id == answer_id)
    else:
        stmt = (
            select(ApplicationScreenerAnswer)
            .join(Application, ApplicationScreenerAnswer.application_id == Application.id)
            .where(
                ApplicationScreenerAnswer.id == answer_id,
                Application.user_id == owner_user_id,
            )
        )
    a = (await session.exec(stmt)).one_or_none()
    if a is None:
        return None
    now = datetime.now(UTC)
    a.answer = body
    a.reviewed_at = now
    a.updated_at = now
    session.add(a)
    await session.flush()
    return a


# ── Submission-result observability (plan 54 / 0.2.5.02) ───────────────


async def aggregate_submission_failures(
    session: AsyncSession,
    *,
    user_id: int,
    since_days: int = 30,
) -> list[dict]:
    """Aggregate `last_failure.kind` counts per board for Settings · Submissions.

    Plan 54 / 0.2.5.02. Single SELECT over `Application` grouped by
    `(board, last_failure.kind)`. Soft-deleted + null-artifacts rows are
    excluded. Returns rows shaped ``{board, failure_kind, count, latest_at}``
    ordered by ``count DESC``. Empty list for users with no failed DRAFTs.

    Postgres path uses ``func.jsonb_extract_path_text`` — typed expression
    API, never raw SQL. Tests without a Postgres engine override this helper
    via monkeypatch at the route layer (no on-disk JSONB query runs).
    """
    cutoff = datetime.now(UTC) - timedelta(days=since_days)
    kind_expr = func.jsonb_extract_path_text(
        Application.submission_artifacts, "last_failure", "kind"
    )
    stmt = (
        select(
            Application.board,
            kind_expr.label("failure_kind"),
            func.count().label("cnt"),
            func.max(Application.updated_at).label("latest_at"),
        )
        .where(
            Application.user_id == user_id,
            Application.deleted_at.is_(None),
            Application.submission_artifacts.is_not(None),
            Application.submission_artifacts.has_key("last_failure"),
            Application.updated_at >= cutoff,
            kind_expr.is_not(None),
        )
        .group_by(Application.board, kind_expr)
        .order_by(func.count().desc())
    )
    rows = (await session.exec(stmt)).all()
    out: list[dict] = []
    for row in rows:
        # session.exec over `select(col, ...)` yields tuples; unpack defensively.
        if isinstance(row, tuple):
            board, kind, count, latest_at = row
        else:
            board, kind, count, latest_at = row[0], row[1], row[2], row[3]
        out.append(
            {
                "board": board.value if board is not None else None,
                "failure_kind": kind,
                "count": int(count),
                "latest_at": latest_at,
            }
        )
    return out


# ── Bulk operations on /tracking list (plan 80 / 0.4.0.09) ──────────────


BULK_MAX_IDS = 50


async def bulk_update_status(
    session: AsyncSession,
    *,
    user_id: int,
    application_ids: list[int],
    new_status: ApplicationStatus,
    closed_reason: ClosedReason | None = None,
) -> tuple[int, list[int]]:
    """Bulk-update status. Returns ``(success_count, failed_ids)``.

    Iterates per-ID and routes through ``update_status`` so the existing
    forward-transition + closed_reason rules + AppEvent emission still fire.
    Failed IDs cover three buckets: missing application, cross-user IDOR
    (silently ignored), and `update_status` raising
    ``IllegalStateTransition`` / ``ValidationError``.

    Caps `application_ids` at ``BULK_MAX_IDS`` (50) to keep transaction
    duration bounded.
    """
    if len(application_ids) > BULK_MAX_IDS:
        raise ValidationError(
            f"Bulk operation limit is {BULK_MAX_IDS} applications per request",
            code="bulk_limit_exceeded",
        )

    success = 0
    failed: list[int] = []
    for app_id in application_ids:
        application = await get_application(session, app_id)
        if application is None or application.user_id != user_id:
            failed.append(app_id)
            continue
        try:
            await update_status(
                session,
                app_id,
                new_status,
                closed_reason=closed_reason,
            )
            success += 1
        except (IllegalStateTransition, ValidationError):
            failed.append(app_id)
    return success, failed


async def bulk_archive(
    session: AsyncSession,
    *,
    user_id: int,
    application_ids: list[int],
) -> tuple[int, list[int]]:
    """Bulk archive: status=CLOSED, closed_reason=USER_ARCHIVED.

    Wraps ``bulk_update_status`` with the USER_ARCHIVED reason so the
    audit-event payload distinguishes operator-initiated archive from
    rejection / withdrawal / ghosting.
    """
    return await bulk_update_status(
        session,
        user_id=user_id,
        application_ids=application_ids,
        new_status=ApplicationStatus.CLOSED,
        closed_reason=ClosedReason.USER_ARCHIVED,
    )


async def list_for_export(
    session: AsyncSession,
    *,
    user_id: int,
    application_ids: list[int],
) -> list[dict]:
    """Fetch + denormalize selected applications for CSV export.

    Honors ``user_id`` boundary (cross-user IDs silently filtered out) and
    skips soft-deleted rows. Returns a list of dicts matching the CSV
    fieldnames in the export route.
    """
    if not application_ids:
        return []
    if len(application_ids) > BULK_MAX_IDS:
        raise ValidationError(
            f"Bulk operation limit is {BULK_MAX_IDS} applications per request",
            code="bulk_limit_exceeded",
        )
    stmt = select(Application).where(
        Application.user_id == user_id,
        Application.id.in_(application_ids),
        Application.deleted_at.is_(None),
    )
    rows = (await session.exec(stmt)).all()
    # Plan 85 / 0.4.0.23 — defang every cell to mitigate Excel/LibreOffice
    # formula injection. Operator-controlled fields (company / role / team /
    # location / external_url) are the high-risk path; enum / typed fields
    # are defense-in-depth.
    return [
        {
            "company": _defang_csv_cell(a.company),
            "role": _defang_csv_cell(a.role),
            "team": _defang_csv_cell(a.team),
            "location": _defang_csv_cell(a.location),
            "status": _defang_csv_cell(a.status.value),
            "applied_at": _defang_csv_cell(a.applied_at.isoformat() if a.applied_at else None),
            "salary_min": _defang_csv_cell(a.salary_min),
            "salary_max": _defang_csv_cell(a.salary_max),
            "board": _defang_csv_cell(a.board.value if a.board else None),
            "external_url": _defang_csv_cell(a.external_url),
        }
        for a in rows
    ]


async def count_applied_since(session: AsyncSession, *, user_id: int, since: datetime) -> int:
    """Applications submitted (applied_at set) since `since` — Discover stats strip."""
    stmt = (
        select(func.count())
        .select_from(Application)
        .where(
            Application.user_id == user_id,
            Application.applied_at.isnot(None),  # type: ignore[union-attr]
            Application.applied_at >= since,
            Application.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    return int((await session.exec(stmt)).one() or 0)
