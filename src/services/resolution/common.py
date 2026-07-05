"""Shared constants + the facade accessor for the resolution package.

Plan 91 Phase 4.5 / plan 92 teardown. `svc()` resolves the
`services.resolution` package surface at call time so
`patch.object(resolver, "X")` seams keep intercepting internal calls.
"""

from __future__ import annotations

import re
from datetime import timedelta

from models import ApplicationBoard


def svc():
    """The `services.resolution` package surface, resolved at call time."""
    from services import resolution

    return resolution


_FETCH_TIMEOUT = 12.0
_MAX_REDIRECTS = 5
_TITLE_MATCH_THRESHOLD = 0.72
# Two postings scoring within this of the winner is a tie the title match can't
# break — the caller should prefer an authoritative source over the guess.
_AMBIGUITY_EPS = 0.02

# Unresolved targets ("external"/"unknown" with no apply_url) walk this backoff
# ladder instead of dying silently: attempt N schedules retry N+1 after
# _RETRY_BACKOFF[N-1]; the attempt that hits MAX and still can't resolve
# terminalizes as via="exhausted" (surfaced in the UI with a manual-paste path).
MAX_RESOLVE_ATTEMPTS = 5
_RETRY_BACKOFF = (
    timedelta(hours=1),
    timedelta(hours=4),
    timedelta(hours=24),
    timedelta(hours=72),
)
# Sweep slots held back from fresh jobs when retries are due, so a heavy
# scrape day can't starve the retry queue indefinitely.
_RETRY_RESERVE = 2

# UI labels double as the closed vocabulary for `Job.apply_kind`.
APPLY_KIND_LABELS: dict[str, str] = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "workday": "Workday",
    "icims": "iCIMS",
    "smartrecruiters": "SmartRecruiters",
    "taleo": "Taleo",
    "bamboohr": "BambooHR",
    "recruitee": "Recruitee",
    "jobvite": "Jobvite",
    "breezy": "Breezy",
    "workable": "Workable",
    "easy_apply": "Easy Apply",
    "company_site": "Company site",
    "external": "External site",
    "unknown": "",  # honest: no chip when we could not classify
}

# Host-pattern → kind. Checked in order; first match wins.
_ATS_HOST_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("greenhouse", re.compile(r"(?:^|\.)greenhouse\.io$|^grnh\.se$")),
    ("lever", re.compile(r"^jobs\.(?:eu\.)?lever\.co$")),
    ("ashby", re.compile(r"^jobs\.ashbyhq\.com$")),
    ("workday", re.compile(r"\.myworkdayjobs\.com$|\.myworkdaysite\.com$")),
    ("icims", re.compile(r"\.icims\.com$")),
    ("smartrecruiters", re.compile(r"^(?:jobs|careers)\.smartrecruiters\.com$")),
    ("taleo", re.compile(r"\.taleo\.net$")),
    ("bamboohr", re.compile(r"\.bamboohr\.com$")),
    ("recruitee", re.compile(r"\.recruitee\.com$")),
    ("jobvite", re.compile(r"^jobs\.jobvite\.com$")),
    ("breezy", re.compile(r"\.breezy\.hr$")),
    ("workable", re.compile(r"^(?:apply|jobs)\.workable\.com$")),
)

# Kinds that map to an ApplicationBoard — resolution promotes Job.board so
# adapter dispatch + SUPPORTED_AUTO_SUBMIT_BOARDS gating follow the truth.
_KIND_TO_BOARD: dict[str, ApplicationBoard] = {
    "greenhouse": ApplicationBoard.GREENHOUSE,
    "lever": ApplicationBoard.LEVER,
    "ashby": ApplicationBoard.ASHBY,
    "workday": ApplicationBoard.WORKDAY,
    "easy_apply": ApplicationBoard.LINKEDIN,
    "company_site": ApplicationBoard.COMPANY_DIRECT,
}

_LINKEDIN_DETAIL_BASE = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/"

# Legal/noise suffixes stripped before slug candidates are built.
_COMPANY_NOISE = re.compile(
    r"\b(?:inc|llc|ltd|corp|corporation|co|gmbh|technologies|technology)\b\.?", re.IGNORECASE
)
