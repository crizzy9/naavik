"""CSV export with formula-injection defang (plan 85 / 0.4.0.23).

Split out of the former services/application_service.py in plan 91 Phase 4.2;
behaviour unchanged. Internal calls to shimmed/patched seams go through
`svc()` (the facade) so test interception keeps working.
"""

from __future__ import annotations

import logging

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models import (
    Application,
)
from services.applications.common import (
    ValidationError,
)
from services.applications.state import BULK_MAX_IDS

log = logging.getLogger(__name__)


# ── CSV formula-injection defang (plan 85 / 0.4.0.23) ───────────────────

# OWASP A03:2021 — Injection. Excel / LibreOffice / Numbers treat any cell
# whose first character is one of these as a formula expression. Operator-
# typed fields (company / role / team / location / external_url) can be
# trivially weaponized via `=cmd|'/c calc'!A1`. Defang by prefixing a
# single-quote leader — CSV-RFC-4180 quote semantics are unaffected.
_CSV_FORMULA_LEADERS = ("=", "+", "-", "@", "\t", "\r")


def _defang_csv_cell(value: object) -> str:
    """Return `value` as a CSV-injection-safe string.

    Prefixes a single-quote to any value whose first character is a known
    formula leader (`=` / `+` / `-` / `@` / tab / CR). Applied to every
    operator-controllable cell in `list_for_export`; also applied (defense-
    in-depth) to typed / enum cells so future schema additions can't leak.

    None → empty string. Non-string values are coerced via `str()` first.
    """
    if value is None:
        return ""
    s = str(value)
    if s and s[0] in _CSV_FORMULA_LEADERS:
        return "'" + s
    return s


async def list_for_export(
    session: AsyncSession,
    *,
    user_id: int,
    application_ids: list[int],
) -> list[dict]:
    """Fetch + denormalize selected applications for CSV export.

    Honors ``user_id`` boundary (cross-user IDs silently filtered out) and
    skips soft-deleted rows. Returns a list of dicts matching the CSV
    fieldnames in the export route.
    """
    if not application_ids:
        return []
    if len(application_ids) > BULK_MAX_IDS:
        raise ValidationError(
            f"Bulk operation limit is {BULK_MAX_IDS} applications per request",
            code="bulk_limit_exceeded",
        )
    stmt = select(Application).where(
        Application.user_id == user_id,
        Application.id.in_(application_ids),
        Application.deleted_at.is_(None),
    )
    rows = (await session.exec(stmt)).all()
    # Plan 85 / 0.4.0.23 — defang every cell to mitigate Excel/LibreOffice
    # formula injection. Operator-controlled fields (company / role / team /
    # location / external_url) are the high-risk path; enum / typed fields
    # are defense-in-depth.
    return [
        {
            "company": _defang_csv_cell(a.company),
            "role": _defang_csv_cell(a.role),
            "team": _defang_csv_cell(a.team),
            "location": _defang_csv_cell(a.location),
            "status": _defang_csv_cell(a.status.value),
            "applied_at": _defang_csv_cell(a.applied_at.isoformat() if a.applied_at else None),
            "salary_min": _defang_csv_cell(a.salary_min),
            "salary_max": _defang_csv_cell(a.salary_max),
            "board": _defang_csv_cell(a.board.value if a.board else None),
            "external_url": _defang_csv_cell(a.external_url),
        }
        for a in rows
    ]
