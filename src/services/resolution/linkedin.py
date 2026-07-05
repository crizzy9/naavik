"""Authoritative LinkedIn apply-target resolution — two tiers, one seam.

Both tiers feed the same `ResolvedApply` that `apply_site_resolver` already
stamps onto `Job`, so this is a resolver STAGE, not a rewrite. `source` stays
`LINKEDIN`; `board` / `apply_kind` / `apply_url` become the real apply site.

Tier A — guest HTML, no auth. The logged-out guest job-detail page structurally
hides the offsite apply TARGET (the Apply button only bounces to a LinkedIn
sign-in), but it DOES carry the LinkedIn company-page slug (`/company/<slug>`),
which is very often the org's real ATS board slug. "Catapult" scrapes as
company "Catapult" — no rule derives the Greenhouse slug `catapultsports` — but
the guest page's own org link is `/company/catapultsports`, and the Greenhouse
board `catapultsports` lists the exact posting. Feeding that slug into the
public ATS board APIs resolves the posting precisely (confirmed by title
match), never a guess. `parse_guest_detail` is pure and unit-tested.

Tier B — authenticated LinkedIn. When Tier A can't (LI slug ≠ ATS slug, or a
non-Greenhouse/Lever/Ashby ATS), a persistent logged-in Chromium profile reads
the authenticated Voyager job API, whose `applyMethod.…OffsiteApply
.companyApplyUrl` IS the real external apply URL (and `description` the full
JD). Access is SERIALIZED (module lock — one session, requests queue), jittered,
and attempted only when a session is configured; unconfigured deployments skip
it silently. Prefers Patchright (stealth Chromium fork) pointed at the
Nix-pinned browser via `executable_path`; falls back to plain Playwright with
stealth launch args when Patchright's bundled-browser revision is unavailable.

Security: the session lives as a browser PROFILE under
`DATA_DIR/linkedin/profile` (chmod 0700, gitignored), never credentials in the
DB. Bootstrap it from the `LINKEDIN_SESSION_COOKIE` env slot (an `li_at` value)
or a one-time headed login via `scripts/linkedin_login.py`.
"""

from __future__ import annotations

import asyncio
import glob
import json
import logging
import os
import random
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from config import settings
from services.resolution.url_rules import ResolvedApply, ats_org_from_url, classify_apply_url

log = logging.getLogger(__name__)


def _li():
    """The `services.resolution` package surface, resolved at call time —
    keeps `patch.object(resolution, "read_session_health")` seams
    intercepting internal calls (plan 91 Phase 4.5 / plan 92 teardown)."""
    from services import resolution

    return resolution


# ── Tier A: guest-HTML parsing (pure) ────────────────────────────────────

# The guest detail page marks an offsite (external ATS) apply with this token
# in the CTA tracking-control names; native Easy Apply never carries it.
GUEST_OFFSITE_MARKER = "apply-link-offsite"

_COMPANY_SLUG_RE = re.compile(r"/company/([a-z0-9][a-z0-9\-]*)", re.IGNORECASE)
# The org link on the guest topcard is the RELIABLE slug — logo + org-name
# anchors both carry a `public_jobs_topcard…` tracking marker.
_TOPCARD_SLUG_RE = re.compile(
    r"/company/([a-z0-9][a-z0-9\-]*)/?\?trk=[^\"']*topcard", re.IGNORECASE
)
_SLUG_OK_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,60}$")


@dataclass
class GuestDetail:
    """What the (unauthenticated) guest job-detail page can tell us."""

    is_offsite: bool | None  # True external, False Easy Apply, None can't tell
    company_slug: str | None  # LinkedIn `/company/<slug>` — an ATS-slug candidate
    description_html: str | None
    description_text: str | None
    # The FULL posting title ("Senior Software Engineer (GO)") — richer than the
    # scraper's normalized `Job.role` ("Senior Software Engineer"), which drops
    # discriminators the title match needs to pick THE posting.
    posting_title: str | None = None


def _extract_company_slug(html: str) -> str | None:
    """The org's LinkedIn slug — the best ATS-board-slug candidate we have."""
    for m in _TOPCARD_SLUG_RE.finditer(html):
        slug = m.group(1).lower()
        if _SLUG_OK_RE.match(slug):
            return slug
    slugs = [s.lower() for s in _COMPANY_SLUG_RE.findall(html) if _SLUG_OK_RE.match(s.lower())]
    if not slugs:
        return None
    return Counter(slugs).most_common(1)[0][0]


