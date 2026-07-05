"""Read-only calendar sync via secret ICS URL — item 11 (2026-07).

Google killed CalDAV basic-auth; the honest self-hosted path is the
calendar's SECRET ICS address (Google Calendar → Settings → your calendar
→ "Secret address in iCal format"). This module owns:

- `validate_ics_url` — https-only + the same SSRF posture as the scraper
  URL guard (private/link-local/IMDS destinations rejected; DNS fail =
  fail closed).
- Fernet encryption of the URL at rest (same SECRET_KEY trust posture as
  the IMAP app-password — `services/email_credentials.py`).
- A dependency-free VEVENT parser (folded lines, UTC/floating/all-day
  DTSTART) — enough for Google/Fastmail/Proton exports; unknown
  properties are ignored.
- `sync_connection` — fetch + upsert a bounded window of events and
  fuzzy-match them to the user's applications by company name.

Event creation is a future OAuth follow-up (docs/design/EMAIL_MONITORING.md
§ Calendar).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import Application, ApplicationStatus, CalendarConnection, CalendarEvent, Job
from scraper.url_guard import is_safe_destination
from services._crypto import secret_key_fernet

log = logging.getLogger(__name__)

SAFE_URL_ERROR = (
    "That calendar URL is not permitted. Use the https ICS address from Google Calendar settings."
)
_FETCH_TIMEOUT = 15.0
_MAX_ICS_BYTES = 5 * 1024 * 1024  # a personal calendar export is well under 5 MB
# Sync window: recent past (recently finished interviews still matter on the
# detail view) through two months out.
_WINDOW_PAST_DAYS = 7
_WINDOW_FUTURE_DAYS = 60


def _fernet() -> Fernet:
    return secret_key_fernet()


def store_ics_url(connection: CalendarConnection, url: str) -> None:
    connection.ics_url_encrypted = _fernet().encrypt(url.encode("utf-8")).decode("ascii")


def load_ics_url(connection: CalendarConnection) -> str | None:
    token = connection.ics_url_encrypted
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        log.warning(
            "calendar_sync: decrypt failed for connection_id=%s (SECRET_KEY rotated?)",
            connection.id,
        )
        return None


def validate_ics_url(url: str) -> tuple[bool, str | None]:
    """https-only + SSRF-guarded. Returns (ok, server-side reason)."""
    url = (url or "").strip()
    if not url.lower().startswith("https://"):
        return False, "scheme_not_https"
    ok, reason = is_safe_destination(url)
    if not ok:
        return False, reason
    return True, None


# ── Minimal ICS parsing ─────────────────────────────────────────────────


@dataclass(slots=True)
class ParsedEvent:
    uid: str
    title: str = ""
    location: str | None = None
    description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    all_day: bool = False
    extra: dict = field(default_factory=dict)


_ICS_ESCAPES = {r"\n": "\n", r"\N": "\n", r"\,": ",", r"\;": ";", r"\\": "\\"}


def _unescape(value: str) -> str:
    out = value
    for src, dst in _ICS_ESCAPES.items():
        out = out.replace(src, dst)
    return out


def _unfold_lines(text: str) -> list[str]:
    """RFC 5545 §3.1 — a line starting with SPACE/TAB continues the previous."""
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _parse_ics_datetime(value: str, params: dict[str, str]) -> tuple[datetime | None, bool]:
    """Return (aware datetime, all_day). Floating/TZID times are treated as
    UTC — a bounded distortion that keeps the parser dependency-free; the
    surfaces show the date + title, not minute-precision agendas."""
    value = value.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", value):
        try:
            d = datetime.strptime(value, "%Y%m%d").replace(tzinfo=UTC)
        except ValueError:
            return None, True
        return d, True
    try:
        if value.endswith("Z"):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC), False
        return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=UTC), False
    except ValueError:
        return None, False


def parse_ics(text: str) -> list[ParsedEvent]:
    """Parse VEVENT blocks. Ignores VTODO/VALARM/anything else. Recurring
    events yield their first instance only (RRULE expansion is out of scope
    for a read-only interview surface)."""
    events: list[ParsedEvent] = []
    current: ParsedEvent | None = None
    for line in _unfold_lines(text):
        if not line:
            continue
        if line.startswith("BEGIN:VEVENT"):
            current = ParsedEvent(uid="")
            continue
        if line.startswith("END:VEVENT"):
            if current and current.uid and current.starts_at is not None:
                events.append(current)
            current = None
            continue
        if current is None or ":" not in line:
            continue
        prop, _, value = line.partition(":")
        name, *param_parts = prop.split(";")
        params = {}
        for part in param_parts:
            k, _, v = part.partition("=")
            params[k.upper()] = v
        name = name.upper()
        if name == "UID":
            current.uid = value.strip()[:512]
        elif name == "SUMMARY":
            current.title = _unescape(value).strip()[:512]
        elif name == "LOCATION":
            current.location = _unescape(value).strip()[:512] or None
        elif name == "DESCRIPTION":
            current.description = _unescape(value).strip()[:240] or None
        elif name == "DTSTART":
            current.starts_at, current.all_day = _parse_ics_datetime(value, params)
        elif name == "DTEND":
            current.ends_at, _ = _parse_ics_datetime(value, params)
    return events


# ── Fetch + sync ────────────────────────────────────────────────────────


async def fetch_ics(url: str) -> str:
    """Fetch the ICS body with size cap + no-redirect-to-private posture.

    Redirects are followed manually so every hop is re-checked against the
    SSRF guard (Google's secret ICS URL 302s between hosts).
    """
    async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT, follow_redirects=False) as client:
        current = url
        for _hop in range(5):
            ok, reason = validate_ics_url(current)
            if not ok:
                raise ValueError(f"ics_url_rejected:{reason}")
            resp = await client.get(current)
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                if not location:
                    raise ValueError("redirect_without_location")
                current = str(httpx.URL(current).join(location))
                continue
            resp.raise_for_status()
            if len(resp.content) > _MAX_ICS_BYTES:
                raise ValueError("ics_too_large")
            return resp.text
    raise ValueError("too_many_redirects")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())


async def _match_events_to_applications(
    session: AsyncSession, *, user_id: int, events: list[CalendarEvent]
) -> None:
    """Company-name containment match — read-only suggestion, cheap on
    purpose. An event titled "Interview with Stripe" matches the user's
    Stripe application; ties break toward the most recently updated app."""
    rows = (
        await session.exec(
            select(Application, Job)
            .join(Job, Job.id == Application.job_id)
            .where(
                Application.user_id == user_id,
                Application.deleted_at.is_(None),
                Application.status != ApplicationStatus.DRAFT,
            )
            .order_by(Application.updated_at.desc())
        )
    ).all()
    companies: list[tuple[str, int]] = []
    for application, job in rows:
        name = _norm(job.company).strip()
        if len(name) >= 3:
            companies.append((name, application.id))
    for event in events:
        haystack = f" {_norm(event.title)} {_norm(event.description_snippet or '')} "
        for company, app_id in companies:
            if f" {company} " in haystack or (len(company) > 5 and company in haystack):
                event.matched_application_id = app_id
                break


async def sync_connection(session: AsyncSession, connection: CalendarConnection) -> tuple[int, int]:
    """Fetch + upsert the window of events. Returns (parsed_in_window, new)."""
    url = load_ics_url(connection)
    now = datetime.now(UTC)
    if url is None:
        connection.status = "fetch_failed"
        connection.last_error = "credential decrypt failed — re-paste the ICS address"
        connection.updated_at = now
        session.add(connection)
        await session.flush()
        return 0, 0
    try:
        body = await fetch_ics(url)
        parsed = parse_ics(body)
    except Exception as exc:  # noqa: BLE001 — cron must survive flaky fetches
        log.warning("calendar sync failed for connection %s: %s", connection.id, exc)
        connection.status = "fetch_failed"
        connection.last_error = str(exc)[:300]
        connection.updated_at = now
        session.add(connection)
        await session.flush()
        return 0, 0

    lo = now - timedelta(days=_WINDOW_PAST_DAYS)
    hi = now + timedelta(days=_WINDOW_FUTURE_DAYS)
    windowed = [e for e in parsed if e.starts_at and lo <= e.starts_at <= hi]

    existing = {
        row.uid: row
        for row in (
            await session.exec(
                select(CalendarEvent).where(CalendarEvent.user_id == connection.user_id)
            )
        ).all()
    }
    new_count = 0
    touched: list[CalendarEvent] = []
    for e in windowed:
        row = existing.get(e.uid)
        if row is None:
            row = CalendarEvent(
                user_id=connection.user_id,
                connection_id=connection.id,
                uid=e.uid,
                starts_at=e.starts_at,
            )
            new_count += 1
        row.title = e.title
        row.location = e.location
        row.description_snippet = e.description
        row.starts_at = e.starts_at
        row.ends_at = e.ends_at
        row.all_day = e.all_day
        row.updated_at = now
        session.add(row)
        touched.append(row)

    # Drop events that left the window / were removed upstream.
    windowed_uids = {e.uid for e in windowed}
    for uid, row in existing.items():
        if uid not in windowed_uids:
            await session.delete(row)

    await _match_events_to_applications(session, user_id=connection.user_id, events=touched)

    connection.status = "ok"
    connection.last_error = None
    connection.last_sync_at = now
    connection.event_count = len(windowed)
    connection.updated_at = now
    session.add(connection)
    await session.flush()
    return len(windowed), new_count


async def get_connection(session: AsyncSession, user_id: int) -> CalendarConnection | None:
    return (
        await session.exec(
            select(CalendarConnection).where(
                CalendarConnection.user_id == user_id,
                CalendarConnection.deleted_at.is_(None),
            )
        )
    ).one_or_none()


async def upcoming_events(
    session: AsyncSession, *, user_id: int, days: int = 14, limit: int = 6
) -> list[CalendarEvent]:
    now = datetime.now(UTC)
    rows = (
        await session.exec(
            select(CalendarEvent)
            .where(
                CalendarEvent.user_id == user_id,
                CalendarEvent.starts_at >= now - timedelta(hours=2),
                CalendarEvent.starts_at <= now + timedelta(days=days),
            )
            .order_by(CalendarEvent.starts_at)
            .limit(limit)
        )
    ).all()
    return list(rows)


async def events_for_application(
    session: AsyncSession, *, user_id: int, application_id: int
) -> list[CalendarEvent]:
    rows = (
        await session.exec(
            select(CalendarEvent)
            .where(
                CalendarEvent.user_id == user_id,
                CalendarEvent.matched_application_id == application_id,
            )
            .order_by(CalendarEvent.starts_at)
        )
    ).all()
    return list(rows)


def format_event_when(event: CalendarEvent, *, today: date | None = None) -> str:
    """Human label: 'Tue Jul 7 · 14:30' / 'Tue Jul 7 · all day'."""
    d = event.starts_at
    label = d.strftime("%a %b %-d")
    if event.all_day:
        return f"{label} · all day"
    return f"{label} · {d.strftime('%H:%M')} UTC"
