"""Regression lint — plan 61 (0.2.7.14 + 0.2.7.16) + plan 75 (0.3.3.01).

Every read against `JobEmbedding`, `ProfileAnswer`, or `ProfileEmbedding`
MUST filter by `user_id` (decision D8 — per-user only, no cross-tenant).
The lint scans `src/` for any `select(<table>...)` without an
accompanying `.user_id ==` filter in the same statement.

Why this exists: the embedding row tables don't carry a tenant prefix on
the PK like Application does (job_id PK), so a SELECT without `WHERE
user_id = :uid` would surface another tenant's rows on a multi-user
deployment. The cosine-distance operator returns the closest matches
across the WHOLE table when no predicate is bound. Same logic for
ProfileAnswer — fingerprint collisions across users would leak answers.

Plan 75 / 0.3.3.01: `ProfileEmbedding` (shipped in 0.3.0.03) joins the
target list — code is clean today (3 reads filter by `user_id`); this
extends the guardrail.

If you ever need a cross-user read (admin tooling, debug), add an explicit
`# lint: cross-user-read-ok` pragma on the line — the lint sees that as a
deliberate bypass and lets the line through.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.uses_sample_data_shims

_TARGET_TABLES = ("JobEmbedding", "ProfileAnswer", "ProfileEmbedding")
_PRAGMA = "lint: cross-user-read-ok"


def _select_blocks(src: str, table: str) -> list[tuple[int, str]]:
    """Find `select(<table>...)` statements and capture the surrounding lines.

    A 'block' = the line carrying `select(<table>` plus the next 8 lines so
    the `.where(...)` clause shows up. Returns `[(line_number, block_text)]`.
    """
    lines = src.splitlines()
    pat = re.compile(rf"\bselect\(\s*{re.escape(table)}\b")
    out: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if pat.search(line):
            block = "\n".join(lines[i : i + 8])
            out.append((i + 1, block))
    return out


def _block_has_user_id_filter(block: str) -> bool:
    """True iff the block contains `<Table>.user_id ==` OR carries the
    deliberate-bypass pragma.
    """
    if _PRAGMA in block:
        return True
    return ".user_id ==" in block or ".user_id ==" in block.replace(" ", "")


def test_no_cross_user_select_against_embedding_or_profile_answer():
    src = Path(__file__).resolve().parent.parent / "src"
    offenders: list[str] = []
    for table in _TARGET_TABLES:
        for path in src.rglob("*.py"):
            try:
                body = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for line_no, block in _select_blocks(body, table):
                if not _block_has_user_id_filter(block):
                    rel = path.relative_to(src)
                    offenders.append(f"{rel}:{line_no} — select({table}) without user_id filter")
    assert not offenders, (
        "Plan 61 decision D8 — every JobEmbedding / ProfileAnswer read MUST "
        "filter by user_id. Offenders:\n  - " + "\n  - ".join(offenders) + "\n"
        "If a cross-user read is genuinely needed (admin tooling, debug), "
        "add a `# lint: cross-user-read-ok` pragma on the line."
    )


def test_search_similar_carries_user_id_predicate():
    """The single explicit raw-SQL path in `embedding_service.search_similar`
    must keep `WHERE user_id = :uid` in the SQL string.
    """
    src = Path(__file__).resolve().parent.parent / "src"
    body = (src / "services" / "embedding_service.py").read_text(encoding="utf-8")
    assert "WHERE user_id = :uid" in body, (
        "embedding_service.search_similar lost its `WHERE user_id = :uid` "
        "predicate. Plan 61 decision D8 / multi-tenant boundary. Restore it."
    )
