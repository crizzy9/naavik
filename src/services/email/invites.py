"""Calendar-invite ground truth — plan 96 slice 96d.

Parses `text/calendar` MIME parts + `.ics` attachments out of the RFC822 the
sync loop already fetched (no extra IMAP round-trips) via the `icalendar`
library, persists them as `EmailInvite` rows (the supersedence LEDGER), and
derives the schedule truth from them:

- **Supersedence is derived, not stored** (`resolve_final`): the final invite
  for an (ics_uid, recurrence_id) chain is the max-sequence non-cancelled
  REQUEST; a CANCEL at ≥ that sequence kills the chain. Pure function.
- **Invites are the scheduling axis, not the interview axis** (owner decision
  2026-07-08): one calendar event may carry several interviews (Chime's
  5-segment onsite rode ONE invite). Rounds ride their container via
  `InterviewRound.invite_uid` (non-unique); a chain reschedule SHIFTS every
  riding round by the container delta, a cancellation without replacement
  reverts riders to `planned`. 96d guarantees one round per live container
  deterministically; 96e's thread-level pass itemizes the interviews inside.
- Parse failures degrade to a log line — sync never fails on a malformed
  invite.

The one-shot `backfill_invites` recovers ground truth for already-stored
mail: PEEK by stored `imap_uid`, resolving the UID via an IMAP Message-ID
header search for pre-95l rows that lack one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from email.message import Message
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import Application, EmailAccount, EmailInvite, EmailMessage
from models.email_invite import INVITE_METHODS
from models.enums import EmailClassification

log = logging.getLogger(__name__)

# One calendar event usually means one interview block; bound the attendee
# list so a company-wide invite can't balloon the JSONB column.
_MAX_ATTENDEES = 30
_MAX_TEXT = 512

_CALENDAR_CONTENT_TYPES = ("text/calendar", "application/ics")


def _aware_utc(dt: datetime | None) -> datetime | None:
    """Stored datetimes are UTC by contract; sqlite round-trips drop tzinfo."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class InviteLike(Protocol):
    """Structural type shared by `ParsedInvite` and `EmailInvite` — the
    supersedence functions work on either."""

    ics_uid: str
    recurrence_id: str
    sequence: int
    method: str
    status: str


@dataclass(slots=True)
class ParsedInvite:
    ics_uid: str
    recurrence_id: str = ""
    sequence: int = 0
    method: str = "request"
    status: str = "confirmed"
    summary: str | None = None
    location: str | None = None
    organizer_email: str | None = None
    attendee_emails: list[str] = field(default_factory=list)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    tz: str | None = None


# ── MIME → ParsedInvite ─────────────────────────────────────────────────


def has_calendar_part(mime: Message) -> bool:
    """Cheap pre-check so sync only flushes/parses messages that carry ICS."""
    for part in mime.walk():
        if part.get_content_type() in _CALENDAR_CONTENT_TYPES:
            return True
        filename = (part.get_filename() or "").lower()
        if filename.endswith(".ics"):
            return True
    return False


def _clean_email(value: str | None) -> str | None:
    text = (value or "").strip()
    if text.lower().startswith("mailto:"):
        text = text[7:]
    return text[:254] or None


def _decode_dt(component: Any, prop: str) -> tuple[datetime | None, str | None]:
    """Return (aware-UTC datetime, original TZID) for a date/date-time prop.

    icalendar resolves TZID/VTIMEZONE to aware datetimes itself; the naive
    branch is a fallback for floating times (treated as UTC — same bounded
    distortion `calendar_sync` documents). All-day DATE values normalize to
    midnight UTC.
    """
    raw = component.get(prop)
    if raw is None:
        return None, None
    value = getattr(raw, "dt", None)
    if value is None:
        return None, None
    tz_name = None
    params = getattr(raw, "params", None) or {}
    tzid = params.get("TZID")
    if tzid:
        tz_name = str(tzid)[:64]
    if isinstance(value, datetime):
        if value.tzinfo is None:
            if tz_name:
                try:
                    value = value.replace(tzinfo=ZoneInfo(tz_name))
                except Exception:  # noqa: BLE001 — unknown TZID: floating → UTC
                    value = value.replace(tzinfo=UTC)
            else:
                value = value.replace(tzinfo=UTC)
        if tz_name is None:
            tz_name = str(value.tzinfo)[:64]
        return value.astimezone(UTC), tz_name
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC), tz_name
    return None, tz_name


