"""Closed-vocabulary CHECK constraints on de-facto enum string columns.

Revision ID: 0040_closed_vocab_checks
Revises: 0039_money_numeric
Create Date: 2026-07-05

Plan 94 slice C (plan 91 § 7.3). Eight string columns carry closed
vocabularies enforced only by writer discipline; a stray value renders as
a blank chip / silently skips filters instead of failing loudly. The
vocabularies below were derived from the writers and verified against the
live dev DB (every existing row already passes — no data rewrite needed).

Deliberately skipped (see plan 94 § Deviations): the `Settings.*` strings
(single-row-per-user config with service-layer validation) and columns
whose vocabulary is still open by design.

Postgres-only like 0038/0039: the sqlite test substrate builds from model
metadata directly (these constraints ship on the models too).
"""

from __future__ import annotations

from alembic import op

revision = "0040_closed_vocab_checks"
down_revision = "0039_money_numeric"
branch_labels = None
depends_on = None

_CHECKS: list[tuple[str, str, str]] = [
    (
        "ck_job_url_type_vocab",
        "job",
        "url_type IN ('ats', 'external', 'manual', 'email_receipt')",
    ),
    (
        "ck_job_apply_kind_vocab",
        "job",
        "apply_kind IS NULL OR apply_kind IN ("
        "'greenhouse', 'lever', 'ashby', 'workday', 'icims', "
        "'smartrecruiters', 'taleo', 'bamboohr', 'recruitee', 'jobvite', "
        "'breezy', 'workable', 'external', 'easy_apply', 'unknown')",
    ),
    (
        "ck_job_apply_resolved_via_vocab",
        "job",
        "apply_resolved_via IS NULL OR apply_resolved_via IN ("
        "'ats_discovery', 'board_trust', 'direct', 'exhausted', "
        "'linkedin_auth', 'linkedin_guest', 'linkedin_guest_slug', "
        "'manual', 'unresolved')",
    ),
    (
        "ck_project_kind_vocab",
        "project",
        "kind IN ('project', 'open_source')",
    ),
    (
        "ck_email_thread_provider_vocab",
        "email_thread",
        "provider IN ('gmail', 'outlook', 'imap')",
    ),
    (
        "ck_email_message_provider_vocab",
        "email_message",
        "provider IN ('gmail', 'outlook', 'imap')",
    ),
    (
        "ck_outreach_message_channel_vocab",
        "outreach_message",
        "channel IN ('linkedin_dm', 'linkedin', 'email')",
    ),
    (
        "ck_api_usage_method_vocab",
        "api_usage",
        "method IN ('complete', 'structured', 'stream', 'embed')",
    ),
]


def upgrade() -> None:
    for name, table, condition in _CHECKS:
        op.create_check_constraint(name, table, condition)


def downgrade() -> None:
    for name, table, _condition in _CHECKS:
        op.drop_constraint(name, table, type_="check")
