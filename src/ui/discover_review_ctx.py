"""Context builder for /discover/{job_id} (Discover · review & apply)."""

from __future__ import annotations

from db import sample_data as sd
from db.sample_data_models import Application, Job
from ui.discover_ctx import _initial_color, _salary_range

COVER_LABELS = {
    "intro": "INTRO",
    "body": "BODY",
    "why_company": "WHY COMPANY",
    "close": "CLOSE",
}

# Module-level mutable shim — stub edits persist for server-process lifetime.
COVER_SECTION_TEXT: dict[str, str] = {
    "intro": (
        "I've spent the last five years owning ML personalization at Intuit, "
        "and the constraint surface you're tackling at Stripe Atlas is exactly "
        "the kind of problem I want to land on next."
    ),
    "body": (
        "At Intuit I shipped a personalization platform from prototype to "
        "production for 100M+ users, lifting homepage CTR by 23% and recovering "
        "$4.2M in annual revenue based on lift-tested A/B reads. The work spanned "
        "feature pipelines (Airflow), ranking models (PyTorch), and online "
        "inference (Go) — and most importantly, the stand-up of an evaluation "
        "harness that got adopted across three sister teams."
    ),
    "why_company": (
        "Stripe Atlas is the rare team building developer infrastructure that "
        "actually changes founder behavior. Investing in ranking + retrieval at "
        "this stage is the bet I'd make myself."
    ),
    "close": (
        "Happy to chat anytime — would love to hear how the team thinks about "
        "platform investment vs shipping product surface area."
    ),
}


async def tailored_bullet_groups() -> list[dict[str, object]]:
    """Group bullets by experience for the middle column. The first 7 are
    'selected for this resume'; the rest 'excluded with reason'.
    """
    experiences = await sd.get_experiences()
    out = []
    selected_count = 7
    seen = 0
    for e in experiences:
        bullets = await sd.get_bullets_for_experience(e.id)
        rows = []
        for b in bullets:
            seen += 1
            is_selected = seen <= selected_count
            chips = ["jd", "personalization", "scale"] if is_selected else ["older role"]
            rows.append(
                {
                    "id": b.id,
                    "selected": is_selected,
                    "trimmed_line": b.text if not is_selected else _trim(b.text),
                    "chips": chips,
                    "tags": [t.value for t in b.tags],
                }
            )
        out.append(
            {
                "header": f"{e.company} · {e.title} · {e.start_date.year}–"
                f"{(e.end_date.year if e.end_date else 'Present')}",
                "rows": rows,
            }
        )
    return out


def _trim(text: str, max_chars: int = 160) -> str:
    if len(text) <= max_chars:
        return text
    head = text[:max_chars]
    return head.rsplit(" ", 1)[0] + "…"


async def build_review_ctx(
    *, job: Job, application: Application | None, eager: bool
) -> dict[str, object]:
    """Build the full Discover · review template context."""
    initial, color = _initial_color(job.company)

    # Right column tabs default
    sections = [
        {"id": "intro", "label": COVER_LABELS["intro"], "text": COVER_SECTION_TEXT["intro"]},
        {"id": "body", "label": COVER_LABELS["body"], "text": COVER_SECTION_TEXT["body"]},
        {
            "id": "why_company",
            "label": COVER_LABELS["why_company"],
            "text": COVER_SECTION_TEXT["why_company"],
        },
        {"id": "close", "label": COVER_LABELS["close"], "text": COVER_SECTION_TEXT["close"]},
    ]

    warm_intro = None
    if job.warm_intro_contact_id:
        c = await sd.get_contact(job.warm_intro_contact_id)
        if c:
            warm_intro = {
                "name": c.name,
                "title": c.title,
                "company": c.company,
                "linkedin_degree": c.linkedin_degree or "1st",
            }

    # Screener answers
    screener_views = []
    unreviewed = 0
    if application:
        rows = await sd.screener_answers_for_application(application.id)
        for s in rows:
            if s.required and s.reviewed_at is None:
                unreviewed += 1
            screener_views.append(
                {
                    "id": s.id,
                    "question": s.question_text,
                    "body": s.answer or "(awaiting AI draft)",
                    "source": s.source.value,
                    "reviewed_at": s.reviewed_at,
                }
            )

    # Failure banner — shown when the DRAFT carries last_failure
    failure = None
    if application and application.submission_artifacts:
        failure = application.submission_artifacts.get("last_failure")

    return {
        "job": {
            "id": job.id,
            "company": job.company,
            "company_initial": initial,
            "company_color": color,
            "role": job.role,
            "team": job.team,
            "location": job.location,
            "salary_range": _salary_range(job),
            "equity_pct": job.equity_pct,
            "jd_url": job.url,
            "score": int(round(job.score * 100)),
            "match_breakdown": job.match_breakdown,
            "match_overall": job.score,
            "jd_bullets": job.criteria[:5] if job.criteria else [],
            "description": job.description,
            "board_label": (job.board.value if job.board else "manual"),
        },
        "application": {
            "id": application.id if application else None,
            "docs_state": (application.docs_state.value if application else "none"),
        }
        if application
        else None,
        "eager": eager,
        "warm_intro": warm_intro,
        "tailored_bullet_groups": await tailored_bullet_groups() if application else [],
        "cover_sections": sections,
        "screener_answers": screener_views,
        "unreviewed_count": unreviewed,
        "failure": failure,
        "cost_estimate_usd": 0.07,
    }
