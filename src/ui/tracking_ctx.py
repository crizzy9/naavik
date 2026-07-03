"""Project Application rows into tracking_card / tracking_list_row dicts."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel.ext.asyncio.session import AsyncSession

from models import Application
from models.enums import AppEventKind, ApplicationStatus, RecruiterState, ReferralState
from services import application_service, contact_tracker, email_service

_COMPANY_COLORS = {
    "F": "bg-fuchsia-700",
    "A": "bg-emerald-700",
    "S": "bg-indigo-700",
    "L": "bg-purple-700",
    "N": "bg-rose-700",
    "P": "bg-amber-700",
    "R": "bg-amber-700",
    "D": "bg-indigo-700",
    "M": "bg-cyan-700",
    "C": "bg-amber-700",
    "T": "bg-sky-700",
    "G": "bg-rose-600",
    "O": "bg-emerald-700",
}


def _initial_color(company: str) -> tuple[str, str]:
    initial = (company or "?")[:1].upper()
    return initial, _COMPANY_COLORS.get(initial, "bg-slate-700")


def _salary_range(a: Application) -> str | None:
    if a.salary_min and a.salary_max:
        return f"${a.salary_min // 1000}-{a.salary_max // 1000}k"
    if a.salary_min:
        return f"${a.salary_min // 1000}k+"
    return None


def _aware(when: datetime) -> datetime:
    return when if when.tzinfo is not None else when.replace(tzinfo=UTC)


def _relative_label(when: datetime | None) -> str:
    if when is None:
        return "—"
    delta = datetime.now(UTC) - _aware(when)
    days = delta.days
    if days < 1:
        return "today"
    if days == 1:
        return "1d ago"
    if days < 30:
        return f"{days}d ago"
    return f"{days // 30}mo ago"


def _context_chip(a: Application) -> tuple[str | None, str]:
    """Return (chip_label, tone) — small status pill rendered on tracking_card."""
    if a.referral_state == ReferralState.PROVIDED:
        return ("referral", "emerald")
    if a.referral_state in {ReferralState.REQUESTED, ReferralState.IN_FLIGHT}:
        return ("referral pending", "amber")
    if a.recruiter_state == RecruiterState.SILENT:
        return ("reply pending", "amber")
    return (None, "slate")


def application_to_card(a: Application) -> dict[str, object]:
    initial, color = _initial_color(a.company)
    chip, tone = _context_chip(a)
    return {
        "id": a.id,
        "company": a.company,
        "company_initial": initial,
        "company_color": color,
        "role": a.role,
        "team": a.team,
        "score": 80,  # placeholder; jobs carry score
        "salary_range": _salary_range(a),
        "status": a.status.value,
        "status_label": a.status.value.replace("_", " ").lower(),
        "context_chip": chip,
        "context_chip_tone": tone,
        "sub_state_pills": [],
    }


def application_to_list_row(a: Application) -> dict[str, object]:
    initial, color = _initial_color(a.company)
    return {
        "id": a.id,
        "company": a.company,
        "company_initial": initial,
        "company_color": color,
        "role": a.role,
        "team": a.team,
        "status": a.status.value,
        "status_label": a.status.value.replace("_", " "),
        "score": None,
        "salary_range": _salary_range(a),
        "last_activity": _relative_label(a.updated_at),
        "source": (a.board.value if a.board else "manual"),
    }


def _columns_for_board(apps: list[Application], *, show_closed: bool) -> list[dict[str, object]]:
    visible = [
        ApplicationStatus.APPLIED,
        ApplicationStatus.RECRUITER_SCREEN,
        ApplicationStatus.ONSITE_LOOP,
        ApplicationStatus.OFFER,
    ]
    if show_closed:
        visible.append(ApplicationStatus.CLOSED)
    out = []
    for status in visible:
        cards = [application_to_card(a) for a in apps if a.status == status]
        out.append({"status": status.value, "cards": cards})
    return out


async def build_tracking_ctx(
    session: AsyncSession,
    *,
    user_id: int,
    view: str = "board",
    show_closed: bool = False,
    show_drafts: bool = False,
) -> dict[str, object]:
    from services import email_application_inference as inference

    visible_apps = await application_service.list_visible_in_tracking(session, user_id)
    # Item 5 — unconfirmed inferred applications stay off the board; they
    # live in the confirmation banner until the user confirms/dismisses.
    inferred_pending = [a for a in visible_apps if inference.is_unconfirmed_inferred(a)]
    visible_apps = [a for a in visible_apps if not inference.is_unconfirmed_inferred(a)]
    if show_drafts:
        visible_apps = visible_apps + await application_service.list_drafts(session, user_id)
    closed = await application_service.list_closed(session, user_id)
    all_apps = visible_apps + closed if show_closed else visible_apps
    columns = _columns_for_board(all_apps, show_closed=show_closed)

    followup = await application_service.list_in_followup(session, user_id)
    items: list[dict[str, object]] = []
    for a in followup[:4]:
        contacts = await contact_tracker.list_contacts_for_application(session, a.id)
        c = contacts[0] if contacts else None
        items.append(
            {
                "contact": {
                    "name": c.name if c else "Recruiter",
                    "initial": (c.name[:1].upper() if c else a.company[:1].upper()),
                    "color": _initial_color(c.company if c else a.company)[1],
                },
                "application": {"company": a.company},
                "last_touch_label": (
                    f"sent {_relative_label(a.updated_at)} · no reply"
                    if a.recruiter_state == RecruiterState.SILENT
                    else f"asked you back {_relative_label(a.updated_at)}"
                ),
                "action_label": "Draft reply",
                "action_url": f"/outreach?application={a.id}",
            }
        )

    # Honest email-integration state: derived from real EmailAccount rows
    # (plan 90 IMAP foundation) — the prior hardcoded "Gmail connected ·
    # shyam@gmail.com" card implied a connection that never existed.
    email_accounts = await email_service.list_accounts(session, user_id)
    primary_account = email_accounts[0] if email_accounts else None
    # Item 11 — honest calendar state from the real CalendarConnection row;
    # the Connect button used to point at the fake OAuth stub (which
    # round-tripped back showing "not connected" forever).
    from services import calendar_sync

    calendar_connection = await calendar_sync.get_connection(session, user_id)
    upcoming = (
        await calendar_sync.upcoming_events(session, user_id=user_id) if calendar_connection else []
    )
    integrations = [
        {
            "name": "Email (IMAP)",
            "icon": "mail",
            "state": "connected" if primary_account else "not_connected",
            "account": primary_account.account_email if primary_account else None,
            "connect_url": "/integrations/email",
            "disconnect_url": "/integrations/email" if primary_account else None,
            "description": None if primary_account else "connect an inbox to track replies",
        },
        {
            "name": "Calendar",
            "icon": "calendar",
            "state": "connected" if calendar_connection else "not_connected",
            "account": calendar_connection.label if calendar_connection else None,
            "connect_url": "/integrations/email#calendar",
            "disconnect_url": "/integrations/email#calendar" if calendar_connection else None,
            "description": (
                f"{calendar_connection.event_count} events synced · read-only"
                if calendar_connection
                else "interviews on your board — read-only ICS"
            ),
        },
    ]

    return {
        # Item 5 — proposed applications inferred from inbox receipts.
        "inferred_pending": [
            {
                "id": a.id,
                "company": a.company,
                "role": a.role,
                "applied_at_label": _relative_label(a.applied_at),
                "subject": (a.submission_artifacts or {}).get("inferred", {}).get("subject", ""),
            }
            for a in inferred_pending
        ],
        "upcoming_events": [
            {
                "id": e.id,
                "title": e.title or "(untitled event)",
                "when_label": calendar_sync.format_event_when(e),
                "location": e.location,
                "application_id": e.matched_application_id,
            }
            for e in upcoming
        ],
        "email_connected": primary_account is not None,
        "email_account_label": (primary_account.account_email if primary_account else None),
        "email_last_sync_label": (
            _relative_label(primary_account.last_sync_at)
            if primary_account and primary_account.last_sync_at
            else None
        ),
        "current_view": view,
        "show_closed": show_closed,
        "show_drafts": show_drafts,
        "columns": columns,
        "rows": [application_to_list_row(a) for a in visible_apps],
        "active_count": len(visible_apps),
        "closed_count": len(closed),
        "followup_count": len(followup),
        "followup_items": items,
        "integrations": integrations,
    }


async def build_application_detail_ctx(
    session: AsyncSession, application: Application
) -> dict[str, object]:
    """Project Application + related rows into the detail slide-over (plan 53 § C.3)."""
    initial, color = _initial_color(application.company)
    events = await application_service.list_events_for(session, application.id)
    status_timeline = [
        {
            "from": e.payload.get("from"),
            "to": e.payload.get("to"),
            "trigger": e.payload.get("trigger"),
            "occurred_at": e.occurred_at,
            "occurred_at_label": _relative_label(e.occurred_at),
        }
        for e in events
        if e.kind == AppEventKind.STATUS_CHANGE
    ]
    status_timeline.reverse()

    documents = await application_service.list_documents_for(session, application.id)
    _PDF_URLS = {
        "resume": f"/api/v1/applications/{application.id}/resume.pdf",
        "cover_letter": f"/api/v1/applications/{application.id}/cover-letter.pdf",
    }
    seen_kinds: set[str] = set()
    docs = []
    for d in documents:
        kind = d.kind.value
        docs.append(
            {
                "id": d.id,
                "kind": kind,
                "compiled_at": d.compiled_at,
                "compiled_at_label": _relative_label(d.compiled_at),
                "path": d.path,
                # Only the latest doc per kind is servable via the PDF routes.
                "pdf_url": _PDF_URLS.get(kind) if kind not in seen_kinds else None,
            }
        )
        seen_kinds.add(kind)

    # Screener answers — what was (or would be) sent with the application.
    screener_rows = [
        {
            "question": s.question_text,
            "answer": s.answer or "",
            "source": s.source.value,
            "reviewed": s.reviewed_at is not None,
        }
        for s in await application_service.list_screener_answers_for(session, application.id)
    ]

    contacts = await contact_tracker.list_contacts_for_application(session, application.id)
    contact_rows = [
        {
            "id": c.id,
            "name": c.name,
            "title": c.title,
            "company": c.company,
            "initial": (c.name[:1] or "?").upper(),
        }
        for c in contacts
    ]

    last_failure = None
    board_application_id = None
    postmortem_ts: str | None = None
    bullet_overrides: dict[str, str] = {}
    if application.submission_artifacts:
        last_failure = application.submission_artifacts.get("last_failure")
        board_application_id = application.submission_artifacts.get("board_application_id")
        if isinstance(last_failure, dict):
            # Plan 81 § D.1 — `last_failure.postmortem_path` is shaped
            # `postmortems/<application_id>/<ts>`. We expose the trailing
            # `<ts>` segment so the modal route can be built in the template
            # without the template having to slice the path.
            pm_path = last_failure.get("postmortem_path")
            if isinstance(pm_path, str) and pm_path:
                postmortem_ts = pm_path.rsplit("/", 1)[-1]
        # Plan 86 / 0.4.5.08 — per-application bullet overrides written by
        # `PUT /api/v1/applications/{id}/bullet-override`. Shape:
        # `{"<bullet_id>": "always_include" | "never_include"}`. Read here so
        # the slide-over can render the three-state toggle pre-selected.
        raw_overrides = application.submission_artifacts.get("bullet_overrides")
        if isinstance(raw_overrides, dict):
            for bid, val in raw_overrides.items():
                if isinstance(val, str) and val in ("always_include", "never_include"):
                    bullet_overrides[str(bid)] = val

    # Plan 86 / 0.4.5.08 — bullets actually used in the latest resume bundle.
    # Source: `GeneratedDocument.bullet_selection["selected_ids"]` (plan 66).
    # Joined with `Bullet.text` for the slide-over override toggle list.
    bullets_used_rows: list[dict[str, object]] = []
    try:
        from sqlmodel import select

        from models import Bullet

        bullet_ids_used: list[int] = []
        for doc in documents:
            sel = doc.bullet_selection if hasattr(doc, "bullet_selection") else None
            if isinstance(sel, dict):
                for bid in sel.get("selected_ids") or []:
                    try:
                        bullet_ids_used.append(int(bid))
                    except (TypeError, ValueError):
                        continue
        if bullet_ids_used:
            unique_ids = list(dict.fromkeys(bullet_ids_used))
            b_rows = (
                await session.exec(select(Bullet.id, Bullet.text).where(Bullet.id.in_(unique_ids)))
            ).all()
            for row in b_rows:
                bid = int(row[0]) if isinstance(row, tuple) else None
                text = row[1] if isinstance(row, tuple) else None
                if bid is None:
                    continue
                bullets_used_rows.append(
                    {
                        "id": bid,
                        "text": (text or "")[:160],
                        "override": bullet_overrides.get(str(bid)),
                    }
                )
    except Exception:  # noqa: BLE001 — slide-over override list is optional
        bullets_used_rows = []

    # Plan 81 § D.3 — surface the Job's score on the slide-over header.
    # Best-effort: skip the lookup for manual entries (job_id is null) and
    # any failure (jobs deleted etc.) falls back to a None chip — template
    # gates render on `a.score is not none and a.job_id`.
    score: int | None = None
    auto_apply = None
    job_url: str | None = None
    if application.job_id is not None:
        try:
            from services import job_service

            job = await job_service.get_job(session, application.job_id)
            if job is not None and getattr(job, "score", None) is not None:
                # Job.score is 0–1; the chip renders 0–100.
                raw = float(job.score)
                score = int(round(raw * 100)) if raw <= 1.0 else int(round(raw))
            if job is not None:
                auto_apply = application_service.auto_apply_phase(application, job)
                job_url = getattr(job, "url", None)
        except Exception:  # noqa: BLE001 — defensive; chip optional
            score = None

    # Item 7 — dry-run / submission screenshot evidence (filenames under the
    # application's auto_apply dir, served by the guarded artifact route).
    auto_apply_artifacts: list[dict[str, str]] = []
    _auto_blob = (application.submission_artifacts or {}).get("auto_apply") or {}
    for _key, _label in (
        ("dry_run_artifacts", "dry-run"),
        ("submission_artifacts_files", "submission"),
        ("failure_artifacts", "failure"),
    ):
        for _name in _auto_blob.get(_key) or []:
            if isinstance(_name, str) and _name:
                auto_apply_artifacts.append(
                    {
                        "label": _label,
                        "name": _name,
                        "url": f"/api/v1/applications/{application.id}/auto-apply-artifacts/{_name}",
                    }
                )

    # Item 11 — calendar events fuzzy-matched to this application.
    from services import calendar_sync

    calendar_events = [
        {
            "title": e.title or "(untitled event)",
            "when_label": calendar_sync.format_event_when(e),
            "location": e.location,
        }
        for e in await calendar_sync.events_for_application(
            session, user_id=application.user_id, application_id=application.id
        )
    ]

    return {
        "application": {
            "id": application.id,
            "job_id": application.job_id,
            "company": application.company,
            "company_initial": initial,
            "company_color": color,
            "role": application.role,
            "team": application.team,
            "location": application.location,
            "salary_range": _salary_range(application),
            "status": application.status.value,
            "status_label": application.status.value.replace("_", " "),
            "board": application.board.value if application.board else None,
            "external_url": application.external_url,
            "notes": application.notes or "",
            "applied_at": application.applied_at,
            "applied_at_label": _relative_label(application.applied_at),
            "board_application_id": board_application_id,
            "score": score,
        },
        "status_timeline": status_timeline,
        "documents": docs,
        "screener_answers": screener_rows,
        "contacts": contact_rows,
        "last_failure": last_failure,
        "postmortem_ts": postmortem_ts,
        "auto_apply": auto_apply,
        "job_url": job_url,
        # Plan 86 / 0.4.5.08
        "bullets_used": bullets_used_rows,
        # Item 7 (2026-07)
        "auto_apply_artifacts": auto_apply_artifacts,
        # Item 11 (2026-07)
        "calendar_events": calendar_events,
    }


# ── Jobs library (Tracking · single lifecycle surface) ──────────────────

LIBRARY_FACETS: list[tuple[str, str]] = [
    ("all", "All"),
    ("unswiped", "New"),
    ("saved", "Saved"),
    ("queued_for_auto_apply", "Auto-apply queue"),
    ("ready_to_submit", "Ready for you"),
    ("applied", "Applied"),
    ("skipped", "Skipped"),
]


def _job_library_row(job, application, phase) -> dict[str, object]:
    initial, color = _initial_color(job.company)
    return {
        "id": job.id,
        "company": job.company,
        "company_initial": initial,
        "company_color": color,
        "role": job.role,
        "location": getattr(job, "location", None),
        "score": int(round(float(getattr(job, "score", 0.0) or 0.0) * 100)),
        "board_label": (job.board.value if getattr(job, "board", None) else "manual"),
        "source_label": (job.source.value if getattr(job, "source", None) else "manual"),
        "state": job.queue_state.value,
        "state_label": job.queue_state.value.replace("_", " "),
        "phase": phase,
        "found_label": _relative_label(getattr(job, "found_at", None)),
        "url": getattr(job, "url", None),
        "application_id": application.id if application else None,
        "application_status": (application.status.value if application else None),
    }


async def build_library_ctx(
    session: AsyncSession,
    *,
    user_id: int,
    state: str = "all",
    q: str = "",
    score_min: float = 0.0,
) -> dict[str, object]:
    """Tracking · Jobs library — every Job the system knows, faceted by
    queue state, searchable, with the auto-apply phase + linked application
    attached per row."""
    from models import JobFilter
    from models.enums import JobQueueState
    from services import job_service

    facet_counts: dict[str, int] = {}
    total = 0
    for value, _label in LIBRARY_FACETS:
        if value == "all":
            continue
        try:
            qs = JobQueueState(value)
        except ValueError:
            continue
        n = await job_service.count_jobs_in_queue_state(session, user_id=user_id, state=qs)
        facet_counts[value] = int(n or 0)
        total += int(n or 0)
    facet_counts["all"] = total

    filters = JobFilter()
    if state != "all":
        try:
            filters = filters.model_copy(update={"queue_state": JobQueueState(state)})
        except ValueError:
            state = "all"
    if q:
        filters = filters.model_copy(update={"q": q})
    if score_min > 0.0:
        filters = filters.model_copy(update={"score_min": score_min})

    jobs = await job_service.list_jobs(
        session, user_id=user_id, filters=filters, page=0, page_size=200
    )

    apps = await application_service.list_applications(session, user_id=user_id)
    apps_by_job: dict[int, Application] = {}
    for a in apps:
        if a.job_id is not None:
            apps_by_job.setdefault(a.job_id, a)

    rows = []
    for j in jobs:
        app = apps_by_job.get(j.id)
        phase = application_service.auto_apply_phase(app, j)
        rows.append(_job_library_row(j, app, phase))

    return {
        "library_rows": rows,
        "library_facets": [
            {"value": v, "label": label, "count": facet_counts.get(v, 0)}
            for v, label in LIBRARY_FACETS
        ],
        "library_state": state,
        "library_q": q,
        "library_score_min": score_min,
    }
