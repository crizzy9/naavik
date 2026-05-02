"""Async DB session factory.

Uses `NullPool` so each connection lives only for its scope — important
when (a) tests use pytest-asyncio with new event loops per test and (b)
the dev server may be restarted while connections are open. Phase 1
single-user MVP doesn't need a pool; revisit if connection-overhead
becomes measurable in load tests.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import NullPool
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    poolclass=NullPool,
)

async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
