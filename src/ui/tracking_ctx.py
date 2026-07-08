"""Project Application rows into tracking_card / tracking_list_row dicts."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlmodel.ext.asyncio.session import AsyncSession

from models import Application
from models.enums import (
    AppEventKind,
    ApplicationStatus,
    RecruiterState,
    ReferralState,
    application_status_label,
)
from services import applications
from services import email as email_service
from services import outreach as contact_tracker

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


def application_to_card(
    a: Application,
    *,
    round_chip: str | None = None,
    quiet_chip: str | None = None,
    suggestion_chip: str | None = None,
) -> dict[str, object]:
    initial, color = _initial_color(a.company)
    chip, tone = _context_chip(a)
    pin = applications.get_status_pin(a)
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
        "status_label": application_status_label(a.status).lower(),
        "context_chip": chip,
        "context_chip_tone": tone,
        # Plan 95 § 3.8.6 — visible pin state ("auto-tracking paused").
        "pin_chip": "auto-paused" if pin else None,
        # Plan 95 § 3.1 — compact `2/5 · system design` chip when rounds exist.
        "round_chip": round_chip,
        # Plan 95 § 3.2 — amber "no signal for N d" chip on quiet cards.
        "quiet_chip": quiet_chip,
        # Plan 96a / B2 — pending email suggestion, visible from the board.
        "suggestion_chip": suggestion_chip,
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
        "status_label": application_status_label(a.status),
        "score": None,
        "salary_range": _salary_range(a),
        "last_activity": _relative_label(a.updated_at),
        "source": (a.board.value if a.board else "manual"),
    }


def _columns_for_board(
    apps: list[Application],
    *,
    show_closed: bool,
    round_chips: dict[int, str] | None = None,
    quiet_chips: dict[int, str] | None = None,
    suggestion_chips: dict[int, str] | None = None,
) -> list[dict[str, object]]:
    visible = [
        ApplicationStatus.APPLIED,
        ApplicationStatus.RECRUITER_SCREEN,
        ApplicationStatus.ONSITE_LOOP,
        ApplicationStatus.OFFER,
    ]
    if show_closed:
        visible.append(ApplicationStatus.CLOSED)
    chips = round_chips or {}
    q_chips = quiet_chips or {}
    s_chips = suggestion_chips or {}
    out = []
    for status in visible:
        cards = [
            application_to_card(
                a,
                round_chip=chips.get(a.id or 0),
                quiet_chip=q_chips.get(a.id or 0),
                suggestion_chip=s_chips.get(a.id or 0),
            )
            for a in apps
            if a.status == status
        ]
        out.append({"status": status.value, "cards": cards})
    return out


async def _round_chips_for(session: AsyncSession, apps: list[Application]) -> dict[int, str]:
    """Batch `2/5 · system design` chips for the board (plan 95 § 3.1)."""
    ids = [a.id for a in apps if a.id is not None]
    if not ids:
        return {}
    from sqlmodel import select

    from models import InterviewRound

    rows = (
        await session.exec(
            select(InterviewRound)
            .where(InterviewRound.application_id.in_(ids))  # type: ignore[union-attr]
            .order_by(InterviewRound.round_no.asc(), InterviewRound.id.asc())
        )
    ).all()
    grouped: dict[int, list] = {}
    for r in rows:
        grouped.setdefault(r.application_id, []).append(r)
    out: dict[int, str] = {}
    for app_id, rounds in grouped.items():
        chip = applications.round_chip(rounds)
        if chip:
            out[app_id] = chip
    return out


_ROUND_STATE_ICONS = {
    "completed": "check-circle-2",
    "scheduled": "calendar-clock",
    "planned": "circle-dashed",
    "cancelled": "x-circle",
}


def round_to_row(r) -> dict[str, object]:
    scheduled_label = None
    if r.scheduled_at is not None:
        when = _aware(r.scheduled_at)
        scheduled_label = when.strftime("%b %d") + (
            when.strftime(" · %H:%M") if (when.hour or when.minute) else ""
        )
    sessions = [
        str(s.get("title", "")).strip()
        for s in (r.sessions or [])
        if isinstance(s, dict) and str(s.get("title", "")).strip()
    ]
    return {
        "id": r.id,
        "round_no": r.round_no,
        "kind": r.kind,
        "kind_label": r.kind.replace("_", " "),
        "title": r.title,
        "state": r.state,
        "state_icon": _ROUND_STATE_ICONS.get(r.state, "circle-dashed"),
        "outcome": r.outcome,
        "scheduled_label": scheduled_label,
        "source": r.source,
        "sessions": sessions,
    }


_CLASSIFICATION_TONES = {
    "interview_request": "indigo",
    "assessment": "cyan",
    "offer": "emerald",
    "rejection": "rose",
    "follow_up": "slate",
    "other": "slate",
}


async def build_conversation_ctx(
    session: AsyncSession, application: Application
) -> list[dict[str, object]]:
    """Threads + messages linked to this application — the § 3.9 evidence
    surface ("why is this at Interview Stage?"). Snippet-only by design;
    rows deep-link to the provider for the full text."""
    from sqlmodel import select

    from models import EmailMessage

    threads = await email_service.list_threads_for_application(session, application.id or 0)
    messages = (
        await session.exec(
            select(EmailMessage)
            .where(EmailMessage.application_id == application.id)
            .order_by(EmailMessage.received_at.desc())
        )
    ).all()
    by_thread: dict[int, list] = {}
    for m in messages:
        by_thread.setdefault(m.thread_id, []).append(m)

    out: list[dict[str, object]] = []
    for t in threads:
        msgs = by_thread.get(t.id or 0, [])
        rows = []
        for m in msgs:
            suggestion = None
            if m.suggested_status is not None:
                suggestion = {
                    "status_label": application_status_label(m.suggested_status),
                    "applied": m.suggestion_applied_at is not None,
                    "dismissed": m.suggestion_dismissed_at is not None,
                    "pending": (
                        m.suggestion_applied_at is None and m.suggestion_dismissed_at is None
                    ),
                }
            rows.append(
                {
                    "id": m.id,
                    "sender": m.sender_name or m.sender_email,
                    "sender_email": m.sender_email,
                    "subject": m.subject,
                    "snippet": m.snippet,
                    # Plan 95 § 3.9.1 — stored excerpt (opt-in) renders
                    # instantly; a UID enables the live full-body fetch.
                    "body_excerpt": m.body_excerpt,
                    "can_fetch_body": bool(m.imap_uid and m.account_id),
                    "received_label": _relative_label(m.received_at),
                    "classification": m.classification.value if m.classification else None,
                    "classification_tone": _CLASSIFICATION_TONES.get(
                        m.classification.value if m.classification else "", "slate"
                    ),
                    "suggestion": suggestion,
                    # Gmail rfc822msgid search — the deep link out for full text.
                    "provider_link": (
                        "https://mail.google.com/mail/u/0/#search/rfc822msgid:"
                        + (m.message_id_external or "").strip("<>")
                        if m.message_id_external
                        else None
                    ),
                }
            )
        classification = t.classification.value if t.classification else None
        out.append(
            {
                "id": t.id,
                "subject": t.subject or "(no subject)",
                "classification": classification,
                "classification_tone": _CLASSIFICATION_TONES.get(classification or "", "slate"),
                "latest_label": _relative_label(t.latest_message_at),
                "message_count": len(msgs) or (t.message_count or 0),
                "messages": rows,
            }
        )
    return out


async def build_rounds_ctx(session: AsyncSession, application: Application) -> dict[str, object]:
    """Ctx for `_rounds_section.html` — shared by the slide-over include and
    the parse/save/state fragment routes."""
    rounds = await applications.list_rounds(session, application_id=application.id or 0)
    return {
        "application": {"id": application.id, "company": application.company},
        "rounds": [round_to_row(r) for r in rounds],
    }


async def build_tracking_ctx(
    session: AsyncSession,
    *,
    user_id: int,
    view: str = "board",
    show_closed: bool = False,
    show_drafts: bool = False,
) -> dict[str, object]:
    from services.email import inference, processes

    visible_apps = await applications.list_visible_in_tracking(session, user_id)
    # Item 5 — unconfirmed inferred applications stay off the board; they
    # live in the confirmation banner until the user confirms/dismisses.
    inferred_pending = [a for a in visible_apps if inference.is_unconfirmed_inferred(a)]
    visible_apps = [a for a in visible_apps if not inference.is_unconfirmed_inferred(a)]
    if show_drafts:
        visible_apps = visible_apps + await applications.list_drafts(session, user_id)
    closed = await applications.list_closed(session, user_id)
    all_apps = visible_apps + closed if show_closed else visible_apps
    round_chips = await _round_chips_for(session, all_apps)

    # Plan 95 § 3.2 — silence as a signal. Threshold from Settings (flat
    # for every stage); flagging is computed live, closes only on click.
    from sqlmodel import select as _select

    from models import Settings as _Settings

    settings_row = (
        await session.exec(_select(_Settings).where(_Settings.user_id == user_id))
    ).one_or_none()
    stale_days = int(getattr(settings_row, "staleness_stale_days", 30) or 30)
    going_quiet = await applications.list_going_quiet(
        session, user_id=user_id, stale_days=stale_days
    )
    quiet_chips = {
        q.application.id: f"no signal {q.days_quiet}d"
        for q in going_quiet
        if q.application.id is not None
    }

    # Plan 96a / B2 — pending email suggestions, visible from the OUTSIDE:
    # an amber chip on the card + the strip at the top of the page. The
    # Apply/Dismiss affordances used to exist only inside the slide-over
    # conversation, so pending rejections sat invisible for days.
    pending = await email_service.list_pending_suggestions(session, user_id=user_id)
    suggestion_chips: dict[int, str] = {}
    for s in pending:
        label = (
            "rejection?"
            if s.suggested_status == ApplicationStatus.CLOSED
            else f"→ {application_status_label(s.suggested_status)}?"
        )
        suggestion_chips.setdefault(s.application_id, label)

    columns = _columns_for_board(
        all_apps,
        show_closed=show_closed,
        round_chips=round_chips,
        quiet_chips=quiet_chips,
        suggestion_chips=suggestion_chips,
    )

    followup = await applications.list_in_followup(session, user_id)
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
    from services.email import calendar_sync

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

    # 2026-07 tracking redesign — interview processes detected in the inbox
    # that map to no tracked application (applied outside Naavik).
    detected = await processes.list_detected_processes(session, user_id=user_id)
    # Plan 95 § 3.3 — agency/platform mail with no named end-client: parked,
    # collapsed, silent.
    parked = await processes.list_parked_sender_groups(session, user_id=user_id)

    # Plan 95 § 3.4 "Merge into…" targets: live application companies plus
    # the OTHER detected groups (template filters out the row's own company).
    merge_targets = sorted(
        {a.company for a in visible_apps if a.company} | {p.company for p in detected if p.company}
    )
    # Plan 96a / B4 — CLOSED is representable: a group whose timeline derives
    # CLOSED must not silently render as "Applied" (the browser picks the
    # first option when none matches).
    track_stage_options = [
        {"value": s.value, "label": application_status_label(s)}
        for s in (
            ApplicationStatus.APPLIED,
            ApplicationStatus.RECRUITER_SCREEN,
            ApplicationStatus.ONSITE_LOOP,
            ApplicationStatus.OFFER,
            ApplicationStatus.CLOSED,
        )
    ]

    return {
        "detected_processes": [
            {
                "company": p.company,
                "role": p.role,
                "status": p.status.value,
                "status_label": application_status_label(p.status),
                "message_count": p.message_count,
                "last_seen_label": _relative_label(p.last_seen),
                "latest_subject": p.latest_subject,
                "possible_rejection_message_id": p.possible_rejection_message_id,
                "sender_domain": p.sender_domain,
                "dom_id": "detected-process-"
                + (re.sub(r"[^a-z0-9]+", "-", p.company.lower()).strip("-") or "unknown"),
            }
            for p in detected
        ],
        "parked_sender_groups": [
            {
                "sender_domain": g.sender_domain,
                "company": g.company,
                "message_count": g.message_count,
                "last_seen_label": _relative_label(g.last_seen),
                "latest_subject": g.latest_subject,
                "latest_message_id": g.latest_message_id,
                "dom_id": "parked-sender-"
                + (re.sub(r"[^a-z0-9]+", "-", g.sender_domain.lower()).strip("-") or "unknown"),
            }
            for g in parked
        ],
        "process_merge_targets": merge_targets,
        "track_stage_options": track_stage_options,
        # Plan 96a / B2 — one row per pending suggestion on the strip.
        "pending_suggestions": [
            {
                "application_id": s.application_id,
                "message_id": s.message_id,
                "company": s.company,
                "role": s.role,
                "current_label": application_status_label(s.current_status),
                "suggested_label": application_status_label(s.suggested_status),
                "is_rejection": s.suggested_status == ApplicationStatus.CLOSED,
                "subject": s.subject,
                "suggested_at_label": _relative_label(s.suggested_at),
                "pinned": s.pinned,
                "dom_id": f"pending-suggestion-{s.message_id}",
            }
            for s in pending
        ],
        "going_quiet": [
            {
                "id": q.application.id,
                "company": q.application.company,
                "role": q.application.role,
                "status_label": application_status_label(q.application.status),
                "days_quiet": q.days_quiet,
                "dom_id": f"going-quiet-{q.application.id}",
            }
            for q in going_quiet
        ],
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
    events = await applications.list_events_for(session, application.id)
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

    documents = await applications.list_documents_for(session, application.id)
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
        for s in await applications.list_screener_answers_for(session, application.id)
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
            from services import jobs as job_service

            job = await job_service.get_job(session, application.job_id)
            if job is not None and getattr(job, "score", None) is not None:
                # Job.score is 0–1; the chip renders 0–100.
                raw = float(job.score)
                score = int(round(raw * 100)) if raw <= 1.0 else int(round(raw))
            if job is not None:
                auto_apply = applications.auto_apply_phase(application, job)
                # Manual-submit link: the RESOLVED apply site beats the
                # aggregator listing the scraper found the job on.
                job_url = getattr(job, "apply_url", None) or getattr(job, "url", None)
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

    # Plan 95 § 3.8 — visible status pin ("auto-tracking paused for X").
    pin = applications.get_status_pin(application)
    status_pin = None
    if pin is not None:
        try:
            rejected = ApplicationStatus(pin.get("rejected"))
            status_pin = {"rejected_label": application_status_label(rejected)}
        except (ValueError, TypeError):
            status_pin = None

    # Plan 95 § 3.1 — interview rounds checklist for the slide-over.
    rounds_ctx = await build_rounds_ctx(session, application)

    # Plan 95 § 3.9 — the conversation that produced the status.
    conversation_threads = await build_conversation_ctx(session, application)

    # Item 11 — calendar events fuzzy-matched to this application.
    from services.email import calendar_sync

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
            "status_label": application_status_label(application.status),
            "board": application.board.value if application.board else None,
            "external_url": application.external_url,
            "notes": application.notes or "",
            "applied_at": application.applied_at,
            "applied_at_label": _relative_label(application.applied_at),
            "board_application_id": board_application_id,
            "score": score,
        },
        "status_timeline": status_timeline,
        # Plan 95 § 3.1
        "rounds": rounds_ctx["rounds"],
        # Plan 95 § 3.8
        "status_pin": status_pin,
        # Plan 95 § 3.9
        "conversation_threads": conversation_threads,
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


def _http_url(url: str | None) -> str | None:
    """Only real links are clickable — email-inferred jobs carry manual:// stubs."""
    if isinstance(url, str) and url.startswith(("http://", "https://")):
        return url
    return None


def _job_library_row(job, application, phase) -> dict[str, object]:
    initial, color = _initial_color(job.company)
    source_url = _http_url(getattr(job, "url", None))
    board_url = _http_url(getattr(job, "apply_url", None))
    return {
        "id": job.id,
        "company": job.company,
        "company_initial": initial,
        "company_color": color,
        "role": job.role,
        "location": getattr(job, "location", None),
        "score": int(round(float(getattr(job, "score", 0.0) or 0.0) * 100)),
        "board_label": (job.board.value if getattr(job, "board", None) else "manual"),
        # Where you actually apply: resolved apply target, else the posting.
        "board_url": board_url or source_url,
        "source_label": (job.source.value if getattr(job, "source", None) else "manual"),
        # Where the job was found: the original posting the scraper saw.
        "source_url": source_url,
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
    from services import jobs as job_service

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

    apps = await applications.list_applications(session, user_id=user_id)
    apps_by_job: dict[int, Application] = {}
    for a in apps:
        if a.job_id is not None:
            apps_by_job.setdefault(a.job_id, a)

    rows = []
    for j in jobs:
        app = apps_by_job.get(j.id)
        phase = applications.auto_apply_phase(app, j)
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
