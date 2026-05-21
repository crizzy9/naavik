"""Redaction helper tests — plan 31 § D.7 #1-#4 + plan 32 § D.2-D.3.

Pure-function tests; no DB, no fixtures, no Crawl4AI.
"""

from __future__ import annotations

from scraper.redaction import safe_exc, safe_msg, safe_url


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
