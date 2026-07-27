"""Engine lifecycle and the readiness probe's failure handling.

No live Postgres here: these pin the behaviour that must hold *without* a database —
lazy engine creation, a clear error when unconfigured, and a probe that reports rather
than raises. Integration tests against a real database arrive with the schema.
"""

from __future__ import annotations

import pytest

from app.core.config import AppEnv, Settings
from app.db import session as db


@pytest.fixture(autouse=True)
async def _reset_engine_state() -> None:
    """Each test starts with no engine and leaves none behind."""
    await db.dispose_engine()


async def test_get_engine_without_a_database_url_raises_a_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(db, "settings", Settings(app_env=AppEnv.local, database_url=None))
    with pytest.raises(db.DatabaseNotConfiguredError, match="DATABASE_URL"):
        db.get_engine()


async def test_the_engine_is_created_once_and_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Importing the module must not connect; the engine is built on first use and
    then shared for the life of the process."""
    monkeypatch.setattr(
        db, "settings", Settings(database_url="postgresql+asyncpg://user@localhost/db")
    )
    assert db.get_engine() is db.get_engine()


async def test_the_sessionmaker_is_created_once_and_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        db, "settings", Settings(database_url="postgresql+asyncpg://user@localhost/db")
    )
    assert db.get_sessionmaker() is db.get_sessionmaker()


async def test_reachability_is_false_when_the_database_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The probe reports state; an unconfigured database is a False, not a 500."""
    monkeypatch.setattr(db, "settings", Settings(database_url=None))
    assert await db.database_is_reachable() is False


async def test_reachability_is_false_when_the_connection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        db,
        "settings",
        Settings(database_url="postgresql+asyncpg://user@127.0.0.1:1/db"),
    )
    assert await db.database_is_reachable() is False


async def test_disposing_clears_the_cached_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        db, "settings", Settings(database_url="postgresql+asyncpg://user@localhost/db")
    )
    first = db.get_engine()
    await db.dispose_engine()
    assert db.get_engine() is not first


async def test_disposing_when_no_engine_exists_is_a_no_op() -> None:
    await db.dispose_engine()
    await db.dispose_engine()