def _extract_guest_description(soup) -> tuple[str | None, str | None]:
    body = soup.select_one("section.show-more-less-html") or soup.select_one("section.description")
    if body is None:
        return None, None
    text = body.get_text("\n").strip() or None
    return str(body), text


def _extract_posting_title(soup) -> str | None:
    for sel in ("h2.top-card-layout__title", "h1.topcard__title", "a.topcard__link"):
        el = soup.select_one(sel)
        if el is not None:
            title = el.get_text(strip=True)
            if title:
                return title
    return None


def parse_guest_detail(html: str | None) -> GuestDetail:
    """Parse the guest job-detail HTML. `None`/empty html → all-unknown."""
    if not html:
        return GuestDetail(
            is_offsite=None, company_slug=None, description_html=None, description_text=None
        )
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    desc_html, desc_text = _extract_guest_description(soup)
    return GuestDetail(
        is_offsite=GUEST_OFFSITE_MARKER in html,
        company_slug=_extract_company_slug(html),
        description_html=desc_html,
        description_text=desc_text,
        posting_title=_extract_posting_title(soup),
    )


# ── Tier B: authenticated Voyager extraction (pure) ──────────────────────


@dataclass
class VoyagerApply:
    apply_url: str | None
    is_easy_apply: bool
    description_text: str | None
    description_html: str | None


@dataclass
class AuthFetch:
    """Raw outcome of one authenticated browser session (injected in tests)."""

    landing_url: str
    logged_in: bool
    voyager: dict | None


def _deep_find(obj: object, key: str) -> object | None:
    """First value for `key` anywhere in a nested dict/list (BFS)."""
    stack = [obj]
    while stack:
        cur = stack.pop(0)
        if isinstance(cur, dict):
            if key in cur:
                return cur[key]
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return None


def _deep_find_all(obj: object, key: str) -> list[object]:
    out: list[object] = []
    stack = [obj]
    while stack:
        cur = stack.pop(0)
        if isinstance(cur, dict):
            if key in cur:
                out.append(cur[key])
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return out


def _voyager_description(payload: dict) -> tuple[str | None, str | None]:
    """The authenticated posting's full JD — `description.text.text` shape."""
    for desc in _deep_find_all(payload, "description"):
        if isinstance(desc, dict):
            text = desc.get("text")
            if isinstance(text, dict):
                text = text.get("text")
            if isinstance(text, str) and text.strip():
                return None, text.strip()
        elif isinstance(desc, str) and desc.strip():
            return None, desc.strip()
    formatted = _deep_find(payload, "formattedDescription")
    if isinstance(formatted, str) and formatted.strip():
        return None, formatted.strip()
    return None, None


def extract_apply_from_voyager(payload: dict) -> VoyagerApply:
    """Pull the real apply target from a Voyager job posting.

    Offsite → `applyMethod.…OffsiteApply.companyApplyUrl`; native Easy Apply →
    an `…OnsiteApply` union member (no external URL). Falls back to a deep
    search for `companyApplyUrl` so decoration drift can't hide the target.
    """
    apply_url: str | None = None
    is_easy_apply = False
    apply_method = _deep_find(payload, "applyMethod")
    if isinstance(apply_method, dict):
        for member, value in apply_method.items():
            if not isinstance(value, dict):
                continue
            if member.endswith("OffsiteApply"):
                candidate = value.get("companyApplyUrl") or value.get("companyApplyUrl~")
                if isinstance(candidate, str) and candidate:
                    apply_url = candidate
            elif "OnsiteApply" in member:
                is_easy_apply = True
    if apply_url is None:
        candidate = _deep_find(payload, "companyApplyUrl")
        if isinstance(candidate, str) and candidate:
            apply_url = candidate
    desc_html, desc_text = _voyager_description(payload)
    return VoyagerApply(
        apply_url=apply_url,
        is_easy_apply=is_easy_apply,
        description_text=desc_text,
        description_html=desc_html,
    )


