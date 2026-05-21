"""Keyword coverage validator — plan 66 (0.3.1) § T8.

Scans the top-30% of the resume text for each JD must-have keyword. ATS
parsers (Workday/Greenhouse/Lever) weight matches near the top of the
document — bullet-2 of experience-1 carries more weight than line-30 of
projects.

Coverage = fraction of must-haves found in the top-30% by line count.
Threshold = 0.75 (`Settings.parse_fidelity_threshold` mirrors this default).

Returns a structured report so the orchestrator can decide:
- `≥ threshold`: pass silently.
- `[0.50, threshold)`: surface a warning chip to the user.
- `< 0.50`: trigger one re-selection cycle with explicit "include
  bullets containing missing keywords: <list>" instruction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_WORD_TOKEN = re.compile(r"[a-zA-Z][a-zA-Z'+-]+")


@dataclass(slots=True)
class CoverageReport:
    """Per-resume keyword-coverage signal.

    `score` ∈ [0.0, 1.0]; fraction of must-haves found in the top
    `top_pct` of the resume. `top_section_text` is the substring scanned
    (debugging aid; not surfaced to the user).
    """

    score: float
    found_keywords: list[str]
    missing_keywords: list[str]
    top_section_text: str = field(default="")
    threshold: float = 0.75


def _normalize_keyword(kw: str) -> str:
    """Lowercase + collapse whitespace. Empty inputs return ''."""
    return " ".join(kw.lower().strip().split())


def _select_top_section(resume_lines: list[str], top_pct: float = 0.30) -> str:
    """Concatenate the first `ceil(top_pct * len)` non-empty lines."""
    non_empty = [line for line in resume_lines if line.strip()]
    if not non_empty:
        return ""
    cutoff = max(1, int(len(non_empty) * top_pct + 0.5))
    return "\n".join(non_empty[:cutoff])


def compute_coverage(
    jd_must_haves: list[str],
    resume_text: str,
    *,
    top_pct: float = 0.30,
    threshold: float = 0.75,
) -> CoverageReport:
    """Compute keyword coverage over `resume_text`.

    `jd_must_haves` comes from `JobScore.matched_tags` ∪ `Job.skills_required[:5]`
    (top 5; the rest are nice-to-haves per T8). Caller decides what counts.
    """
    if not jd_must_haves:
        return CoverageReport(
            score=1.0,
            found_keywords=[],
            missing_keywords=[],
            top_section_text="",
            threshold=threshold,
        )
    if not resume_text:
        return CoverageReport(
            score=0.0,
            found_keywords=[],
            missing_keywords=[_normalize_keyword(kw) for kw in jd_must_haves if kw],
            top_section_text="",
            threshold=threshold,
        )

    lines = resume_text.splitlines()
    top_section = _select_top_section(lines, top_pct=top_pct)
    top_lower = top_section.lower()

    found: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()
    for raw_kw in jd_must_haves:
        kw = _normalize_keyword(raw_kw)
        if not kw or kw in seen:
            continue
        seen.add(kw)
        # Whole-word match; multi-word keywords accepted as substrings.
        if " " in kw:
            present = kw in top_lower
        else:
            present = re.search(r"\b" + re.escape(kw) + r"\b", top_lower) is not None
        if present:
            found.append(kw)
        else:
            missing.append(kw)

    total = len(found) + len(missing)
    score = (len(found) / total) if total else 1.0
    return CoverageReport(
        score=round(score, 3),
        found_keywords=found,
        missing_keywords=missing,
        top_section_text=top_section,
        threshold=threshold,
    )
