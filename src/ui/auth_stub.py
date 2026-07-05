"""Plan-09 stub auth: a fake `naavik_session=fake-1` cookie in lieu of real JWT.

Plan 10 Wave 4 swaps these for real bcrypt + JWT-cookie + DB-backed Profile
lookup. Routes here keep the same signatures so the eventual swap is body-only.

Per plan 09 § Open question 7 (locked): simulate fake session.
"""

from __future__ import annotations

SESSION_COOKIE = "naavik_session"
FAKE_SESSION_VALUE = "fake-1"