def resolved_from_fetch(job, fetch: AuthFetch | None) -> ResolvedApply | None:
    """Turn a raw authenticated fetch into a `ResolvedApply` (pure)."""
    if fetch is None or not fetch.logged_in or not fetch.voyager:
        return None
    parsed = extract_apply_from_voyager(fetch.voyager)
    if parsed.apply_url:
        # An unrecognized host with a URL in hand is a company careers page —
        # "external" is reserved for offsite-with-no-target.
        kind = classify_apply_url(parsed.apply_url) or "company_site"
        return ResolvedApply(
            kind=kind,
            apply_url=parsed.apply_url,
            ats_org=ats_org_from_url(parsed.apply_url, kind),
            description_html=parsed.description_html,
            description_text=parsed.description_text,
            via="linkedin_auth",
        )
    if parsed.is_easy_apply:
        return ResolvedApply(
            kind="easy_apply",
            apply_url=job.url,
            description_html=parsed.description_html,
            description_text=parsed.description_text,
            via="linkedin_auth",
        )
    return None


# ── Tier B: browser session (serialized, jittered) ───────────────────────

# One LinkedIn session process-wide — requests queue behind this lock so we
# never open two authenticated tabs at once (rate-limit / detection hygiene).
_AUTH_LOCK = asyncio.Lock()

_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_STEALTH_ARGS = ["--no-sandbox", "--disable-blink-features=AutomationControlled"]

# Page-context fetch of the authenticated posting — cookies + csrf attached.
_VOYAGER_JS = """async (jobId) => {
    const csrf = (document.cookie.match(/JSESSIONID="?([^;"]+)/) || [])[1] || "";
    const url = `https://www.linkedin.com/voyager/api/jobs/jobPostings/${jobId}`
        + `?decorationId=com.linkedin.voyager.deco.jobs.web.shared.WebFullJobPosting-65`;
    try {
        const r = await fetch(url, {credentials: "include", headers: {
            "csrf-token": csrf, "x-restli-protocol-version": "2.0.0", "accept": "application/json"}});
        return {status: r.status, body: await r.text()};
    } catch (e) { return {status: 0, body: "", error: String(e)}; }
}"""


@dataclass
class AuthContext:
    """Per-sweep budget for the expensive authenticated path."""

    remaining: int = 3
    jitter: tuple[float, float] = (3.0, 7.0)


def profile_dir() -> Path:
    return (Path(settings.data_dir).expanduser() / "linkedin" / "profile").resolve()


def auth_available() -> bool:
    """True when Tier B can run — a bootstrap cookie OR a seeded profile."""
    if settings.linkedin_session_cookie:
        return True
    prof = profile_dir()
    return prof.is_dir() and any(prof.iterdir())


# ── Session health — the latest Tier-B outcome, queryable without a browser ──
# A JSON file next to the profile it describes (deployment-global, like the
# profile itself; no DB session exists inside resolve_via_auth). `alerted`
# latches the one-time Discord notification; recovery to "ok" clears it.


def _health_path() -> Path:
    return (Path(settings.data_dir).expanduser() / "linkedin" / "session_health.json").resolve()


def read_session_health() -> dict | None:
    """Latest recorded Tier-B outcome, or None when never attempted."""
    try:
        payload = json.loads(_health_path().read_text())
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_health(payload: dict) -> None:
    path = _health_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload))
        tmp.replace(path)
    except OSError as exc:
        log.info("could not write linkedin session health: %s", exc)


def record_session_health(status: str, *, landing_url: str | None = None) -> None:
    """Persist the outcome of a Tier-B attempt: ok / not_logged_in / error."""
    prev = _li().read_session_health() or {}
    _write_health(
        {
            "status": status,
            "at": datetime.now(UTC).isoformat(),
            "landing_url": landing_url,
            "alerted": bool(prev.get("alerted")) and status != "ok",
        }
    )


def mark_health_alerted() -> None:
    health = _li().read_session_health()
    if health:
        _write_health({**health, "alerted": True})


def _chromium_executable() -> str | None:
    """The Nix-pinned Chromium — required for Patchright (rev mismatch)."""
    base = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if not base:
        return None
    for pat in ("chromium-*/chrome-linux64/chrome", "chromium-*/chrome-linux/chrome"):
        hits = sorted(glob.glob(os.path.join(base, pat)))
        if hits:
            return hits[-1]
    return None


def _async_playwright():
    """(async_playwright factory, backend_name). Patchright preferred."""
    try:
        from patchright.async_api import async_playwright

        return async_playwright, "patchright"
    except ImportError:
        from playwright.async_api import async_playwright

        return async_playwright, "playwright"


