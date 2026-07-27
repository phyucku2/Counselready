"""Live-Postgres fixtures.

The schema under test is built by running the real migrations rather than
`metadata.create_all`. Creating tables from the models would test the models against
themselves and let the migration drift away from them unnoticed — the migration is
what production runs, so it is what the tests exercise.

Skipped entirely when TEST_DATABASE_URL is unset, so the unit suite still runs on a
machine with no database.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_ROOT = Path(__file__).resolve().parents[2]

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(TEST_DATABASE_URL is None, reason="TEST_DATABASE_URL is not set")


@pytest.fixture(scope="session")
def migrated_database() -> str:
    """Bring the test database to head, once per test session."""
    if TEST_DATABASE_URL is None:  # pragma: no cover - guarded by pytestmark
        pytest.skip("TEST_DATABASE_URL is not set")

    environment = {**os.environ, "DATABASE_URL": TEST_DATABASE_URL}
    # A subprocess rather than alembic's Python API: env.py drives migrations with
    # asyncio.run(), which cannot be called from inside a running event loop.
    subprocess.run(
        ["alembic", "downgrade", "base"],  # noqa: S607
        cwd=BACKEND_ROOT,
        env=environment,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["alembic", "upgrade", "head"],  # noqa: S607
        cwd=BACKEND_ROOT,
        env=environment,
        check=True,
        capture_output=True,
    )
    return TEST_DATABASE_URL


@pytest_asyncio.fixture()
async def session(migrated_database: str) -> AsyncIterator[AsyncSession]:
    """A session whose work is rolled back, so tests cannot leak into each other."""
    engine = create_async_engine(migrated_database, poolclass=None)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
        await db_session.rollback()
    await engine.dispose()
