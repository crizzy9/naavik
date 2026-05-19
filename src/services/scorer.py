"""Scorer — Wave 6 ships the deterministic visa filter.

Per BACKEND.md § H.1 + plan 10 § C.1 + plan 27 § D.5. Full tag-matching +
gap analysis is Phase 3 (plan 12).

The visa filter is deterministic + LLM-free: any job that requires US
citizenship or a Green Card is forced to score 0.0 when the candidate's
profile says they need sponsorship now (`VisaSponsorship.NEEDED_NOW`).
Auto-apply consumes this score, so without the filter the cron would
auto-submit visa-incompatible jobs at non-zero LLM scores — embarrassing
failure mode.

Plan 27 (0.2.0.05) promoted `Job.visa_restrictions` from `str | None` to
typed `VisaRestriction` enum. The blocking set is now enum-typed too.
"""

from __future__ import annotations

import logging

from llm.prompts.score_job import JobScore
from models import Job, Profile, VisaRestriction, VisaSponsorship

log = logging.getLogger(__name__)

# Visa-restriction enum values that zero out the score when the candidate
# needs sponsorship. Per plan 27 § D.5 (4-value VisaRestriction enum).
_BLOCKING_RESTRICTIONS = frozenset(
    {VisaRestriction.US_CITIZEN_ONLY, VisaRestriction.GREEN_CARD_REQUIRED}
)


def needs_visa_zero_out(profile: Profile, job: Job) -> bool:
    """True iff the visa filter must zero this job's score.

    Trips when:
    - `Profile.visa_sponsorship_needed == NEEDED_NOW`, AND
    - `Job.visa_restrictions ∈ {US_CITIZEN_ONLY, GREEN_CARD_REQUIRED}`
    """
    if profile is None or job is None:
        return False
    if profile.visa_sponsorship_needed != VisaSponsorship.NEEDED_NOW:
        return False
    restriction = getattr(job, "visa_restrictions", None)
    if restriction is None:
        return False
    # Accept either VisaRestriction enum or its string value (defensive at
    # this boundary because Job dicts from in-memory shadows + LLM output
    # both flow through here).
    if isinstance(restriction, str):
        try:
            restriction = VisaRestriction(restriction.strip().lower())
        except ValueError:
            return False
    return restriction in _BLOCKING_RESTRICTIONS


def apply_visa_filter(score: JobScore, profile: Profile, job: Job) -> JobScore:
    """Return a `JobScore` with `score=0.0` iff the visa filter trips.

    Preserves the LLM's `matched_tags` + `gaps` for transparency, but
    flips `visa_concern=True` and overwrites `score` to 0.0.
    """
    if not needs_visa_zero_out(profile, job):
        return score
    return JobScore(
        score=0.0,
        explanation=(
            "Visa filter: job requires US citizenship / green card; "
            "candidate needs sponsorship now."
        ),
        matched_tags=list(score.matched_tags),
        gaps=list(score.gaps),
        visa_concern=True,
    )
