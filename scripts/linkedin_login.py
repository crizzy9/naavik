"""Seed / refresh the LinkedIn session for the authenticated apply-target resolver.

`services/linkedin_resolver.py` Tier B reads the real offsite apply URL from an
authenticated LinkedIn session, persisted as a Chromium PROFILE under
`DATA_DIR/linkedin/profile` (chmod 0700, gitignored) — never credentials in the
DB. This script bootstraps or refreshes that profile. Pick the most convenient:

  # 1. Import the `li_at` cookie from the LINKEDIN_SESSION_COOKIE env slot and
  #    verify the session is live (headless — works over SSH / in CI):
  NAAVIK_DEBUG=1 LINKEDIN_SESSION_COOKIE='AQED...' \
      uv run python scripts/linkedin_login.py --import-cookie

  # 2. Import the FULL LinkedIn cookie set from a locally logged-in Firefox /
  #    Zen profile (cookies.sqlite is plaintext — no OS-keyring decrypt). This
  #    is the most reliable path: it carries the load-balancer cookies (lidc /
  #    bcookie / JSESSIONID) that `li_at` alone lacks, avoiding LinkedIn's
  #    www↔apex redirect loop:
  NAAVIK_DEBUG=1 uv run python scripts/linkedin_login.py \
      --from-firefox ~/.config/zen/default/cookies.sqlite

  # 3. One-time interactive login in a real window (needs a display); the
  #    profile persists your session (incl. any 2FA) across runs:
  NAAVIK_DEBUG=1 uv run python scripts/linkedin_login.py --headed

  # 4. Just check whether the existing profile is still logged in:
  NAAVIK_DEBUG=1 uv run python scripts/linkedin_login.py --check

Session cookies expire (~months) and LinkedIn may invalidate them on password
change / suspicious activity. When the resolver logs "session not logged in —
refresh the profile", re-run mode 1 or 3. Prefers Patchright (stealth Chromium
fork); falls back to plain Playwright when Patchright's bundled browser
revision isn't available in this Nix env.
"""

from __future__ import annotations

import argparse
import asyncio
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


_FF_SAMESITE = {0: "None", 1: "Lax", 2: "Strict"}


def _cookies_from_firefox(cookies_sqlite: str) -> list[dict]:
    """Read ALL LinkedIn cookies (Playwright shape) from a Firefox/Zen store.

    Importing the full set — not just `li_at` — seeds the load-balancer cookies
    (`lidc`, `bcookie`, `JSESSIONID`) that LinkedIn's www↔apex redirect needs;
    `li_at` alone loops forever (ERR_TOO_MANY_REDIRECTS). Firefox stores cookie
    values in plaintext, so no OS-keyring decrypt is required.
    """
    con = sqlite3.connect(f"file:{cookies_sqlite}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT name, value, host, path, isSecure, isHttpOnly, sameSite "
            "FROM moz_cookies WHERE host LIKE '%linkedin.com'"
        ).fetchall()
    finally:
        con.close()
    return [
        {
            "name": name,
            "value": value,
            "domain": host,
            "path": path or "/",
            "secure": bool(secure),
            "httpOnly": bool(httponly),
            "sameSite": _FF_SAMESITE.get(samesite, "Lax"),
        }
        for name, value, host, path, secure, httponly, samesite in rows
    ]


async def _run(args: argparse.Namespace) -> int:
    from config import settings
    from services import linkedin_resolver as lr

    prof = lr.profile_dir()
    prof.mkdir(parents=True, exist_ok=True)
    Path(prof).chmod(0o700)
    executable = lr._chromium_executable()

    seed_cookies: list[dict] = []
    if args.from_firefox:
        seed_cookies = _cookies_from_firefox(args.from_firefox)
        names = sorted({c["name"] for c in seed_cookies})
        if "li_at" not in names:
            print(f"✗ no li_at cookie found in {args.from_firefox}")
            return 1
        print(f"✓ read {len(seed_cookies)} LinkedIn cookies from {args.from_firefox}: {names}")
    elif args.import_cookie:
        li_at = settings.linkedin_session_cookie
        if not li_at:
            print("✗ LINKEDIN_SESSION_COOKIE is unset — export it or use --from-firefox")
            return 1
        seed_cookies = lr.cookie_payload(li_at)
        print(f"✓ using li_at ({len(li_at)} chars) from LINKEDIN_SESSION_COOKIE")

    factory, backend = lr._async_playwright()
    if backend == "patchright" and executable is None:
        from playwright.async_api import async_playwright as factory  # noqa: N813

        backend = "playwright"
    print(f"browser backend: {backend}  |  profile: {prof}")

    async with factory() as pw:
        launch_kwargs: dict = {
            "user_data_dir": str(prof),
            "headless": not args.headed,
            "args": lr._STEALTH_ARGS,
            "viewport": {"width": 1440, "height": 900},
            "user_agent": lr._UA,
        }
        if executable:
            launch_kwargs["executable_path"] = executable
        ctx = await pw.chromium.launch_persistent_context(**launch_kwargs)
        try:
            if seed_cookies:
                await ctx.add_cookies(seed_cookies)
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            if args.headed:
                await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
                print("\nComplete login (and any 2FA) in the window, then press Enter here…")
                await asyncio.get_event_loop().run_in_executor(None, input)
            # Verify by loading the authenticated feed.
            await page.goto(
                "https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=45000
            )
            await page.wait_for_timeout(2500)
            landing = page.url
            logged_in = not any(
                x in landing for x in ("/authwall", "/login", "/checkpoint", "/uas/")
            )
            if logged_in:
                print(f"✓ session is LIVE (landed on {landing}) — profile persisted at {prof}")
                return 0
            print(
                f"✗ NOT logged in (landed on {landing}) — cookie stale or a checkpoint is required"
            )
            return 2
        finally:
            await ctx.close()


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed/refresh the LinkedIn resolver session profile.")
    grp = ap.add_mutually_exclusive_group()
    grp.add_argument(
        "--import-cookie", action="store_true", help="seed from LINKEDIN_SESSION_COOKIE env"
    )
    grp.add_argument(
        "--from-firefox", metavar="COOKIES_SQLITE", help="seed from a Firefox/Zen cookies.sqlite"
    )
    grp.add_argument(
        "--headed", action="store_true", help="one-time interactive login (needs a display)"
    )
    grp.add_argument(
        "--check", action="store_true", help="only verify the existing profile session"
    )
    args = ap.parse_args()
    if not any((args.import_cookie, args.from_firefox, args.headed, args.check)):
        args.import_cookie = True  # sensible default
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
