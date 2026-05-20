"""User-Agent rotation pool for `Crawl4AIClient`.

Per docs/design/SCRAPER_BASE.md § G (graduated from plan 38 § D.3). Curated
pool of 8 modern desktop UAs; module-level round-robin counter rotates per
`Crawl4AIClient` instance.

UA rotation is defense-in-depth — Crawl4AI stealth handles `sec-ch-ua` +
canvas + WebGL + plugin enumeration. UA rotation reduces aggregated
per-IP signature visibility; not a primary control.

Refresh ~quarterly. `tests/test_user_agents.py` asserts pool composition +
freshness comment.
"""

from __future__ import annotations

import threading

# Last refreshed: 2026-05-19. Refresh ~quarterly to track stable-channel
# Chrome / Firefox / Safari / Edge versions. Mobile UAs deliberately
# excluded (OQ.4 — mobile UA triggers different DOM on LinkedIn / Indeed).
_USER_AGENTS: tuple[str, ...] = (
    # Chrome 130 on Windows 11
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Chrome 130 on macOS 14 (Sonoma)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Chrome 130 on Linux x86_64
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    # Firefox 130 on Windows 11
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
    # Firefox 130 on macOS 14
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.7; rv:130.0) Gecko/20100101 Firefox/130.0",
    # Firefox 130 on Linux x86_64
    "Mozilla/5.0 (X11; Linux x86_64; rv:130.0) Gecko/20100101 Firefox/130.0",
    # Safari 17.6 on macOS 14 (Sonoma)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.6 Safari/605.1.15",
    # Edge 130 on Windows 11
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
)

_rotator_lock = threading.Lock()
_rotator_index = 0


def pick_user_agent() -> str:
    """Return the next UA from the pool; round-robin under a lock.

    Round-robin (not random) gives deterministic distribution across
    cron firings: six firings in one sweep cycle through six different
    UAs in order rather than potentially picking the same one twice.
    """
    global _rotator_index
    with _rotator_lock:
        ua = _USER_AGENTS[_rotator_index % len(_USER_AGENTS)]
        _rotator_index += 1
    return ua


def pool_size() -> int:
    """Return the number of UAs in the rotation pool (for tests + telemetry)."""
    return len(_USER_AGENTS)


def _reset_for_tests() -> None:
    """Reset the rotator counter to 0. ONLY for tests asserting determinism."""
    global _rotator_index
    with _rotator_lock:
        _rotator_index = 0
