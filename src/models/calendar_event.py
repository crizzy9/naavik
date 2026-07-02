"""Calendar integration models — item 11 (2026-07).

Google killed CalDAV basic-auth, so the read-only integration mirrors the
Gmail one-screen pattern: the user pastes their calendar's SECRET ICS
address (Google Calendar → Settings → "Secret address in iCal format").
The URL is Fernet-encrypted at rest (same SECRET_KEY trust posture as the
IMAP app-password); a cron re-fetches on a 45-minute cadence into
`CalendarEvent` rows, which fuzzy-match to applications for the Tracking
surfaces. Event CREATION stays a future OAuth follow-up — see
docs/design/EMAIL_MONITORING.md § Calendar.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, Text, UniqueConstraint
from sqlmodel import Field, SQLModel

from ._common import utcnow


class CalendarConnection(SQLModel, table=True):
    __tablename__ = "calendar_connection"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", unique=True, index=True)

    label: str = Field(default="Google Calendar", max_length=120)
    # Fernet token of the secret ICS URL — never stored or logged plaintext.
    ics_url_encrypted: str = Field(sa_column=Column(Text, nullable=False))

    status: str = Field(default="ok", max_length=32)  # ok | fetch_failed | disabled
    last_error: str | None = Field(default=None, max_length=300)
    last_sync_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    event_count: int = Field(default=0)

    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    deleted_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class CalendarEvent(SQLModel, table=True):
    __tablename__ = "calendar_event"
    __table_args__ = (UniqueConstraint("user_id", "uid", name="uq_calendar_event_user_uid"),)

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    connection_id: int = Field(foreign_key="calendar_connection.id", ondelete="CASCADE", index=True)

    uid: str = Field(max_length=512)  # iCalendar UID
    title: str = Field(default="", max_length=512)
    location: str | None = Field(default=None, max_length=512)
    # Privacy cap mirrors EmailMessage.snippet — enough to match a company
    # name, not the whole meeting agenda.
    description_snippet: str | None = Field(default=None, max_length=240)
    starts_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    ends_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    all_day: bool = Field(default=False)

    # Fuzzy company/role match against the user's applications (read-only
    # suggestion surface; never mutates the application).
    matched_application_id: int | None = Field(
        default=None, foreign_key="application.id", ondelete="SET NULL", index=True
    )

    created_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    updated_at: datetime = Field(
        default_factory=utcnow, sa_column=Column(DateTime(timezone=True), nullable=False)
    )