def _parse_calendar_blob(blob: bytes, *, fallback_method: str | None) -> list[ParsedInvite]:
    from icalendar import Calendar

    cal = Calendar.from_ical(blob)
    method = (str(cal.get("METHOD", "")).strip().lower() or fallback_method or "publish")[:20]
    out: list[ParsedInvite] = []
    for ev in cal.walk("VEVENT"):
        uid = str(ev.get("UID", "")).strip()[:_MAX_TEXT]
        if not uid:
            continue
        if method not in INVITE_METHODS:
            log.debug("invite: skipping non-vocab METHOD %r uid=%s", method, uid)
            continue
        recurrence_raw = ev.get("RECURRENCE-ID")
        recurrence_id = ""
        if recurrence_raw is not None:
            try:
                recurrence_id = recurrence_raw.to_ical().decode("ascii", "replace")[:64]
            except Exception:  # noqa: BLE001
                recurrence_id = str(recurrence_raw)[:64]
        try:
            sequence = int(ev.get("SEQUENCE", 0))
        except (TypeError, ValueError):
            sequence = 0
        status = str(ev.get("STATUS", "")).strip().lower()
        if method == "cancel" or status == "cancelled":
            status = "cancelled"
        elif status == "tentative":
            status = "tentative"
        else:
            status = "confirmed"

        starts_at, tz_name = _decode_dt(ev, "DTSTART")
        ends_at, _ = _decode_dt(ev, "DTEND")
        attendees_raw = ev.get("ATTENDEE")
        if attendees_raw is None:
            attendees: list[str] = []
        elif isinstance(attendees_raw, list):
            attendees = [a for a in (_clean_email(str(x)) for x in attendees_raw) if a]
        else:
            single = _clean_email(str(attendees_raw))
            attendees = [single] if single else []

        out.append(
            ParsedInvite(
                ics_uid=uid,
                recurrence_id=recurrence_id,
                sequence=sequence,
                method=method,
                status=status,
                summary=str(ev.get("SUMMARY", "")).strip()[:_MAX_TEXT] or None,
                location=str(ev.get("LOCATION", "")).strip()[:_MAX_TEXT] or None,
                organizer_email=_clean_email(str(ev.get("ORGANIZER", ""))),
                attendee_emails=attendees[:_MAX_ATTENDEES],
                starts_at=starts_at,
                ends_at=ends_at,
                tz=tz_name,
            )
        )
    return out


def extract_invites(mime: Message) -> list[ParsedInvite]:
    """All VEVENTs across the message's calendar parts, deduped.

    Google delivers the same VEVENT twice (inline `text/calendar` + an
    `invite.ics` attachment) — dedup on the chain key. A malformed part
    degrades to a log line; other parts still parse.
    """
    seen: set[tuple[str, str, int, str]] = set()
    out: list[ParsedInvite] = []
    for part in mime.walk():
        content_type = part.get_content_type()
        filename = (part.get_filename() or "").lower()
        if content_type not in _CALENDAR_CONTENT_TYPES and not filename.endswith(".ics"):
            continue
        payload = part.get_payload(decode=True)
        if not isinstance(payload, bytes) or not payload.strip():
            continue
        fallback_method = part.get_param("method")
        try:
            parsed = _parse_calendar_blob(
                payload,
                fallback_method=str(fallback_method).lower() if fallback_method else None,
            )
        except Exception as exc:  # noqa: BLE001 — malformed ICS must not sink sync
            log.warning("invite parse failed (part=%s): %s", content_type, exc)
            continue
        for p in parsed:
            key = (p.ics_uid, p.recurrence_id, p.sequence, p.method)
            if key in seen:
                continue
            seen.add(key)
            out.append(p)
    return out


# ── Supersedence (pure) ─────────────────────────────────────────────────


def group_chains(invites: list[InviteLike]) -> dict[tuple[str, str], list]:
    """Bucket invites into (ics_uid, recurrence_id) chains."""
    chains: dict[tuple[str, str], list] = {}
    for inv in invites:
        chains.setdefault((inv.ics_uid, inv.recurrence_id or ""), []).append(inv)
    return chains


