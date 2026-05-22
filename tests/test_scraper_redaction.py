"""Redaction helper tests — plan 31 § D.7 #1-#4 + plan 32 § D.2-D.3 + plan 64 PR #165 fix.

Pure-function tests; no DB, no fixtures, no Crawl4AI.
"""

from __future__ import annotations

import pytest

from scraper.redaction import safe_exc, safe_msg, safe_url

pytestmark = pytest.mark.uses_sample_data_shims


def test_safe_url_strips_query_and_fragment():
    assert (
        safe_url("https://x.com/jobs/12345?token=secret&apply=1#applicant-info")
        == "https://x.com/jobs/12345"
    )


def test_safe_url_handles_none_and_empty():
    assert safe_url(None) == "<no-url>"
    assert safe_url("") == "<no-url>"


def test_safe_url_blocks_non_http_schemes():
    assert safe_url("file:///etc/passwd") == "<scheme-blocked: file '/etc/passwd'>"
    assert safe_url("gopher://x:6379/_INFO") == "<scheme-blocked: gopher '/_INFO'>"
    assert safe_url("javascript:alert(1)") == "<scheme-blocked: javascript 'alert(1)'>"


# ── Plan 64 § D.8 — safe_url strips Basic-auth userinfo ──────────────────


def test_safe_url_strips_basic_auth_userinfo():
    """The pre-plan-64 safe_url preserved netloc; plan 64 fixed it."""
    assert safe_url("https://user:pass@example.com/jobs/1") == "https://example.com/jobs/1"


def test_safe_url_strips_userinfo_with_port():
    assert (
        safe_url("http://user:pass@gate.example.com:7000/path")
        == "http://gate.example.com:7000/path"
    )


def test_safe_url_strips_userinfo_with_special_chars():
    # URL-encoded passwords are common from provider dashboards.
    assert (
        safe_url("http://user-sess-XYZ:pass%21word@gate.smartproxy.com:7000/x")
        == "http://gate.smartproxy.com:7000/x"
    )


def test_safe_url_strips_userinfo_combined_with_query_strip():
    """Both userinfo AND query string are stripped in one call."""
    out = safe_url("https://leaked:creds@example.com/jobs/1?token=abc#section")
    assert out == "https://example.com/jobs/1"
    assert "leaked" not in out
    assert "creds" not in out
    assert "token" not in out


def test_safe_exc_truncates_long_message():
    exc = ValueError("x" * 500)
    redacted = safe_exc(exc)
    assert redacted == "ValueError: " + "x" * 200
    assert len(redacted) <= 220


def test_safe_exc_preserves_class_name():
    class IntegrityError(Exception):
        pass

    assert safe_exc(IntegrityError("dup")).startswith("IntegrityError:")


# ── plan 32 D.2 / D.3 — safe_msg + safe_exc control-char strip ───────────


def test_safe_msg_strips_control_chars_and_caps_at_200():
    raw = "fatal: \x1b[31mERROR\x1b[0m\n  details=" + "x" * 400 + "\x00\x07"
    redacted = safe_msg(raw)
    assert "\x1b" not in redacted
    assert "\x00" not in redacted
    assert "\x07" not in redacted
    assert "\n" in redacted
    assert len(redacted) <= 200
    assert safe_msg(None) == "<no-msg>"
    assert safe_msg("") == "<no-msg>"


def test_safe_exc_strips_ansi_escape_sequences():
    exc = ValueError("\x1b[31mboom\x1b[0m\r\nleak=\x00\x01\x02secret")
    redacted = safe_exc(exc)
    assert redacted.startswith("ValueError:")
    assert "\x1b" not in redacted
    assert "\r" not in redacted
    assert "\x00" not in redacted
    assert "boom" in redacted
    assert "secret" in redacted


# ── Plan 64 PR #165 delta-fix — safe_msg URL-strip (MED) ──────────────────


def test_safe_msg_strips_proxy_userinfo_from_embedded_url():
    """MED: pre-fix safe_msg left embedded URLs intact, leaking proxy creds.

    Upstream libraries (httpx, Playwright, crawl4ai) routinely embed the
    target URL verbatim in their error messages. With Basic-auth in URL form
    that URL carries `user:pass@`, so the leak path was free-text errors
    flowing through safe_msg into log.warning.
    """
    raw = "connect failed for https://leakeduser123:leakedpass456@proxy.example.com:8080/path"
    redacted = safe_msg(raw)
    assert "leakeduser123" not in redacted
    assert "leakedpass456" not in redacted
    assert "proxy.example.com:8080" in redacted


