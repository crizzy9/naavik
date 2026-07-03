"""Ashby adapter — Playwright form filler against the public React form.

Item 7 (2026-07) rebuild. The previous HTTP adapter POSTed JSON-in-
multipart at `api.ashbyhq.com/posting-api/job-posting/{id}/apply` and
trusted any 2xx. Ashby's public application form is a React app at
`jobs.ashbyhq.com/{org}/{id}/application` with `_systemfield_*` inputs;
this adapter fills it for real and requires confirmation text for ok.
"""

from __future__ import annotations

import re

from models import Application, Job

from ._form_filler import PlaywrightFormFiller

URL_PATTERN = re.compile(
    r"https?://jobs\.ashbyhq\.com/(?P<org>[^/?#]+)/(?P<posting_id>[a-fA-F0-9-]{16,})"
)


def parse_url(url: str | None) -> tuple[str, str] | None:
    if not url:
        return None
    m = URL_PATTERN.search(url)
    if not m:
        return None
    return m.group("org"), m.group("posting_id")


class AshbyAdapter(PlaywrightFormFiller):
    board_name = "ashby"

    field_selectors = {
        "full_name": ("#_systemfield_name", 'input[name="_systemfield_name"]'),
        "email": (
            "#_systemfield_email",
            'input[name="_systemfield_email"]',
            'input[type="email"]',
        ),
        "phone": (
            "#_systemfield_phone",
            'input[name="_systemfield_phone"]',
            'input[type="tel"]',
        ),
        "location": ("#_systemfield_location", 'input[name="_systemfield_location"]'),
        "linkedin": ('input[name*="linkedin" i]', 'input[aria-label*="LinkedIn" i]'),
    }
    file_selectors = (
        'input[type="file"]#_systemfield_resume',
        'input[type="file"][name="_systemfield_resume"]',
        'input[type="file"]',
    )
    submit_selectors = (
        "button.ashby-application-form-submit-button",
        'button[type="submit"]',
    )
    confirmation_patterns = (
        "application submitted",
        "thank you for applying",
        "your application was submitted",
        "we have received your application",
        "success! your application",
    )

    def apply_url(self, application: Application) -> str | None:
        parsed = parse_url(application.external_url)
        if parsed is None:
            return None
        org, posting_id = parsed
        return f"https://jobs.ashbyhq.com/{org}/{posting_id}/application"

    def can_submit(self, job: Job) -> bool:
        return parse_url(job.url) is not None
