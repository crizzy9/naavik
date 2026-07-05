"""Event vocabulary, per-channel renderers, toggles, composite emitters.

Split out of services/notifications.py in plan 91 Phase 4.6;
behaviour unchanged. Internal calls to patched seams route through
`svc()` (the facade) so test interception keeps working.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from models import Application, Job, JobScrapeRun, Settings

log = logging.getLogger(__name__)


def svc():
    """The `services.notifications` facade, resolved at call time — keeps
    `patch("services.notifications.X")` seams intercepting internal calls
    (plan 91 Phase 4.6)."""
    from services import notifications

    return notifications


# Per-event toggle keys (matching Settings.notifications_enabled JSON shape).
EVENT_NEW_HIGH_SCORE = "new_high_score_job"
EVENT_APPLICATION_SENT = "application_sent"
EVENT_INTERVIEW_SCHEDULED = "interview_scheduled"
EVENT_OFFER_RECEIVED = "offer_received"
EVENT_REJECTION = "rejection"
EVENT_AUTO_APPLY_FAILED = "auto_apply_failed"
# Plan 37 / 0.2.0.12: per-scrape-run summary fired after run_scraper finalizes.
EVENT_SCRAPE_RUN_NEW_JOBS = "scrape_run_new_jobs"

# Plan 37 / 0.2.0.12: max top-jobs links inlined into the summary embed/text.
_SCRAPE_RUN_TOP_N = 5


def _embed_for_event(
    event: str,
    *,
    application: Application | None = None,
    job: Job | None = None,
) -> dict[str, Any]:
    if event == EVENT_NEW_HIGH_SCORE and job is not None:
        return {
            "title": f"New high-score job: {job.role} @ {job.company}",
            "description": (job.description or "")[:280],
            "url": job.url,
            "color": 5793266,  # cyan-ish
            "fields": [
                {"name": "Score", "value": f"{job.score:.2f}", "inline": True},
                {
                    "name": "Location",
                    "value": job.location or "Remote",
                    "inline": True,
                },
            ],
            "footer": {"text": "naavik · scraped just now"},
        }
    if event == EVENT_APPLICATION_SENT and application is not None:
        return {
            "title": f"Application submitted: {application.role} @ {application.company}",
            "color": 5763719,  # green
            "fields": [
                {
                    "name": "Board",
                    "value": (application.board.value if application.board else "manual"),
                    "inline": True,
                }
            ],
        }
    if event == EVENT_INTERVIEW_SCHEDULED and application is not None:
        return {
            "title": f"Interview scheduled: {application.company}",
            "color": 16744192,
        }
    if event == EVENT_OFFER_RECEIVED and application is not None:
        return {
            "title": f"OFFER · {application.company} · {application.role}",
            "color": 16766720,
        }
    if event == EVENT_REJECTION and application is not None:
        return {
            "title": f"Rejection · {application.company} · {application.role}",
            "color": 13632027,
        }
    if event == EVENT_AUTO_APPLY_FAILED and application is not None:
        return {
            "title": f"Auto-apply failed · {application.company}",
            "description": (application.submission_artifacts or {})
            .get("last_failure", {})
            .get("message", ""),
            "color": 13632027,
        }
    return {"title": event, "color": 9807270}


def _is_event_enabled(settings: Settings, event: str) -> bool:
    payload = settings.notifications_enabled or {}
    if not payload:
        # Defaults: rejections off, everything else on.
        defaults = {
            EVENT_NEW_HIGH_SCORE: True,
            EVENT_APPLICATION_SENT: True,
            EVENT_INTERVIEW_SCHEDULED: True,
            EVENT_OFFER_RECEIVED: True,
            EVENT_REJECTION: False,
            EVENT_AUTO_APPLY_FAILED: True,
            EVENT_SCRAPE_RUN_NEW_JOBS: True,
        }
        return defaults.get(event, True)
    return bool(payload.get(event, True))


def _telegram_text_for_event(
    event: str,
    *,
    application: Application | None = None,
    job: Job | None = None,
) -> str:
    """Plain-text Telegram message body — no Markdown emphasis.

    Mirrors `_telegram_text_for_scrape_run`'s no-parse_mode contract
    (plan 46 / 0.2.0.12a). Scraper-controlled `role` / `company` strings
    can carry `*` / `_` / `[]()` characters; emitting `*x*` bolding under
    parse_mode=Markdown turned them into formatting / phishing-link
    surfaces. We drop emphasis here and remove parse_mode in `send_telegram`
    so any literal `*` / `_` / `[` / `(` in scraper output renders verbatim
    rather than being interpreted by the Telegram client.
    """
    if event == EVENT_NEW_HIGH_SCORE and job is not None:
        return (
            f"📌 New match: {job.role} @ {job.company}\n"
            f"Score: {job.score:.2f} · {job.location or 'Remote'}\n"
            f"{job.url}"
        )
    if event == EVENT_APPLICATION_SENT and application is not None:
        return (
            f"📤 Submitted: {application.role} @ {application.company} "
            f"({application.board.value if application.board else 'manual'})"
        )
    if event == EVENT_INTERVIEW_SCHEDULED and application is not None:
        return f"🗓️ Interview · {application.company}"
    if event == EVENT_OFFER_RECEIVED and application is not None:
        return f"🎉 OFFER · {application.company} · {application.role}"
    if event == EVENT_REJECTION and application is not None:
        return f"🚪 Rejection · {application.company} · {application.role}"
    if event == EVENT_AUTO_APPLY_FAILED and application is not None:
        return (
            f"⚠️ Auto-apply failed · {application.company}\n"
            f"{(application.submission_artifacts or {}).get('last_failure', {}).get('message', '')}"
        )
    return event


async def notify_new_high_score(
    *, settings: Settings, job: Job, http_client: httpx.AsyncClient | None = None
) -> None:
    if job.score < settings.notify_threshold:
        return
    await asyncio.gather(
        svc().send_discord(
            settings=settings, event=EVENT_NEW_HIGH_SCORE, job=job, http_client=http_client
        ),
        svc().send_telegram(
            settings=settings, event=EVENT_NEW_HIGH_SCORE, job=job, http_client=http_client
        ),
        return_exceptions=True,
    )


async def notify_application_submitted(
    *,
    settings: Settings,
    application: Application,
    http_client: httpx.AsyncClient | None = None,
) -> None:
    await asyncio.gather(
        svc().send_discord(
            settings=settings,
            event=EVENT_APPLICATION_SENT,
            application=application,
            http_client=http_client,
        ),
        svc().send_telegram(
            settings=settings,
            event=EVENT_APPLICATION_SENT,
            application=application,
            http_client=http_client,
        ),
        return_exceptions=True,
    )


async def notify_priority_email(
    *,
    settings: Settings,
    application: Application,
    classification: str,
    http_client: httpx.AsyncClient | None = None,
) -> None:
    """Fan a classified email out to Discord + Telegram.

    Plan 90 / 0.5.0.04. Dispatches by classification onto the existing
    `EVENT_INTERVIEW_SCHEDULED` / `EVENT_OFFER_RECEIVED` / `EVENT_REJECTION`
    surfaces — no new templates, no new toggle keys. `Settings.notifications_enabled`
    per-event flags continue to honor mute state (REJECTION defaults off).
    """
    from models.enums import EmailClassification

    # classifier passes the StrEnum value; normalize either str or enum.
    if isinstance(classification, EmailClassification):
        cls = classification
    else:
        try:
            cls = EmailClassification(str(classification).lower())
        except ValueError:
            return

    if cls in (EmailClassification.INTERVIEW_REQUEST, EmailClassification.ASSESSMENT):
        event = EVENT_INTERVIEW_SCHEDULED
    elif cls == EmailClassification.OFFER:
        event = EVENT_OFFER_RECEIVED
    elif cls == EmailClassification.REJECTION:
        event = EVENT_REJECTION
    else:
        # FOLLOW_UP / OTHER — not worth an outbound ping.
        return

    await asyncio.gather(
        svc().send_discord(
            settings=settings,
            event=event,
            application=application,
            http_client=http_client,
        ),
        svc().send_telegram(
            settings=settings,
            event=event,
            application=application,
            http_client=http_client,
        ),
        return_exceptions=True,
    )


def _embed_for_scrape_run(run: JobScrapeRun, top_jobs: list[Job]) -> dict[str, Any]:
    """Discord rich embed for one completed JobScrapeRun summary.

    Description: bulleted top-N job links (`+M more` line when truncated).
    Fields: run counters + score-gate disclaimer. Color matches the
    `EVENT_NEW_HIGH_SCORE` cyan convention.
    """
    source = run.source.value
    total_new = run.new_jobs

    lines: list[str] = []
    for job in top_jobs[:_SCRAPE_RUN_TOP_N]:
        # role @ company — link
        role = job.role or "—"
        company = job.company or "—"
        url = job.url or ""
        lines.append(f"• {role} @ {company} — {url}")
    leftover = max(0, total_new - len(lines))
    if leftover > 0:
        lines.append(f"• … +{leftover} more")
    description = "\n".join(lines) if lines else "(no link-able new jobs)"

    duration_label = "—"
    if run.duration_ms is not None:
        duration_label = f"{run.duration_ms / 1000:.1f}s"

    run_summary = (
        f"{source} · {run.listings_returned} listings · "
        f"{run.new_jobs} new · {run.updated_jobs} updated · "
        f"{duration_label}"
    )

    finished = (run.finished_at or run.started_at).isoformat()

    return {
        "title": f"🆕 {total_new} new jobs from {source}",
        "description": description[:4000],
        "color": 5793266,  # cyan — matches EVENT_NEW_HIGH_SCORE
        "fields": [
            {"name": "Run", "value": run_summary, "inline": False},
            {
                "name": "Threshold",
                "value": "score gate disabled until 0.3.0",
                "inline": False,
            },
        ],
        "footer": {"text": f"naavik · {finished}"},
    }


def _telegram_text_for_scrape_run(run: JobScrapeRun, top_jobs: list[Job]) -> str:
    """Plain-text summary for Telegram sendMessage.

    No parse_mode is used; scraper-controlled `role`/`company`/`url` would
    otherwise allow Markdown injection (e.g. `[phish](url)`). URLs still
    auto-linkify in Telegram clients without parse_mode.

    Stays well under the 4096-byte payload limit via the top-N cap.
    """
    source = run.source.value
    total_new = run.new_jobs

    lines = [f"📌 {total_new} new jobs from {source}"]
    for job in top_jobs[:_SCRAPE_RUN_TOP_N]:
        role = job.role or "—"
        company = job.company or "—"
        url = job.url or ""
        lines.append(f"• {role} @ {company} — {url}")
    leftover = max(0, total_new - min(len(top_jobs), _SCRAPE_RUN_TOP_N))
    if leftover > 0:
        lines.append(f"• … +{leftover} more")

    duration_label = "—"
    if run.duration_ms is not None:
        duration_label = f"{run.duration_ms / 1000:.1f}s"
    lines.append(
        f"_Run: {run.listings_returned} listings · "
        f"{run.new_jobs} new · {run.updated_jobs} updated · "
        f"{duration_label}_"
    )
    return "\n".join(lines)[:4000]


async def notify_scrape_run_summary(
    *,
    settings: Settings,
    run: JobScrapeRun,
    top_jobs: list[Job],
    http_client: httpx.AsyncClient | None = None,
) -> None:
    """Fan-out one JobScrapeRun summary to Discord + Telegram.

    No-ops when `run.new_jobs <= 0` so the caller can invoke unconditionally
    after lifecycle finalize. Per-channel mutes + missing-env cases handled
    inside each send helper. `asyncio.gather(return_exceptions=True)` so a
    bad-actor channel never cancels the others.
    """
    if run.new_jobs <= 0:
        return
    await asyncio.gather(
        svc()._send_discord_scrape_run(
            settings=settings, run=run, top_jobs=top_jobs, http_client=http_client
        ),
        svc()._send_telegram_scrape_run(
            settings=settings, run=run, top_jobs=top_jobs, http_client=http_client
        ),
        return_exceptions=True,
    )