def resolve_final(chain: list[InviteLike]):
    """The reschedule/cancel state machine, as one pure function.

    Input: every observed invite of ONE (ics_uid, recurrence_id) chain.
    Returns the final live invite — the max-SEQUENCE non-cancelled REQUEST —
    or None when the chain is dead (no live REQUEST, or a CANCEL at ≥ the
    final REQUEST's sequence). Ties on sequence break toward the
    latest-persisted row (id), then input order.
    """
    live_requests = [i for i in chain if i.method == "request" and i.status != "cancelled"]
    if not live_requests:
        return None
    final = max(
        enumerate(live_requests),
        key=lambda pair: (pair[1].sequence, getattr(pair[1], "id", None) or 0, pair[0]),
    )[1]
    kill_sequences = [i.sequence for i in chain if i.method == "cancel" or i.status == "cancelled"]
    if any(seq >= final.sequence for seq in kill_sequences):
        return None
    return final


# ── Persistence ─────────────────────────────────────────────────────────


async def ingest_message_invites(
    session: AsyncSession, msg: EmailMessage, mime: Message
) -> list[EmailInvite]:
    """Upsert `EmailInvite` rows for every VEVENT the message carries.

    Idempotent on the chain key — a re-delivered/forwarded copy of the same
    invite updates the existing row instead of duplicating it (§ 6 risk:
    invite dedup). Returns the touched rows.
    """
    parsed = extract_invites(mime)
    if not parsed:
        return []
    now = datetime.now(UTC)
    out: list[EmailInvite] = []
    for p in parsed:
        row = (
            await session.exec(
                select(EmailInvite).where(
                    EmailInvite.user_id == msg.user_id,
                    EmailInvite.ics_uid == p.ics_uid,
                    EmailInvite.recurrence_id == p.recurrence_id,
                    EmailInvite.sequence == p.sequence,
                    EmailInvite.method == p.method,
                )
            )
        ).one_or_none()
        if row is None:
            row = EmailInvite(
                user_id=msg.user_id,
                email_message_id=msg.id or 0,
                application_id=msg.application_id,
                ics_uid=p.ics_uid,
                recurrence_id=p.recurrence_id,
                sequence=p.sequence,
                method=p.method,
                created_at=now,
            )
        elif row.application_id is None and msg.application_id is not None:
            row.application_id = msg.application_id
        row.status = p.status
        row.summary = p.summary
        row.location = p.location
        row.organizer_email = p.organizer_email
        row.attendee_emails = list(p.attendee_emails)
        row.starts_at = p.starts_at
        row.ends_at = p.ends_at
        row.tz = p.tz
        row.updated_at = now
        session.add(row)
        out.append(row)
    await session.flush()
    return out


async def adopt_message_invites(session: AsyncSession, msg: EmailMessage) -> bool:
    """Stamp the message's application onto its invite rows once linking has
    happened (classify-time hook — sync may have ingested them unlinked).
    Returns True when the message carries any invites at all."""
    rows = (
        await session.exec(select(EmailInvite).where(EmailInvite.email_message_id == msg.id))
    ).all()
    if not rows:
        return False
    if msg.application_id is not None:
        for row in rows:
            if row.application_id != msg.application_id:
                row.application_id = msg.application_id
                row.updated_at = datetime.now(UTC)
                session.add(row)
        await session.flush()
    return True


# ── Invite chains → interview rounds ────────────────────────────────────


async def _kind_for_chain(session: AsyncSession, chain: list, final) -> tuple[str, int | None]:
    """(round kind, carrying message id) for a chain that needs a new round.

    The carrying message's `extracted_round_kind` wins (the classifier read
    the whole email); the summary-title heuristic is the fallback. 96e's
    thread pass refines kinds later — this only seeds the container round.
    """
    from services import applications as applications_service

    message_ids = [i.email_message_id for i in chain if i.email_message_id]
    carrying_id = final.email_message_id if final.email_message_id else None
    kind: str | None = None
    if message_ids:
        messages = (
            await session.exec(select(EmailMessage).where(EmailMessage.id.in_(message_ids)))  # type: ignore[union-attr]
        ).all()
        by_id = {m.id: m for m in messages}
        ordered = [by_id.get(carrying_id)] + [m for m in messages if m.id != carrying_id]
        for m in ordered:
            if m is not None and m.extracted_round_kind:
                kind = m.extracted_round_kind
                break
    if kind is None:
        kind = applications_service.round_kind_from_title(final.summary or "") or "other"
    return kind, carrying_id


