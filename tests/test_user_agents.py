"""UA rotation pool tests — plan 38 § D.3.

Asserts pool composition + browser-product smoke + round-robin determinism.
Freshness check on the `# Last refreshed:` comment ensures the pool doesn't
silently rot past the soft expiry.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest

from scraper import user_agents


def test_pool_has_eight_user_agents():
    assert user_agents.pool_size() == 8


def test_every_ua_contains_recognized_browser_product():
    products = ("Chrome", "Firefox", "Safari", "Edg")
    for ua in user_agents._USER_AGENTS:
        assert any(product in ua for product in products), f"unrecognized UA: {ua}"


def test_pool_covers_three_major_engines():
    """Pool must include at least one Chrome, one Firefox, one Safari."""
    blob = "\n".join(user_agents._USER_AGENTS)
    assert "Chrome/" in blob
    assert "Firefox/" in blob
    # Safari UA has both "Safari/605" (engine) and "Version/" (browser).
    assert "Version/" in blob


def test_pool_includes_three_oses():
    """Windows, macOS, Linux all represented at least once."""
    blob = "\n".join(user_agents._USER_AGENTS)
    assert "Windows NT" in blob
    assert "Mac OS X" in blob
    assert "Linux" in blob


def test_pool_excludes_mobile_user_agents():
    """Mobile UAs trigger different DOM on LinkedIn/Indeed (OQ.4)."""
    blob = "\n".join(user_agents._USER_AGENTS)
    assert "Mobile" not in blob
    assert "Android" not in blob
    assert "iPhone" not in blob
    assert "iPad" not in blob


def test_pick_user_agent_is_round_robin():
    """Successive calls cycle through every UA in order, then wrap."""
    user_agents._reset_for_tests()
    picks = [user_agents.pick_user_agent() for _ in range(user_agents.pool_size())]
    assert picks == list(user_agents._USER_AGENTS)
    # Wrap-around: 9th pick equals the first.
    assert user_agents.pick_user_agent() == user_agents._USER_AGENTS[0]


def test_pick_user_agent_thread_safe(monkeypatch):
    """Round-robin must serialize even under concurrent picks."""
    import threading

    user_agents._reset_for_tests()
    results: list[str] = []

    def pick():
        results.append(user_agents.pick_user_agent())

    threads = [threading.Thread(target=pick) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 16 picks → every UA appears exactly twice (16 = 2 * pool_size).
    assert len(results) == 16
    counts = {ua: results.count(ua) for ua in user_agents._USER_AGENTS}
    assert all(c == 2 for c in counts.values()), counts


def test_pool_refresh_marker_present():
    """A `# Last refreshed: YYYY-MM-DD` comment lives at the top of the pool."""
    src_path = Path(__file__).resolve().parent.parent / "src" / "scraper" / "user_agents.py"
    text = src_path.read_text()
    match = re.search(r"#\s*Last refreshed:\s*(\d{4}-\d{2}-\d{2})", text)
    assert match is not None, "missing `# Last refreshed: YYYY-MM-DD` marker"


def test_pool_refresh_marker_not_stale():
    """`# Last refreshed:` date must be within 365 days (soft expiry).

    Forces a quarterly-ish refresh cadence so the pool doesn't fingerprint
    Naavik as "ancient Chrome 130 traffic" forever.
    """
    src_path = Path(__file__).resolve().parent.parent / "src" / "scraper" / "user_agents.py"
    text = src_path.read_text()
    match = re.search(r"#\s*Last refreshed:\s*(\d{4}-\d{2}-\d{2})", text)
    assert match is not None
    last_refresh = datetime.strptime(match.group(1), "%Y-%m-%d")
    # If this test fails: refresh `_USER_AGENTS` to current stable-channel
    # versions per https://www.useragentstring.com/ + bump the comment.
    age_days = (datetime.now() - last_refresh).days
    if age_days > 365:
        pytest.fail(f"UA pool is {age_days} days stale; refresh _USER_AGENTS + bump comment")


# ── Integration with Crawl4AIClient ──────────────────────────────────────


def test_crawl4ai_client_uses_pool_when_no_user_agent_given():
    """Default `Crawl4AIClient` construction pulls from the rotation pool."""
    from scraper.crawl4ai_client import Crawl4AIClient

    client = Crawl4AIClient()
    assert client.user_agent in user_agents._USER_AGENTS


def test_crawl4ai_client_pinned_user_agent_wins():
    """Explicit `user_agent=...` bypasses the rotation."""
    from scraper.crawl4ai_client import Crawl4AIClient

    pinned = "Mozilla/5.0 TestPin"
    client = Crawl4AIClient(user_agent=pinned)
    assert client.user_agent == pinned
    assert client._browser_config.user_agent == pinned
