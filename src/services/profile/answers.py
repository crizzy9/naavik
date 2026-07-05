"""ProfileAnswer reuse cache — plan 61 (0.2.7.14).

Per-user reuse offering for substantially-equivalent screener questions.
Fingerprint algorithm = exact-normalized v1 (lowercase + strip punctuation
+ remove curated company tokens + Porter-stem + SHA-1 prefix) per
decision D6. Semantic fingerprint deferred to 0.8.0.

Per AGENTS.md § Key Conventions § DB:
- AsyncSession everywhere
- No raw SQL in route handlers
- Per-user scoping enforced on every read (decision D8)
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import ApplicationScreenerAnswer, ProfileAnswer

log = logging.getLogger(__name__)

# Static curated blocklist of company / brand tokens that screener wording
# routinely embeds. Stripping these collapses paraphrase like "Why Acme?"
# vs "Why XYZ?" onto the same fingerprint key. The list is conservative —
# only universally non-content tokens. Operators can extend via the
# `company_name` arg to `fingerprint()`.
_COMPANY_TOKEN_BLOCKLIST: frozenset[str] = frozenset(
    {
        "inc",
        "incorporated",
        "llc",
        "corp",
        "corporation",
        "co",
        "company",
        "ltd",
        "limited",
        "the",
        "our",
        "this",
        "us",
        "we",
    }
)

# Minimal Porter-ish stemmer — strips a handful of common English suffixes.
# Full Porter requires nltk; for v1 we keep it dependency-free.
_STEM_SUFFIXES: tuple[str, ...] = (
    "ational",
    "tional",
    "ization",
    "ation",
    "ness",
    "ment",
    "ity",
    "ous",
    "ive",
    "ies",
    "ing",
    "ed",
    "es",
    "ly",
    "s",
)

_PUNCT_RE = re.compile(r"[^\w\s]+")
_WS_RE = re.compile(r"\s+")


def _porter_stem(token: str) -> str:
    """Strip the longest matching suffix; minimal length floor of 4."""
    if len(token) <= 3:
        return token
    for suffix in _STEM_SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def fingerprint(question_text: str, *, company_name: str | None = None) -> str:
    """Deterministic v1 fingerprint over a screener question.

    Lowercase → strip punctuation → collapse whitespace → tokenize → remove
    curated company tokens (+ caller-supplied `company_name` tokens) →
    minimal-Porter stem → SHA-1 prefix.

    Pure function. Reproducible across hosts + processes. Returns a 40-char
    lowercase hex string (SHA-1 full hex) for collision space safety; the
    DB column caps at 256 chars so future algorithm-version prefixes fit.
    """
    text = (question_text or "").lower()
    text = _PUNCT_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()

    extra_blocklist: set[str] = set()
    if company_name:
        normalized = _PUNCT_RE.sub(" ", company_name.lower())
        extra_blocklist.update(t for t in normalized.split() if t)

    tokens: list[str] = []
    for raw in text.split():
        if raw in _COMPANY_TOKEN_BLOCKLIST or raw in extra_blocklist:
            continue
        tokens.append(_porter_stem(raw))

    canonical = " ".join(tokens)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


async def get_suggestion(
    session: AsyncSession,
    *,
    user_id: int,
    question_text: str,
    company_name: str | None = None,
) -> ProfileAnswer | None:
    """Find a prior answer with a fingerprint match for this user.

    Increments `times_offered` on hit (best-effort flush — never raises).
    Per-user only (decision D8) — `user_id` is a hard filter on the SELECT.
    """
    fp = fingerprint(question_text, company_name=company_name)
    stmt = select(ProfileAnswer).where(
        ProfileAnswer.user_id == user_id,
        ProfileAnswer.question_fingerprint == fp,
    )
    row = (await session.exec(stmt)).one_or_none()
    if row is None:
        return None

    row.times_offered = (row.times_offered or 0) + 1
    row.updated_at = datetime.now(UTC)
    session.add(row)
    try:
        await session.flush()
    except Exception as exc:  # noqa: BLE001
        log.warning("profile_answer times_offered bump failed: %s", exc)
    return row


async def record_acceptance(
    session: AsyncSession,
    *,
    user_id: int,
    profile_answer_id: int,
) -> bool:
    """Bump `times_accepted` + `last_used_at` when user accepts the draft.

    Returns True if a row was found + updated; False on IDOR mismatch or
    missing id (caller can map to 404). Per-user scoped (decision D8).
    """
    stmt = select(ProfileAnswer).where(
        ProfileAnswer.id == profile_answer_id,
        ProfileAnswer.user_id == user_id,
    )
    row = (await session.exec(stmt)).one_or_none()
    if row is None:
        return False
    now = datetime.now(UTC)
    row.times_accepted = (row.times_accepted or 0) + 1
    row.last_used_at = now
    row.updated_at = now
    session.add(row)
    await session.flush()
    return True


async def upsert_from_screener_answer(
    session: AsyncSession,
    *,
    user_id: int,
    screener_answer: ApplicationScreenerAnswer,
    company_name: str | None = None,
) -> ProfileAnswer | None:
    """Persist (or refresh) a ProfileAnswer row derived from a reviewed screener.

    Called by `application_service.submit_draft` AFTER a successful submission.
    Last-write-wins on `(user_id, question_fingerprint)` collisions.

    Guards:
    - `screener_answer.answer` must be non-empty (no-op otherwise).
    - `user_id` is required + must come from the caller's owner check — this
      function does not re-derive it from the application row (decision D8).

    Returns the persisted row, or None when guards short-circuit.
    """
    if not screener_answer.answer or not screener_answer.answer.strip():
        return None
    if screener_answer.id is None:
        # New (un-flushed) screener answer — caller should flush first.
        return None

    fp = fingerprint(screener_answer.question_text, company_name=company_name)
    stmt = select(ProfileAnswer).where(
        ProfileAnswer.user_id == user_id,
        ProfileAnswer.question_fingerprint == fp,
    )
    row = (await session.exec(stmt)).one_or_none()
    now = datetime.now(UTC)
    if row is None:
        row = ProfileAnswer(
            user_id=user_id,
            question_fingerprint=fp,
            question_text_sample=screener_answer.question_text[:1024],
            answer=screener_answer.answer[:8192],
            source_screener_answer_id=screener_answer.id,
            times_offered=0,
            times_accepted=0,
            last_used_at=now,
        )
    else:
        row.question_text_sample = screener_answer.question_text[:1024]
        row.answer = screener_answer.answer[:8192]
        row.source_screener_answer_id = screener_answer.id
        row.last_used_at = now
        row.updated_at = now
    session.add(row)
    await session.flush()
    return row


async def list_recent(
    session: AsyncSession,
    *,
    user_id: int,
    limit: int = 50,
) -> list[ProfileAnswer]:
    """Most-recently-used ProfileAnswers for a user.

    Per-user scoped (decision D8). Used by future Settings · Profile Answers
    debug panel.
    """
    stmt = (
        select(ProfileAnswer)
        .where(ProfileAnswer.user_id == user_id)
        .order_by(ProfileAnswer.last_used_at.desc())
        .limit(limit)
    )
    return list((await session.exec(stmt)).all())


async def delete_answer(
    session: AsyncSession,
    *,
    user_id: int,
    profile_answer_id: int,
) -> bool:
    """User-initiated deletion. Returns True on success, False on IDOR / 404."""
    stmt = select(ProfileAnswer).where(
        ProfileAnswer.id == profile_answer_id,
        ProfileAnswer.user_id == user_id,
    )
    row = (await session.exec(stmt)).one_or_none()
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True
