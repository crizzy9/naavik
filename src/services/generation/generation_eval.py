"""Generation evaluation harness — item 9 (2026-07).

Scores every generated bundle against the house guidelines so quality
regressions are visible instead of vibes:

- Deterministic checks (free, always run): exactly one page; contact-line
  completeness; every bullet within the one-line budget; no blocklisted
  AI-tell phrases; first-person cover letter; parse-fidelity + keyword
  coverage surfaced from the trace.
- LLM-judge rubric (ONE tracked call per bundle, skipped without a
  provider): ATS-friendliness, JD keyword usage, honesty vs profile, tone.

The scorecard persists into `Application.generation_trace["eval_scorecard"]`
and renders in the review workspace as a quality chip. `scripts/eval_generation.py`
runs the same evaluation standalone over seeded applications so prompt
changes can be compared before/after.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from llm import LLMProviderError, get_provider
from models import Application, GeneratedDocumentKind, Job, Settings
from services import llm_tracker
from services.generation.ai_tell_blocklist import BAKED_IN_BLOCKLIST

log = logging.getLogger(__name__)

EVAL_SCHEMA_VERSION = 1

# ── Deterministic checks ────────────────────────────────────────────────


def check_one_page(page_count: int | None) -> dict[str, Any]:
    return {
        "passed": page_count == 1,
        "value": page_count,
        "detail": "resume must be exactly one page",
    }


def check_contact_line(pdf_text: str | None, profile) -> dict[str, Any]:
    """Every populated contact field must survive into the PDF text."""
    if not pdf_text:
        return {"passed": None, "value": None, "detail": "pdf text unavailable (pdfplumber)"}
    expected = {
        "email": profile.email,
        "phone": profile.phone,
        "location": profile.location,
        "linkedin": profile.linkedin_handle,
        "github": profile.github_handle,
        "portfolio": profile.portfolio_url,
    }
    flat = re.sub(r"\s+", " ", pdf_text)
    missing = [
        name
        for name, value in expected.items()
        if value and str(value).replace("https://", "").split("?")[0] not in flat
    ]
    return {
        "passed": not missing,
        "value": missing,
        "detail": "contact line carries phone, email, location, linkedin, github, portfolio",
    }


def check_bullets_one_line(trimmed_lines: dict[str, str], budget: int) -> dict[str, Any]:
    over = {k: len(v) for k, v in trimmed_lines.items() if len(v) > budget}
    return {
        "passed": not over,
        "value": over,
        "detail": f"every rendered bullet within the {budget}-char one-line budget",
    }


def check_no_ai_tells(texts: list[str]) -> dict[str, Any]:
    corpus = " ".join(texts).lower()
    found = sorted(
        {term for term in BAKED_IN_BLOCKLIST if re.search(r"\b" + re.escape(term) + r"\b", corpus)}
    )
    if re.search(r"[‒–—―]", " ".join(texts)):
        found.append("em-dash")
    return {
        "passed": not found,
        "value": found,
        "detail": "no blocklisted AI-tell phrases in bullets/summary/cover",
    }


def check_cover_first_person(sections: dict[str, str] | None, full_name: str) -> dict[str, Any]:
    if not sections or not any((v or "").strip() for v in sections.values()):
        return {"passed": None, "value": None, "detail": "no cover letter generated"}
    body = " ".join(str(v) for v in sections.values())
    has_first_person = bool(re.search(r"\b(I|I'm|I've|my|me)\b", body))
    # The letter is FROM the candidate — their own name mid-letter reads as
    # third-person template output ("Shyam has 7 years of...").
    name_tokens = [t for t in (full_name or "").split() if len(t) > 2]
    third_person = [t for t in name_tokens if re.search(r"\b" + re.escape(t) + r"\b", body)]
    passed = has_first_person and not third_person
    return {
        "passed": passed,
        "value": {"first_person": has_first_person, "name_mentions": third_person},
        "detail": "letter speaks in first person, never about the candidate by name",
    }


def surfaced_trace_scores(trace: dict[str, Any]) -> dict[str, Any]:
    return {
        "parse_fidelity": trace.get("parse_fidelity_score"),
        "keyword_coverage": trace.get("keyword_coverage_score"),
        "keyword_coverage_missing": trace.get("keyword_coverage_missing") or [],
        "burstiness_std": trace.get("burstiness_std"),
    }


# ── LLM judge ───────────────────────────────────────────────────────────

JUDGE_PROMPT = """You are auditing ONE generated job-application bundle (resume lines +
cover letter) against the candidate's REAL profile and the job description.

Job description (excerpt):
{job_text}

Candidate's real profile bullets (source of truth):
{profile_bullets}

Generated resume lines:
{resume_lines}

Generated cover letter:
{cover_text}

Score each dimension 0.0-1.0 (be strict — 1.0 means flawless):
- ats_friendliness: plain phrasing, standard section vocabulary, no
  graphics-dependent meaning, keywords appear in natural sentences.
- jd_keyword_usage: the JD's actual terminology appears where truthful;
  not keyword stuffing.
- honesty_vs_profile: every generated claim traces to a real profile
  bullet. Any invented metric, tool, or scope inflation caps this at 0.3
  and MUST be quoted in `violations`.
- tone: confident, concrete, human; no filler or AI boilerplate.