async def apply_invites_for_application(session: AsyncSession, *, application: Application) -> None:
    """Re-derive round schedule from the application's invite ledger.

    Idempotent per chain:
    - dead chain (cancelled without replacement) → scheduled riders revert to
      `planned` (dateless — the time no longer exists);
    - live chain with no rider → adopt the round the carrying message already
      produced, else upsert one container round (96e itemizes later);
    - live chain → shift every open rider so the earliest rider sits at the
      final invite's start (segment offsets within the container survive a
      container-level reschedule); `planned` riders ratchet to `scheduled`.
    """
    from services import applications as applications_service

    invites = (
        await session.exec(select(EmailInvite).where(EmailInvite.application_id == application.id))
    ).all()
    if not invites:
        return
    now = datetime.now(UTC)
    rounds = await applications_service.list_rounds(session, application_id=application.id or 0)

    for (uid, _rid), chain in group_chains(list(invites)).items():
        final = resolve_final(chain)
        riders = [r for r in rounds if r.invite_uid == uid]

        if final is None:
            for r in riders:
                if r.state == "scheduled":
                    r.state = "planned"
                    r.scheduled_at = None
                    r.updated_at = now
                    session.add(r)
            continue

        if not any(r.state != "cancelled" for r in riders):
            adopted = next(
                (
                    r
                    for r in rounds
                    if r.invite_uid is None
                    and r.email_message_id is not None
                    and r.state not in ("cancelled", "completed")
                    and any(i.email_message_id == r.email_message_id for i in chain)
                ),
                None,
            )
            if adopted is not None:
                adopted.invite_uid = uid
                adopted.updated_at = now
                session.add(adopted)
            else:
                kind, carrying_id = await _kind_for_chain(session, chain, final)
                await applications_service.upsert_round(
                    session,
                    application=application,
                    kind=kind,
                    source="email",
                    title=final.summary,
                    state="scheduled",
                    scheduled_at=final.starts_at,
                    email_message_id=carrying_id,
                    invite_uid=uid,
                )
            rounds = await applications_service.list_rounds(
                session, application_id=application.id or 0
            )
            riders = [r for r in rounds if r.invite_uid == uid]

        open_riders = [r for r in riders if r.state in ("planned", "scheduled")]
        final_start = _aware_utc(final.starts_at)
        if not open_riders or final_start is None:
            continue
        dated = [_aware_utc(r.scheduled_at) for r in open_riders if r.scheduled_at is not None]
        base = min(dated) if dated else None
        delta = (final_start - base) if base is not None else None
        for r in open_riders:
            r.scheduled_at = (
                _aware_utc(r.scheduled_at) + delta
                if (delta is not None and r.scheduled_at is not None)
                else final_start
            )
            if r.state == "planned":
                r.state = "scheduled"
            r.updated_at = now
            session.add(r)

    await session.flush()
    await applications_service.resequence_rounds(session, application_id=application.id or 0)


async def final_invites_for_user(session: AsyncSession, *, user_id: int) -> list[EmailInvite]:
    """Every live final invite across the user's chains (scheduling truth —
    consumed by the schedule panel and, later, the 96f slot engine)."""
    rows = (await session.exec(select(EmailInvite).where(EmailInvite.user_id == user_id))).all()
    finals = []
    for chain in group_chains(list(rows)).values():
        final = resolve_final(chain)
        if final is not None:
            finals.append(final)
    return finals


# ── Upcoming-interviews schedule (owner decision 2026-07-08: Tracking panel) ─


@dataclass(slots=True)
class ScheduleEntry:
    round_id: int
    label: str  # title or kind label
    kind: str
    time_label: str | None  # segment time within the container, local tz


