"""Email → inferred application tracking — item 5 (2026-07).

The inbox becomes a source of truth: application-confirmation receipts
("thanks for applying", ATS receipt patterns from Greenhouse / Lever /
Ashby / Workday / LinkedIn, plus a generic phrase net) turn into:

1. a link to the EXISTING application when the company already matches —
   so a job you applied to yourself starts receiving email-signal status
   updates the moment the receipt lands;
2. else a proposed Application (status APPLIED, applied_at = email date)
   attached to a matching library Job when one exists (fuzzy company +
   role-token match);
3. else a brand-new library Job — scraped for real when the receipt
   carries a posting URL, created from email metadata with
   `source=email` otherwise — plus the proposed Application.

Proposed applications carry `submission_artifacts["inferred"]`
(`confirmed: false`) and stay OUT of the pipeline board until the user
confirms them in Tracking (human-confirm seam, same posture as the plan 90
status suggestions). Dismissal soft-deletes the application; the Job stays
in the library.

Deterministic on purpose — receipts are template emails; regex beats an
LLM here on both cost and reliability, and inference keeps working with
no provider configured.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    AppEvent,
    AppEventKind,
    Application,
    ApplicationStatus,
    DocsState,
    EmailMessage,
    EmailThread,
    Job,
    RecruiterState,
    ReferralState,
    StatusChangeTrigger,
)
from models.enums import ApplicationBoard, JobSource

log = logging.getLogger(__name__)

UNKNOWN_ROLE = "Unknown role (from email receipt)"


@dataclass(slots=True)
class ReceiptHit:
    board: ApplicationBoard
    company: str | None
    role: str | None
    posting_url: str | None


_SENDER_BOARDS: tuple[tuple[str, ApplicationBoard], ...] = (
    ("greenhouse.io", ApplicationBoard.GREENHOUSE),
    ("greenhouse-mail.io", ApplicationBoard.GREENHOUSE),
    ("lever.co", ApplicationBoard.LEVER),
    ("ashbyhq.com", ApplicationBoard.ASHBY),
    ("myworkday.com", ApplicationBoard.WORKDAY),
    ("workday.com", ApplicationBoard.WORKDAY),
    ("linkedin.com", ApplicationBoard.LINKEDIN),
    ("indeed.com", ApplicationBoard.INDEED),
)

# Generic receipt phrasing — matched against subject + snippet, lowercased.
_RECEIPT_PHRASES = (
    "thank you for applying",
    "thanks for applying",
    "thank you for your application",
    "your application was sent",
    "your application has been received",
    "we received your application",
    "we've received your application",
    "we have received your application",
    "application received",
    "your application to",
    "thank you for your interest in the",
)

# Combined role-at-company shape (Ashby et al): "applying to the
# Staff Engineer, Backend Systems role at Lightfield!" — role may contain
# commas, so it gets its own permissive capture before the generic
# company patterns run.
_ROLE_AT_COMPANY = re.compile(
    r"(?:applying|application|interest in) (?:to |for |in )?(?:the )?"
    r"(?P<role>.+?) (?:role|position|opening) at (?P<company>[^!.,\n]+)",
    re.I,
)

# Company extractors, tried in order against the SUBJECT.
_COMPANY_PATTERNS = (
    re.compile(r"(?:thank you|thanks) for applying to (?P<company>[^!.,\n]+)", re.I),
    re.compile(r"your application (?:was sent to|to) (?P<company>[^!.,\n]+)", re.I),
    re.compile(r"application to (?P<company>[^!.,\n]+) (?:was received|has been received)", re.I),
    re.compile(
        r"thank you for your interest in the .+? (?:role|position) at (?P<company>[^!.,\n]+)",
        re.I,
    ),
    re.compile(
        r"we(?:'ve| have)? received your application (?:to|at) (?P<company>[^!.,\n]+)", re.I
    ),
)

# Role extractors — subject first, then snippet.
_ROLE_PATTERNS = (
    re.compile(r"applying (?:to|for) the (?P<role>[^!.,\n]+?) (?:role|position|opening)", re.I),
    re.compile(r"your application for (?:the )?(?P<role>[^!.,\n]+?) (?:role|position|at)", re.I),
    re.compile(r"interest in the (?P<role>[^!.,\n]+?) (?:role|position)", re.I),
    re.compile(r"you applied to (?P<role>[^!.,\n]+?) at ", re.I),
    re.compile(r"application (?:to|for) the (?P<role>[^!.,\n]+?) (?:role|position)", re.I),
)

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
# Posting-URL hosts worth a real scrape (receipt links to the ad itself).
_POSTING_URL_HINTS = (
    "boards.greenhouse.io",
    "jobs.lever.co",
    "jobs.ashbyhq.com",
    "myworkdayjobs.com",
    "/jobs/",
    "/careers/",
)


def _sender_board(sender_email: str) -> ApplicationBoard | None:
    domain = sender_email.rsplit("@", 1)[-1].lower()
    for suffix, board in _SENDER_BOARDS:
        if domain == suffix or domain.endswith("." + suffix):
            return board
    return None


def _clean_capture(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().strip("\"'“”").rstrip(" -–|")
    # Receipts love trailing boilerplate ("... team"); keep it bounded.
    return cleaned[:120] or None


def _company_capture(value: str | None) -> str | None:
    """Company-specific sanity net: "your application to the Senior
    Software Engineer role" must NOT yield company="the Senior Software
    Engineer role" (human replies phrase it this way without an
    "at <company>" tail)."""
    cleaned = _clean_capture(value)
    if cleaned is None:
        return None
    lowered = cleaned.lower()
    if lowered.startswith("the ") or lowered.endswith((" role", " position", " opening", " team")):
        return None
    return cleaned


_GENERIC_MAIL_DOMAINS = frozenset(
    {"gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com", "icloud.com"}
)


def _company_from_sender(sender_email: str) -> str | None:
    """Last-resort company guess for direct-from-company receipts
    (kris@onoai.io → "Onoai"). Never fires for ATS or generic domains."""
    domain = sender_email.rsplit("@", 1)[-1].lower()
    if not domain or domain in _GENERIC_MAIL_DOMAINS or _sender_board(sender_email) is not None:
        return None
    root = domain.split(".")[0]
    if len(root) < 3:
        return None
    return root.capitalize()


def detect_receipt(*, sender_email: str, subject: str, snippet: str | None) -> ReceiptHit | None:
    """Deterministic application-receipt detector. None = not a receipt."""
    subject = subject or ""
    haystack = f"{subject}\n{snippet or ''}"
    lower = haystack.lower()
    board = _sender_board(sender_email or "")
    phrase_hit = any(p in lower for p in _RECEIPT_PHRASES)
    if not phrase_hit:
        # Known ATS sender alone isn't enough — they also send rejections,
        # interview invites, marketing. The phrase is the receipt signal.
        return None

    company = None
    role = None
    combo = _ROLE_AT_COMPANY.search(subject) or _ROLE_AT_COMPANY.search(haystack)
    if combo:
        role = _clean_capture(combo.group("role"))
        company = _company_capture(combo.group("company"))
    for pattern in _COMPANY_PATTERNS:
        if company:
            break
        m = pattern.search(subject) or pattern.search(haystack)
        if m:
            company = _company_capture(m.group("company"))
    if company is None:
        company = _company_from_sender(sender_email or "")

    for pattern in _ROLE_PATTERNS:
        if role:
            break
        m = pattern.search(subject) or pattern.search(haystack)
        if m:
            role = _clean_capture(m.group("role"))

    posting_url = None
    for m in _URL_RE.finditer(haystack):
        candidate = m.group(0)
        if any(hint in candidate.lower() for hint in _POSTING_URL_HINTS):
            posting_url = candidate
            break

    return ReceiptHit(
        board=board or ApplicationBoard.COMPANY_DIRECT,
        company=company,
        role=role,
        posting_url=posting_url,
    )


# ── Matching ────────────────────────────────────────────────────────────


def _norm(text: str | None) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).strip()


def _company_matches(candidate: str, target: str) -> bool:
    a, b = _norm(candidate), _norm(target)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _role_overlaps(candidate: str | None, target: str | None) -> bool:
    a = set(_norm(candidate).split()) - {"the", "a", "an", "of"}
    b = set(_norm(target).split()) - {"the", "a", "an", "of"}
    if not a or not b:
        return True  # unknown role never blocks a company match
    return len(a & b) >= min(2, len(a), len(b))


async def _find_existing_application(
    session: AsyncSession, *, user_id: int, company: str
) -> Application | None:
    rows = (
        await session.exec(
            select(Application)
            .where(
                Application.user_id == user_id,
                Application.deleted_at.is_(None),
                Application.status != ApplicationStatus.DRAFT,
            )
            .order_by(Application.updated_at.desc())
        )
    ).all()
    for application in rows:
        if _company_matches(company, application.company):
            return application
    return None


async def _find_library_job(
    session: AsyncSession, *, user_id: int, company: str, role: str | None
) -> Job | None:
    rows = (
        await session.exec(
            select(Job)
            .where(Job.user_id == user_id, Job.deleted_at.is_(None))
            .order_by(Job.found_at.desc())
        )
    ).all()
    for job in rows:
        if _company_matches(company, job.company) and _role_overlaps(role, job.role):
            return job
    return None


# ── Creation ────────────────────────────────────────────────────────────


async def _create_job_from_receipt(
    session: AsyncSession,
    *,
    user_id: int,
    msg: EmailMessage,
    hit: ReceiptHit,
) -> Job:
    """Library Job for a receipt that matched nothing. Posting URL → the
    real add-by-URL pipeline (guard → fetch → LLM extract → upsert);
    metadata-only receipts land as `source=email` rows."""
    from services import job_service

    if hit.posting_url:
        try:
            job = await _scrape_posting_url(session, user_id=user_id, url=hit.posting_url)
            if job is not None:
                return job
        except Exception as exc:  # noqa: BLE001 — degrade to the metadata row
            log.warning("receipt posting-URL scrape failed (%s); metadata row", exc)

    import hashlib

    external_id = (
        f"email-{hashlib.sha1(f'{msg.id}:{msg.message_id_external}'.encode()).hexdigest()[:12]}"
    )
    job, _created = await job_service.upsert_job(
        session,
        user_id=user_id,
        source=JobSource.EMAIL,
        external_id=external_id,
        raw={
            "board": hit.board,
            "url": f"manual://email/{msg.id}",
            "url_type": "email_receipt",
            "company": hit.company or "Unknown company",
            "role": hit.role or UNKNOWN_ROLE,
            "description": (
                f"Inferred from the application-confirmation email "
                f"“{msg.subject}” received {msg.received_at:%Y-%m-%d}. "
                "No posting URL was present — edit this job to attach one."
            ),
        },
    )

    # No posting URL in the receipt — probe the company's public ATS board
    # (the receipt names the board) for the real posting: canonical link +
    # full JD instead of a one-sentence stub. Best-effort; the row above is
    # already a valid fallback.
    try:
        from services import jd_enrichment
        from services import resolution as apply_site_resolver

        resolved = await apply_site_resolver.resolve_job(job)
        apply_site_resolver.apply_resolution(job, resolved)
        if resolved.apply_url and (resolved.description_html or resolved.description_text):
            jd_enrichment.maybe_apply_discovered_description(job, resolved)
            job.url = resolved.apply_url
            job.url_type = "ats"
        session.add(job)
        await session.flush()
    except Exception as exc:  # noqa: BLE001 — enrichment must not sink the receipt
        log.info("inferred-job ATS discovery failed for job %s: %s", job.id, exc)
    return job


async def _scrape_posting_url(session: AsyncSession, *, user_id: int, url: str) -> Job | None:
    """The real add-by-URL pipeline, headless (mirrors the Discover modal)."""
    import hashlib

    from llm import LLMProviderError, get_provider
    from scraper.crawl4ai_client import Crawl4AIClient
    from scraper.types import RawJob
    from scraper.url_guard import is_safe_destination
    from services import job_service, settings_service
    from services.job_extractor import enrich_raw_job

    safe, reason = is_safe_destination(url)
    if not safe:
        log.info("receipt posting URL rejected (%s): %s", reason, url)
        return None
    client = Crawl4AIClient(rate_limit_per_minute=30.0, random_delay_seconds=(0.0, 0.1))
    html = await client.fetch_html(url)
    if not html:
        return None
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    page_title = (title_match.group(1).strip()[:160] if title_match else "") or "Unknown role"
    seed_role, seed_company = page_title, "Unknown"
    for sep in (" | ", " – ", " — ", " - ", " · "):
        if sep in page_title:
            left, right = page_title.split(sep, 1)
            seed_role = left.strip() or "Unknown role"
            seed_company = right.strip() or "Unknown"
            break
    external_id = f"email-{hashlib.sha1(url.encode()).hexdigest()[:12]}"
    raw_job = RawJob(
        source=JobSource.EMAIL,
        external_id=external_id,
        source_url=url,
        board=ApplicationBoard.MANUAL,
        url_type="email_receipt",
        company_name=seed_company,
        position_title=seed_role,
        description_html=html,
    )
    settings = await settings_service.get_or_create(session, user_id=user_id)
    try:
        provider = get_provider(settings)
        raw_job = await enrich_raw_job(session, user_id=user_id, provider=provider, raw_job=raw_job)
    except LLMProviderError:
        pass
    job, _created = await job_service.upsert_job(
        session,
        user_id=user_id,
        source=JobSource.EMAIL,
        external_id=external_id,
        raw=raw_job.to_upsert_payload(),
    )
    return job


async def _create_inferred_application(
    session: AsyncSession,
    *,
    user_id: int,
    job: Job,
    msg: EmailMessage,
) -> Application:
    now = datetime.now(UTC)
    application = Application(
        user_id=user_id,
        job_id=job.id,
        company=job.company,
        role=job.role,
        team=job.team,
        location=job.location,
        board=job.board,
        external_url=job.url if not job.url.startswith("manual://") else None,
        status=ApplicationStatus.APPLIED,
        docs_state=DocsState.NONE,
        referral_state=ReferralState.NONE,
        recruiter_state=RecruiterState.NONE,
        applied_at=msg.received_at,
        submission_artifacts={
            "inferred": {
                "email_message_id": msg.id,
                "confirmed": False,
                "inferred_at": now.isoformat(),
                "subject": (msg.subject or "")[:200],
            }
        },
        created_at=now,
        updated_at=now,
    )
    session.add(application)
    await session.flush()
    session.add(
        AppEvent(
            user_id=user_id,
            application_id=application.id,
            kind=AppEventKind.STATUS_CHANGE,
            occurred_at=now,
            payload={
                "from": None,
                "to": ApplicationStatus.APPLIED.value,
                "trigger": StatusChangeTrigger.AUTO_FROM_EMAIL.value,
                "inferred_from_email": msg.id,
            },
            actor="email_application_inference",
        )
    )
    return application


def is_unconfirmed_inferred(application: Application) -> bool:
    artifacts = getattr(application, "submission_artifacts", None) or {}
    inferred = artifacts.get("inferred")
    return isinstance(inferred, dict) and not inferred.get("confirmed", False)


# ── Entry points ────────────────────────────────────────────────────────


async def infer_from_message(session: AsyncSession, msg: EmailMessage) -> Application | None:
    """Process one message. Returns the newly created proposed Application,
    or None (not a receipt / linked to an existing application)."""
    now = datetime.now(UTC)
    msg.inference_processed_at = now
    session.add(msg)

    hit = detect_receipt(sender_email=msg.sender_email, subject=msg.subject, snippet=msg.snippet)
    if hit is None:
        return None

    company = hit.company
    if company is None:
        # A receipt with no parseable company can't be matched or created
        # honestly — leave it classified but uninferred.
        log.info("receipt without company (msg %s): %r", msg.id, msg.subject)
        return None

    # 1. Existing application → just link (status signals start flowing).
    existing = await _find_existing_application(session, user_id=msg.user_id, company=company)
    if existing is not None:
        msg.application_id = existing.id
        thread = await session.get(EmailThread, msg.thread_id)
        if thread is not None and thread.application_id is None:
            thread.application_id = existing.id
            session.add(thread)
        session.add(msg)
        await session.flush()
        log.info("receipt linked to existing application %s (%s)", existing.id, company)
        return None

    # 2. Library job → proposed application on it.
    job = await _find_library_job(session, user_id=msg.user_id, company=company, role=hit.role)

    # 3. Nothing known → create the Job (scrape when a URL is present).
    if job is None:
        job = await _create_job_from_receipt(session, user_id=msg.user_id, msg=msg, hit=hit)

    application = await _create_inferred_application(session, user_id=msg.user_id, job=job, msg=msg)
    msg.application_id = application.id
    thread = await session.get(EmailThread, msg.thread_id)
    if thread is not None and thread.application_id is None:
        thread.application_id = application.id
        session.add(thread)
    session.add(msg)
    await session.flush()
    log.info(
        "inferred application %s from receipt (company=%s role=%s job=%s)",
        application.id,
        company,
        hit.role,
        job.id,
    )
    return application


async def infer_unprocessed(session: AsyncSession, *, limit: int = 100) -> int:
    """Cron entry — examine messages the detector hasn't seen. Returns the
    number of NEW proposed applications created."""
    rows = (
        await session.exec(
            select(EmailMessage)
            .where(
                EmailMessage.inference_processed_at.is_(None),
                EmailMessage.application_id.is_(None),
            )
            .order_by(EmailMessage.received_at.desc())
            .limit(limit)
        )
    ).all()
    created = 0
    for msg in rows:
        try:
            if await infer_from_message(session, msg) is not None:
                created += 1
        except Exception as exc:  # noqa: BLE001 — one bad message never stalls the cron
            log.warning("inference failed for message %s: %s", msg.id, exc)
    return created


async def list_unconfirmed(session: AsyncSession, *, user_id: int) -> list[Application]:
    rows = (
        await session.exec(
            select(Application)
            .where(
                Application.user_id == user_id,
                Application.deleted_at.is_(None),
                Application.status == ApplicationStatus.APPLIED,
            )
            .order_by(Application.created_at.desc())
        )
    ).all()
    return [a for a in rows if is_unconfirmed_inferred(a)]


async def confirm(session: AsyncSession, *, user_id: int, application_id: int) -> bool:
    application = await session.get(Application, application_id)
    if (
        application is None
        or application.user_id != user_id
        or not is_unconfirmed_inferred(application)
    ):
        return False
    artifacts = dict(application.submission_artifacts or {})
    inferred = dict(artifacts.get("inferred") or {})
    inferred["confirmed"] = True
    inferred["confirmed_at"] = datetime.now(UTC).isoformat()
    artifacts["inferred"] = inferred
    application.submission_artifacts = artifacts
    application.updated_at = datetime.now(UTC)
    session.add(application)
    await session.flush()
    return True


async def dismiss(session: AsyncSession, *, user_id: int, application_id: int) -> bool:
    """Soft-delete the proposed application. The library Job stays."""
    application = await session.get(Application, application_id)
    if (
        application is None
        or application.user_id != user_id
        or not is_unconfirmed_inferred(application)
    ):
        return False
    now = datetime.now(UTC)
    application.deleted_at = now
    application.updated_at = now
    session.add(application)
    await session.flush()
    return True
