"""Read accessors — single fetch, cover sections, list family, counts.

Split out of services/application_service.py in plan 91 Phase 4.2;
behaviour unchanged. Internal calls to shimmed/patched seams go through
`svc()` (the facade) so test interception keeps working.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    AppEvent,
    Application,
    ApplicationScreenerAnswer,
    ApplicationStatus,
    GeneratedDocument,
    GeneratedDocumentKind,
    RecruiterState,
)

log = logging.getLogger(__name__)


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