@dataclass(slots=True)
class ScheduleGroup:
    """One calendar event (or standalone dated round) on the schedule."""

    application_id: int
    company: str
    role: str | None
    starts_at: datetime
    ends_at: datetime | None
    date_label: str  # "Mon Jul 13"
    time_label: str  # "2:00–5:45 PM EDT"
    entries: list[ScheduleEntry]
    job_id: int | None = None
    invite_uid: str | None = None


def _local(dt: datetime) -> datetime:
    """Render times in the host's current timezone — the owner's calendar
    follows the device (owner decision 2026-07-08); a Settings override
    arrives with 96f's `scheduling_timezone`."""
    return (_aware_utc(dt) or dt).astimezone()


def _fmt_time(dt: datetime) -> str:
    return _local(dt).strftime("%-I:%M %p").lower()


def _fmt_span(starts_at: datetime, ends_at: datetime | None) -> str:
    start_local = _local(starts_at)
    label = _fmt_time(starts_at)
    if ends_at is not None and ends_at > starts_at:
        label += f"–{_fmt_time(ends_at)}"
    return f"{label} {start_local.strftime('%Z')}".strip()


async def upcoming_interview_schedule(
    session: AsyncSession, *, user_id: int, days: int = 14
) -> list[ScheduleGroup]:
    """Scheduled rounds across all live applications, grouped by the calendar
    event that carries them — "what interviews are on what date"."""
    from models import InterviewRound

    now = datetime.now(UTC)
    lo = now - timedelta(hours=6)
    hi = now + timedelta(days=days)
    rows = (
        await session.exec(
            select(InterviewRound, Application)
            .where(
                InterviewRound.application_id == Application.id,
                InterviewRound.user_id == user_id,
                InterviewRound.state == "scheduled",
                InterviewRound.scheduled_at.is_not(None),  # type: ignore[union-attr]
                InterviewRound.scheduled_at >= lo,  # type: ignore[operator]
                InterviewRound.scheduled_at <= hi,  # type: ignore[operator]
                Application.deleted_at.is_(None),  # type: ignore[union-attr]
            )
            .order_by(InterviewRound.scheduled_at.asc())  # type: ignore[union-attr]
        )
    ).all()
    if not rows:
        return []

    finals_by_uid = {f.ics_uid: f for f in await final_invites_for_user(session, user_id=user_id)}

    grouped: dict[tuple[int, str], list] = {}
    for round_row, application in rows:
        key = (
            application.id or 0,
            round_row.invite_uid or f"round-{round_row.id}",
        )
        grouped.setdefault(key, []).append((round_row, application))

    out: list[ScheduleGroup] = []
    for (app_id, group_key), members in grouped.items():
        members.sort(
            key=lambda pair: _aware_utc(pair[0].scheduled_at) or datetime.max.replace(tzinfo=UTC)
        )
        first_round, application = members[0]
        invite_uid = first_round.invite_uid
        final = finals_by_uid.get(invite_uid) if invite_uid else None
        starts_at = (
            _aware_utc(final.starts_at if final else None)
            or _aware_utc(first_round.scheduled_at)
            or datetime.now(UTC)
        )
        ends_at = _aware_utc(final.ends_at if final else None)
        multi = len(members) > 1
        entries = [
            ScheduleEntry(
                round_id=r.id or 0,
                label=(r.title or r.kind.replace("_", " ")),
                kind=r.kind,
                time_label=_fmt_time(r.scheduled_at) if (multi and r.scheduled_at) else None,
            )
            for r, _ in members
        ]
        out.append(
            ScheduleGroup(
                application_id=app_id,
                company=application.company,
                role=application.role,
                starts_at=starts_at,
                ends_at=ends_at,
                date_label=_local(starts_at).strftime("%a %b %-d"),
                time_label=_fmt_span(starts_at, ends_at),
                entries=entries,
                job_id=application.job_id,
                invite_uid=group_key if invite_uid else None,
            )
        )
    out.sort(key=lambda g: g.starts_at)
    return out


# ── One-shot backfill (PEEK by UID; header-search for pre-95l rows) ─────


