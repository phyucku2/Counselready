"""Startup guards and configuration.

The guard lives in the lifespan rather than in `Settings` construction (ADR-0003), so
these tests also pin that a bare `Settings()` never raises — importing config must stay
safe for Alembic and scripts.
"""

from __future__ import annotations

import pytest

from app.core.config import AppEnv, Settings
from app.core.logging import configure_logging
from app.main import StartupConfigurationError, check_serving_configuration


def test_constructing_settings_without_a_database_url_does_not_raise() -> None:
    """A config-time validator would break `alembic upgrade head`, which holds a
    database URL but no serving configuration."""
    assert Settings(app_env=AppEnv.production, database_url=None).database_url is None


def test_serving_in_production_without_a_database_url_fails_closed() -> None:
    with pytest.raises(StartupConfigurationError, match="DATABASE_URL"):
        check_serving_configuration(Settings(app_env=AppEnv.production, database_url=None))


def test_serving_in_staging_without_a_database_url_fails_closed() -> None:
    with pytest.raises(StartupConfigurationError, match="DATABASE_URL"):
        check_serving_configuration(Settings(app_env=AppEnv.staging, database_url=None))


def test_serving_locally_without_a_database_url_is_allowed() -> None:
    """Local development boots without Postgres so API-shape work is unblocked."""
    check_serving_configuration(Settings(app_env=AppEnv.local, database_url=None))


def test_serving_with_a_database_url_is_allowed_in_production() -> None:
    check_serving_configuration(
        Settings(app_env=AppEnv.production, database_url="postgresql+asyncpg://h/db")
    )


def test_is_production_reflects_the_environment() -> None:
    assert Settings(app_env=AppEnv.production).is_production
    assert not Settings(app_env=AppEnv.local).is_production


def test_configure_logging_installs_exactly_one_handler() -> None:
    import logging

    configure_logging("DEBUG")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert root.level == logging.DEBUG
