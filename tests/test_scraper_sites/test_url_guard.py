"""URL guard tests — plan 33 § D.5 / D.8 (8 tests).

Closes the 0.2.0.06b forward refs by enforcing userinfo rejection +
RFC1918 / IMDS / link-local / loopback denylist with a `Settings.debug=True`
escape hatch for localhost dev fixtures.
"""

from __future__ import annotations

import pytest

from scraper import url_guard
from scraper.url_guard import is_safe_destination


@pytest.fixture(autouse=True)
def _reset_resolve_cache():
    """Clear the LRU between tests so monkeypatched DNS doesn't leak."""
    url_guard._resolve_host.cache_clear()
    yield
    url_guard._resolve_host.cache_clear()


def _patch_dns(monkeypatch, host_to_addrs: dict[str, tuple[str, ...]]) -> None:
    """Force `_resolve_host` to return canned results without hitting the network."""

    def fake_resolve(host: str) -> tuple[str, ...]:
        return host_to_addrs.get(host, ())

    monkeypatch.setattr(url_guard, "_resolve_host", fake_resolve)


def test_is_safe_destination_allows_public_https(monkeypatch):
    """Canonical happy path — public host resolves to a public IP."""
    _patch_dns(monkeypatch, {"linkedin.com": ("13.107.42.14",)})
    safe, reason = is_safe_destination("https://linkedin.com/jobs/3729012345")
    assert safe is True
    assert reason is None


def test_userinfo_rejected(monkeypatch):
    """`user:pass@host` form is rejected before DNS resolution even runs."""
    _patch_dns(monkeypatch, {"linkedin.com": ("13.107.42.14",)})
    safe, reason = is_safe_destination("https://user:pass@linkedin.com/")
    assert safe is False
    assert reason == "userinfo_present"


def test_loopback_rejected_when_not_debug(monkeypatch):
    """`Settings.debug=False` blocks the 127.0.0.0/8 RFC range."""
    monkeypatch.setattr(url_guard._settings, "debug", False)
    safe, reason = is_safe_destination("http://127.0.0.1/x")
    assert safe is False
    assert reason is not None
    assert reason.startswith("private_destination:")


def test_loopback_allowed_when_debug(monkeypatch):
    """Dev orchestrator (`NAAVIK_DEBUG=1`) needs localhost fixtures to work."""
    monkeypatch.setattr(url_guard._settings, "debug", True)
    safe, reason = is_safe_destination("http://localhost:8000/x")
    assert safe is True
    assert reason is None


def test_rfc1918_rejected_even_in_debug(monkeypatch):
    """RFC1918 ranges are hard-blocked — debug mode does NOT relax them."""
    monkeypatch.setattr(url_guard._settings, "debug", True)
    _patch_dns(monkeypatch, {"internal.example.com": ("10.0.0.5",)})
    safe, reason = is_safe_destination("http://internal.example.com/")
    assert safe is False
    assert reason == "private_destination:10.0.0.5"


def test_imds_rejected(monkeypatch):
    """AWS IMDS endpoint (169.254.169.254) is the canonical SSRF target."""
    _patch_dns(monkeypatch, {"metadata.example": ("169.254.169.254",)})
    safe, reason = is_safe_destination("http://metadata.example/latest/meta-data/")
    assert safe is False
    assert reason == "private_destination:169.254.169.254"


def test_ipv6_link_local_rejected(monkeypatch):
    """IPv6 link-local (`fe80::/10`) covers the IPv6 SSRF equivalent."""
    safe, reason = is_safe_destination("http://[fe80::1]/x")
    assert safe is False
    assert reason is not None
    assert reason.startswith("private_destination:")


def test_dns_failure_rejected(monkeypatch):
    """When DNS returns no addresses, default to refuse rather than accept."""
    _patch_dns(monkeypatch, {"will.not.resolve": ()})
    safe, reason = is_safe_destination("https://will.not.resolve/x")
    assert safe is False
    assert reason == "dns_resolution_failed"


def test_invalid_host_rejected():
    """`https:///path` has no hostname; reject as malformed."""
    safe, reason = is_safe_destination("https:///path")
    assert safe is False
    assert reason == "invalid_host"


def test_non_http_scheme_rejected():
    """`file://` / `ftp://` / `gopher://` mirror `Crawl4AIClient`'s HttpUrl gate."""
    safe, reason = is_safe_destination("file:///etc/passwd")
    assert safe is False
    assert reason == "scheme_not_allowed:file"
