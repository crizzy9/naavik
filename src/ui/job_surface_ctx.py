"""One canonical context for the job surface (plan 96c — R3/R4, owner #9).

Everything about a job, reachable from the job, in one ctx call: the job
itself (JD / score / apply target), its applications (all of them —
re-applications are legal; newest is primary), the conversation (threads +
messages + per-email signal detail), rounds, contacts, documents, and the
status timeline. Rendered by `pages/jobs/_job_surface.html` in two mounts
(modal + page) and two state-dependent views (pre_apply / post_apply).
"""

from __future__ import annotations

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import Application, EmailThread
from models.enums import ApplicationStatus, application_status_label

VIEWS = ("pre_apply", "post_apply")

_CLOSED_REASON_LABELS = {
    "rejected_by_them": "They rejected this application",
    "withdrawn_by_me": "You withdrew",
    "ghosted": "Closed as ghosted — no response",
    "accepted_other": "Closed — you accepted another offer",
    "user_archived": "Archived",
}


async def build_job_surface_ctx(
    session: AsyncSession,
    *,
    user_id: int,
    job_id: int | None = None,
    application_id: int | None = None,
    view_override: str | None = None,
) -> dict[str, object] | None:
    """Resolve by job OR by application (manual applications may have no
    job). Returns None for missing/cross-user rows — routes map to 404."""
    from services import jobs as job_service
    from ui import jobs_ctx
    from ui import tracking_ctx as tctx

    job = None
    applications: list[Application] = []
    selected: Application | None = None

    if application_id is not None:
        selected = await session.get(Application, application_id)
        if selected is None or selected.user_id != user_id:
            return None
        if job_id is not None and selected.job_id != job_id:
            return None
        job_id = selected.job_id

    if job_id is not None:
        job = await job_service.get_job(session, job_id)
        if job is None or job.user_id != user_id or job.deleted_at is not None:
            if selected is None:
                return None
            # The application outlives its (archived) job — degrade to the
            # application-only surface instead of 404ing a live process.
            job = None
            job_id = None

    if job_id is not None:
        # ALL applications on the job — the alive-unique index means
        # re-applications live as soft-deleted history; they must still
        # surface (R3 gap c). Alive first, newest first.
        rows = (
            await session.exec(
                select(Application)
                .where(
                    Application.user_id == user_id,
                    Application.job_id == job_id,
                )
                .order_by(Application.created_at.desc())
            )
        ).all()
        applications = sorted(rows, key=lambda a: a.deleted_at is not None)
    elif selected is not None:
        applications = [selected]
    else:
        return None

    alive = [a for a in applications if a.deleted_at is None]
    primary = selected or (alive[0] if alive else None)

    # View: manual tab switch wins; else no application / DRAFT → pre,
    # APPLIED+ → post (CLOSED → post with the closed banner).
    can_pre = job is not None
    can_post = primary is not None
    if view_override in VIEWS:
        view = view_override
    elif primary is None or primary.status == ApplicationStatus.DRAFT:
        view = "pre_apply"
    else:
        view = "post_apply"
    if view == "pre_apply" and not can_pre:
        view = "post_apply"
    if view == "post_apply" and not can_post:
        view = "pre_apply"

    ctx: dict[str, object] = {}
    if job is not None:
        scrape_run = None
        if job.last_scrape_run_id is not None:
            scrape_run = await job_service.get_scrape_run(session, job.last_scrape_run_id)
        ctx.update(await jobs_ctx.build_job_detail_ctx(session, job=job, scrape_run=scrape_run))
    else:
        ctx.update({"job": None, "scrape_run": None})

    if primary is not None:
        ctx.update(await tctx.build_application_detail_ctx(session, primary))
    else:
        ctx.update(
            {
                "application": None,
                "status_timeline": [],
                "rounds": [],
                "status_pin": None,
                "conversation_threads": [],
                "documents": [],
                "screener_answers": [],
                "contacts": [],
                "last_failure": None,
                "postmortem_ts": None,
                "auto_apply": None,
                "job_url": None,
                "bullets_used": [],
                "auto_apply_artifacts": [],
                "calendar_events": [],
            }
        )

    # Gap (b): mail linked to the JOB with no application yet (96c1 thread
    # job link) — plus, when several applications exist, threads belonging
    # to the job but not the selected application.
    unlinked_job_threads: list[dict[str, object]] = []
    if job is not None:
        rows = (
            await session.exec(
                select(EmailThread)
                .where(
                    EmailThread.user_id == user_id,
                    EmailThread.job_id == job.id,
                    EmailThread.application_id.is_(None),
                )
                .order_by(EmailThread.latest_message_at.desc())
            )
        ).all()
        unlinked_job_threads = [
            {
                "id": t.id,
                "subject": t.subject or "(no subject)",
                "classification": t.classification.value if t.classification else None,
                "classification_tone": tctx._CLASSIFICATION_TONES.get(
                    t.classification.value if t.classification else "", "slate"
                ),
                "latest_label": tctx._relative_label(t.latest_message_at),
                "message_count": t.message_count or 0,
            }
            for t in rows
        ]

    # Identity header works from either side.
    company = primary.company if primary is not None else (job.company if job else "")
    role = primary.role if primary is not None else (job.role if job else "")
    initial, color = tctx._initial_color(company)

    closed = None
    if primary is not None and primary.status == ApplicationStatus.CLOSED:
        reason = primary.closed_reason.value if primary.closed_reason else None
        closed = {
            "reason": reason,
            "label": _CLOSED_REASON_LABELS.get(reason or "", "Closed"),
        }

    ctx.update(
        {
            "surface": {
                "view": view,
                "can_pre": can_pre,
                "can_post": can_post,
                "job_id": job.id if job is not None else None,
                "application_id": primary.id if primary is not None else None,
                "company": company,
                "role": role,
                "company_initial": initial,
                "company_color": color,
                "status": primary.status.value if primary is not None else None,
                "status_label": (
                    application_status_label(primary.status) if primary is not None else None
                ),
                "closed": closed,
                # The modal's "expand" affordance; None for job-less
                # applications (their deep-link stays /tracking/{id}).
                "page_url": (
                    f"/jobs/{job.id}"
                    + (f"?application={primary.id}" if primary is not None else "")
                    if job is not None
                    else None
                ),
            },
            "surface_applications": [
                {
                    "id": a.id,
                    "status": a.status.value,
                    "status_label": application_status_label(a.status),
                    "applied_at_label": tctx._relative_label(a.applied_at),
                    "is_selected": primary is not None and a.id == primary.id,
                    "is_removed": a.deleted_at is not None,
                }
                for a in applications
            ],
            "unlinked_job_threads": unlinked_job_threads,
        }
    )
    return ctx
