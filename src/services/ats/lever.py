"""Lever adapter — Playwright form filler against the public apply page.

Item 7 (2026-07) rebuild. The previous HTTP adapter POSTed at
`api.lever.co/v0/postings/{site}/{id}/apply` and treated any 2xx as
success without confirmation evidence. This adapter drives the real form
at `jobs.lever.co/{site}/{id}/apply` and only reports ok when the
post-submit page shows positive confirmation.
"""

from __future__ import annotations

import re

from models import Application, Job

from ._form_filler import PlaywrightFormFiller

URL_PATTERN = re.compile(
    r"https?://jobs\.(?:eu\.)?lever\.co/(?P<site>[^/?#]+)/(?P<posting_id>[a-fA-F0-9-]{16,})"
)


def parse_url(url: str | None) -> tuple[str, str] | None:
    if not url:
        return None
    m = URL_PATTERN.search(url)
    if not m:
        return None
    return m.group("site"), m.group("posting_id")


class LeverAdapter(PlaywrightFormFiller):
    board_name = "lever"

    field_selectors = {
        "full_name": ('input[name="name"]',),
        "email": ('input[name="email"]', 'input[type="email"]'),
        "phone": ('input[name="phone"]', 'input[type="tel"]'),
        "location": ('input[name="location"]',),
        "company": ('input[name="org"]',),
        "linkedin": ('input[name="urls[LinkedIn]"]',),
        "github": ('input[name="urls[GitHub]"]',),
        "portfolio": ('input[name="urls[Portfolio]"]', 'input[name="urls[Other]"]'),
    }
    file_selectors = (
        'input[type="file"]#resume-upload-input',
        'input[type="file"][name="resume"]',
        'input[type="file"]',
    )
    submit_selectors = (
        "#btn-submit",
        'button[type="submit"].postings-btn',
        'button[type="submit"]',
    )
    confirmation_patterns = (
        "application submitted",
        "thank you for applying",
        "thanks for applying",
        "your application has been received",
    )

    def apply_url(self, application: Application) -> str | None:
        parsed = parse_url(application.external_url)
        if parsed is None:
            return None
        site, posting_id = parsed
        return f"https://jobs.lever.co/{site}/{posting_id}/apply"

    def can_submit(self, job: Job) -> bool:
        return parse_url(job.apply_url or job.url) is not None
