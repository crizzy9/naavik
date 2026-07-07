"""Deterministic PII scrubber — plan 95 § 3.4.2 (slice 95f).

Few-shot exemplars built from the owner's corrections travel to cloud
providers; the owner's condition (2026-07-07) is that they leak no
addresses / sensitive data. This is a PURE function with unit tests — no
LLM, no I/O, no config. Applied to every exemplar field before it enters
a prompt; the eval harness asserts no raw @-address survives.

Scrubbed:
- email addresses            → [email]
- phone numbers (7+ digits,  → [phone]
  international/US shapes)
- URLs carrying query strings → [link]  (tracking tokens live there;
  bare path URLs are kept — they identify the ATS, which is signal)
"""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# URLs with a query string — tracking/auth tokens live in the params.
_TOKENED_URL_RE = re.compile(r"https?://[^\s<>\"')\]]*\?[^\s<>\"')\]]*")
# Phone shapes: +1 (617) 555-0123 / 617-555-0123 / +44 20 7946 0958 …
# Requires 7+ digits total so plain years/ids don't false-positive.
_PHONE_RE = re.compile(
    r"(?<![\w./])(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{2,4}[\s.-]\d{2,4}[\s.-]?\d{2,6}"
    r"(?![\w-])"
)


def _phone_replace(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return "[phone]" if len(digits) >= 7 else match.group(0)


def scrub(text: str | None) -> str:
    """Replace addresses, phone numbers, and tokened URLs with placeholders."""
    if not text:
        return ""
    out = _EMAIL_RE.sub("[email]", text)
    out = _TOKENED_URL_RE.sub("[link]", out)
    out = _PHONE_RE.sub(_phone_replace, out)
    return out
