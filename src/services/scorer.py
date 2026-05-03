"""Scorer — Wave 6 ships the deterministic visa filter.

Per BACKEND.md § H.1 + plan 10 § C.1. Full tag-matching + gap analysis is
Phase 3 (plan 12).

The visa filter is deterministic + LLM-free: any job that requires US
citizenship or a Green Card is forced to score 0.0 when the candidate's
profile says they need sponsorship now (`VisaSponsorship.NEEDED_NOW`).
Auto-apply consumes this score, so without the filter the cron would
auto-submit visa-incompatible jobs at non-zero LLM scores — embarrassing
failure mode.
"""

from __future__ import annotations

import logging

from llm.prompts.score_job import JobScore
from models import Job, Profile, VisaSponsorship

log = logging.getLogger(__name__)

# Visa-restriction strings the scraper writes to `Job.visa_restrictions`.
# These two are the categorical "no sponsorship" markers.
_BLOCKING_RESTRICTIONS = frozenset({"us_citizen_only", "green_card_required"})


def needs_visa_zero_out(profile: Profile, job: Job) -> bool:
    """True iff the visa filter must zero this job's score.

    Trips when:
    - `Profile.visa_sponsorship_needed == NEEDED_NOW`, AND
    - `Job.visa_restrictions ∈ {us_citizen_only, green_card_required}`
    """
    if profile is None or job is None:
        return False
    if profile.visa_sponsorship_needed != VisaSponsorship.NEEDED_NOW:
        return False
    restriction = (job.visa_restrictions or "").strip().lower()
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
