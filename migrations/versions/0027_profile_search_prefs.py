"""Profile — job-search preferences (docs/design/JOB_SEARCH_PREFERENCES.md).

Revision ID: 0027_profile_search_prefs
Revises: 0026_enum_label_names
Create Date: 2026-07-02

Four additive columns on `profile`:

- `target_titles` (ARRAY[String], NOT NULL default '{}') — user-entered
  target titles; the primary input every scraper derives its queries from.
- `title_expansions` (JSONB, NOT NULL default '{}') — LLM-generated
  equivalent-title sets keyed by title.
- `target_cities` (ARRAY[String], NOT NULL default '{}') — normalized
  "City, ST" strings.
- `remote_ok` (BOOLEAN, NOT NULL default true).

Data migration: seed `target_titles` / `target_cities` from the legacy
per-source `Settings.linkedin_keywords` / `linkedin_location` (falling back
to the Indeed pair) for profiles that have none, then clear the Settings
fields — they survive only as explicit per-source overrides (empty =
derived from profile).

Downgrade drops the columns; the cleared Settings fields are NOT restored
(one-way data move, same posture as the vault sunset migrations).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0027_profile_search_prefs"
down_revision: str | None = "0026_enum_label_names"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    array_type = postgresql.ARRAY(sa.String()) if is_postgres else sa.String()
    jsonb_type = postgresql.JSONB if is_postgres else sa.String()

    op.add_column(
        "profile",
        sa.Column("target_titles", array_type, nullable=False, server_default="{}"),
    )
    op.add_column(
        "profile",
        sa.Column("title_expansions", jsonb_type, nullable=False, server_default="{}"),
    )
    op.add_column(
        "profile",
        sa.Column("target_cities", array_type, nullable=False, server_default="{}"),
    )
    op.add_column(
        "profile",
        sa.Column(
            "remote_ok",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    if not is_postgres:
        return

    # Seed from legacy per-source Settings inputs (LinkedIn first, then
    # Indeed) where the profile has no titles yet, then clear the legacy
    # fields so they become pure per-source overrides.
    bind.execute(
        sa.text(
            """
            UPDATE profile p
            SET target_titles = COALESCE(
                    NULLIF(s.linkedin_keywords, '{}'),
                    NULLIF(s.indeed_keywords, '{}'),
                    '{}'
                ),
                target_cities = CASE
                    WHEN COALESCE(s.linkedin_location, s.indeed_location) IS NOT NULL
                        THEN ARRAY[COALESCE(s.linkedin_location, s.indeed_location)]
                    ELSE '{}'
                END
            FROM settings s
            WHERE s.user_id = p.user_id
              AND p.target_titles = '{}'
              AND (s.linkedin_keywords IS NOT NULL OR s.indeed_keywords IS NOT NULL)
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE settings
            SET linkedin_keywords = NULL,
                linkedin_location = NULL,
                indeed_keywords = NULL,
                indeed_location = NULL
            WHERE linkedin_keywords IS NOT NULL
               OR linkedin_location IS NOT NULL
               OR indeed_keywords IS NOT NULL
               OR indeed_location IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_column("profile", "remote_ok")
    op.drop_column("profile", "target_cities")
    op.drop_column("profile", "title_expansions")
    op.drop_column("profile", "target_titles")
