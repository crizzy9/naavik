"""initial — every entity per docs/design/DATA_MODEL.md § C.

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-02

Single migration covering the full Phase 1 schema:
- pgvector extension (cheap insurance for Phase 6 JobEmbedding)
- 20 tables (19 entities + Settings singleton)
- Every Postgres ENUM type backing the StrEnum vocabulary
- Indexes per DATA_MODEL.md § G (incl. GIN on tag arrays + partial uniques)
- CHECK constraints per DATA_MODEL.md § E (incl. corrected 2026-05-01
  Application.applied_at form covering DRAFT, post-submission, and
  discarded-DRAFT cases)

Implementation note (plan 84 / 0.7.0.37, 2026-05-21):

The original `upgrade()` used `SQLModel.metadata.create_all(LIVE)`, which
snapshots the LIVE in-memory model state at apply time — meaning every
column / table later added by 0002-0022 got created in 0001 too. Each
subsequent `op.add_column` then crashed on `DuplicateColumnError`, making
fresh-install (`rm -rf .naavik/` + `nix run .#dev`) impossible.

This module now builds a SYNTHETIC `MetaData` that mirrors the 0001-era
schema by cloning the surviving LIVE tables and surgically applying the
0001 → today delta:

- **Exclude** the 7 tables created by later migrations
  (`_TABLES_CREATED_LATER`).
- **Strip** the columns later migrations `add_column` against
  (`_COLUMNS_ADDED_LATER`).
- **Restore** the columns later migrations `drop_column`
  (`_COLUMNS_DROPPED_LATER`).

The synthetic metadata is what `op.create_table` receives — `LIVE`
metadata is consulted only as the structural source for column types,
indexes, and constraints (none of which need surgery between 0001 and
today). This keeps the file small + auto-tracks any innocuous LIVE
metadata change (e.g. a Field rename in a 0001-era model) without
hand-editing 600 LOC of explicit DDL.

A static-text regression guard
(`tests/test_alembic_0001_chain_replay.py::test_0001_does_not_use_metadata_create_all`)
fails CI if a future author re-introduces `metadata.create_all` / `drop_all`
in this file. A chain-replay test (NAAVIK_LIVE_DB=1 gated) catches schema
drift between this synthetic 0001-era metadata and what
`metadata.create_all(LIVE)` would produce after applying 0002-0022.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Column, MetaData, Table
from sqlmodel import SQLModel

# Importing the package registers every entity in SQLModel.metadata.
# We consult LIVE metadata as the structural source (column types,
# indexes, constraints) then build a SYNTHETIC MetaData that reflects
# the 0001-era schema.
import models  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ── Delta map — what 0002-0022 change about the 0001-era schema ───────
# Maintained alongside the migration chain. When a new migration adds a
# table / column or drops one, mirror the change here so the chain-replay
# test (`tests/test_alembic_0001_chain_replay.py`) keeps passing.

# Tables created by 0002+ — exclude from 0001's create-set.
_TABLES_CREATED_LATER: frozenset[str] = frozenset(
    {
        "job_scrape_run",  # 0005 plan 27
        "revoked_jwt",  # 0010 plan 50
        "profile_answer",  # 0012 plan 61
        "job_embedding",  # 0013 plan 61
        "tenant",  # 0014 plan 62
        "tenant_signing_key",  # 0014 plan 62
        "profile_embedding",  # 0017 plan 65
    }
)

# Columns added by 0002+ via `op.add_column` — strip from 0001's create-set.
# Keyed by table name.
_COLUMNS_ADDED_LATER: dict[str, frozenset[str]] = {
    "settings": frozenset(
        {
            # 0002 plan 10b
            "allow_multiple_users",
            # 0007 plan 35
            "linkedin_keywords",
            "linkedin_location",
            "indeed_keywords",
            "indeed_location",
            "consecutive_scrape_failures",
            # 0008 plan 38
            "scraper_rate_limits",
            # 0011 plan 59
            "auto_apply_immediate_dispatch",
            # 0013 plan 61
            "semantic_match_enabled",
            "embedding_provider",
            "semantic_match_threshold",
            "semantic_match_sync_on_upsert",
            # 0014 plan 62
            "jwt_rotation_days",
            "jwt_rotation_grace_days",
            # 0016 plan 63
            "auto_apply_adapter_confidence_threshold",
            # 0017 plan 65
            "score_per_dim_weights",
            # 0018 plan 66
            "ai_writing_voice_samples",
            "cover_letter_format",
            "tier_2_evasion_enabled",
            "resume_template_preference",
            "parse_fidelity_threshold",
            # 0019 plan 67
            "generation_tier",
            "originality_api_key",
            # 0021 plan 78
            "auto_apply_per_board_daily_caps",
            "auto_apply_dry_run",
        }
    ),
    "user": frozenset(
        {
            # 0003 plan 18
            "must_change_password",
        }
    ),
    "job": frozenset(
        {
            # 0005 plan 27
            "external_id",
            "remote_policy",
            "seniority_level",
            "posted_at_text",
            "description_extracted_at",
            "description_extraction_model",
            "last_scrape_run_id",
            # 0006 plan 34
            "duplicate_of_id",
        }
    ),
    "application": frozenset(
        {
            # 0018 plan 66
            "generation_trace",
        }
    ),
    "profile": frozenset(
        {
            # 0020 plan 73
            "score_history",
        }
    ),
}


# Columns whose TYPE was changed by 0002+ — override LIVE column type
# with the 0001-era type in the synthetic metadata. 0005 then performs
# the type-promotion / ENUM-extension dance against the 0001-era shape.
#
# Each entry returns the 0001-era `sa.Column` to use in place of the
# LIVE column. The returned column keeps the same name as LIVE.
def _type_overrides_for(table: str) -> dict[str, Column]:
    if table == "job":
        # 0001-era jobsource enum had only `AUTOMATED` + `MANUAL`; 0005
        # added 9 per-source values via `ALTER TYPE jobsource ADD VALUE`.
        # 0001 must create the type with the 2-value form so 0005's
        # `ALTER TYPE` calls succeed AND `WHERE source = 'AUTOMATED'`
        # literals parse.
        jobsource_old = sa.Enum("AUTOMATED", "MANUAL", name="jobsource", native_enum=True)
        # 0001-era `visa_restrictions` was free-form VARCHAR; 0005
        # promoted to a typed enum.
        return {
            "source": Column("source", jobsource_old, nullable=False),
            "visa_restrictions": Column("visa_restrictions", sa.String(), nullable=True),
        }
    if table == "application":
        # 0001-era closedreason enum had 4 values; 0022 added
        # `user_archived`. Recreate the 0001-era 4-value form so 0022's
        # `ALTER TYPE ... ADD VALUE` adds the 5th.
        closedreason_old = sa.Enum(
            "rejected_by_them",
            "withdrawn_by_me",
            "ghosted",
            "accepted_other",
            name="closedreason",
            native_enum=True,
        )
        return {
            "closed_reason": Column("closed_reason", closedreason_old, nullable=True),
        }
    return {}


# Columns dropped by 0002+ via `op.drop_column` — restore in 0001 so the
# later `drop_column` finds something to drop. Column spec captured at
# the time the migration shipped (see deviation note in each migration).
def _restored_columns_for(table: str) -> list[Column]:
    """Return the columns 0002+ migrations drop from `table`.

    These columns existed in the 0001-era model definitions but were
    deleted by later migrations. The chain-replay test verifies the
    drop migrations can still find their target column after 0001 runs.
    """
    if table == "settings":
        # 0004 plan 26 — vault deprecation. The 5 columns were the
        # vault-presence indicators on the Settings singleton; spec
        # matches the live (at-that-time) model definition.
        return [
            Column("llm_api_key_fingerprint", sa.String(), nullable=True),
            Column(
                "discord_webhook_configured",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            Column(
                "telegram_bot_configured",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            Column(
                "portfolio_webhook_configured",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            Column(
                "scraper_proxy_configured",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        ]
    return []


def _build_initial_metadata() -> MetaData:
    """Compose the SYNTHETIC 0001-era MetaData from LIVE + the delta map.

    For each LIVE table that survived to today, clone it into a fresh
    MetaData minus the columns 0002+ added, plus the columns 0002+
    later dropped. Tables created by 0002+ are excluded entirely.

    Indexes are taken from `live_table.indexes` (the authoritative
    source — SQLAlchemy registers both `index=True` column flags and
    `__table_args__` indexes there). To avoid duplicate-index errors
    we strip the `index` flag from cloned columns; the explicit Index
    copy is the sole source.
    """
    initial = MetaData()
    for table_name, live_table in SQLModel.metadata.tables.items():
        if table_name in _TABLES_CREATED_LATER:
            continue
        stripped = _COLUMNS_ADDED_LATER.get(table_name, frozenset())
        type_overrides = _type_overrides_for(table_name)
        kept_columns: list[Column] = []
        for live_col in live_table.columns:
            if live_col.name in stripped:
                continue
            if live_col.name in type_overrides:
                # Type changed between 0001-era and LIVE — use the 0001-
                # era column spec.
                kept_columns.append(type_overrides[live_col.name])
                continue
            # Copy the column into the new MetaData unowned. SQLAlchemy's
            # `Column._copy()` is the documented surface for this.
            new_col = live_col._copy()
            # Strip the `index` flag so SQLAlchemy doesn't auto-create
            # the index — we re-add explicitly from `live_table.indexes`
            # below.
            new_col.index = False
            # Strip the column-level `unique` flag for the same reason —
            # `live_table.constraints` already carries the explicit
            # UniqueConstraint.
            new_col.unique = None
            kept_columns.append(new_col)
        for restored_col in _restored_columns_for(table_name):
            kept_columns.append(restored_col)
        # Carry CHECK + Unique + FK constraints. The implicit PK is
        # rebuilt by sa.Table from the column-level `primary_key=True`
        # flags (preserved by `_copy()`).
        kept_constraints: list = []
        for constraint in live_table.constraints:
            if isinstance(constraint, sa.PrimaryKeyConstraint):
                continue
            if isinstance(constraint, sa.ForeignKeyConstraint):
                if constraint.referred_table.name in _TABLES_CREATED_LATER:
                    continue
                if any(c.name in stripped for c in constraint.columns):
                    continue
            if isinstance(constraint, sa.UniqueConstraint) and any(
                c.name in stripped for c in constraint.columns
            ):
                continue
            kept_constraints.append(_copy_constraint(constraint))
        new_table = Table(
            table_name,
            initial,
            *kept_columns,
            *kept_constraints,
        )
        # Re-attach indexes against the new table, skipping any that
        # reference stripped columns. SQLAlchemy auto-registers each
        # constructed Index on `new_table`.
        for index in live_table.indexes:
            referenced_names = {c.name for c in index.columns if hasattr(c, "name")}
            if referenced_names & stripped:
                continue
            _copy_index_for_table(index, new_table)
    return initial


def _copy_constraint(constraint: sa.Constraint) -> sa.Constraint:
    """Best-effort shallow copy of a constraint for the synthetic MetaData.

    SQLAlchemy doesn't expose a public `Constraint.copy()`. For the
    constraints used in the 0001-era schema (CheckConstraint,
    UniqueConstraint, ForeignKeyConstraint) the inputs are
    string-substitutable; we reconstruct from the source.
    """
    if isinstance(constraint, sa.CheckConstraint):
        # CheckConstraint.sqltext is the canonical source; serialize
        # via str().
        return sa.CheckConstraint(str(constraint.sqltext), name=constraint.name)
    if isinstance(constraint, sa.UniqueConstraint):
        return sa.UniqueConstraint(*[c.name for c in constraint.columns], name=constraint.name)
    if isinstance(constraint, sa.ForeignKeyConstraint):
        # Capture local + remote column names + ondelete/onupdate.
        return sa.ForeignKeyConstraint(
            [c.name for c in constraint.columns],
            [str(fk.column) for fk in constraint.elements],
            name=constraint.name,
            ondelete=constraint.ondelete,
            onupdate=constraint.onupdate,
        )
    # Unknown constraint type — return the original; callers will fail
    # loudly if the constraint can't be re-attached.
    return constraint


def _copy_index_for_table(index: sa.Index, new_table: Table) -> sa.Index:
    """Re-create an index on the new (cloned) table.

    Uses the new table's column references. Preserves dialect kwargs
    (e.g. `postgresql_where` for partial uniques) verbatim — these are
    the load-bearing bits the JOB partial-unique and the GIN trigram
    indexes depend on.
    """
    name_to_col = {c.name: c for c in new_table.columns}
    new_cols = [name_to_col[c.name] for c in index.columns if c.name in name_to_col]
    # `sa.Index(...)` auto-registers on the parent table of the columns
    # it's built from.
    return sa.Index(
        index.name,
        *new_cols,
        unique=index.unique,
        **dict(index.kwargs.items()),
    )


def upgrade() -> None:
    bind = op.get_bind()
    # pgvector enables future Phase 6 JobEmbedding without a re-run.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Build + materialize the synthetic 0001-era MetaData.
    initial = _build_initial_metadata()
    initial.create_all(bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    # Drop in reverse-dependency order. The synthetic MetaData knows
    # the FK graph, so we can ride on its sorted order without manually
    # ordering tables.
    initial = _build_initial_metadata()
    initial.drop_all(bind, checkfirst=False)
    op.execute("DROP EXTENSION IF EXISTS vector")
