"""Context builder for /discover/{job_id} (Discover · review & apply)."""

from __future__ import annotations

from sqlmodel.ext.asyncio.session import AsyncSession

from models import Application, Job
from services import application_service, contact_tracker, profile_service
from ui.discover_ctx import _initial_color, _salary_range

COVER_LABELS = {
    "intro": "INTRO",
    "body": "BODY",
    "why_company": "WHY COMPANY",
    "close": "CLOSE",
}

# Cover-letter section text is now sourced from the real generated document
# (`application_service.get_latest_cover_sections`). The prior module-level
# hardcoded Intuit/Stripe placeholder was removed — it rendered fake content
# into every job's review workspace. `_EMPTY_COVER_SECTIONS` is the honest
# empty state shown before generation runs.
_EMPTY_COVER_SECTIONS: dict[str, str] = {
    "intro": "",
    "body": "",
    "why_company": "",
    "close": "",
}


def _bullet_tags(b) -> list[str]:
    return [t.value if hasattr(t, "value") else str(t) for t in (b.tags or [])]


def _rationale_index_from_trace(
    application: Application | None,
) -> dict[int, dict[str, object]]:
    """Project `generation_trace.bullet_selection_log` into a per-bullet rationale map.

    Plan 72 § Surface 2 — bundle_generator writes
    `bullet_selection_log: list[{bullet_id, selected, why_selected, why_dropped}]`
    onto `Application.generation_trace`. We index by bullet_id so the row
    builder can look up rationale in O(1) without re-iterating the log.

    Returns an empty dict when the application has no trace yet (lazy path),
    no log key (legacy bundles pre-plan-72), or a malformed entry — the
    template guards via `{% if rationale %}` so the row degrades gracefully.
    """
    if application is None:
        return {}
    # Defensive — sample_data Application rows don't pass the generation_trace
    # kwarg, so SQLModel/Pydantic raises AttributeError on plain attribute
    # access. `getattr(..., None)` makes the read tolerant for legacy and
    # fixture-only Applications (graceful degrade — UI renders without ledger).
    trace = getattr(application, "generation_trace", None) or {}
    log = trace.get("bullet_selection_log") or []
    out: dict[int, dict[str, object]] = {}
    for entry in log:
        if not isinstance(entry, dict):
            continue
        bid = entry.get("bullet_id")
        try:
            bid_int = int(bid) if bid is not None else None
        except (TypeError, ValueError):
            continue
        if bid_int is None:
            continue
        out[bid_int] = {
            "selected": bool(entry.get("selected", False)),
            "why_selected": entry.get("why_selected"),
            "why_dropped": entry.get("why_dropped"),
        }
    return out


async def tailored_bullet_groups(
    session: AsyncSession,
    *,
    user_id: int,
    application: Application | None = None,
) -> list[dict[str, object]]:
    """Group bullets by experience for the middle column.

    The first 7 are 'selected for this resume'; the rest 'excluded with reason'.
    When `application` is supplied and its `generation_trace` carries a
    `bullet_selection_log`, each row picks up a `rationale` dict so the
    template can render the inline ledger (plan 72 § Surface 2).
    """
    experiences = await profile_service.list_experiences(session, user_id)
    rationale_index = _rationale_index_from_trace(application)
    out = []
    selected_count = 7
    seen = 0
    for e in experiences:
        bullets = await profile_service.get_bullets_for_experience(session, e.id)
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
                    "tags": _bullet_tags(b),
                    "rationale": rationale_index.get(b.id),
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
    session: AsyncSession,
    *,
    user_id: int,
    job: Job,
    application: Application | None,
    eager: bool,
) -> dict[str, object]:
    """Build the full Discover · review template context."""
    initial, color = _initial_color(job.company)

    # Real cover-letter section text from the latest generated document; falls
    # back to an honest empty state (no more hardcoded Intuit/Stripe copy).
    cover_text = _EMPTY_COVER_SECTIONS
    cover_generated = False
    if application is not None:
        fetched = await application_service.get_latest_cover_sections(session, application.id)
        if fetched:
            cover_text = {**_EMPTY_COVER_SECTIONS, **fetched}
            cover_generated = any(v.strip() for v in fetched.values())

    sections = [
        {"id": "intro", "label": COVER_LABELS["intro"], "text": cover_text["intro"]},
        {"id": "body", "label": COVER_LABELS["body"], "text": cover_text["body"]},
        {
            "id": "why_company",
            "label": COVER_LABELS["why_company"],
            "text": cover_text["why_company"],
        },
        {"id": "close", "label": COVER_LABELS["close"], "text": cover_text["close"]},
    ]

    warm_intro = None
    if job.warm_intro_contact_id:
        c = await contact_tracker.get_contact(session, job.warm_intro_contact_id)
        if c:
            warm_intro = {
                "name": c.name,
                "title": c.title,
                "company": c.company,
                "linkedin_degree": c.linkedin_degree or "1st",
            }

    screener_views: list[dict[str, object]] = []
    unreviewed = 0
    if application:
        rows = await application_service.list_screener_answers_for(session, application.id)
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
        "tailored_bullet_groups": (
            await tailored_bullet_groups(session, user_id=user_id, application=application)
            if application
            else []
        ),
        "cover_sections": sections,
        "cover_generated": cover_generated,
        "screener_answers": screener_views,
        "unreviewed_count": unreviewed,
        "failure": failure,
        "cost_estimate_usd": 0.07,
    }
