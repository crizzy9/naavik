"""ATS adapter tests — item 7 (2026-07) Playwright form-filler rebuild.

The old suite mocked httpx against the API-POST adapters; those adapters
reported ok on any 2xx from read-only endpoints (the Greenhouse one POSTed
at the job-DETAILS endpoint — root cause of "submitted but no confirmation
email"). The new engine is driven here with a stub Page object:

- URL parsing per board (incl. the current job-boards.greenhouse.io host)
- login-wall / CAPTCHA detection (pure)
- dry-run contract: fill + screenshot, NO submit click, ok=True dry_run=True
- real-run contract: ok=True ONLY with positive confirmation text
- CAPTCHA blocks real submission (FAILURE_CAPTCHA) but not dry-run evidence
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from models import ApplicationBoard, ScreenerAnswerSource
from services.ats import dispatch
from services.ats._form_filler import (
    best_answer_for_label,
    html_has_captcha,
    html_has_login_wall,
    identity_from_bundle,
    match_confirmation,
)
from services.ats.ashby import AshbyAdapter
from services.ats.ashby import parse_url as ashby_parse
from services.ats.base import (
    FAILURE_AUTH_REQUIRED,
    FAILURE_CAPTCHA,
    FAILURE_UNKNOWN,
    ApplicationBundle,
    SubmissionResult,
)
from services.ats.greenhouse import GreenhouseAdapter
from services.ats.greenhouse import parse_url as gh_parse
from services.ats.lever import LeverAdapter
from services.ats.lever import parse_url as lever_parse

pytestmark = pytest.mark.uses_sample_data_shims


# ── Stub browser page ───────────────────────────────────────────────────


class StubElement:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    async def fill(self, value):
        self.page.filled[self.selector] = value

    async def click(self):
        self.page.clicked.append(self.selector)
        if self.page.html_after_submit is not None:
            self.page.html = self.page.html_after_submit

    async def set_input_files(self, path):
        self.page.uploads.append((self.selector, path))

    async def get_attribute(self, name):
        return None

    async def inner_text(self):
        return ""

    async def input_value(self):
        return self.page.filled.get(self.selector, "")

    async def query_selector(self, selector):
        return None


class StubPage:
    """Duck-typed Playwright Page for the engine's `_run`."""

    def __init__(self, *, html: str, selectors: set[str], html_after_submit: str | None = None):
        self.html = html
        self.selectors = selectors
        self.html_after_submit = html_after_submit
        self.url = "https://stub.example/apply"
        self.filled: dict[str, str] = {}
        self.uploads: list[tuple[str, str]] = []
        self.clicked: list[str] = []
        self.screenshots: list[str] = []

    async def goto(self, url, wait_until=None):
        self.url = url

    async def wait_for_timeout(self, ms):
        return None

    async def content(self):
        return self.html

    async def query_selector(self, selector):
        if selector in self.selectors:
            return StubElement(self, selector)
        return None

    async def query_selector_all(self, selector):
        return []

    async def screenshot(self, path=None, full_page=False):
        self.screenshots.append(path)
        Path(path).write_bytes(b"\x89PNG fake")

    def set_default_timeout(self, ms):
        return None


# ── Fixtures ────────────────────────────────────────────────────────────


def _tmp_pdf() -> Path:
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fd:
        fd.write(b"%PDF-1.7\n%fake")
        return Path(fd.name)


def _make_app(board: ApplicationBoard, url: str):
    return SimpleNamespace(
        id=90901,
        user_id=1,
        company="Stripe",
        role="Senior Backend Engineer",
        location="Remote",
        external_url=url,
        board=board,
    )


def _profile():
    return SimpleNamespace(
        full_name="Shyam Padia",
        email="shyam@example.com",
        phone="+1 555 555 0100",
        location="Fremont, CA",
        linkedin_handle="shyampadia",
        github_handle="crizzy9",
        portfolio_url="crypticsoul.dev",
        current_company="Intuit",
    )


