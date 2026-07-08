"""Interview rounds within a stage — plan 95 § 3.1 (slice 95d).

Three producers, one consumer:

1. **Email** — the classifier's `round_kind` upserts a round on the linked
   application (upsert key: application + kind + scheduled-date, so two
   different Camber rounds become two rows and three reminders about one
   round stay one row).
2. **Recruiter notes** — the explicit "Parse interview plan" action projects
   the owner's notes into `state=planned` rows; emails/calendar then check
   them off (planned → scheduled → completed).
3. **Calendar** — a matched event whose title looks like a round upserts
   `state=scheduled` with the event link.

Stage derivation stays downstream: a completed/scheduled round of an
onsite-evidence kind implies ONSITE_LOOP via the same `update_status` path
as email transitions — a round never IS a stage, it EVIDENCES one.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime, timedelta

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import Application, InterviewRound
from models.enums import ApplicationStatus, StatusChangeTrigger
from models.interview_round import (
    ONSITE_EVIDENCE_KINDS,
    ROUND_KINDS,
    ROUND_STATES,
)

log = logging.getLogger(__name__)

_STATE_RANK = {"planned": 0, "scheduled": 1, "completed": 2, "cancelled": 0}

# Calendar-title → round-kind heuristics, first match wins (§ 3.1 producer 3).
_TITLE_KIND_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"system design", "system_design"),
    (r"take.?home", "take_home"),
    (r"hiring manager|hm chat|hm interview", "hiring_manager"),
    (r"builder", "builder_interview"),
    (r"team match|team fit", "team_match"),
    (r"panel", "panel"),
    (r"onsite|on-site|final round|virtual loop", "onsite_loop"),
    (r"recruiter (?:screen|call|chat)|phone screen|intro call", "recruiter_screen"),
    (r"technical (?:screen|interview|round)|coding|live code", "technical_screen"),
    (r"interview|screen", "other"),
)


class RoundError(Exception):
    """Ownership / validation failure — routes map this to 404/422."""


def round_kind_from_title(title: str | None) -> str | None:
    """None = the title doesn't look like an interview round at all."""
    text = (title or "").lower()
    for pattern, kind in _TITLE_KIND_PATTERNS:
        if re.search(pattern, text):
            return kind
    return None


async def list_rounds(session: AsyncSession, *, application_id: int) -> list[InterviewRound]:
    rows = (
        await session.exec(
            select(InterviewRound)
            .where(InterviewRound.application_id == application_id)
            .order_by(InterviewRound.round_no.asc(), InterviewRound.id.asc())
        )
    ).all()
    return list(rows)


def _find_matching_round(
    rounds: list[InterviewRound],
    *,
    kind: str,
    scheduled_date: date | None,
    invite_uid: str | None = None,
) -> InterviewRound | None:
    """Upsert key: application + kind + scheduled-date (§ 3.1); plan 96d adds
    `invite_uid` as a stronger evidence key on the same seam.

    A round already riding the invite's calendar event is THE match
    regardless of date (the invite is scheduling ground truth). Otherwise a
    dateless signal (reminder emails) reuses any open round of the kind; a
    dated signal matches the same date first, then fills the date into an
    open dateless round. Rounds riding a DIFFERENT calendar event are never
    adopted. Only when every same-kind round is completed does a new one get
    created (a genuine second round of that kind).
    """
    if invite_uid is not None:
        for r in rounds:
            if r.invite_uid == invite_uid and r.kind == kind and r.state != "cancelled":
                return r
        # Never steal a round riding a DIFFERENT calendar event; several
        # rounds legitimately share ONE event (owner 2026-07-08), so a
        # same-uid different-kind upsert creates a sibling rider instead.
        candidates = [
            r for r in rounds if r.kind == kind and r.state != "cancelled" and r.invite_uid is None
        ]
    else:
        candidates = [r for r in rounds if r.kind == kind and r.state != "cancelled"]
    if scheduled_date is not None:
        for r in candidates:
            if r.scheduled_at is not None and r.scheduled_at.date() == scheduled_date:
                return r
        for r in candidates:
            if r.scheduled_at is None and r.state != "completed":
                return r
        return None
    for r in candidates:
        if r.state != "completed":
            return r
    return None


def _merge_sessions(existing: list, incoming: list) -> list:
    """Clubbed-loop sessions merge by title — a later email adding segments
    upserts into `sessions`, never creates sibling rounds (§ 3.1)."""
    merged = [dict(s) for s in existing if isinstance(s, dict)]
    titles = {str(s.get("title", "")).lower() for s in merged}
    for s in incoming or []:
        if not isinstance(s, dict):
            continue
        title = str(s.get("title", "")).strip()
        if title and title.lower() not in titles:
            merged.append(dict(s))
            titles.add(title.lower())
    return merged


