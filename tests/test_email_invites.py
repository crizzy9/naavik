"""Invite parsing + supersedence pure functions (plan 96 slice 96d).

Vendor fixtures mirror real payloads from the owner's inbox (Google/Ashby
invites carry the same VEVENT twice — inline `text/calendar` + an
`invite.ics` attachment; Outlook uses Windows TZIDs). `resolve_final` is the
reschedule/cancel state machine — the matrix below IS its contract.
"""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime
from email.message import EmailMessage as MIMEMessage

os.environ.setdefault("NAAVIK_DEBUG", "1")

from services.email.invites import (  # noqa: E402
    ParsedInvite,
    extract_invites,
    group_chains,
    has_calendar_part,
    resolve_final,
)

GOOGLE_ICS = """BEGIN:VCALENDAR
PRODID:-//Google Inc//Google Calendar 70.9054//EN
VERSION:2.0
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
DTSTART;TZID=America/Los_Angeles:20260715T110000
DTEND;TZID=America/Los_Angeles:20260715T120000
DTSTAMP:20260707T225700Z
ORGANIZER;CN=Interviews-Ashby:mailto:c_84b0deadbeef@group.calendar.google.com
UID:sr5jur2sqkhngkm32ls23uposs@google.com
ATTENDEE;CUTYPE=INDIVIDUAL;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE;CN=shyam.padia930@gmail.com;X-NUM-GUESTS=0:mailto:shyam.padia930@gmail.com
CREATED:20260707T225656Z
SEQUENCE:0
STATUS:CONFIRMED
SUMMARY:Interview with Headway | Shyam Padia | Senior Backend Software Engineer
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
"""

OUTLOOK_ICS = """BEGIN:VCALENDAR
METHOD:REQUEST
PRODID:Microsoft Exchange Server 2010
VERSION:2.0
BEGIN:VEVENT
ORGANIZER;CN=Recruiting Team:mailto:recruiting@corp.example.com
ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE;CN=Shyam:mailto:shyam.padia930@gmail.com
SUMMARY:Technical Screen - Corp
UID:040000008200E00074C5B7101A82E00800000000B0
SEQUENCE:2
DTSTART;TZID=Eastern Standard Time:20260720T140000
DTEND;TZID=Eastern Standard Time:20260720T150000
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR
"""

CANCEL_ICS = """BEGIN:VCALENDAR
PRODID:-//Google Inc//Google Calendar 70.9054//EN
VERSION:2.0
METHOD:CANCEL
BEGIN:VEVENT
DTSTART;TZID=America/Los_Angeles:20260715T110000
DTEND;TZID=America/Los_Angeles:20260715T120000
UID:sr5jur2sqkhngkm32ls23uposs@google.com
SEQUENCE:1
STATUS:CANCELLED
SUMMARY:Interview with Headway | Shyam Padia | Senior Backend Software Engineer
END:VEVENT
END:VCALENDAR
"""


def mime_with(
    ics: str | None, *, also_attachment: bool = False, method: str = "REQUEST"
) -> MIMEMessage:
    m = MIMEMessage()
    m["Message-ID"] = "<x@example.com>"
    m["From"] = "Interviews <invites@ashbyhq.com>"
    m["Subject"] = "Invitation: Interview"
    m.set_content("plain body")
    if ics is not None:
        m.add_attachment(
            ics.encode(), maintype="text", subtype="calendar", params={"method": method}
        )
        if also_attachment:
            m.add_attachment(
                ics.encode(), maintype="application", subtype="ics", filename="invite.ics"
            )
    return m


# ── Parsing ─────────────────────────────────────────────────────────────


