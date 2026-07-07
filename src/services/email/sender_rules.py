"""Sender treatment rules — plan 95 § 3.3.

Three layers that fail independently, in strict precedence order:

    user `SenderRule` row  >  deterministic seed  >  LLM `sender_type` guess

- User rules are ground truth ("Flag sender…"): deterministic, auditable,
  reversible. Checked before any LLM judgment is applied.
- Seeds are a small static list of known staffing / platform / outplacement
  domains. They sit BELOW user rules, so flagging a seeded domain as
  "Actually an employer" permanently overrides the seed (this is also why
  they live in code rather than as deletable rows: a user override is an
  explicit rule, never a re-seedable gap).
- The LLM's `sender_type` is the default judgment when neither layer fires.

Treatment semantics:
- `agency`  — park: the sender is an intermediary; its mail never becomes a
  detected process (an explicitly named end-client still does).
- `ignore`  — not job-related: classification forced to OTHER, extraction
  cleared, never grouped.
- `employer`— the sender IS the hiring company; overrides agency guesses.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import ClassificationCorrection, EmailMessage, SenderRule
from models.enums import EmailClassification
from services.email.inference import canonical_company_key

log = logging.getLogger(__name__)

# Sender types that PARK — mail from these never opens a detected process
# unless it names an end-client (plan 95 § 3.3).
PARKED_SENDER_TYPES = frozenset({"agency_recruiter", "platform", "outplacement"})

SENDER_TYPE_VOCAB = frozenset(
    {"employer", "ats", "agency_recruiter", "platform", "outplacement", "other"}
)

# Deterministic seeds (plan 95 § 3.3 item 3) — known staffing / platform /
# outplacement domains from the owner's inbox plus the usual suspects.
SEED_DOMAIN_TREATMENTS: dict[str, str] = {
    "g2i.co": "agency",
    "camopeople.com": "agency",
    "risesmart.com": "agency",  # Intuit-side outplacement
    "randstadrisesmart.com": "agency",
    "hired.com": "agency",
    "triplebyte.com": "agency",
    "roberthalf.com": "agency",
    "randstad.com": "agency",
    "adeccogroup.com": "agency",
    "kforce.com": "agency",
    "insightglobal.com": "agency",
    "teksystems.com": "agency",
}


class SenderRuleError(Exception):
    """Validation failure — routes map this to 422."""


def sender_domain(sender_email: str) -> str:
    return (sender_email or "").rsplit("@", 1)[-1].strip().lower()


def _domain_matches(domain: str, rule_value: str) -> bool:
    return domain == rule_value or domain.endswith("." + rule_value)


async def load_rules(session: AsyncSession, *, user_id: int) -> list[SenderRule]:
    return list((await session.exec(select(SenderRule).where(SenderRule.user_id == user_id))).all())


def treatment_for(
    rules: list[SenderRule],
    *,
    sender_email: str,
    company: str | None = None,
) -> str | None:
    """Resolve the treatment for one message. `rules` from `load_rules`
    (loaded once per batch — the classifier ticks over up to 100 rows)."""
    domain = sender_domain(sender_email)
    if domain:
        for rule in rules:
            if rule.matcher == "domain" and _domain_matches(domain, rule.value):
                return rule.treatment
    if company:
        key = canonical_company_key(company)
        for rule in rules:
            if rule.matcher == "company_key" and rule.value == key:
                return rule.treatment
    if domain:
        for seed_domain, treatment in SEED_DOMAIN_TREATMENTS.items():
            if _domain_matches(domain, seed_domain):
                return treatment
    return None


def apply_treatment(msg: EmailMessage, treatment: str | None) -> None:
    """Mutate one message per the resolved treatment (idempotent)."""
    if treatment == "agency":
        msg.extracted_sender_type = "agency_recruiter"
    elif treatment == "employer":
        msg.extracted_sender_type = "employer"
        msg.extracted_end_client = None
    elif treatment == "ignore":
        msg.classification = EmailClassification.OTHER
        msg.extracted_company = None
        msg.extracted_role = None
        msg.extracted_stage = None
        msg.extracted_end_client = None
        msg.extracted_sender_type = "other"


async def flag_sender(
    session: AsyncSession,
    *,
    user_id: int,
    domain: str,
    treatment: str,
    from_message_id: int | None = None,
) -> int:
    """ "Flag sender…" — persist the rule and retroactively re-treat the
    domain's already-classified mail. Returns messages affected.

    Retroactivity is the point: a flag must fix the CURRENT panel, not just
    future syncs ("a flag permanently overrides model judgment for that
    domain").
    """
    domain = sender_domain(f"@{domain}" if "@" not in domain else domain)
    if not domain or "." not in domain:
        raise SenderRuleError("Not a valid sender domain")
    if treatment not in ("agency", "ignore", "employer"):
        raise SenderRuleError("Unknown treatment")

    existing = (
        await session.exec(
            select(SenderRule).where(
                SenderRule.user_id == user_id,
                SenderRule.matcher == "domain",
                SenderRule.value == domain,
            )
        )
    ).one_or_none()
    if existing is not None:
        existing.treatment = treatment
        existing.is_seed = False
        session.add(existing)
    else:
        session.add(
            SenderRule(
                user_id=user_id,
                matcher="domain",
                value=domain,
                treatment=treatment,
                created_from_message_id=from_message_id,
            )
        )

    rows = (
        await session.exec(
            select(EmailMessage)
            .where(
                EmailMessage.user_id == user_id,
                EmailMessage.classification.is_not(None),
            )
            .order_by(EmailMessage.received_at.asc())
        )
    ).all()
    affected = [m for m in rows if _domain_matches(sender_domain(m.sender_email), domain)]
    company_before = affected[-1].extracted_company if affected else None
    for msg in affected:
        apply_treatment(msg, treatment)
        msg.updated_at = datetime.now(UTC)
        session.add(msg)

    if affected:
        session.add(
            ClassificationCorrection(
                user_id=user_id,
                message_id=(from_message_id or affected[-1].id or 0),
                kind="flag_sender",
                from_classification=None,
                to_classification=None,
                from_company=company_before,
                to_company=None,
            )
        )
    await session.flush()
    log.info("sender rule %s → %s (retro-applied to %d messages)", domain, treatment, len(affected))
    return len(affected)
