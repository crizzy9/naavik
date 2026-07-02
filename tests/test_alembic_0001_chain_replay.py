"""Migration chain-replay verification — plan 84 (0.7.0.37).

The existing `tests/test_alembic_NNNN.py` files each verify ONE migration
against the LIVE model state in isolation; none of them cover the FULL
chain (`0001 → head`) from an empty DB. Plan 83's fresh-install Manual
QA was the first surface that exercised that chain on an empty DB; it
crashed on the alembic 0001+0002 race (`DuplicateColumnError`) because
`0001_initial.py` was calling `SQLModel.metadata.create_all(LIVE)` —
snapshotting today's model state and creating columns that 0002-0022
later try to `add_column`.

This file holds three checks:

1. `test_0001_does_not_use_metadata_create_all` — STATIC text guard
   against the root cause. Greps the 0001 body; FAIL if any future
   author reintroduces `SQLModel.metadata.create_all` or
   `SQLModel.metadata.drop_all`. Runs unconditionally.

2. `test_chain_replay_table_set_matches_metadata` — runs `alembic
   upgrade head` against an ephemeral sqlite DB then asserts the
   resulting tables (minus `alembic_version`) equal
   `SQLModel.metadata.tables`. Catches "0001 forgot a table" /
   "0001 created a table 0014 also creates" drift.

3. `test_chain_replay_columns_match_metadata` — asserts every table's
   COLUMN SET (chain-replayed) equals the LIVE metadata's column set.
   Catches "0001 forgot a column" / "0001 created a column 0007 also
   creates" drift.

The two chain-replay tests run only when `NAAVIK_LIVE_DB=1` is exported
(existing repo convention per `tests/test_jwt_rotation_routes.py:55`),
because several migrations (0005 ENUMs, 0013/0017 pgvector, 0014
backfill, etc.) contain Postgres-only DDL gated on
`bind.dialect.name == "postgresql"` — sqlite chain-replay diverges
intentionally on those (see plan 84 § D.2 fallback). The static-text
guard runs unconditionally — it's the floor that prevents the
underlying class of bug from creeping back in.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlmodel import SQLModel

import models  # noqa: F401 — registers metadata

pytestmark = pytest.mark.uses_sample_data_shims

REPO_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
MIGRATIONS_DIR = REPO_ROOT / "migrations" / "versions"
FRESH_INSTALL_LIVE_DB = os.environ.get("NAAVIK_LIVE_DB") == "1"


# ── 1. Static regression guard — runs unconditionally ──────────────────
def test_0001_does_not_use_metadata_create_all() -> None:
    """Plan 84 / 0.7.0.37 root-cause guard.

    `0001_initial.py` must not call `SQLModel.metadata.create_all` or
    `SQLModel.metadata.drop_all`. Either path snapshots the LIVE model
    state and races with 0002+ add/drop operations — see Issue #199 /
    `docs/plans/archive/84-0.7.0.37-alembic-fresh-install-fix.md`.

    Future authors should use explicit `op.create_table(...)` calls (or
    a synthetic-metadata helper) for the 0001-era schema instead.

    The check walks the AST so docstring references to the forbidden
    pattern (the rationale block at the top of the file) don't false-
    positive — only actual `*.metadata.create_all(...)` /
    `*.metadata.drop_all(...)` call expressions trip the guard.
    """
    import ast

    body = (MIGRATIONS_DIR / "0001_initial.py").read_text()
    tree = ast.parse(body)
    forbidden_attr_chains: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match `<anything>.metadata.create_all(...)` and `.drop_all(...)`.
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr not in ("create_all", "drop_all"):
            continue
        parent = func.value
        if isinstance(parent, ast.Attribute) and parent.attr == "metadata":
            forbidden_attr_chains.append(f"{ast.unparse(parent)}.{func.attr}")
    assert not forbidden_attr_chains, (
        "0001_initial.py contains forbidden calls: "
        f"{forbidden_attr_chains!r}. See ROADMAP 0.7.0.37 / Issue #199 / "
        "plan 84. Use explicit op.create_table / op.drop_table calls "
        "(or a synthetic-metadata helper) for the 0001-era schema."
    )


# ── 2 + 3. Chain-replay — runs only when NAAVIK_LIVE_DB=1 (see header) ──
def _alembic_upgrade_head(database_url: str) -> None:
    """Run `alembic upgrade head` as a subprocess against the URL."""
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        check=True,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
    )


@pytest.fixture(scope="module")
def _live_db_url() -> str:
    """DESTRUCTIVE-test DB URL — never plain DATABASE_URL.

    The chain-replay fixture below runs `DROP SCHEMA public CASCADE`. When
    this read plain `DATABASE_URL`, the documented optional gate
    (`NAAVIK_LIVE_DB=1 uv run pytest`) pointed it at the operator's live
    dev database and WIPED IT (2026-07-02 incident — all users / jobs /
    settings lost). Destructive replay is now opt-in via a dedicated env
    var, with a name-based belt-and-suspenders check.
    """
    url = os.environ.get("NAAVIK_CHAIN_REPLAY_DB_URL")
    if not url:
        pytest.skip(
            "chain-replay DROPS the target schema — set NAAVIK_CHAIN_REPLAY_DB_URL "
            "to a THROWAWAY database (name must contain 'test' or 'replay') to enable"
        )
    db_name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    if "test" not in db_name and "replay" not in db_name:
        pytest.fail(
            f"refusing to chain-replay against {db_name!r}: the database name "
            "must contain 'test' or 'replay' (the fixture DROPs the schema)"
        )
    return url


@pytest.fixture
def chain_replayed_inspector(_live_db_url: str) -> sa.engine.reflection.Inspector:
    """Reset the throwaway replay DB, apply 0001 → head, return an Inspector."""
    sync_url = _live_db_url.replace("+asyncpg", "+psycopg")
    engine = sa.create_engine(sync_url)
    with engine.begin() as conn:
        # Drop everything so the test is hermetic across runs.
        conn.execute(sa.text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(sa.text("CREATE SCHEMA public"))
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    engine.dispose()
    _alembic_upgrade_head(_live_db_url)
    engine = sa.create_engine(sync_url)
    try:
        yield sa.inspect(engine)
    finally:
        engine.dispose()


def _live_metadata_table_names() -> set[str]:
    return set(SQLModel.metadata.tables.keys())


def _live_metadata_columns_for(table: str) -> set[str]:
    return {c.name for c in SQLModel.metadata.tables[table].columns}


@pytest.mark.skipif(
    not FRESH_INSTALL_LIVE_DB,
    reason="chain-replay needs Postgres; set NAAVIK_LIVE_DB=1 to enable",
)
def test_chain_replay_table_set_matches_metadata(
    chain_replayed_inspector: sa.engine.reflection.Inspector,
) -> None:
    """Tables after `alembic upgrade head` == LIVE `SQLModel.metadata.tables`.

    Catches: 0001 forgot to create a table that no later migration adds;
    0001 creates a table that 0014 ALSO creates (`tenant`, `tenant_signing_key`,
    etc.); 0002+ adds a table that LIVE metadata no longer has.
    """
    chain_tables = set(chain_replayed_inspector.get_table_names())
    chain_tables.discard("alembic_version")  # alembic-internal; not in LIVE
    chain_tables.discard("apscheduler_jobs")  # plan 25 — created by scheduler
    live_tables = _live_metadata_table_names()
    extra_in_chain = chain_tables - live_tables
    missing_in_chain = live_tables - chain_tables
    assert not extra_in_chain, (
        f"chain-replayed DB has tables LIVE metadata doesn't: {sorted(extra_in_chain)}"
    )
    assert not missing_in_chain, (
        f"LIVE metadata has tables chain-replayed DB doesn't: {sorted(missing_in_chain)}"
    )


@pytest.mark.skipif(
    not FRESH_INSTALL_LIVE_DB,
    reason="chain-replay needs Postgres; set NAAVIK_LIVE_DB=1 to enable",
)
def test_chain_replay_columns_match_metadata(
    chain_replayed_inspector: sa.engine.reflection.Inspector,
) -> None:
    """Per-table column SETS equal LIVE metadata after chain replay.

    Catches: 0001 creates a column that 0007 then `add_column`s
    (`linkedin_keywords` etc.); 0001 forgets a column that 0004 then
    `drop_column`s (the 5 vault columns); 0007 adds a column that LIVE
    no longer has; etc.
    """
    failures: list[str] = []
    for table in sorted(_live_metadata_table_names()):
        if table not in set(chain_replayed_inspector.get_table_names()):
            # Already reported by the table-set test; skip to keep this
            # one's failure messages focused on column drift.
            continue
        chain_cols = {c["name"] for c in chain_replayed_inspector.get_columns(table)}
        live_cols = _live_metadata_columns_for(table)
        extra = chain_cols - live_cols
        missing = live_cols - chain_cols
        if extra or missing:
            failures.append(
                f"  {table!r}: chain-only={sorted(extra)!r} live-only={sorted(missing)!r}"
            )
    assert not failures, (
        "Column-set drift between chain-replayed DB and LIVE metadata:\n" + "\n".join(failures)
    )
