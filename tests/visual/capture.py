"""Playwright snapshot capture for plan-09 visual QA.

Per plan 09 § E:
- Captures every Phase 1 screen at desktop (1440×900) + mobile (375×812).
- Authenticated routes inject the fake `naavik_session=fake-1` cookie.
- Snapshots land at `tests/visual/screenshots/<screen>-<viewport>.png`.

Usage:
    # Boot the dev server in another terminal:
    NAAVIK_DEBUG=1 uv run fastapi dev src/main.py

    # Then run the capture script (single screen or full matrix):
    uv run python tests/visual/capture.py
    uv run python tests/visual/capture.py --screen=login
    uv run python tests/visual/capture.py --base-url=http://127.0.0.1:8000

This script is intentionally NOT picked up by `uv run pytest` — it's a manual
visual-QA tool. CI-side diff lives in a follow-up plan.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# (slug, url) — every Phase 1 screen + the bullet-editor modal.
SCREENS: list[tuple[str, str]] = [
    ("login", "/login"),
    ("onboarding-step1", "/onboarding?step=1"),
    ("onboarding-step2", "/onboarding?step=2"),
    ("onboarding-step3", "/onboarding?step=3"),
    ("overview", "/"),
    ("profile", "/profile"),
    ("profile-edit", "/profile/edit"),
    ("bullet-modal", "/_modal/bullet-editor/1"),
    ("discover", "/discover"),
    ("discover-review-eager", "/discover/113"),
    ("discover-review-stuck", "/discover/114"),
    ("tracking-board", "/tracking?view=board"),
    ("tracking-list", "/tracking?view=list"),
    ("outreach", "/outreach?application=2"),
    ("settings-llm", "/settings/llm-provider"),
    ("settings-deployment", "/settings/deployment"),
    ("settings-account", "/settings/account"),
    ("settings-notifications", "/settings/notifications"),
    ("settings-auto-apply", "/settings/auto-apply"),
    ("settings-sources", "/settings/sources"),
]

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900},
    "mobile": {"width": 375, "height": 812},
}


def capture(base_url: str, only_screen: str | None, out_dir: Path) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Playwright is not installed. Run `uv sync --extra dev` then "
            "`uv run playwright install chromium` (or enter the nix devshell "
            "which provides chromium via PLAYWRIGHT_BROWSERS_PATH)."
        )
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    targets = [(s, u) for s, u in SCREENS if (only_screen is None or s == only_screen)]
    if not targets:
        print(f"No matching screen for --screen={only_screen!r}")
        return 1

    failures: list[tuple[str, str]] = []
    with sync_playwright() as p:
        for vp_name, vp in VIEWPORTS.items():
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport=vp)
            context.add_cookies(
                [
                    {
                        "name": "naavik_session",
                        "value": "fake-1",
                        "url": base_url,
                    },
                ]
            )
            for slug, url in targets:
                page = context.new_page()
                full = base_url.rstrip("/") + url
                try:
                    page.goto(full, wait_until="networkidle", timeout=15_000)
                except Exception as exc:
                    print(f"  ! {slug}@{vp_name}: navigation failed — {exc}")
                    failures.append((slug, vp_name))
                    page.close()
                    continue
                # Tiny settle for SSE icons to paint.
                page.wait_for_timeout(300)
                out = out_dir / f"{slug}-{vp_name}.png"
                page.screenshot(path=str(out), full_page=True)
                print(f"  ✓ {slug}@{vp_name} → {out.relative_to(Path.cwd())}")
                page.close()
            context.close()
            browser.close()

    if failures:
        print(f"\n{len(failures)} screenshot(s) failed:")
        for slug, vp in failures:
            print(f"  - {slug}@{vp}")
        return 1
    print(f"\n{len(targets) * len(VIEWPORTS)} snapshots written to {out_dir}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url", default="http://127.0.0.1:8000", help="Where the dev server is listening."
    )
    parser.add_argument(
        "--screen",
        default=None,
        help="Capture only this screen slug (e.g. 'login', 'discover-review-eager').",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("tests/visual/screenshots"),
        help="Output directory for PNGs.",
    )
    args = parser.parse_args(argv)
    return capture(args.base_url, args.screen, args.out_dir)


if __name__ == "__main__":
    sys.exit(main())