def _make_bundle(board: ApplicationBoard, url: str):
    return ApplicationBundle(
        application=_make_app(board, url),
        resume=SimpleNamespace(kind="resume", path=str(_tmp_pdf())),
        cover_letter=None,
        screener_answers=[
            SimpleNamespace(
                id=4,
                question_text="Why do you want to work at Stripe?",
                answer="Because of payments infra.",
                source=ScreenerAnswerSource.DRAFTED,
                reviewed_at=datetime.now(UTC),
            )
        ],
        profile=_profile(),
    )


GH_URL = "https://job-boards.greenhouse.io/stripe/jobs/5678901"
GH_FORM_SELECTORS = {
    "#first_name",
    "#last_name",
    "#email",
    "#phone",
    'input[type="file"]',
    'button[type="submit"]',
}


# ── URL parsing ─────────────────────────────────────────────────────────


def test_greenhouse_url_parsing_all_hosts():
    assert gh_parse("https://boards.greenhouse.io/stripe/jobs/123") == ("stripe", "123")
    assert gh_parse("https://job-boards.greenhouse.io/stripe/jobs/123") == ("stripe", "123")
    assert gh_parse("https://job-boards.eu.greenhouse.io/stripe/jobs/123") == ("stripe", "123")
    assert gh_parse("https://jobs.lever.co/x/y") is None
    assert gh_parse(None) is None


def test_lever_url_parsing():
    assert lever_parse("https://jobs.lever.co/plaid/8f9a1b2c-3d4e-5f60-7182-93a4b5c6d7e8") == (
        "plaid",
        "8f9a1b2c-3d4e-5f60-7182-93a4b5c6d7e8",
    )
    assert lever_parse("https://boards.greenhouse.io/x/jobs/1") is None


def test_ashby_url_parsing():
    assert ashby_parse(
        "https://jobs.ashbyhq.com/lightfield/0a1b2c3d-4e5f-6071-8293-a4b5c6d7e8f9"
    ) == (
        "lightfield",
        "0a1b2c3d-4e5f-6071-8293-a4b5c6d7e8f9",
    )
    assert ashby_parse("https://jobs.lever.co/x/y") is None


def test_dispatch_returns_form_fillers():
    assert isinstance(dispatch(ApplicationBoard.GREENHOUSE), GreenhouseAdapter)
    assert isinstance(dispatch(ApplicationBoard.LEVER), LeverAdapter)
    assert isinstance(dispatch(ApplicationBoard.ASHBY), AshbyAdapter)


# ── Pure detectors ──────────────────────────────────────────────────────


def test_captcha_detection():
    assert html_has_captcha('<div class="g-recaptcha" data-sitekey="x"></div>')
    assert html_has_captcha('<iframe src="https://hcaptcha.com/x"></iframe>')
    assert html_has_captcha('<div class="cf-turnstile"></div>')
    assert not html_has_captcha("<form><input name='email'></form>")


def test_login_wall_detection():
    assert html_has_login_wall("<h1>Sign in to continue</h1>")
    assert html_has_login_wall("<html></html>", url="https://x.com/login?next=/apply")
    assert not html_has_login_wall("<form>apply here</form>", url="https://x.com/apply")


def test_confirmation_matching():
    assert (
        match_confirmation("<h1>Thank You For Applying!</h1>", ("thank you for applying",))
        == "thank you for applying"
    )
    assert match_confirmation("<h1>Review your application</h1>", ("thank you",)) is None


def test_screener_label_matching():
    answers = [
        SimpleNamespace(
            question_text="Why do you want to work at Stripe?",
            answer="Because of payments infra.",
        ),
        SimpleNamespace(question_text="Notice period", answer="2 weeks"),
    ]
    hit = best_answer_for_label("Why do you want to work here at Stripe?", answers)
    assert hit == "Because of payments infra."
    assert best_answer_for_label("Desired salary in USD", answers) is None


def test_identity_from_bundle_builds_urls():
    bundle = _make_bundle(ApplicationBoard.GREENHOUSE, GH_URL)
    identity = identity_from_bundle(bundle)
    assert identity.first_name == "Shyam"
    assert identity.last_name == "Padia"
    assert identity.linkedin_url == "https://linkedin.com/in/shyampadia"
    assert identity.portfolio_url == "https://crypticsoul.dev"


# ── Engine flow (stub page) ─────────────────────────────────────────────


