"""Apply-target resolution provenance — guessed vs authoritative.

Revision ID: 0034_apply_resolved_via
Revises: 0033_scrape_dedup_counter
Create Date: 2026-07-03

The LinkedIn pipeline redesign resolves the real apply target from the guest
page's company slug (Tier A) or an authenticated LinkedIn session (Tier B)
instead of guessing. `job.apply_resolved_via` records WHICH path produced the
result — "direct" / "linkedin_guest_slug" / "linkedin_auth" are authoritative,
"ats_discovery" is a company-name guess, "unresolved" ran but stayed unknown.
NULL = resolution never attempted.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_apply_resolved_via"
down_revision: str | None = "0033_scrape_dedup_counter"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job", sa.Column("apply_resolved_via", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("job", "apply_resolved_via")