def cookie_payload(li_at: str) -> list[dict]:
    li_at = li_at.strip().strip('"')
    # Set on BOTH the apex and the www subdomain: with the apex-only cookie
    # LinkedIn bounces the www↔apex redirect forever (ERR_TOO_MANY_REDIRECTS).
    return [
        {
            "name": "li_at",
            "value": li_at,
            "domain": domain,
            "path": "/",
            "secure": True,
            "httpOnly": True,
        }
        for domain in (".linkedin.com", ".www.linkedin.com")
    ]


async def _open_and_fetch(job) -> AuthFetch:
    """Launch the persistent session, load the job, return the Voyager JSON."""
    factory, backend = _async_playwright()
    executable = _chromium_executable()
    if backend == "patchright" and executable is None:
        # Patchright can't self-download in the read-only Nix store; without a
        # usable binary, fall back to plain Playwright (default resolution).
        from playwright.async_api import async_playwright as pw_factory

        factory, backend = pw_factory, "playwright"
    prof = profile_dir()
    prof.mkdir(parents=True, exist_ok=True)
    os.chmod(prof, 0o700)

    async with factory() as pw:
        launch_kwargs: dict = {
            "user_data_dir": str(prof),
            "headless": True,
            "args": _STEALTH_ARGS,
            "viewport": {"width": 1440, "height": 900},
            "user_agent": _UA,
        }
        if executable:
            launch_kwargs["executable_path"] = executable
        ctx = await pw.chromium.launch_persistent_context(**launch_kwargs)
        try:
            if settings.linkedin_session_cookie:
                await ctx.add_cookies(cookie_payload(settings.linkedin_session_cookie))
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto(
                f"https://www.linkedin.com/jobs/view/{job.external_id}/",
                wait_until="domcontentloaded",
                timeout=45000,
            )
            await page.wait_for_timeout(int(random.uniform(2500, 4000)))
            landing = page.url
            logged_in = not any(
                x in landing for x in ("/authwall", "/login", "/checkpoint", "/uas/")
            )
            voyager: dict | None = None
            if logged_in:
                result = await page.evaluate(_VOYAGER_JS, str(job.external_id))
                if isinstance(result, dict) and result.get("status") == 200 and result.get("body"):
                    try:
                        voyager = json.loads(result["body"])
                    except (ValueError, TypeError):
                        voyager = None
                if voyager is None and isinstance(result, dict):
                    # Distinguish "Voyager refused" (403 = soft-block, 404 =
                    # posting gone) from "payload had no target" in the logs.
                    log.info(
                        "linkedin voyager fetch yielded nothing for job %s (status=%s)",
                        job.id,
                        result.get("status"),
                    )
            return AuthFetch(landing_url=landing, logged_in=logged_in, voyager=voyager)
        finally:
            await ctx.close()
            log.info("linkedin auth session closed (backend=%s job=%s)", backend, job.id)


async def resolve_via_auth(job, auth: AuthContext | None, *, _fetcher=None) -> ResolvedApply | None:
    """Serialized authenticated resolution of one job's offsite apply target."""
    if auth is None or auth.remaining <= 0:
        return None
    fetcher = _fetcher or _open_and_fetch
    async with _AUTH_LOCK:
        auth.remaining -= 1
        await asyncio.sleep(random.uniform(*auth.jitter))
        try:
            fetch = await fetcher(job)
        except Exception as exc:  # noqa: BLE001 — a browser hiccup must not kill the sweep
            log.warning("linkedin auth resolve failed for job %s: %s", job.id, exc)
            record_session_health("error")
            return None
        if fetch is not None:
            record_session_health(
                "ok" if fetch.logged_in else "not_logged_in",
                landing_url=fetch.landing_url,
            )
    if fetch is not None and not fetch.logged_in:
        log.warning(
            "linkedin auth session not logged in (landing=%s) — refresh the profile",
            fetch.landing_url,
        )
    return resolved_from_fetch(job, fetch)


__all__ = [
    "AuthContext",
    "AuthFetch",
    "GUEST_OFFSITE_MARKER",
    "GuestDetail",
    "VoyagerApply",
    "auth_available",
    "cookie_payload",
    "extract_apply_from_voyager",
    "mark_health_alerted",
    "parse_guest_detail",
    "profile_dir",
    "read_session_health",
    "record_session_health",
    "resolve_via_auth",
    "resolved_from_fetch",
]