def _fetch_raw_by_uids(
    client,
    *,
    username: str,
    password: str,
    targets: list[tuple[int, str | None, str]],
) -> dict[int, bytes]:
    """Synchronous IMAP block — one connection for the whole backfill.

    `targets` = (message_row_id, imap_uid or None, message_id_external).
    Rows without a stored UID (pre-95l mail) resolve it via an IMAP
    Message-ID HEADER search first. Read-only select + BODY.PEEK — the
    backfill never marks mail read.
    """
    client.login(username, password)
    client.select("INBOX", readonly=True)
    out: dict[int, bytes] = {}
    for row_id, uid, message_id_external in targets:
        if not uid and message_id_external:
            try:
                typ, data = client.uid(
                    "SEARCH", None, f'(HEADER "Message-ID" "{message_id_external}")'
                )
                if typ == "OK" and data and data[0]:
                    found = data[0].split()
                    if found:
                        uid = found[-1].decode("ascii")
            except Exception:  # noqa: BLE001 — search miss: skip the row
                uid = None
        if not uid:
            continue
        typ, fetched = client.uid("FETCH", uid, "(BODY.PEEK[])")
        if typ != "OK" or not fetched:
            continue
        for part in fetched:
            if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], bytes):
                out[row_id] = part[1]
                break
    client.logout()
    return out


async def backfill_invites(
    session: AsyncSession,
    *,
    account: EmailAccount,
    limit: int = 120,
    client_factory=None,
) -> dict[str, int]:
    """One-shot: parse invites for already-stored interview mail.

    Bounded to the account's INTERVIEW_REQUEST / ASSESSMENT messages (the
    classes that schedule interviews), newest-first, `limit` rows. Resolves
    missing UIDs via Message-ID header search (pre-95l rows), stamps the
    recovered UID back onto the row, ingests invites, then re-applies chains
    per affected application. Caller commits.
    """
    import asyncio
    import email as email_lib

    from services.email import credentials as email_credentials
    from services.email.imap_host_guard import ensure_imap_host_allowed
    from services.email.sync import _default_client_factory

    stats = {"scanned": 0, "fetched": 0, "invites": 0, "applications": 0}
    password = email_credentials.load_imap_password(account)
    if password is None:
        log.warning("invite backfill: credential decrypt failed account=%s", account.id)
        return stats

    messages = (
        await session.exec(
            select(EmailMessage)
            .where(
                EmailMessage.user_id == account.user_id,
                EmailMessage.classification.in_(  # type: ignore[union-attr]
                    [EmailClassification.INTERVIEW_REQUEST, EmailClassification.ASSESSMENT]
                ),
            )
            .order_by(EmailMessage.received_at.desc())
            .limit(limit)
        )
    ).all()
    stats["scanned"] = len(messages)
    if not messages:
        return stats

    factory = client_factory or _default_client_factory
    targets = [(m.id or 0, m.imap_uid, m.message_id_external) for m in messages]

    def _runner() -> dict[int, bytes]:
        ensure_imap_host_allowed(account.imap_host, account.imap_port)
        client = factory(account.imap_host, account.imap_port)
        return _fetch_raw_by_uids(
            client, username=account.imap_username, password=password, targets=targets
        )

    raws = await asyncio.to_thread(_runner)
    stats["fetched"] = len(raws)

    by_id = {m.id: m for m in messages}
    affected_app_ids: set[int] = set()
    for row_id, raw in raws.items():
        msg = by_id.get(row_id)
        if msg is None:
            continue
        try:
            mime = email_lib.message_from_bytes(raw)
        except Exception as exc:  # noqa: BLE001
            log.warning("invite backfill: MIME parse failed message=%s: %s", row_id, exc)
            continue
        try:
            rows = await ingest_message_invites(session, msg, mime)
        except Exception as exc:  # noqa: BLE001 — one bad invite never stalls the sweep
            log.warning("invite backfill: ingest failed message=%s: %s", row_id, exc)
            continue
        stats["invites"] += len(rows)
        if rows and msg.application_id is not None:
            affected_app_ids.add(msg.application_id)

    for app_id in affected_app_ids:
        application = await session.get(Application, app_id)
        if application is None:
            continue
        try:
            await apply_invites_for_application(session, application=application)
        except Exception as exc:  # noqa: BLE001
            log.warning("invite backfill: apply failed application=%s: %s", app_id, exc)
    stats["applications"] = len(affected_app_ids)
    return stats
