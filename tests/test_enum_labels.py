"""Postgres enum-label ↔ Python member-name parity — migration 0026 guard.

SQLAlchemy's `sa.Enum(PyEnum)` binds parameters as the member **name**, so
every native Postgres enum type must carry labels equal to the Python member
names. Four types were historically created from lowercase *values* instead
(`closedreason`, `emailaccountprovider`, `emailaccountstatus`,
`unclassifiedreason`, plus one `appeventkind` label), which made every bind
against them fail at runtime — the email-sync cron crashed every 10 minutes
and applications could not be closed with a reason. Migration
`0026_enum_label_names` renames those labels.

Two layers of defense:

1. `test_pg_enum_labels_match_member_names` (NAAVIK_LIVE_DB=1) — for every
   model column bound to a native enum, assert the live Postgres type's
   labels equal the member names. Catches any future migration that creates
   or extends a type with `.value` labels.

2. `test_migration_0026_covers_all_name_value_mismatches` (unconditional) —
   static check that 0026's rename table maps each historical lowercase
   label to the exact member name of the current Python enum, so enum
   renames in `models/enums.py` can't silently diverge from the migration.
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from sqlmodel import SQLModel

import models  # noqa: F401 — registers metadata
from models.enums import (
    AppEventKind,
    ClosedReason,
    EmailAccountProvider,
    EmailAccountStatus,
    SigningAlgorithm,
    UnclassifiedReason,
)

LIVE_DB = os.environ.get("NAAVIK_LIVE_DB") == "1"


def _native_enum_columns() -> dict[str, set[str]]:
    """Map Postgres enum type name → expected labels (member names)."""
    expected: dict[str, set[str]] = {}
    for table in SQLModel.metadata.tables.values():
        for column in table.columns:
            col_type = column.type
            if isinstance(col_type, sa.Enum) and col_type.enum_class is not None:
                expected.setdefault(col_type.name, set()).update(
                    m.name for m in col_type.enum_class
                )
    return expected


@pytest.mark.skipif(not LIVE_DB, reason="requires NAAVIK_LIVE_DB=1 + live Postgres")
def test_pg_enum_labels_match_member_names() -> None:
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine

    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://naavik:password@127.0.0.1:5433/naavik",
    )

    async def _fetch() -> list[tuple[str, str]]:
        engine = create_async_engine(url)
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    sa.text(
                        "SELECT t.typname, e.enumlabel FROM pg_type t "
                        "JOIN pg_enum e ON t.oid = e.enumtypid"
                    )
                )
                return list(result.all())
        finally:
            await engine.dispose()

    rows = asyncio.run(_fetch())
    live: dict[str, set[str]] = {}
    for typname, label in rows:
        live.setdefault(typname, set()).add(label)

    mismatches = {}
    for typname, expected_labels in _native_enum_columns().items():
        got = live.get(typname)
        if got is None:
            continue  # type not migrated yet — chain-replay tests own that
        if not expected_labels <= got:
            mismatches[typname] = {
                "missing_labels": sorted(expected_labels - got),
                "db_labels": sorted(got),
            }
    assert not mismatches, (
        "Postgres enum labels diverge from Python member names (SQLAlchemy "
        f"binds names — these columns fail at runtime): {mismatches}"
    )


def test_migration_0026_covers_all_name_value_mismatches() -> None:
    # Import by path — migrations/ is not an importable package.
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parent.parent
        / "migrations"
        / "versions"
        / "0026_enum_label_names.py"
    )
    spec = importlib.util.spec_from_file_location("m0026", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    renames = {(t, old): new for t, old, new in mod._RENAMES}

    for enum_cls, typname in [
        (ClosedReason, "closedreason"),
        (EmailAccountProvider, "emailaccountprovider"),
        (EmailAccountStatus, "emailaccountstatus"),
        (UnclassifiedReason, "unclassifiedreason"),
    ]:
        for member in enum_cls:
            assert renames.get((typname, member.value)) == member.name, (
                f"0026 must rename {typname} label {member.value!r} → "
                f"{member.name!r}; update _RENAMES if the enum changed"
            )

    assert renames.get(("appeventkind", AppEventKind.EMAIL_STATUS_SUGGESTED.value)) == (
        AppEventKind.EMAIL_STATUS_SUGGESTED.name
    )
    assert renames.get(("signingalgorithm", SigningAlgorithm.EDDSA.value)) == (
        SigningAlgorithm.EDDSA.name
    )
