"""APScheduler jobstore — pickle → JSON one-shot rewrite.

Revision ID: 0009_pickle_to_json_jobs
Revises: 0008_scraper_rate_limits
Create Date: 2026-05-20

Per docs/plans/48-0.2.0.10b-pickle-deser-replacement.md § D.3. Reads
existing `apscheduler_jobs.job_state` BYTEA rows, decodes each pickle
blob, re-encodes as JSON via `scheduler.json_jobstore._encode_job_state`,
writes back in-place. Idempotent: rows already in JSON format (detected
by first byte != pickle protocol marker) are skipped. Corrupt /
unrecognized rows are LOGGED + SKIPPED — migration completes even if a
row fails. Matches SQLAlchemyJobStore._get_jobs's existing "remove on
failed reconstitute" contract — the next scheduler boot sweeps any
remaining corrupt rows.

Downgrade reverses: JSON → pickle. Same skip-on-failure semantics.
"""

from __future__ import annotations

import logging
import pickle  # noqa: S403 — migration-only; not in runtime code path
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_pickle_to_json_jobs"
down_revision: str | None = "0008_scraper_rate_limits"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")

# Pickle blobs start with PROTO opcode 0x80 followed by the protocol byte.
# JSON-encoded UTF-8 starts with `{` (0x7b). The rewrite re-encodes via
# `_encode_job_state`, so legitimate JSON rows pass through unchanged on
# re-encode.
_PICKLE_PROTO_BYTE = 0x80


def _looks_like_pickle(blob: bytes) -> bool:
    return len(blob) > 0 and blob[0] == _PICKLE_PROTO_BYTE


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "apscheduler_jobs" not in inspector.get_table_names():
        log.info("apscheduler_jobs table absent; skipping pickle→JSON rewrite")
        return

    from scheduler.json_jobstore import _encode_job_state

    rows = bind.execute(sa.text("SELECT id, job_state FROM apscheduler_jobs")).fetchall()

    rewritten = 0
    skipped_json = 0
    failed = 0
    for row in rows:
        job_id, blob = row[0], bytes(row[1])
        if not _looks_like_pickle(blob):
            skipped_json += 1
            continue
        try:
            state = pickle.loads(blob)  # noqa: S301 — migrating away from this
            new_blob = _encode_job_state(state)
        except Exception as exc:  # noqa: BLE001
            log.warning("0009: skipping non-decodable job_state for id=%s: %s", job_id, exc)
            failed += 1
            continue
        bind.execute(
            sa.text("UPDATE apscheduler_jobs SET job_state = :s WHERE id = :i"),
            {"s": new_blob, "i": job_id},
        )
        rewritten += 1
    log.info(
        "0009 pickle→JSON: rewritten=%d skipped_already_json=%d failed=%d",
        rewritten,
        skipped_json,
        failed,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "apscheduler_jobs" not in inspector.get_table_names():
        return

    from scheduler.json_jobstore import _decode_job_state

    rows = bind.execute(sa.text("SELECT id, job_state FROM apscheduler_jobs")).fetchall()

    rewritten = 0
    failed = 0
    for row in rows:
        job_id, blob = row[0], bytes(row[1])
        if _looks_like_pickle(blob):
            continue
        try:
            state = _decode_job_state(blob)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "0009 downgrade: skipping non-decodable job_state for id=%s: %s",
                job_id,
                exc,
            )
            failed += 1
            continue
        new_blob = pickle.dumps(state, pickle.HIGHEST_PROTOCOL)
        bind.execute(
            sa.text("UPDATE apscheduler_jobs SET job_state = :s WHERE id = :i"),
            {"s": new_blob, "i": job_id},
        )
        rewritten += 1
    log.info("0009 downgrade JSON→pickle: rewritten=%d failed=%d", rewritten, failed)
