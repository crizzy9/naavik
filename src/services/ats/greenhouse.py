"""Greenhouse adapter — Playwright form filler against the PUBLIC apply form.

Item 7 (2026-07) rebuild. The previous HTTP adapter POSTed multipart data
at `boards-api.greenhouse.io/v1/boards/{org}/jobs/{id}` — the job-DETAILS
read endpoint — and `_interpret_response` treated any 2xx as success, with
the job JSON's `id` masquerading as `board_application_id`. Nothing ever
reached the employer (root cause of the owner's "submitted but no
confirmation email"). This adapter drives the real form at
`job-boards.greenhouse.io/{org}/jobs/{id}` (and the legacy
`boards.greenhouse.io` host) and only reports ok with confirmation text.
"""

from __future__ import annotations

import re

from models import Application, Job

from ._form_filler import PlaywrightFormFiller

URL_PATTERN = re.compile(
    r"https?://(?:job-boards|boards)(?:-api)?\.(?:eu\.)?greenhouse\.io/"
    r"(?:embed/job_app\?token=(?P<token>\d+)|(?P<org>[^/?#]+)/jobs/(?P<job_id>\d+))"
)


def parse_url(url: str | None) -> tuple[str, str] | None:
    """(org, job_id) from any Greenhouse posting URL shape; None otherwise."""
    if not url:
        return None
    m = URL_PATTERN.search(url)
    if not m or not m.group("org"):
        return None
    return m.group("org"), m.group("job_id")


class GreenhouseAdapter(PlaywrightFormFiller):
    board_name = "greenhouse"

    field_selectors = {
        "first_name": (
            "#first_name",
            'input[name="job_application[first_name]"]',
            'input[name="first_name"]',
            'input[autocomplete="given-name"]',
        ),
        "last_name": (
            "#last_name",
            'input[name="job_application[last_name]"]',
            'input[name="last_name"]',
            'input[autocomplete="family-name"]',
        ),
        "email": (
            "#email",
            'input[name="job_application[email]"]',
            'input[type="email"]',
        ),
        "phone": (
            "#phone",
            'input[name="job_application[phone]"]',
            'input[type="tel"]',
        ),
        "location": (
            "#candidate-location",
            'input[name="job_application[location]"]',
            "#auto_complete_input",
        ),
        "linkedin": (
            'input[name*="linkedin" i]',
            'input[aria-label*="LinkedIn" i]',
        ),
    }
    file_selectors = (
        'input[type="file"]#resume',
        'input[type="file"][name="resume"]',
        'input[type="file"][name="job_application[resume]"]',
        'input[type="file"]',
    )
    cover_letter_file_selectors = (
        'input[type="file"]#cover_letter',
        'input[type="file"][name="cover_letter"]',
        'input[type="file"][name="job_application[cover_letter]"]',
    )
    submit_selectors = (
        "#submit_app",
        'button[type="submit"]',
        'input[type="submit"]',
    )
    confirmation_patterns = (
        "thank you for applying",
        "your application has been submitted",
        "application was submitted",
        "we have received your application",
    )

    def apply_url(self, application: Application) -> str | None:
        parsed = parse_url(application.external_url)
        if parsed is None:
            return None
        org, job_id = parsed
        # The current-generation host renders the form inline on the posting.
        return f"https://job-boards.greenhouse.io/{org}/jobs/{job_id}"

    def can_submit(self, job: Job) -> bool:
        return parse_url(job.url) is not None