async def test_dry_run_fills_and_screenshots_without_submitting(tmp_path, monkeypatch):
    from services import generation as dg

    monkeypatch.setattr(dg, "_app_documents_dir", lambda app_id: tmp_path)
    adapter = GreenhouseAdapter()
    bundle = _make_bundle(ApplicationBoard.GREENHOUSE, GH_URL)
    page = StubPage(html="<form>apply</form>", selectors=GH_FORM_SELECTORS)

    result = await adapter._run(page, bundle.application, bundle, GH_URL, dry_run=True)

    assert result.ok is True
    assert result.dry_run is True
    assert page.clicked == []  # the submit click never happened
    assert page.uploads and page.uploads[0][1] == bundle.resume.path
    assert page.filled["#first_name"] == "Shyam"
    assert page.filled["#email"] == "shyam@example.com"
    assert result.artifacts and all(Path(a).exists() for a in result.artifacts)


async def test_real_submit_requires_confirmation_text(tmp_path, monkeypatch):
    from services import generation as dg

    monkeypatch.setattr(dg, "_app_documents_dir", lambda app_id: tmp_path)
    adapter = GreenhouseAdapter()
    bundle = _make_bundle(ApplicationBoard.GREENHOUSE, GH_URL)

    # No confirmation after clicking submit → NOT ok, evidence kept.
    page = StubPage(
        html="<form>apply</form>",
        selectors=GH_FORM_SELECTORS,
        html_after_submit="<div>Review your answers</div>",
    )
    monkeypatch.setattr("services.ats._form_filler._CONFIRM_TIMEOUT_MS", 2000)
    result = await adapter._run(page, bundle.application, bundle, GH_URL, dry_run=False)
    assert result.ok is False
    assert result.error == FAILURE_UNKNOWN
    assert page.clicked  # it DID click submit

    # Confirmation present → ok with evidence.
    page2 = StubPage(
        html="<form>apply</form>",
        selectors=GH_FORM_SELECTORS,
        html_after_submit="<h1>Thank you for applying to Stripe!</h1>",
    )
    result2 = await adapter._run(page2, bundle.application, bundle, GH_URL, dry_run=False)
    assert result2.ok is True
    assert result2.raw["confirmation_text"] == "thank you for applying"


async def test_captcha_blocks_real_submit_but_not_dry_run(tmp_path, monkeypatch):
    from services import generation as dg

    monkeypatch.setattr(dg, "_app_documents_dir", lambda app_id: tmp_path)
    adapter = GreenhouseAdapter()
    bundle = _make_bundle(ApplicationBoard.GREENHOUSE, GH_URL)
    captcha_html = '<form>apply</form><div class="g-recaptcha"></div>'

    dry = await adapter._run(
        StubPage(html=captcha_html, selectors=GH_FORM_SELECTORS),
        bundle.application,
        bundle,
        GH_URL,
        dry_run=True,
    )
    assert dry.ok is True and dry.dry_run is True
    assert dry.raw["captcha_present"] is True

    real = await adapter._run(
        StubPage(html=captcha_html, selectors=GH_FORM_SELECTORS),
        bundle.application,
        bundle,
        GH_URL,
        dry_run=False,
    )
    assert real.ok is False
    assert real.error == FAILURE_CAPTCHA


async def test_login_wall_fails_honestly(tmp_path, monkeypatch):
    from services import generation as dg

    monkeypatch.setattr(dg, "_app_documents_dir", lambda app_id: tmp_path)
    adapter = AshbyAdapter()
    url = "https://jobs.ashbyhq.com/x/0a1b2c3d-4e5f-6071-8293-a4b5c6d7e8f9/application"
    bundle = _make_bundle(ApplicationBoard.ASHBY, url)
    page = StubPage(html="<h1>Sign in to continue</h1>", selectors=set())
    result = await adapter._run(page, bundle.application, bundle, url, dry_run=True)
    assert result.ok is False
    assert result.error == FAILURE_AUTH_REQUIRED


def test_submission_result_carries_dry_run_contract():
    r = SubmissionResult(ok=True, dry_run=True, artifacts=["/x/a.png"])
    assert r.dry_run is True
    assert r.artifacts == ["/x/a.png"]
    assert SubmissionResult(ok=False).dry_run is False