async def upsert_round(
    session: AsyncSession,
    *,
    application: Application,
    kind: str,
    source: str,
    title: str | None = None,
    state: str = "scheduled",
    scheduled_at: datetime | None = None,
    sessions: list | None = None,
    email_message_id: int | None = None,
    calendar_event_id: int | None = None,
    invite_uid: str | None = None,
) -> InterviewRound:
    """Idempotent producer entry — reminders never duplicate rounds."""
    if kind not in ROUND_KINDS:
        kind, title = "other", title or kind
    rounds = await list_rounds(session, application_id=application.id or 0)
    scheduled_date = scheduled_at.date() if scheduled_at is not None else None
    row = _find_matching_round(
        rounds, kind=kind, scheduled_date=scheduled_date, invite_uid=invite_uid
    )
    now = datetime.now(UTC)

    if row is None:
        row = InterviewRound(
            user_id=application.user_id,
            application_id=application.id or 0,
            round_no=max((r.round_no for r in rounds), default=0) + 1,
            kind=kind,
            title=title,
            state=state,
            scheduled_at=scheduled_at,
            sessions=list(sessions or []),
            source=source,
            email_message_id=email_message_id,
            calendar_event_id=calendar_event_id,
            invite_uid=invite_uid,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.flush()
        log.info("round created app=%s kind=%s source=%s", application.id, kind, source)
        return row

    # Update-in-place: state only ratchets forward (a reminder about a
    # completed round must not re-open it), evidence links fill if empty,
    # sessions merge, a date fills a dateless row.
    if _STATE_RANK.get(state, 0) > _STATE_RANK.get(row.state, 0):
        row.state = state
    if scheduled_at is not None and row.scheduled_at is None:
        row.scheduled_at = scheduled_at
    if title and not row.title:
        row.title = title
    if sessions:
        row.sessions = _merge_sessions(row.sessions or [], sessions)
    if email_message_id is not None and row.email_message_id is None:
        row.email_message_id = email_message_id
    if calendar_event_id is not None and row.calendar_event_id is None:
        row.calendar_event_id = calendar_event_id
    if invite_uid is not None and row.invite_uid is None:
        row.invite_uid = invite_uid
    row.updated_at = now
    session.add(row)
    await session.flush()
    return row


async def resequence_rounds(session: AsyncSession, *, application_id: int) -> None:
    """Renumber `round_no` chronologically (plan 96d, owner 2026-07-08):
    "round 1" must be the interview that happened first, not the row created
    first. Dated rounds order by time; dateless rounds keep their relative
    order after every dated one."""
    rounds = await list_rounds(session, application_id=application_id)
    now = datetime.now(UTC)

    def _key(r: InterviewRound):
        return (r.scheduled_at is None, r.scheduled_at or datetime.max, r.round_no, r.id or 0)

    for position, r in enumerate(sorted(rounds, key=_key), start=1):
        if r.round_no != position:
            r.round_no = position
            r.updated_at = now
            session.add(r)
    await session.flush()


async def complete_past_due_rounds(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Plan 96d time-passage rider (rides `tracking.sync_calendars`) —
    completion-by-time is the one evidence class with no email trigger.

    A `scheduled` round whose evidenced end has passed (+1h overrun grace)
    completes with `outcome=pending`. End evidence, strongest first: the
    final invite of the round's chain (`ends_at`), the matched calendar
    event's `ends_at`, else `scheduled_at` + 1h default duration. Completed
    rounds feed the same forward-only stage derivation as every producer.
    """
    from models import CalendarEvent, EmailInvite
    from services.email.invites import group_chains, resolve_final

    now = now or datetime.now(UTC)
    grace = timedelta(hours=1)
    default_duration = timedelta(hours=1)

    rows = (
        await session.exec(
            select(InterviewRound).where(
                InterviewRound.state == "scheduled",
                InterviewRound.scheduled_at.is_not(None),  # type: ignore[union-attr]
                InterviewRound.scheduled_at <= now,  # type: ignore[operator]
            )
        )
    ).all()
    if not rows:
        return 0

    invite_uids = {r.invite_uid for r in rows if r.invite_uid}
    finals: dict[str, EmailInvite] = {}
    if invite_uids:
        invites = (
            await session.exec(
                select(EmailInvite).where(EmailInvite.ics_uid.in_(invite_uids))  # type: ignore[union-attr]
            )
        ).all()
        for (uid, _rid), chain in group_chains(list(invites)).items():
            final = resolve_final(chain)
            if final is not None:
                finals[uid] = final

    def _aware(dt: datetime | None) -> datetime | None:
        # sqlite round-trips drop tzinfo; stored values are UTC by contract.
        if dt is not None and dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt

    completed = 0
    touched_apps: set[int] = set()
    for r in rows:
        end: datetime | None = None
        if r.invite_uid and r.invite_uid in finals:
            end = _aware(finals[r.invite_uid].ends_at)
        if end is None and r.calendar_event_id is not None:
            event = await session.get(CalendarEvent, r.calendar_event_id)
            if event is not None:
                end = _aware(event.ends_at)
        if end is None and r.scheduled_at is not None:
            end = _aware(r.scheduled_at) + default_duration
        if end is None or now < end + grace:
            continue
        r.state = "completed"
        r.outcome = r.outcome or "pending"
        r.updated_at = now
        session.add(r)
        completed += 1
        touched_apps.add(r.application_id)

    if completed:
        await session.flush()
    for app_id in touched_apps:
        application = await session.get(Application, app_id)
        if application is None:
            continue
        try:
            await derive_stage_from_rounds(session, application=application)
        except Exception as exc:  # noqa: BLE001 — derivation must not sink the cron
            log.warning("past-due stage derivation failed for app %s: %s", app_id, exc)
    return completed


async def create_planned_rounds(
    session: AsyncSession,
    *,
    application: Application,
    parsed_rounds: list[dict],
) -> list[InterviewRound]:
    """Notes → plan projection (producer 2). Upserts so re-parsing after an
    email already created a round checks it off instead of duplicating."""
    out: list[InterviewRound] = []
    for item in parsed_rounds:
        kind = str(item.get("kind", "other")).strip().lower()
        title = (str(item.get("title") or "").strip() or None) if item else None
        sessions = [
            {"title": str(t).strip()} for t in (item.get("sessions") or []) if str(t).strip()
        ]
        row = await upsert_round(
            session,
            application=application,
            kind=kind,
            source="notes",
            title=title,
            state="planned",
            sessions=sessions,
        )
        out.append(row)
    return out


async def set_round_state(
    session: AsyncSession,
    *,
    user_id: int,
    round_id: int,
    state: str,
    outcome: str | None = None,
) -> InterviewRound:
    if state not in ROUND_STATES:
        raise RoundError("Unknown round state")
    row = await session.get(InterviewRound, round_id)
    if row is None or row.user_id != user_id:
        raise RoundError("No such round")
    row.state = state
    if state == "completed":
        row.outcome = outcome or "pending"
    row.updated_at = datetime.now(UTC)
    session.add(row)
    await session.flush()

    application = await session.get(Application, row.application_id)
    if application is not None and state == "completed":
        await derive_stage_from_rounds(
            session, application=application, trigger=StatusChangeTrigger.MANUAL
        )
    return row


async def derive_stage_from_rounds(
    session: AsyncSession,
    *,
    application: Application,
    trigger: StatusChangeTrigger = StatusChangeTrigger.AUTO_FROM_EMAIL,
) -> None:
    """Rounds feed the SAME forward-only status path as email transitions.

    A completed round of an onsite-evidence kind implies ONSITE_LOOP; a
    completed recruiter screen implies RECRUITER_SCREEN. Forward-only and
    idempotent — `update_status` refuses backward moves and same-status
    writes are skipped here.
    """
    from services import applications as applications_service

    rounds = await list_rounds(session, application_id=application.id or 0)
    target: ApplicationStatus | None = None
    for r in rounds:
        if r.state != "completed":
            continue
        if r.kind in ONSITE_EVIDENCE_KINDS:
            target = ApplicationStatus.ONSITE_LOOP
            break
        if r.kind == "recruiter_screen":
            target = ApplicationStatus.RECRUITER_SCREEN
    if target is None:
        return
    rank = {
        ApplicationStatus.DRAFT: 0,
        ApplicationStatus.APPLIED: 1,
        ApplicationStatus.RECRUITER_SCREEN: 2,
        ApplicationStatus.ONSITE_LOOP: 3,
        ApplicationStatus.OFFER: 4,
    }
    if application.status not in rank or rank[target] <= rank[application.status]:
        return
    try:
        await applications_service.update_status(
            session,
            application.id,
            target,
            notes="Derived from completed interview rounds",
            trigger=trigger,
        )
    except applications_service.ApplicationServiceError as exc:
        log.info("round stage derivation skipped for app %s: %s", application.id, exc)


def round_chip(rounds: list[InterviewRound]) -> str | None:
    """Board-card chip: `2/5 · system design` — done/total and the next
    open round. None when no live rounds exist."""
    live = [r for r in rounds if r.state != "cancelled"]
    if not live:
        return None
    done = sum(1 for r in live if r.state == "completed")
    current = next((r for r in live if r.state != "completed"), None)
    label = f"{done}/{len(live)}"
    if current is not None:
        name = (current.title or current.kind.replace("_", " ")).strip()
        label += f" · {name[:28]}"
    return label