def test_safe_msg_strips_multiple_embedded_urls():
    """Two URLs in one message — both get URL-stripped."""
    raw = "tried http://user1:pass1@a.example:7000 then https://user2:pass2@b.example:8443/path"
    redacted = safe_msg(raw)
    assert "user1" not in redacted
    assert "pass1" not in redacted
    assert "user2" not in redacted
    assert "pass2" not in redacted
    assert "a.example:7000" in redacted
    assert "b.example:8443" in redacted


def test_safe_msg_preserves_message_without_url():
    raw = "fatal: index out of range"
    redacted = safe_msg(raw)
    assert redacted == "fatal: index out of range"


def test_safe_msg_url_strip_runs_before_truncation():
    """Credentials at the start of a long message survive the URL-strip even if
    the message would otherwise be capped past them."""
    raw = "https://leakuserSTART:leakpassSTART@gate.example.com:7000 " + ("x" * 400)
    redacted = safe_msg(raw)
    assert "leakuserSTART" not in redacted
    assert "leakpassSTART" not in redacted


# ── Plan 64 PR #165 delta-fix — safe_exc chain walk + URL strip (HIGH) ────


def test_safe_exc_flat_strips_proxy_url_from_message():
    """HIGH: a flat exception carrying a proxy URL in its message must redact."""

    class ProxyError(Exception):
        pass

    exc = ProxyError("connect to https://leakuser:leakpass@proxy.example.com:8080 failed")
    redacted = safe_exc(exc)
    assert "leakuser" not in redacted
    assert "leakpass" not in redacted
    assert "proxy.example.com:8080" in redacted
    assert redacted.startswith("ProxyError: ")


def test_safe_exc_walks_chained_cause():
    """HIGH: chained-exception `raise X from Y` — both levels URL-stripped."""

    class OriginalProxyError(Exception):
        pass

    class WrapperError(Exception):
        pass

    try:
        try:
            raise OriginalProxyError(
                "tcp connect to https://leakuser:leakpass@proxy.example.com:8080 timed out"
            )
        except OriginalProxyError as cause:
            raise WrapperError("scrape failed during fetch") from cause
    except WrapperError as exc:
        redacted = safe_exc(exc)

    assert "leakuser" not in redacted
    assert "leakpass" not in redacted
    assert "WrapperError" in redacted
    assert "OriginalProxyError" in redacted
    assert "caused by:" in redacted
    assert "proxy.example.com:8080" in redacted


def test_safe_exc_walks_implicit_context():
    """During-handling-of chaining (`__context__`) — same redaction."""

    class A(Exception):
        pass

    class B(Exception):
        pass

    try:
        try:
            raise A("first: http://leakuserA:leakpassA@a.example:7000")
        except A:
            # No `from` → context only, not cause.
            raise B("wrapper")  # noqa: B904
    except B as exc:
        redacted = safe_exc(exc)

    assert "leakuserA" not in redacted
    assert "leakpassA" not in redacted
    assert "B:" in redacted
    assert "A:" in redacted


def test_safe_exc_truncates_at_max_len():
    """Default max_len=500 truncates a chain that would otherwise be longer."""

    class E1(Exception):
        pass

    class E2(Exception):
        pass

    try:
        try:
            raise E1("x" * 300)
        except E1 as cause:
            raise E2("y" * 300) from cause
    except E2 as exc:
        redacted = safe_exc(exc)

    assert len(redacted) <= 500


def test_safe_exc_custom_max_len():
    """`max_len` parameter caps the joined output."""
    exc = ValueError("a" * 1000)
    redacted = safe_exc(exc, max_len=50)
    assert len(redacted) <= 50


def test_safe_exc_depth_limit_terminates_self_referential_chain():
    """Pathological self-referential chain doesn't infinite-loop."""

    class Looping(Exception):
        pass

    exc = Looping("looped")
    # Cycle by hand — __cause__ pointing back at itself.
    exc.__cause__ = exc  # noqa: PLW0177  not really; this is the cycle
    # Must terminate (the seen-set guard catches the cycle).
    redacted = safe_exc(exc)
    assert "Looping" in redacted


def test_safe_exc_signature_backward_compatible():
    """Single-arg call still works (existing test contract)."""
    exc = ValueError("x" * 500)
    redacted = safe_exc(exc)
    # Single level → per-level msg cap is 200, prefix is "ValueError: ".
    assert redacted.startswith("ValueError: ")
    # safe_msg caps message at 200; total len = "ValueError: " + 200 = 212
    assert len(redacted) <= 220
