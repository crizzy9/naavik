"""Few-shot exemplar block from owner corrections — plan 95 § 3.4.2 (95f).

Per-user personalization WITHOUT training anything: the K most recent
`ClassificationCorrection` rows whose sender-domain or subject-shape matches
the email being classified render as precedents in the classify prompt.

Privacy contract (owner condition, 2026-07-07): exemplars carry the sender
DOMAIN only — never the full address — and subject/snippet run through the
deterministic `pii_scrub` before entering any prompt. `assert_no_addresses`
is the belt the eval harness (and unit tests) buckle over the result.
"""

from __future__ import annotations

import logging
import re

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import ClassificationCorrection, EmailMessage
from services.email.pii_scrub import scrub
from services.email.sender_rules import sender_domain

log = logging.getLogger(__name__)

MAX_EXEMPLARS = 5
_SNIPPET_CAP = 160
_CANDIDATE_POOL = 40  # recent corrections scanned for a match
_STOPWORDS = frozenset(
    {"re", "fwd", "the", "your", "for", "at", "a", "an", "of", "to", "with", "and", "on", "in"}
)


def _subject_tokens(subject: str | None) -> set[str]:
    return {
        t for t in re.sub(r"[^a-z0-9 ]", " ", (subject or "").lower()).split() if len(t) > 2
    } - _STOPWORDS


def assert_no_addresses(block: str) -> None:
    """Loud guard: a raw @-address in an exemplar block is a bug, not a
    formatting nit — fail before the prompt leaves the machine."""
    if "@" in block:
        raise ValueError("few-shot exemplar block leaked a raw @-address")


async def build_few_shot_block(
    session: AsyncSession,
    *,
    user_id: int,
    sender_email: str,
    subject: str,
    k: int = MAX_EXEMPLARS,
) -> str:
    """Render the "Owner corrections" prompt block, or "" when no correction
    matches the incoming email's sender-domain or subject shape."""
    rows = (
        await session.exec(
            select(ClassificationCorrection, EmailMessage)
            .join(EmailMessage, EmailMessage.id == ClassificationCorrection.message_id)  # type: ignore[arg-type]
            .where(
                ClassificationCorrection.user_id == user_id,
                ClassificationCorrection.kind == "reclassify",
                ClassificationCorrection.to_classification.is_not(None),  # type: ignore[union-attr]
            )
            .order_by(ClassificationCorrection.corrected_at.desc())
            .limit(_CANDIDATE_POOL)
        )
    ).all()
    if not rows:
        return ""

    domain = sender_domain(sender_email)
    tokens = _subject_tokens(subject)
    exemplars: list[str] = []
    for correction, msg in rows:
        if len(exemplars) >= k:
            break
        msg_domain = sender_domain(msg.sender_email)
        domain_match = bool(domain) and msg_domain == domain
        shape_match = len(tokens & _subject_tokens(msg.subject)) >= 2
        if not (domain_match or shape_match):
            continue
        exemplars.append(
            f"- From domain: {msg_domain or '[unknown]'}\n"
            f"  Subject: {scrub(msg.subject)[:120]}\n"
            f"  Snippet: {scrub(msg.snippet)[:_SNIPPET_CAP]}\n"
            f"  Correct classification: {correction.to_classification}"
        )
    if not exemplars:
        return ""
    block = (
        "\nOwner corrections — follow these precedents (the owner manually "
        "fixed earlier mistakes on similar emails):\n" + "\n".join(exemplars) + "\n"
    )
    assert_no_addresses(block)
    return block
