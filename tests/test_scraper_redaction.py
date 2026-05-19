"""Redaction helper tests — plan 31 § D.7 #1-#4.

Pure-function tests; no DB, no fixtures, no Crawl4AI.
"""

from __future__ import annotations

from scraper.redaction import safe_exc, safe_url


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


def test_safe_exc_truncates_long_message():
    exc = ValueError("x" * 500)
    redacted = safe_exc(exc)
    assert redacted == "ValueError: " + "x" * 200
    assert len(redacted) <= 220


def test_safe_exc_preserves_class_name():
    class IntegrityError(Exception):
        pass

    assert safe_exc(IntegrityError("dup")).startswith("IntegrityError:")
