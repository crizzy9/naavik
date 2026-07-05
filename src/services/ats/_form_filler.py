"""Playwright form-filler engine for public ATS application forms — item 7.

Replaces the HTTP adapters that POSTed multipart payloads at read-only
board API endpoints and treated any 2xx as success (the Greenhouse one
reported ok against the job-DETAILS endpoint — the job JSON's `id` became
`board_application_id` and no application ever reached the employer;
that's why the owner's "successful" manual submit never produced a
confirmation email).

The engine drives the REAL public apply form:

  navigate → login-wall / CAPTCHA detection → fill identity from Profile
  → upload resume (+ cover letter where the form takes one) → answer
  screeners by label match → screenshot the filled form →
    dry_run:   return ok=True, dry_run=True, artifacts=[screenshots]
    real run:  click submit → wait for positive confirmation text →
               ok=True ONLY with `raw["confirmation_text"]` evidence

Board subclasses supply URL parsing + selector tables; everything that
can be tested without a browser (URL parsing, captcha/confirmation
matchers, label matching) is a pure function here.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from models import Application, ScreenerAnswerSource

from .base import (
    FAILURE_AUTH_REQUIRED,
    FAILURE_CAPTCHA,
    FAILURE_FIELD_MISMATCH,
    FAILURE_UNKNOWN,
    ApplicationBundle,
    ATSAdapter,
    SubmissionResult,
)

log = logging.getLogger(__name__)

_NAV_TIMEOUT_MS = 45_000
_CONFIRM_TIMEOUT_MS = 20_000

# ── Pure detectors (unit-testable) ──────────────────────────────────────

_CAPTCHA_MARKERS = (
    "g-recaptcha",
    "grecaptcha",
    "recaptcha/api",
    "hcaptcha.com",
    "h-captcha",
    "cf-turnstile",
    "challenges.cloudflare.com",
)

_LOGIN_WALL_MARKERS = (
    "sign in to continue",
    "log in to continue",
    "please sign in",
    "create an account to apply",
    "login to apply",
    "sign in to apply",
)


def html_has_captcha(html: str) -> bool:
    lower = html.lower()
    return any(marker in lower for marker in _CAPTCHA_MARKERS)


def html_has_login_wall(html: str, url: str = "") -> bool:
    lower = html.lower()
    if any(marker in lower for marker in _LOGIN_WALL_MARKERS):
        return True
    return bool(re.search(r"/(login|signin|sign-in|authwall)\b", url.lower()))


def match_confirmation(text: str, patterns: tuple[str, ...]) -> str | None:
    """Return the matched confirmation phrase, or None. Case-insensitive."""
    lower = text.lower()
    for pattern in patterns:
        if pattern.lower() in lower:
            return pattern
    return None


_LABEL_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "are",
        "at",
        "do",
        "for",
        "in",
        "is",
        "of",
        "on",
        "the",
        "this",
        "to",
        "you",
        "your",
        "what",
        "why",
        "how",
        "please",
        "describe",
    }
)


def _label_tokens(text: str) -> set[str]:
    return {
        t
        for t in re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).split()
        if len(t) >= 3 and t not in _LABEL_STOPWORDS
    }


def best_answer_for_label(label: str, answers: list) -> str | None:
    """Pick the prepared screener answer whose question best matches a form
    label (≥60% token overlap of the smaller side). USER-sourced unreviewed
    rows are excluded upstream."""
    lt = _label_tokens(label)
    if not lt:
        return None
    best: tuple[float, str] | None = None
    for a in answers:
        qt = _label_tokens(getattr(a, "question_text", "") or "")
        if not qt or not (a.answer or "").strip():
            continue
        overlap = len(lt & qt) / min(len(lt), len(qt))
        if overlap >= 0.6 and (best is None or overlap > best[0]):
            best = (overlap, a.answer.strip())
    return best[1] if best else None


# ── Identity ────────────────────────────────────────────────────────────


@dataclass(slots=True)
class Identity:
    full_name: str
    first_name: str
    last_name: str
    email: str
    phone: str
    location: str
    linkedin_url: str
    github_url: str
    portfolio_url: str
    current_company: str


def identity_from_bundle(bundle: ApplicationBundle) -> Identity:
    p = bundle.profile
    full = (getattr(p, "full_name", "") or "").strip() or "Applicant"
    first, _, last = full.partition(" ")
    linkedin = (getattr(p, "linkedin_handle", "") or "").strip()
    github = (getattr(p, "github_handle", "") or "").strip()
    portfolio = (getattr(p, "portfolio_url", "") or "").strip()
    return Identity(
        full_name=full,
        first_name=first or full,
        last_name=last or first or full,
        email=(getattr(p, "email", "") or "").strip(),
        phone=(getattr(p, "phone", "") or "").strip(),
        location=(getattr(p, "location", "") or "").strip(),
        linkedin_url=f"https://linkedin.com/in/{linkedin}" if linkedin else "",
        github_url=f"https://github.com/{github}" if github else "",
        portfolio_url=(portfolio if portfolio.startswith("http") else f"https://{portfolio}")
        if portfolio
        else "",
        current_company=(getattr(p, "current_company", "") or "").strip(),
    )


# ── The engine ──────────────────────────────────────────────────────────


class PlaywrightFormFiller(ATSAdapter):
    """Board subclasses define: `board_name`, `apply_url(application)`,
    `field_selectors` (logical name → selector candidates), `submit_selectors`,
    `confirmation_patterns`, and optionally `pre_fill(page)` for board quirks."""

    # logical field → tuple of selector candidates, first match wins
    field_selectors: dict[str, tuple[str, ...]] = {}
    file_selectors: tuple[str, ...] = ('input[type="file"]',)
    cover_letter_file_selectors: tuple[str, ...] = ()
    submit_selectors: tuple[str, ...] = ('button[type="submit"]',)
    confirmation_patterns: tuple[str, ...] = ("thank you for applying",)

    def requires_credential(self) -> bool:
        return False

    def apply_url(self, application: Application) -> str | None:  # pragma: no cover
        raise NotImplementedError

    async def pre_fill(self, page) -> None:
        """Board hook — e.g. click an 'Apply' tab to reveal the form."""

    async def submit(
        self,
        application: Application,
        bundle: ApplicationBundle,
        *,
        dry_run: bool = False,
    ) -> SubmissionResult:
        url = self.apply_url(application)
        if url is None:
            return SubmissionResult(
                ok=False,
                error=FAILURE_FIELD_MISMATCH,
                error_message=(
                    f"could not derive a {self.board_name} apply URL from "
                    f"{application.external_url!r}"
                ),
            )
        if bundle.resume is None or not Path(bundle.resume.path).exists():
            return SubmissionResult(
                ok=False,
                error=FAILURE_FIELD_MISMATCH,
                error_message="resume PDF not found on disk",
            )

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return SubmissionResult(
                ok=False,
                error=FAILURE_UNKNOWN,
                error_message="playwright is not installed in this environment",
            )

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                context = await browser.new_context(viewport={"width": 1440, "height": 1600})
                page = await context.new_page()
                page.set_default_timeout(_NAV_TIMEOUT_MS)
                return await self._run(page, application, bundle, url, dry_run=dry_run)
            finally:
                await browser.close()

    # The page-driving core — takes any Page-like object so tests can drive
    # it with a stub instead of a real browser.
    async def _run(
        self,
        page,
        application: Application,
        bundle: ApplicationBundle,
        url: str,
        *,
        dry_run: bool,
    ) -> SubmissionResult:
        artifacts: list[str] = []
        raw: dict = {"request_url": url}

        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(2500)  # let React boards hydrate
        await self.pre_fill(page)

        html = await page.content()
        current_url = page.url
        if html_has_login_wall(html, current_url):
            artifacts.append(await self._screenshot(page, application, "login-wall"))
            return SubmissionResult(
                ok=False,
                error=FAILURE_AUTH_REQUIRED,
                error_message=f"{self.board_name} presented a login wall",
                raw=raw,
                artifacts=artifacts,
            )
        captcha_present = html_has_captcha(html)
        raw["captcha_present"] = captcha_present

        filled, missing = await self._fill_identity(page, bundle)
        raw["fields_filled"] = filled
        raw["fields_missing"] = missing
        uploaded = await self._upload_files(page, bundle)
        raw["resume_uploaded"] = uploaded
        if not uploaded:
            artifacts.append(await self._screenshot(page, application, "no-resume-input"))
            return SubmissionResult(
                ok=False,
                error=FAILURE_FIELD_MISMATCH,
                error_message=f"{self.board_name} form has no resume file input",
                raw=raw,
                artifacts=artifacts,
            )
        await page.wait_for_timeout(2000)  # resume parse spinners
        answered = await self._fill_screeners(page, bundle)
        raw["screeners_answered"] = answered

        artifacts.append(await self._screenshot(page, application, "filled"))

        if dry_run:
            return SubmissionResult(
                ok=True,
                dry_run=True,
                raw=raw,
                artifacts=artifacts,
                confidence=1.0 if not missing else 0.8,
            )

        if captcha_present:
            return SubmissionResult(
                ok=False,
                error=FAILURE_CAPTCHA,
                error_message=f"{self.board_name} form is CAPTCHA-protected",
                raw=raw,
                artifacts=artifacts,
            )

        clicked = False
        for selector in self.submit_selectors:
            el = await page.query_selector(selector)
            if el is not None:
                await el.click()
                clicked = True
                break
        if not clicked:
            return SubmissionResult(
                ok=False,
                error=FAILURE_FIELD_MISMATCH,
                error_message=f"{self.board_name} submit button not found",
                raw=raw,
                artifacts=artifacts,
            )

        confirmation = await self._await_confirmation(page)
        artifacts.append(await self._screenshot(page, application, "after-submit"))
        if confirmation is None:
            return SubmissionResult(
                ok=False,
                error=FAILURE_UNKNOWN,
                error_message=(
                    f"{self.board_name} gave no positive confirmation after submit — "
                    "treating as NOT submitted"
                ),
                raw=raw,
                artifacts=artifacts,
            )
        raw["confirmation_text"] = confirmation
        return SubmissionResult(ok=True, raw=raw, artifacts=artifacts, confidence=1.0)

    # ── steps ───────────────────────────────────────────────────────────

    async def _fill_identity(self, page, bundle: ApplicationBundle) -> tuple[list[str], list[str]]:
        identity = identity_from_bundle(bundle)
        values = {
            "first_name": identity.first_name,
            "last_name": identity.last_name,
            "full_name": identity.full_name,
            "email": identity.email,
            "phone": identity.phone,
            "location": identity.location,
            "linkedin": identity.linkedin_url,
            "github": identity.github_url,
            "portfolio": identity.portfolio_url,
            "company": identity.current_company,
        }
        filled: list[str] = []
        missing: list[str] = []
        for logical, selectors in self.field_selectors.items():
            value = values.get(logical, "")
            if not value:
                continue
            done = False
            for selector in selectors:
                el = await page.query_selector(selector)
                if el is not None:
                    await el.fill(value)
                    filled.append(logical)
                    done = True
                    break
            if not done:
                missing.append(logical)
        return filled, missing

    async def _upload_files(self, page, bundle: ApplicationBundle) -> bool:
        uploaded = False
        for selector in self.file_selectors:
            el = await page.query_selector(selector)
            if el is not None:
                await el.set_input_files(bundle.resume.path)
                uploaded = True
                break
        if uploaded and bundle.cover_letter is not None and Path(bundle.cover_letter.path).exists():
            for selector in self.cover_letter_file_selectors:
                el = await page.query_selector(selector)
                if el is not None:
                    await el.set_input_files(bundle.cover_letter.path)
                    break
        return uploaded

    async def _fill_screeners(self, page, bundle: ApplicationBundle) -> int:
        """Best-effort label-matched answers into visible text inputs /
        textareas. Radios/selects are left for the human — a wrong guess on
        a knockout question is worse than a hand-off."""
        answers = [
            a
            for a in bundle.screener_answers
            if not (a.source == ScreenerAnswerSource.USER and a.reviewed_at is None)
        ]
        if not answers:
            return 0
        count = 0
        labels = await page.query_selector_all("label")
        for label_el in labels:
            try:
                label_text = (await label_el.inner_text()).strip()
            except Exception:  # noqa: BLE001
                continue
            if not label_text or len(label_text) < 12:
                continue
            answer = best_answer_for_label(label_text, answers)
            if answer is None:
                continue
            target = None
            for_attr = await label_el.get_attribute("for")
            if for_attr:
                target = await page.query_selector(
                    f'textarea#{for_attr}, input[type="text"]#{for_attr}'
                )
            if target is None:
                target = await label_el.query_selector('textarea, input[type="text"]')
            if target is None:
                continue
            existing = await target.input_value()
            if existing:
                continue
            await target.fill(answer)
            count += 1
        return count

    async def _await_confirmation(self, page) -> str | None:
        deadline_ms = _CONFIRM_TIMEOUT_MS
        step = 1000
        waited = 0
        while waited <= deadline_ms:
            await page.wait_for_timeout(step)
            waited += step
            try:
                html = await page.content()
            except Exception:  # noqa: BLE001 — navigation race mid-redirect
                continue
            hit = match_confirmation(html, self.confirmation_patterns)
            if hit is not None:
                return hit
        return None

    async def _screenshot(self, page, application: Application, tag: str) -> str:
        from services.generation import _app_documents_dir

        out_dir = _app_documents_dir(application.id) / "auto_apply"
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        path = out_dir / f"{ts}-{self.board_name}-{tag}.png"
        try:
            await page.screenshot(path=str(path), full_page=True)
        except Exception as exc:  # noqa: BLE001 — evidence capture is best-effort
            log.warning("screenshot failed (%s): %s", tag, exc)
            return ""
        return str(path)
