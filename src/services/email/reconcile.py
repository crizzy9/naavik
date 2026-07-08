"""Event-driven process reconciler — plan 96 slice 96e (owner #8, #12, #13).

Re-derives an application's rounds + stage from ALL evidence — instead of
trusting incremental dispatch order alone. **No standing cron**: a reconcile
runs only when new information about a specific application arrives (owner
decision #13) —

- the classify tick, batched per application at end-of-tick,
- a recorded correction (reclassify / unlink / merge / flag-sender),
- applying an email suggestion,
- invite ingest (via the classify tick that carries the invite's message).

Shape per reconcile:

1. **Deterministic core** (always): re-run alias/sender-rule grouping to link
   stray mail that belongs to this application (heals the "rejection landed
   in a different group" class); re-resolve invite chains (96d, idempotent);
   re-fold the (classification, stage) timeline and diff against the current
   status.
2. **Conversation-coherent LLM pass** (owner #12) — ONE application-level
   `tracked_call` over every signal conversation (deviation 18: per-thread
   calls read the process from partial views and duplicated rounds), fired
   only when a TRIGGERING thread carries mail newer than its stamp in the
   `submission_artifacts["reconcile"]` slot. The result is the CANONICAL
   itemized interview list (owner 2026-07-08: one round per interview, even
   when several share a calendar event) which ADOPTS/REWRITES existing
   rounds in place (owner decision, session 2) — matched by
   kind/container, generic rows upgraded, container times anchored to the
   final invite's start, never deleted.
3. **Writes ride existing seams**: rounds through the 95d upsert producer
   (plus the owner-approved in-place rewrite for adopted rows), stage through
   `update_status` — forward-only, `trigger=RECONCILED`, § 3.8 pin
   suppression downgrades to suggestions, CLOSED absolute, rejection stays
   human-confirm. The reconciler can never do anything a well-ordered email
   stream couldn't.

Idempotence is the design invariant: reconciling twice with no new evidence
produces zero writes (the thread stamp gates the LLM pass; the deterministic
core converges).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from llm import LLMProviderError, get_provider
from llm.prompts.classify_thread import PROMPT as THREAD_PROMPT
from llm.prompts.classify_thread import ThreadReconcileResult
from models import (
    AppEventKind,
    Application,
    EmailInvite,
    EmailMessage,
    EmailThread,
    Settings,
)
from models.enums import (
    ApplicationStatus,
    EmailClassification,
    StatusChangeTrigger,
)
from models.interview_round import ROUND_KINDS
from services import llm_tracker

log = logging.getLogger(__name__)

RECONCILE_KEY = "reconcile"

# Threads worth a conversation-coherent LLM read. OTHER stays out; FOLLOW_UP
# is IN — rejection-shaped follow-ups are exactly the per-message blind spot
# (§ 3.4.4).
_THREAD_PASS_CLASSIFICATIONS = frozenset(
    {
        EmailClassification.INTERVIEW_REQUEST,
        EmailClassification.ASSESSMENT,
        EmailClassification.OFFER,
        EmailClassification.REJECTION,
        EmailClassification.FOLLOW_UP,
    }
)

_MAX_THREAD_MESSAGES = 8
_MAX_THREADS_PER_PASS = 10
_MAX_EXCERPT_CHARS = 800

_RANK = {
    ApplicationStatus.DRAFT: 0,
    ApplicationStatus.APPLIED: 1,
    ApplicationStatus.RECRUITER_SCREEN: 2,
    ApplicationStatus.ONSITE_LOOP: 3,
    ApplicationStatus.OFFER: 4,
}

_STAGE_TARGETS = {
    "screen": ApplicationStatus.RECRUITER_SCREEN,
    "interview": ApplicationStatus.ONSITE_LOOP,
    "offer": ApplicationStatus.OFFER,
}


@dataclass(slots=True)
class DerivedRound:
    kind: str
    title: str | None
    interviewer: str | None
    state: str
    scheduled_at: datetime | None
    invite_uid: str | None
    # Minutes-of-day the thread stated (tz-ambiguous — Gmail subjects render
    # in the OWNER's tz, invites in the organizer's). Container rounds resolve
    # via `_anchor_container_times`, never by trusting a tz guess.
    raw_minutes: int | None = None


@dataclass(slots=True)
class ReconcileResult:
    application_id: int
    relinked_messages: int = 0
    thread_passes: int = 0
    rounds_touched: int = 0
    status_moved: bool = False
    status_suggested: bool = False
    needs_scheduling: bool = False
    derived: list[DerivedRound] = field(default_factory=list)


def _aware_utc(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


async def _get_settings(session: AsyncSession, *, user_id: int) -> Settings | None:
    return (await session.exec(select(Settings).where(Settings.user_id == user_id))).one_or_none()


# ── Entry points ────────────────────────────────────────────────────────


async def reconcile_application(
    session: AsyncSession,
    *,
    application_id: int,
    triggering_thread_ids: set[int] | None = None,
) -> ReconcileResult | None:
    """Re-derive rounds + stage for ONE application from all its evidence.

    `triggering_thread_ids` scopes the LLM pass to the threads that actually
    carry new information; None/empty means deterministic-core-only. Caller
    commits; failures should be caught by the caller (one bad reconcile must
    never sink a classify tick).
    """
    from services import applications as applications_service

    application = await applications_service.get_application(session, application_id)
    if application is None or application.deleted_at is not None:
        return None
    result = ReconcileResult(application_id=application_id)

    # 1a. Re-group: stray unlinked mail that canonicalizes to this company
    # (aliases + sender rules applied) joins the application.
    result.relinked_messages = await _relink_matching_messages(session, application)

    # 1b. Re-resolve invite chains (96d, idempotent).
    from services.email import invites as invites_service

    await invites_service.apply_invites_for_application(session, application=application)

    # 2. Thread-level LLM pass for triggering threads with unseen mail.
    llm_stage, llm_rejection = None, False
    if triggering_thread_ids:
        llm_stage, llm_rejection = await _thread_pass(
            session, application, set(triggering_thread_ids), result
        )

    # 3. Adopt/rewrite rounds from the derived itemization (owner 2026-07-08).
    if result.derived:
        finals = await _final_invites(session, application)
        _anchor_container_times(result.derived, finals)
        result.rounds_touched = await _apply_derived_rounds(session, application, result.derived)

    # 4. Re-fold the timeline + LLM stage → forward-only diff.
    await _apply_stage(
        session, application, llm_stage=llm_stage, llm_rejection=llm_rejection, result=result
    )

    await session.flush()
    return result


async def reconcile_group(
    session: AsyncSession, *, user_id: int, company: str
) -> ReconcileResult | None:
    """Group variant for detected processes: their state derives at read time
    (`processes.list_detected_processes`), so the reconciler's job is only to
    notice when the group NOW resolves to a tracked application (an alias or
    correction is new information) and hand over."""
    from services.email.inference import find_application_for_company

    application = await find_application_for_company(session, user_id=user_id, company=company)
    if application is None or application.id is None:
        return None
    return await reconcile_application(session, application_id=application.id)


# ── 1a. Deterministic re-group ──────────────────────────────────────────


async def _relink_matching_messages(session: AsyncSession, application: Application) -> int:
    """Link stray unlinked mail whose canonical company key (end-client for
    parked sender types, per § 3.3) matches this application's — with current
    aliases, so a "Merge into…" heals history. Newly linked messages'
    threads inherit both link facts."""
    from services.email.inference import (
        canonical_company_key,
        find_application_for_company,
        load_company_alias_map,
    )
    from services.email.sender_rules import PARKED_SENDER_TYPES
    from services.email.service import link_thread

    aliases = await load_company_alias_map(session, user_id=application.user_id)
    app_key = canonical_company_key(application.company, aliases=aliases)
    if not app_key:
        return 0

    # Human intent outranks machine inference (§ 3.8): a thread the human
    # explicitly UNLINKED must never be re-adopted by company match — the
    # unlink correction is the durable objection.
    from models import ClassificationCorrection

    unlinked_thread_ids = set(
        (
            await session.exec(
                select(EmailMessage.thread_id)
                .join(
                    ClassificationCorrection,
                    ClassificationCorrection.message_id == EmailMessage.id,  # type: ignore[arg-type]
                )
                .where(
                    ClassificationCorrection.user_id == application.user_id,
                    ClassificationCorrection.kind == "unlink",
                )
            )
        ).all()
    )

    # Parallel processes at one company (plan 95 § 3.0): when 2+ live
    # applications share this key, per-message role disambiguation decides —
    # a plain key match would steal the sibling's mail.
    siblings = (
        await session.exec(
            select(Application).where(
                Application.user_id == application.user_id,
                Application.deleted_at.is_(None),  # type: ignore[union-attr]
            )
        )
    ).all()
    ambiguous = (
        sum(1 for a in siblings if canonical_company_key(a.company, aliases=aliases) == app_key) > 1
    )

    candidates = (
        await session.exec(
            select(EmailMessage).where(
                EmailMessage.user_id == application.user_id,
                EmailMessage.application_id.is_(None),  # type: ignore[union-attr]
                EmailMessage.process_dismissed_at.is_(None),  # type: ignore[union-attr]
                EmailMessage.classification.is_not(None),  # type: ignore[union-attr]
            )
        )
    ).all()
    linked = 0
    now = datetime.now(UTC)
    for msg in candidates:
        if msg.thread_id in unlinked_thread_ids:
            continue
        if msg.extracted_sender_type in PARKED_SENDER_TYPES:
            company = msg.extracted_end_client
        else:
            company = msg.extracted_company
        if not company or canonical_company_key(company, aliases=aliases) != app_key:
            continue
        if ambiguous:
            resolved = await find_application_for_company(
                session, user_id=application.user_id, company=company, role=msg.extracted_role
            )
            if resolved is None or resolved.id != application.id:
                continue
        msg.application_id = application.id
        msg.updated_at = now
        session.add(msg)
        linked += 1
        thread = await session.get(EmailThread, msg.thread_id)
        if thread is not None and thread.application_id is None:
            link_thread(thread, application)
            thread.updated_at = now
            session.add(thread)
    return linked


# ── 2. Thread-level LLM pass ────────────────────────────────────────────


def _render_conversation(messages: list[EmailMessage]) -> str:
    lines: list[str] = []
    for m in messages:
        when = m.received_at.strftime("%Y-%m-%d %H:%M") if m.received_at else "?"
        body = (m.body_excerpt or m.snippet or "")[:_MAX_EXCERPT_CHARS]
        lines.append(f"[{when}] From: {m.sender_email}\nSubject: {m.subject}\n{body}\n")
    return "\n".join(lines)


async def _thread_pass(
    session: AsyncSession,
    application: Application,
    thread_ids: set[int],
    result: ReconcileResult,
) -> tuple[str | None, bool]:
    """ONE application-level `tracked_call` over every signal conversation.

    Deviation from the plan's per-thread sketch (logged): independent
    per-thread calls read the same process from partial views and their
    outputs merged into duplicate rounds — the application-level read
    dedupes where the context lives, and costs less. It runs only when a
    TRIGGERING thread carries mail newer than its stamp in the
    `submission_artifacts["reconcile"]` slot (cost + idempotence gate);
    stamps then advance for every rendered thread. Degrades to
    (None, False) without a provider — the deterministic core already ran.
    """
    settings = await _get_settings(session, user_id=application.user_id)
    if settings is None:
        return None, False
    try:
        provider = get_provider(settings)
    except LLMProviderError:
        return None, False

    artifacts = dict(application.submission_artifacts or {})
    stamp = dict(artifacts.get(RECONCILE_KEY) or {})
    thread_stamps: dict[str, Any] = dict(stamp.get("threads") or {})

    threads = (
        await session.exec(
            select(EmailThread)
            .where(
                EmailThread.user_id == application.user_id,
                EmailThread.application_id == application.id,
                EmailThread.classification.in_(  # type: ignore[union-attr]
                    list(_THREAD_PASS_CLASSIFICATIONS)
                ),
            )
            .order_by(EmailThread.latest_message_at.desc())
            .limit(_MAX_THREADS_PER_PASS)
        )
    ).all()

    unseen = False
    blocks: list[str] = []
    latest_by_thread: dict[int, int] = {}
    newest_signal: EmailThread | None = None
    for thread in threads:
        messages = (
            await session.exec(
                select(EmailMessage)
                .where(EmailMessage.thread_id == thread.id)
                .order_by(EmailMessage.received_at.desc())
                .limit(_MAX_THREAD_MESSAGES)
            )
        ).all()
        if not messages:
            continue
        latest_by_thread[thread.id or 0] = messages[0].id or 0
        if newest_signal is None:
            newest_signal = thread
        if thread.id in thread_ids and thread_stamps.get(str(thread.id)) != messages[0].id:
            unseen = True
        blocks.append(f"### Conversation: {thread.subject}\n{_render_conversation(list(messages))}")
    if not unseen or not blocks:
        return None, False

    role_clause = f" for the role {application.role!r}" if application.role else ""
    rendered = THREAD_PROMPT.format(
        company=application.company,
        role_clause=role_clause,
        conversation="\n".join(blocks),
    )
    try:
        raw = await llm_tracker.tracked_call(
            session=session,
            user_id=application.user_id,
            provider=provider,
            method="structured",
            prompt_name="classify_thread",
            prompt=rendered,
            schema=ThreadReconcileResult,
        )
        parsed = _parse_thread_result(raw)
    except Exception as exc:  # noqa: BLE001 — LLM failure never blocks the core
        log.warning("application pass failed for application %s: %s", application.id, exc)
        return None, False

    for tid, mid in latest_by_thread.items():
        thread_stamps[str(tid)] = mid
    result.thread_passes = 1

    if parsed.needs_scheduling and newest_signal is not None:
        stamp["needs_scheduling"] = {
            "thread_id": newest_signal.id,
            "subject": newest_signal.subject[:120],
            "detected_at": datetime.now(UTC).isoformat(),
        }
        result.needs_scheduling = True
    else:
        stamp.pop("needs_scheduling", None)

    finals_by_uid = await _final_invites(session, application)
    for r in parsed.rounds:
        result.derived.append(_to_derived(r, finals_by_uid))

    stamp["threads"] = thread_stamps
    stamp["at"] = datetime.now(UTC).isoformat()
    artifacts[RECONCILE_KEY] = stamp
    application.submission_artifacts = artifacts
    session.add(application)
    best_stage = parsed.process_stage if parsed.process_stage in _STAGE_TARGETS else None
    return best_stage, parsed.rejection


def _parse_thread_result(raw: Any) -> ThreadReconcileResult:
    value = getattr(raw, "value", None)
    if isinstance(value, ThreadReconcileResult):
        return value
    if isinstance(value, dict):
        return ThreadReconcileResult.model_validate(value)
    if isinstance(raw, ThreadReconcileResult):
        return raw
    if isinstance(raw, dict):
        return ThreadReconcileResult.model_validate(raw)
    raise ValueError(f"unexpected structured result shape: {type(raw).__name__}")


async def _final_invites(session: AsyncSession, application: Application) -> dict[str, EmailInvite]:
    from services.email.invites import group_chains, resolve_final

    invites = (
        await session.exec(select(EmailInvite).where(EmailInvite.application_id == application.id))
    ).all()
    finals: dict[str, EmailInvite] = {}
    for (uid, _rid), chain in group_chains(list(invites)).items():
        final = resolve_final(chain)
        if final is not None:
            finals[uid] = final
    return finals


def _to_derived(r, finals_by_uid: dict[str, EmailInvite]) -> DerivedRound:
    """Resolve a thread-pass round onto the calendar axis: the container is
    the final invite whose date matches; its TZ interprets the stated time."""
    kind = (r.kind or "").strip().lower()
    if kind not in ROUND_KINDS:
        kind, title = "other", (r.title or r.kind or None)
    else:
        title = r.title
    if title and r.interviewer and r.interviewer.lower() not in title.lower():
        title = f"{title} — {r.interviewer}"
    elif not title and r.interviewer:
        title = r.interviewer

    scheduled_at: datetime | None = None
    invite_uid: str | None = None
    raw_minutes: int | None = None
    parsed_date = None
    if r.date:
        try:
            parsed_date = datetime.strptime(r.date.strip(), "%Y-%m-%d").date()
        except ValueError:
            parsed_date = None
    if r.time:
        try:
            hh, mm = (int(x) for x in r.time.strip().split(":", 1))
            raw_minutes = hh * 60 + mm
        except (ValueError, TypeError):
            raw_minutes = None
    if parsed_date is not None:
        for uid, final in finals_by_uid.items():
            starts = _aware_utc(final.starts_at)
            ends = _aware_utc(final.ends_at) or starts
            if starts is None:
                continue
            tz = _safe_zone(final.tz)
            if (
                starts.astimezone(tz).date()
                <= parsed_date
                <= (ends or starts).astimezone(tz).date()
            ):
                invite_uid = uid
                break
        if invite_uid is None and raw_minutes is not None:
            # Containerless dated round: the stated time interprets in the
            # host's local tz (same bounded posture as the schedule panel).
            local = datetime.combine(parsed_date, datetime.min.time()).astimezone()
            scheduled_at = local.replace(
                hour=raw_minutes // 60, minute=raw_minutes % 60
            ).astimezone(UTC)

    state = r.state if r.state in ("planned", "scheduled", "completed") else "planned"
    return DerivedRound(
        kind=kind,
        title=title,
        interviewer=r.interviewer,
        state=state,
        scheduled_at=scheduled_at,
        invite_uid=invite_uid,
        raw_minutes=raw_minutes,
    )


def _safe_zone(name: str | None):
    if name:
        try:
            return ZoneInfo(name)
        except Exception:  # noqa: BLE001
            pass
    return UTC


def _anchor_container_times(derived: list[DerivedRound], finals_by_uid: dict) -> None:
    """Resolve container rounds' times without trusting a timezone guess.

    Email prose states clock times in whatever tz the sender/Gmail rendered
    (the Headway subject says GMT-4 while its invite's TZID is
    America/Los_Angeles); the container's START is unambiguous UTC ground
    truth. So: the earliest stated segment anchors to the container start
    and the others keep their stated offsets. No stated times → every rider
    sits at the container start. Deterministic post-check: a round whose
    resolved time is in the future can never be "completed"."""
    now = datetime.now(UTC)
    by_uid: dict[str, list[DerivedRound]] = {}
    for d in derived:
        if d.invite_uid:
            by_uid.setdefault(d.invite_uid, []).append(d)
    for uid, group in by_uid.items():
        final = finals_by_uid.get(uid)
        start = _aware_utc(final.starts_at) if final is not None else None
        if start is None:
            continue
        timed = [d.raw_minutes for d in group if d.raw_minutes is not None]
        base = min(timed) if timed else None
        for d in group:
            offset = (
                (d.raw_minutes - base) if (base is not None and d.raw_minutes is not None) else 0
            )
            d.scheduled_at = start + timedelta(minutes=offset)
    for d in derived:
        if (
            d.state == "planned"
            and d.scheduled_at is not None
            or d.state == "completed"
            and d.scheduled_at is not None
            and d.scheduled_at > now
        ):
            d.state = "scheduled"


# ── 3. Adopt/rewrite rounds (owner decision 2026-07-08) ─────────────────


async def _apply_derived_rounds(
    session: AsyncSession, application: Application, derived: list[DerivedRound]
) -> int:
    """Fold the itemized interviews into the round table.

    Adopt/rewrite-in-place (owner): a derived interview upgrades an existing
    row — same kind riding the same container first, then the container's
    generic rider, then a generic dateless legacy row — instead of siblinging
    it; only unmatched interviews create rows (via the 95d upsert). Never
    deletes. Converges: a second run with the same derivation matches the
    rows it wrote and changes nothing.
    """
    from services import applications as applications_service

    rounds = await applications_service.list_rounds(session, application_id=application.id or 0)
    consumed: set[int] = set()
    touched = 0
    now = datetime.now(UTC)

    def _match(d: DerivedRound):
        pools = []
        if d.invite_uid:
            # Same kind riding the same calendar event — the exact row.
            pools.append(
                [
                    r
                    for r in rounds
                    if r.kind == d.kind and r.invite_uid == d.invite_uid and r.state != "cancelled"
                ]
            )
            # Then the container's generic 96d rider — an itemized interview
            # UPGRADES it before any uidless same-kind row is considered
            # (adopting a stray same-kind row while the container still
            # holds a generic rider is how duplicates were born).
            pools.append(
                [
                    r
                    for r in rounds
                    if r.invite_uid == d.invite_uid and r.kind == "other" and r.state != "cancelled"
                ]
            )
        # Same kind, not riding a DIFFERENT event.
        pools.append(
            [
                r
                for r in rounds
                if r.kind == d.kind
                and r.state != "cancelled"
                and (r.invite_uid is None or r.invite_uid == d.invite_uid)
            ]
        )
        # A generic dateless legacy row (pre-invite email extraction).
        pools.append(
            [
                r
                for r in rounds
                if r.kind == "other"
                and r.invite_uid is None
                and r.scheduled_at is None
                and r.state not in ("cancelled", "completed")
            ]
        )
        for pool in pools:
            for r in pool:
                if r.id not in consumed:
                    return r
        return None

    for d in derived:
        row = _match(d)
        if row is None:
            new_row = await applications_service.upsert_round(
                session,
                application=application,
                kind=d.kind,
                source="email",
                title=d.title,
                state=d.state,
                scheduled_at=d.scheduled_at,
                invite_uid=d.invite_uid,
            )
            rounds = await applications_service.list_rounds(
                session, application_id=application.id or 0
            )
            consumed.add(new_row.id or -1)
            touched += 1
            continue

        consumed.add(row.id or -1)
        changed = False
        was_generic = row.kind == "other"
        if was_generic and d.kind != "other":
            row.kind = d.kind
            changed = True
        if d.title and (not row.title or was_generic) and row.title != d.title:
            row.title = d.title
            changed = True
        if d.invite_uid and row.invite_uid is None:
            row.invite_uid = d.invite_uid
            changed = True
        if d.scheduled_at is not None and row.state != "completed":
            current = _aware_utc(row.scheduled_at)
            if current != d.scheduled_at:
                row.scheduled_at = d.scheduled_at
                changed = True
        state_rank = {"planned": 0, "scheduled": 1, "completed": 2, "cancelled": 0}
        row_time = _aware_utc(row.scheduled_at)
        if state_rank.get(d.state, 0) > state_rank.get(row.state, 0):
            if d.state == "completed" and row_time is not None and row_time > now:
                # A round whose resolved time is in the FUTURE cannot have
                # completed, whatever a dateless derivation claims.
                if row.state == "planned":
                    row.state = "scheduled"
                    changed = True
            else:
                row.state = d.state
                if d.state == "completed":
                    row.outcome = row.outcome or "pending"
                changed = True
        elif (
            row.state == "completed"
            and row.outcome in (None, "pending")
            and d.state == "scheduled"
            and _aware_utc(row.scheduled_at) is not None
            and _aware_utc(row.scheduled_at) > now
        ):
            # Repair, not ratchet: a FUTURE round can't have completed — an
            # earlier hallucinated "completed" (no human outcome recorded)
            # downgrades to what the evidence supports.
            row.state = "scheduled"
            row.outcome = None
            changed = True
        if changed:
            row.updated_at = now
            session.add(row)
            touched += 1

    if touched:
        await applications_service.resequence_rounds(session, application_id=application.id or 0)
    return touched


# ── 4. Stage diff (forward-only, pin-gated, CLOSED human-confirm) ───────


async def _apply_stage(
    session: AsyncSession,
    application: Application,
    *,
    llm_stage: str | None,
    llm_rejection: bool,
    result: ReconcileResult,
) -> None:
    from services import applications as applications_service
    from services.applications.pins import auto_transition_allowed, get_status_pin
    from services.email.status_mapper import status_for_email_timeline

    messages = (
        await session.exec(
            select(EmailMessage)
            .where(
                EmailMessage.application_id == application.id,
                EmailMessage.classification.is_not(None),  # type: ignore[union-attr]
            )
            .order_by(EmailMessage.received_at.asc())
        )
    ).all()
    # OTHER never evidences a stage — a mislinked newsletter must not move
    # the pipeline (FOLLOW_UP receipts DO baseline APPLIED, per 96a).
    signal = [m for m in messages if m.classification != EmailClassification.OTHER]
    timeline = [(m.classification, m.extracted_stage) for m in signal if m.classification]
    if not timeline and llm_stage is None and not llm_rejection:
        return  # zero evidence — a reconcile must never invent a move
    target: ApplicationStatus | None = None
    if timeline:
        target, _closed_reason = status_for_email_timeline(timeline)
    if llm_stage in _STAGE_TARGETS:
        llm_target = _STAGE_TARGETS[llm_stage]
        if target != ApplicationStatus.CLOSED and (
            target is None or _RANK.get(llm_target, 0) > _RANK.get(target, 0)
        ):
            target = llm_target
    if llm_rejection and target != ApplicationStatus.OFFER:
        target = ApplicationStatus.CLOSED
    if target is None:
        return

    current = application.status
    if current == ApplicationStatus.CLOSED:
        return  # rule 4 — CLOSED is absolute; reopening is a human act
    if target == ApplicationStatus.CLOSED:
        # Asymmetric autonomy: the reconciler never closes — it makes the
        # rejection visible as a pending suggestion (strip + card chip).
        if current != ApplicationStatus.OFFER:
            result.status_suggested = await _ensure_suggestion(
                session, application, messages, target
            )
        return
    if current not in _RANK or _RANK.get(target, 0) <= _RANK[current]:
        return

    if auto_transition_allowed(application, target):
        if current == ApplicationStatus.DRAFT and application.applied_at is None and signal:
            # Leaving DRAFT on email evidence: the funnel date is when the
            # company first wrote, not reconcile time (96a deviation 5).
            application.applied_at = signal[0].received_at
            session.add(application)
        await applications_service.update_status(
            session,
            application.id,
            target,
            notes="Reconciled from all email/invite evidence",
            trigger=StatusChangeTrigger.RECONCILED,
        )
        result.status_moved = True
        return

    # Rule 5 — a pin-suppressed move is recorded, never silently swallowed.
    result.status_suggested = await _ensure_suggestion(session, application, messages, target)
    if result.status_suggested:
        await _emit_suggested_event(
            session,
            application,
            target,
            suppressed_by_pin=get_status_pin(application) is not None,
        )


async def _ensure_suggestion(
    session: AsyncSession,
    application: Application,
    messages: list[EmailMessage],
    target: ApplicationStatus,
) -> bool:
    """Anchor a pending suggestion on the newest signal message — the strip
    and card chip read `EmailMessage.suggested_status`. No-op when an
    unresolved suggestion for the same target already exists (idempotence)."""
    if application.status == target:
        return False
    for m in messages:
        if (
            m.suggested_status == target
            and m.suggestion_applied_at is None
            and m.suggestion_dismissed_at is None
        ):
            return False  # already pending — nothing new to say
    # Prefer the newest message whose classification actually argues for the
    # target (the strip shows its subject as evidence); fall back to the
    # newest unresolved message.
    relevant = (
        {EmailClassification.REJECTION}
        if target == ApplicationStatus.CLOSED
        else {
            EmailClassification.INTERVIEW_REQUEST,
            EmailClassification.ASSESSMENT,
            EmailClassification.OFFER,
        }
    )
    unresolved = [
        m
        for m in reversed(messages)
        if m.suggestion_applied_at is None and m.suggestion_dismissed_at is None
    ]
    anchor = next((m for m in unresolved if m.classification in relevant), None) or next(
        iter(unresolved), None
    )
    if anchor is None:
        return False
    anchor.suggested_status = target
    anchor.suggested_at = datetime.now(UTC)
    session.add(anchor)
    return True


async def _emit_suggested_event(
    session: AsyncSession,
    application: Application,
    target: ApplicationStatus,
    *,
    suppressed_by_pin: bool,
) -> None:
    from models import AppEvent

    session.add(
        AppEvent(
            user_id=application.user_id,
            application_id=application.id,
            kind=AppEventKind.EMAIL_STATUS_SUGGESTED,
            payload={
                "source": "reconcile",
                "current_status": application.status.value,
                "suggested_status": target.value,
                "reason": "Reconciled from all email/invite evidence",
                "applied": False,
                "dismissed": False,
                "suppressed_by_pin": suppressed_by_pin,
            },
            occurred_at=datetime.now(UTC),
        )
    )
    await session.flush()