Return BundleJudgeScore with the four scores, `violations` (quotes of any
dishonest/invented claims, empty if none), and `notes` (≤300 chars, the
single most useful improvement).
"""


class BundleJudgeScore(BaseModel):
    ats_friendliness: float = Field(ge=0.0, le=1.0)
    jd_keyword_usage: float = Field(ge=0.0, le=1.0)
    honesty_vs_profile: float = Field(ge=0.0, le=1.0)
    tone: float = Field(ge=0.0, le=1.0)
    violations: list[str] = Field(default_factory=list, max_length=8)
    notes: str = Field(default="", max_length=400)


async def _judge_bundle(
    session: AsyncSession,
    *,
    settings: Settings,
    user_id: int,
    application_id: int,
    job_text: str,
    profile_bullets: list[str],
    resume_lines: list[str],
    cover_text: str,
) -> dict[str, Any] | None:
    try:
        provider = get_provider(settings)
    except LLMProviderError:
        return None
    prompt = JUDGE_PROMPT.format(
        job_text=job_text[:2400],
        profile_bullets="\n".join(f"- {b}" for b in profile_bullets)[:4000],
        resume_lines="\n".join(f"- {line}" for line in resume_lines)[:4000],
        cover_text=cover_text[:2400],
    )
    try:
        result = await llm_tracker.tracked_call(
            session=session,
            user_id=user_id,
            provider=provider,
            method="structured",
            prompt_name="eval_bundle_judge",
            application_id=application_id,
            prompt=prompt,
            schema=BundleJudgeScore,
        )
        judged = BundleJudgeScore.model_validate(result.value)
    except (LLMProviderError, Exception) as exc:  # noqa: BLE001 — eval never blocks generation
        log.warning("bundle judge failed: %s", exc)
        return None
    return judged.model_dump()


# ── Entry point ─────────────────────────────────────────────────────────


def _extract_pdf_text(path: str | None) -> str | None:
    if not path:
        return None
    try:
        import pdfplumber
    except Exception:  # noqa: BLE001 — optional dependency, degrade honestly
        return None
    try:
        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as exc:  # noqa: BLE001
        log.warning("eval pdf extract failed for %s: %s", path, exc)
        return None


async def evaluate_bundle(
    session: AsyncSession,
    application: Application,
    *,
    settings: Settings,
    run_judge: bool = True,
) -> dict[str, Any] | None:
    """Score the application's latest generated bundle. Returns the
    scorecard dict (also written into `generation_trace["eval_scorecard"]`
    by the caller), or None when nothing has been generated."""
    from services import generation as dg

    resume_doc = await dg._latest_error_free_doc(
        session, application.id, GeneratedDocumentKind.RESUME
    )
    if resume_doc is None or not resume_doc.bullet_selection:
        return None
    cover_doc = await dg._latest_error_free_doc(
        session, application.id, GeneratedDocumentKind.COVER_LETTER
    )
    snap = await dg.load_profile_snapshot(session, application.user_id)
    if snap is None:
        return None
    job = None
    if application.job_id is not None:
        job = (await session.exec(select(Job).where(Job.id == application.job_id))).one_or_none()

    blob = dict(resume_doc.bullet_selection)
    trimmed_lines = {str(k): str(v) for k, v in (blob.get("trimmed_lines") or {}).items()}
    selected_ids = {str(b) for b in (blob.get("selected_ids") or [])}
    rendered_lines = [v for k, v in trimmed_lines.items() if k in selected_ids] or list(
        trimmed_lines.values()
    )
    summary = str(blob.get("summary") or "")
    sections = (
        {k: str(v) for k, v in (cover_doc.bullet_selection or {}).get("sections", {}).items()}
        if cover_doc is not None and cover_doc.bullet_selection
        else None
    )
    cover_text = " ".join(sections.values()) if sections else ""
    pdf_text = _extract_pdf_text(resume_doc.path)
    trace = dict(getattr(application, "generation_trace", None) or {})

    deterministic = {
        "one_page": check_one_page(resume_doc.page_count),
        "contact_line": check_contact_line(pdf_text, snap.profile),
        "bullets_one_line": check_bullets_one_line(
            {k: v for k, v in trimmed_lines.items() if k in selected_ids} or trimmed_lines,
            dg.RESUME_BULLET_LINE_CAPACITY,
        ),
        "no_ai_tells": check_no_ai_tells([*rendered_lines, summary, cover_text]),
        "cover_first_person": check_cover_first_person(sections, snap.profile.full_name),
    }
    hard_checks = [c for c in deterministic.values() if c["passed"] is not None]
    passed_count = sum(1 for c in hard_checks if c["passed"])

    judge = None
    if run_judge:
        judge = await _judge_bundle(
            session,
            settings=settings,
            user_id=application.user_id,
            application_id=application.id,
            job_text=(job.description or job.description_html or "") if job else "",
            profile_bullets=[b.text for b in dg._bullet_inventory(snap)][:30],
            resume_lines=[*rendered_lines, summary],
            cover_text=cover_text,
        )

    scorecard: dict[str, Any] = {
        "schema_version": EVAL_SCHEMA_VERSION,
        "deterministic": deterministic,
        "deterministic_passed": passed_count,
        "deterministic_total": len(hard_checks),
        "trace_scores": surfaced_trace_scores(trace),
        "judge": judge,
    }
    return scorecard
