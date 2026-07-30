"""Database engine and session management.

The engine is created lazily so that importing this module never opens a connection —
tests, Alembic, and CLI scripts all import it without a running database.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


class DatabaseNotConfiguredError(RuntimeError):
    """Raised when a database operation is attempted without DATABASE_URL set."""


def get_engine() -> AsyncEngine:
    """Return the process-wide engine, creating it on first use."""
    global _engine
    if _engine is None:
        if settings.database_url is None:
            raise DatabaseNotConfiguredError("DATABASE_URL is not set")
        _engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory, creating it on first use."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session that commits on success.

    The transaction wraps the whole request so a handler that writes an audit event
    and then fails leaves neither behind.
    """
    async with get_sessionmaker()() as session:
        async with session.begin():
            yield session


async def database_is_reachable() -> bool:
    """True when a trivial round-trip to the database succeeds.

    Used by the readiness probe, so it swallows every failure mode — an unreachable
    database is a `False`, not an exception propagating into the probe response.
    """
    try:
        engine = get_engine()
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        return False
    return True


async def dispose_engine() -> None:
    """Close pooled connections. Called on application shutdown."""
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
