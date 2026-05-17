"""Idempotent seeding from `db/sample_data.py` into Postgres.

Per plan 10 § B.9 + SAMPLE_DATA.md § A. Reads every fixture list from the
Pydantic shadow models in `db/sample_data.py`, converts each row to its
SQLModel counterpart via `model_dump()`, and INSERTs in dependency order
with `ON CONFLICT (id) DO NOTHING` so reruns are safe.

CLI: `uv run python -m db.seed`. Called automatically by `nix run .#dev`
after `alembic upgrade head` succeeds (per plan 10 § B.9).

Plan 10b (item 3, 2026-05-03): the seeded `User` row gets a real bcrypt
hash at seed time. Source of truth for the plaintext password:

  1. `NAAVIK_DEV_PASSWORD` env var when set — stable across reseeds, never
     printed (the operator already knows it).
  2. Otherwise a fresh 16-char alphanumeric secret, printed once to stdout
     so the self-hoster can sign in.

If a User row already exists at seed time, we leave its `password_hash`
alone (idempotency) and print a hint about how to reset it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import string
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import settings as app_settings
from db import sample_data as sd
from db.session import async_session, engine
from models import (
    ApiUsage,
    AppEvent,
    Application,
    ApplicationScreenerAnswer,
    ATSCredential,
    Bullet,
    Certification,
    Contact,
    ContactApplicationLink,
    Education,
    EmailThread,
    Experience,
    GeneratedDocument,
    Job,
    OutreachMessage,
    Profile,
    Project,
    Settings,
    Skill,
    User,
)
from models.enums import DeploymentMode
from services.auth import hash_password

log = logging.getLogger(__name__)


# Insert order respects FK dependencies: parents → children. Each tuple is
# (sql_model_class, source_iterable, primary_key_columns_for_conflict).
_TABLE_ORDER: list[tuple[type[SQLModel], Sequence, tuple[str, ...]]] = [
    (User, [sd.USER], ("id",)),
    (Settings, [sd.SETTINGS], ("user_id",)),
    (Profile, [sd.PROFILE], ("id",)),
    (Experience, sd.EXPERIENCES, ("id",)),
    (Bullet, sd.BULLETS, ("id",)),
    (Skill, sd.SKILLS, ("id",)),
    (Education, sd.EDUCATIONS, ("id",)),
    (Project, sd.PROJECTS, ("id",)),
    (Certification, sd.CERTIFICATIONS, ("id",)),
    (Contact, sd.CONTACTS, ("id",)),
    (Job, sd.JOBS, ("id",)),
    (Application, sd.APPLICATIONS, ("id",)),
    (ContactApplicationLink, sd.CONTACT_APPLICATION_LINKS, ("id",)),
    (OutreachMessage, sd.OUTREACH_MESSAGES, ("id",)),
    (EmailThread, sd.EMAIL_THREADS, ("id",)),
    (AppEvent, sd.APP_EVENTS, ("id",)),
    (GeneratedDocument, sd.GENERATED_DOCUMENTS, ("id",)),
    (ApplicationScreenerAnswer, sd.SCREENER_ANSWERS, ("id",)),
    (ATSCredential, sd.ATS_CREDENTIALS, ("id",)),
    (ApiUsage, sd.API_USAGE, ("id",)),
]


_DEV_PASSWORD_ENV = "NAAVIK_DEV_PASSWORD"
_DEV_PASSWORD_ALPHABET = string.ascii_letters + string.digits
_DEV_CREDENTIALS_FILENAME = "dev-credentials"


def _resolve_dev_password() -> tuple[str, str]:
    """Return `(plaintext, source)` where source ∈ {"env", "generated"}.

    Env source means the operator chose the value (printing it back is noise).
    Generated source means we made one up and the operator must capture it
    from stdout.
    """
    env = os.environ.get(_DEV_PASSWORD_ENV, "").strip()
    if env:
        return env, "env"
    plaintext = "".join(secrets.choice(_DEV_PASSWORD_ALPHABET) for _ in range(16))
    return plaintext, "generated"


def _write_dev_credentials_file(email: str, password: str) -> Path | None:
    """Persist the seeded dev credential to `<data_dir>/dev-credentials`.

    Plan 10c (10c.3a, 2026-05-11): the orchestrator's `[seed]` stdout line
    scrolls past quickly under `nix run .#dev`; the lifespan echo in
    `src/main.py` reads this file back so the credential lands near the
    bottom of the scrollback, AND `cat ~/.naavik/dev-credentials` is the
    canonical recovery path for self-hosters.

    File contents (two-line format, simple `cat`-friendly):

        email: <addr>
        password: <plaintext>

    Mode 0600 — owner-readable only.

    Caller must enforce the gate (generated + debug + SELF_HOSTED). This
    helper just writes the file.
    """
    data_dir = Path(app_settings.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    creds_path = data_dir / _DEV_CREDENTIALS_FILENAME
    creds_path.write_text(f"email: {email}\npassword: {password}\n")
    creds_path.chmod(0o600)
    return creds_path


def _shadow_to_payload(shadow_obj) -> dict:
    """Convert a Pydantic-shadow instance to a dict suitable for INSERT.

    Uses `model_dump(mode="python")` so `datetime` stays as `datetime`,
    enums stay as enum members, and SQLAlchemy + asyncpg get the native
    types they expect.
    """
    return shadow_obj.model_dump(mode="python")


async def _seed_one(
    session: AsyncSession,
    sql_cls: type[SQLModel],
    rows: Sequence,
    pk_cols: tuple[str, ...],
    *,
    overrides: dict | None = None,
) -> int:
    """INSERT one table's rows with ON CONFLICT DO NOTHING.

    `overrides` (plan 10b item 3): a dict merged into every payload before
    insert. Used to inject a fresh bcrypt hash into the seeded User row
    without baking secret material into the static fixture file.

    Returns the count of rows inserted (rowcount may be -1 with some drivers
    when ON CONFLICT skips; we count what we tried to insert).
    """
    if not rows:
        return 0
    payloads = [_shadow_to_payload(r) for r in rows]
    if overrides:
        for p in payloads:
            p.update(overrides)
    table = sql_cls.__table__
    stmt = pg_insert(table).values(payloads).on_conflict_do_nothing(index_elements=pk_cols)
    await session.exec(stmt)
    return len(payloads)


async def _bump_sequence(session: AsyncSession, table: str, pk_col: str = "id") -> None:
    """Bump the autoincrement sequence past the max id in the table.

    Required after `INSERT ... ON CONFLICT DO NOTHING` with explicit ids,
    since Postgres doesn't advance the sequence when the explicit PK is
    used. Without this, subsequent INSERTs that rely on the sequence
    (e.g. test fixtures appending new rows) collide with seeded ids.
    """
    from sqlalchemy import text

    # Default sequence name follows Postgres' implicit naming for SERIAL/IDENTITY.
    seq_name = f"{table}_{pk_col}_seq"
    sql = text(
        f"""
        SELECT setval(
            '{seq_name}',
            COALESCE((SELECT MAX({pk_col}) FROM "{table}"), 0) + 1,
            false
        )
        """
    )
    try:
        await session.exec(sql)
    except Exception as exc:  # noqa: BLE001
        log.warning("could not bump sequence %s: %s", seq_name, exc)


async def seed() -> dict[str, int]:
    """Idempotent seed across every fixture list. Returns inserted-count summary.

    The seeded `User` row gets a real bcrypt hash sourced from
    `NAAVIK_DEV_PASSWORD` or generated. If the User row already exists,
    we don't change its hash (the operator must own credential rotation).

    Plan 10c (10c.3a, 2026-05-11): when the credential was generated
    (no env override) AND `app_settings.debug` is True AND the seeded
    Settings are self-hosted, also writes `<data_dir>/dev-credentials`
    (mode 0600) so the orchestrator's lifespan echo + `cat` retrieval
    can recover the value if the stdout line scrolled past.
    """
    summary: dict[str, int] = {}
    dev_password, dev_password_source = _resolve_dev_password()

    async with async_session() as session:
        existing_user = (
            await session.exec(select(User).where(User.id == sd.USER.id))
        ).one_or_none()
        user_existed = existing_user is not None

        for sql_cls, rows, pk_cols in _TABLE_ORDER:
            if sql_cls is User and not user_existed:
                # Fresh DB — inject the real bcrypt hash before insert.
                count = await _seed_one(
                    session,
                    sql_cls,
                    rows,
                    pk_cols,
                    overrides={
                        "password_hash": hash_password(dev_password),
                        # Plan 18 (PC.6, 2026-05-17): server-generated dev
                        # credentials force a change on first login. Env-
                        # supplied creds stay operator-owned (matches plan
                        # 10c's "echo to disk" gate-2 logic).
                        "must_change_password": dev_password_source == "generated",
                    },
                )
            else:
                count = await _seed_one(session, sql_cls, rows, pk_cols)
            summary[sql_cls.__name__] = count
            log.info("seed: %s × %d rows", sql_cls.__name__, count)

        # Advance every sequence past the seeded max so subsequent inserts
        # using SERIAL autoincrement don't collide with existing rows.
        for sql_cls, _, pk_cols in _TABLE_ORDER:
            if pk_cols == ("id",):
                await _bump_sequence(session, sql_cls.__tablename__, "id")
        await session.commit()

    print(f"[seed] dev user: {sd.USER.email}")
    if user_existed:
        print(
            "[seed] dev password: (existing user — credential unchanged; "
            f"unset {_DEV_PASSWORD_ENV}, wipe ./.naavik/db, and reseed to reset)"
        )
    elif dev_password_source == "env":
        print(f"[seed] dev password: (from {_DEV_PASSWORD_ENV} env)")
    else:
        print(
            f"[seed] dev password: {dev_password}  "
            f"(set {_DEV_PASSWORD_ENV} env to override on next reseed)"
        )

    # Plan 10c (10c.3a, 2026-05-11): persist the generated credential to
    # `<data_dir>/dev-credentials` so it survives the orchestrator scrollback
    # interleave. Gated three ways:
    #   1. `dev_password_source == "generated"` — env-supplied passwords are
    #      owned by the operator; never echo them back to disk.
    #   2. `app_settings.debug` — production self-hosters with debug=False
    #      never produce the file.
    #   3. Seeded `Settings.deployment_mode == SELF_HOSTED` — cloud-tier
    #      installs (deployment_mode=CLOUD) never persist plaintext creds.
    # The retrieval path is plain `cat <data_dir>/dev-credentials`; the
    # FastAPI lifespan also re-echoes the file after startup so it lands at
    # the bottom of the orchestrator's scrollback.
    if (
        not user_existed
        and dev_password_source == "generated"
        and app_settings.debug
        and sd.SETTINGS.deployment_mode == DeploymentMode.SELF_HOSTED
    ):
        try:
            creds_path = _write_dev_credentials_file(sd.USER.email, dev_password)
            print(f"[seed] dev credentials written to {creds_path} (mode 0600)")
        except OSError as exc:
            log.warning(
                "could not write %s under %s: %s — credential is still in the [seed] log line above",
                _DEV_CREDENTIALS_FILENAME,
                app_settings.data_dir,
                exc,
            )

    return summary


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    summary = await seed()
    total = sum(summary.values())
    print(f"[seed] inserted {total} rows across {len(summary)} entities")
    for name, count in summary.items():
        print(f"  {name:32s} {count:5d}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
