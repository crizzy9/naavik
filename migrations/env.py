"""Alembic environment — sync template (alembic-blessed default).

Wave 4 (plan 10 § B) wired `target_metadata = SQLModel.metadata` so the
single `0001_initial.py` migration captures every entity defined in
`src/models/*.py`. Subsequent migrations are additive.

Plan 10a (PC.1, 2026-05-02) converted from the async wrapper to the sync
template after the async path showed silent stalls at the SQLAlchemy
greenlet-bridge seam in some interactive-shell environments. Migrations
are one-shot and sequential — sync is the right tool. Runtime app code
keeps the AsyncEngine in `db/session.py` unchanged.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Import every model so `SQLModel.metadata` knows about every table when
# Alembic compares against the DB (autogenerate + create_all).
import models  # noqa: F401
from config import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata

# Migration-time URL derives from the runtime URL by swapping the async
# driver for the sync one. The runtime app keeps asyncpg unchanged.
config.set_main_option(
    "sqlalchemy.url",
    settings.database_url.replace("+asyncpg", "+psycopg"),
)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
