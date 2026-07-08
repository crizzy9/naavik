"""Free-slot engine — plan 96 slice 96f (owner decisions #5, #6).

Pure functions on `zoneinfo`: no DB, no network, no now() of their own —
everything injected, so the DST matrix is unit-testable. The working window
is a WALL-CLOCK band in the user's zone ("10:00-18:00" stays 10 am across a
DST transition; the UTC offset is what moves). Busy intervals come from the
read-only calendar (synced events + final invites) — the caller assembles
them; this module only does the arithmetic.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

DEFAULT_WINDOW = "10:00-18:00"
_DEFAULT_DURATION = timedelta(minutes=45)
# Never propose a slot the owner can't realistically make.
_DEFAULT_LEAD = timedelta(hours=3)
_STEP = timedelta(minutes=30)


@dataclass(slots=True)
class Slot:
    starts_at: datetime  # aware UTC
    ends_at: datetime  # aware UTC


def parse_window(text: str | None) -> tuple[time, time]:
    """Parse "HH:MM-HH:MM"; malformed input degrades to the default band."""
    raw = (text or "").strip() or DEFAULT_WINDOW
    try:
        lo_raw, hi_raw = raw.split("-", 1)
        lo_h, lo_m = (int(x) for x in lo_raw.strip().split(":", 1))
        hi_h, hi_m = (int(x) for x in hi_raw.strip().split(":", 1))
        lo, hi = time(lo_h, lo_m), time(hi_h, hi_m)
    except (ValueError, TypeError):
        return parse_window(DEFAULT_WINDOW)
    if lo >= hi:
        return parse_window(DEFAULT_WINDOW)
    return lo, hi


def _overlaps(start: datetime, end: datetime, busy: list[tuple[datetime, datetime]]) -> bool:
    return any(start < b_end and b_start < end for b_start, b_end in busy)


def free_slots(
    *,
    busy: list[tuple[datetime, datetime]],
    tz: ZoneInfo,
    window: tuple[time, time],
    now: datetime,
    duration: timedelta = _DEFAULT_DURATION,
    count: int = 3,
    business_days: int = 5,
    lead: timedelta = _DEFAULT_LEAD,
    step: timedelta = _STEP,
) -> list[Slot]:
    """The next `count` conflict-free slots across `business_days` weekdays.

    Candidates advance in `step` increments through each day's wall-clock
    window (constructed IN `tz`, so DST transitions move the UTC offset,
    never the 10 am), must start ≥ now+lead, and must not overlap any busy
    interval. Inputs and outputs are aware UTC.
    """
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    busy_norm = [
        (
            b_start if b_start.tzinfo else b_start.replace(tzinfo=UTC),
            b_end if b_end.tzinfo else b_end.replace(tzinfo=UTC),
        )
        for b_start, b_end in busy
        if b_start is not None and b_end is not None
    ]
    window_lo, window_hi = window
    earliest = now + lead

    out: list[Slot] = []
    day = now.astimezone(tz).date()
    weekdays_seen = 0
    while weekdays_seen < business_days and len(out) < count:
        if day.weekday() >= 5:  # Sat/Sun
            day += timedelta(days=1)
            continue
        weekdays_seen += 1
        cursor = datetime.combine(day, window_lo, tzinfo=tz)
        day_end = datetime.combine(day, window_hi, tzinfo=tz)
        while cursor + duration <= day_end and len(out) < count:
            start_utc = cursor.astimezone(UTC)
            end_utc = (cursor + duration).astimezone(UTC)
            if start_utc >= earliest and not _overlaps(start_utc, end_utc, busy_norm):
                out.append(Slot(starts_at=start_utc, ends_at=end_utc))
            cursor += step
        day += timedelta(days=1)
    return out


def format_slot(slot: Slot, tz: ZoneInfo) -> str:
    """Human label with an EXPLICIT tz — "Thu Jul 9, 10:00–10:45 am EDT"
    (§ 6 risk: suggested slots always render with the zone spelled out)."""
    lo = slot.starts_at.astimezone(tz)
    hi = slot.ends_at.astimezone(tz)
    lo_label = lo.strftime("%-I:%M %p").lower()
    hi_label = hi.strftime("%-I:%M %p").lower()
    if lo.strftime("%p") == hi.strftime("%p"):
        lo_label = lo.strftime("%-I:%M").lower()
    return f"{lo.strftime('%a %b %-d')}, {lo_label}–{hi_label} {lo.strftime('%Z')}"