def test_google_invite_parses_and_dedups_duplicate_parts():
    # Google delivers the identical VEVENT as text/calendar AND invite.ics —
    # one ParsedInvite, not two (§ 6 risk: invite dedup).
    out = extract_invites(mime_with(GOOGLE_ICS, also_attachment=True))
    assert len(out) == 1
    p = out[0]
    assert p.ics_uid == "sr5jur2sqkhngkm32ls23uposs@google.com"
    assert (p.method, p.status, p.sequence, p.recurrence_id) == ("request", "confirmed", 0, "")
    # 11:00 America/Los_Angeles (PDT) normalizes to 18:00 UTC.
    assert p.starts_at == datetime(2026, 7, 15, 18, 0, tzinfo=UTC)
    assert p.ends_at == datetime(2026, 7, 15, 19, 0, tzinfo=UTC)
    assert p.tz == "America/Los_Angeles"
    assert p.organizer_email == "c_84b0deadbeef@group.calendar.google.com"
    assert p.attendee_emails == ["shyam.padia930@gmail.com"]
    assert p.summary and p.summary.startswith("Interview with Headway")


def test_outlook_windows_tzid_parses():
    out = extract_invites(mime_with(OUTLOOK_ICS))
    assert len(out) == 1
    p = out[0]
    assert p.sequence == 2
    # 14:00 "Eastern Standard Time" (Windows TZID, EDT in July) → 18:00 UTC.
    assert p.starts_at == datetime(2026, 7, 20, 18, 0, tzinfo=UTC)


def test_cancel_parses_as_cancelled():
    out = extract_invites(mime_with(CANCEL_ICS, method="CANCEL"))
    assert len(out) == 1
    assert (out[0].method, out[0].status, out[0].sequence) == ("cancel", "cancelled", 1)


def test_malformed_part_degrades_to_empty():
    out = extract_invites(mime_with("BEGIN:VCALENDAR\nTHIS IS NOT VALID"))
    assert out == []


def test_no_calendar_part_yields_nothing():
    m = mime_with(None)
    assert has_calendar_part(m) is False
    assert extract_invites(m) == []


def test_has_calendar_part_detects_inline_and_attachment():
    assert has_calendar_part(mime_with(GOOGLE_ICS)) is True


# ── Supersedence matrix ─────────────────────────────────────────────────


def _inv(seq: int = 0, method: str = "request", status: str = "confirmed", **kw) -> ParsedInvite:
    return ParsedInvite(
        ics_uid="uid-1",
        sequence=seq,
        method=method,
        status=status,
        starts_at=datetime(2026, 7, 15, 18, 0, tzinfo=UTC),
        **kw,
    )


def test_single_request_is_final():
    assert resolve_final([_inv()]) is not None


def test_reschedule_max_sequence_wins():
    first = _inv(seq=0)
    moved = replace(_inv(seq=1), starts_at=datetime(2026, 7, 16, 18, 0, tzinfo=UTC))
    final = resolve_final([first, moved])
    assert final is moved


def test_cancel_at_equal_sequence_kills_chain():
    assert resolve_final([_inv(seq=1), _inv(seq=1, method="cancel", status="cancelled")]) is None


def test_cancel_at_higher_sequence_kills_chain():
    assert resolve_final([_inv(seq=0), _inv(seq=3, method="cancel", status="cancelled")]) is None


def test_request_after_cancel_reinstates():
    chain = [
        _inv(seq=0),
        _inv(seq=1, method="cancel", status="cancelled"),
        _inv(seq=2),
    ]
    final = resolve_final(chain)
    assert final is chain[2]


def test_cancelled_status_request_never_final():
    assert resolve_final([_inv(seq=0, status="cancelled")]) is None


def test_non_request_methods_never_final():
    # REPLY / COUNTER / PUBLISH observe or negotiate; only REQUEST schedules.
    assert resolve_final([_inv(method="reply"), _inv(method="counter", seq=5)]) is None


def test_recurring_instances_are_separate_chains():
    base = _inv(seq=0)
    instance = replace(_inv(seq=0), recurrence_id="20260722T180000")
    chains = group_chains([base, instance])
    assert set(chains.keys()) == {("uid-1", ""), ("uid-1", "20260722T180000")}
    # Cancelling one instance leaves the other chain live.
    cancelled = replace(
        _inv(seq=1, method="cancel", status="cancelled"), recurrence_id="20260722T180000"
    )
    chains = group_chains([base, instance, cancelled])
    assert resolve_final(chains[("uid-1", "")]) is base
    assert resolve_final(chains[("uid-1", "20260722T180000")]) is None
