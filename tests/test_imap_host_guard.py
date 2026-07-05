"""IMAP host SSRF guard tests — plan 90 / 0.5.0.01 (PR #214 hacker H1).

Mirrors `tests/test_scraper_sites/test_url_guard.py`: enforces the RFC1918 /
IMDS / loopback / IPv6-ULA denylist + the `{143, 993}` port allowlist + the
`Settings.debug` loopback escape, all with a monkeypatched resolver so no live
network is touched.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("NAAVIK_DEBUG", "1")

from services.email import imap_host_guard  # noqa: E402
from services.email.imap_host_guard import (  # noqa: E402
    ImapHostNotAllowed,
    check_imap_host,
    ensure_imap_host_allowed,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    imap_host_guard._DNS_CACHE.clear()
    yield
    imap_host_guard._DNS_CACHE.clear()


def _patch_dns(monkeypatch, mapping: dict[str, tuple[str, ...]]) -> None:
    monkeypatch.setattr(imap_host_guard, "_resolve_host", lambda host: mapping.get(host, ()))


def test_allows_public_host_993(monkeypatch):
    _patch_dns(monkeypatch, {"imap.fastmail.com": ("103.168.172.45",)})
    safe, reason = check_imap_host("imap.fastmail.com", 993)
    assert safe is True
    assert reason is None


def test_allows_public_host_143(monkeypatch):
    _patch_dns(monkeypatch, {"imap.fastmail.com": ("103.168.172.45",)})
    safe, _ = check_imap_host("imap.fastmail.com", 143)
    assert safe is True


def test_rejects_imds(monkeypatch):
    """AWS IMDS endpoint is the canonical SSRF target."""
    _patch_dns(monkeypatch, {"metadata.evil": ("169.254.169.254",)})
    safe, reason = check_imap_host("metadata.evil", 993)
    assert safe is False
    assert reason == "private_destination:169.254.169.254"


@pytest.mark.parametrize("ip", ["10.0.0.5", "172.16.4.4", "192.168.1.10"])
def test_rejects_rfc1918(monkeypatch, ip):
    _patch_dns(monkeypatch, {"internal.evil": (ip,)})
    safe, reason = check_imap_host("internal.evil", 993)
    assert safe is False
    assert reason == f"private_destination:{ip}"


def test_rejects_loopback_when_not_debug(monkeypatch):
    monkeypatch.setattr(imap_host_guard._settings, "debug", False)
    _patch_dns(monkeypatch, {"127.0.0.1": ("127.0.0.1",)})
    safe, reason = check_imap_host("127.0.0.1", 993)
    assert safe is False
    assert reason.startswith("private_destination:")


def test_rejects_loopback_ollama_port_even_if_loopback(monkeypatch):
    """Loopback Ollama (`127.0.0.1:11434`) is double-blocked: port + IP."""
    monkeypatch.setattr(imap_host_guard._settings, "debug", True)
    safe, reason = check_imap_host("127.0.0.1", 11434)
    assert safe is False
    assert reason == "port_not_allowed:11434"


@pytest.mark.parametrize("ip6", ["::1", "fe80::1", "fc00::1", "fd12:3456::1"])
def test_rejects_ipv6_internal(monkeypatch, ip6):
    _patch_dns(monkeypatch, {"v6.evil": (ip6,)})
    safe, reason = check_imap_host("v6.evil", 993)
    assert safe is False
    assert reason.startswith("private_destination:")


def test_rejects_ipv6_bracketed_literal(monkeypatch):
    monkeypatch.setattr(imap_host_guard._settings, "debug", False)
    _patch_dns(monkeypatch, {"::1": ("::1",)})
    safe, reason = check_imap_host("[::1]", 993)
    assert safe is False
    assert reason.startswith("private_destination:")


@pytest.mark.parametrize("port", [25, 80, 110, 587, 5432, 11434, 0, 8003])
def test_rejects_disallowed_port(port):
    """Port allowlist is checked before DNS — no resolution needed."""
    safe, reason = check_imap_host("imap.fastmail.com", port)
    assert safe is False
    assert reason == f"port_not_allowed:{port}"


def test_loopback_allowed_when_debug(monkeypatch):
    monkeypatch.setattr(imap_host_guard._settings, "debug", True)
    safe, reason = check_imap_host("localhost", 993)
    assert safe is True
    assert reason is None


def test_rfc1918_rejected_even_in_debug(monkeypatch):
    """debug only opens the loopback escape; RFC1918 stays hard-blocked."""
    monkeypatch.setattr(imap_host_guard._settings, "debug", True)
    _patch_dns(monkeypatch, {"internal.evil": ("10.1.2.3",)})
    safe, reason = check_imap_host("internal.evil", 993)
    assert safe is False
    assert reason == "private_destination:10.1.2.3"


def test_dns_failure_rejected_fail_closed(monkeypatch):
    """No resolved address → DENY (never accept-by-default)."""
    _patch_dns(monkeypatch, {"will.not.resolve": ()})
    safe, reason = check_imap_host("will.not.resolve", 993)
    assert safe is False
    assert reason == "dns_resolution_failed"


def test_empty_host_rejected():
    safe, reason = check_imap_host("   ", 993)
    assert safe is False
    assert reason == "invalid_host"


def test_ensure_raises_on_denied(monkeypatch):
    _patch_dns(monkeypatch, {"metadata.evil": ("169.254.169.254",)})
    with pytest.raises(ImapHostNotAllowed) as exc_info:
        ensure_imap_host_allowed("metadata.evil", 993)
    assert exc_info.value.reason == "private_destination:169.254.169.254"


def test_ensure_passes_on_allowed(monkeypatch):
    _patch_dns(monkeypatch, {"imap.fastmail.com": ("103.168.172.45",)})
    assert ensure_imap_host_allowed("imap.fastmail.com", 993) is None


def test_dns_rebind_toctou_recheck_catches_internal(monkeypatch):
    """A host that resolves public at connect then rebinds to internal is
    caught on the next check once the cache is re-resolved."""
    calls = {"public": ("103.168.172.45",)}

    def _resolve(host: str) -> tuple[str, ...]:
        return calls["host_value"] if host == "imap.fastmail.com" else ()

    calls["host_value"] = ("103.168.172.45",)
    monkeypatch.setattr(imap_host_guard, "_resolve_host", _resolve)

    safe, _ = check_imap_host("imap.fastmail.com", 993)
    assert safe is True

    # DNS rebinds to an internal target (TTL expiry simulated by re-resolve).
    calls["host_value"] = ("169.254.169.254",)
    safe, reason = check_imap_host("imap.fastmail.com", 993)
    assert safe is False
    assert reason == "private_destination:169.254.169.254"


def test_dns_cache_is_ttl_bounded():
    from cachetools import TTLCache

    assert isinstance(imap_host_guard._DNS_CACHE, TTLCache)
    assert imap_host_guard._DNS_CACHE.maxsize == 256
    assert imap_host_guard._DNS_CACHE.ttl == 60.0
