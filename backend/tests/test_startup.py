"""Startup guards and configuration.

The guard lives in the lifespan rather than in `Settings` construction (ADR-0003), so
these tests also pin that a bare `Settings()` never raises — importing config must stay
safe for Alembic and scripts.
"""

from __future__ import annotations

import pytest

from app.core.config import AppEnv, Settings
from app.core.logging import configure_logging
from app.main import (
    StartupConfigurationError,
    check_serving_configuration,
    resolve_jwt_secret,
)


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


def test_serving_in_production_with_full_configuration_is_allowed() -> None:
    check_serving_configuration(
        Settings(
            app_env=AppEnv.production,
            database_url="postgresql+asyncpg://h/db",
            jwt_secret="SYNTHETIC_SIGNING_KEY_LONG_ENOUGH_FOR_HS256",
        )
    )


def test_serving_in_production_without_a_jwt_secret_fails_closed() -> None:
    """A missing signing key must stop the boot, not quietly mint an ephemeral one
    that invalidates every token on the next restart."""
    with pytest.raises(StartupConfigurationError, match="JWT_SECRET"):
        check_serving_configuration(
            Settings(app_env=AppEnv.production, database_url="postgresql+asyncpg://h/db")
        )


def test_multiple_workers_without_a_jwt_secret_fails_closed() -> None:
    """Each worker would mint a different ephemeral key, so a token signed by one is
    rejected by the next — an intermittent logout rather than an honest failure."""
    with pytest.raises(StartupConfigurationError, match="more than one worker"):
        check_serving_configuration(Settings(app_env=AppEnv.local, web_concurrency=4))


def test_a_single_local_worker_without_a_jwt_secret_is_allowed() -> None:
    check_serving_configuration(Settings(app_env=AppEnv.local, web_concurrency=1))


def test_a_configured_secret_is_used_verbatim() -> None:
    assert (
        resolve_jwt_secret(Settings(jwt_secret="SYNTHETIC_SIGNING_KEY_LONG_ENOUGH_FOR_HS256"))
        == "SYNTHETIC_SIGNING_KEY_LONG_ENOUGH_FOR_HS256"
    )


def test_an_unconfigured_secret_yields_a_fresh_ephemeral_key_each_time() -> None:
    """Two boots must not share a key by accident — that would make the ephemeral
    path silently behave like a configured one."""
    first = resolve_jwt_secret(Settings())
    second = resolve_jwt_secret(Settings())
    assert first != second
    assert len(first) >= 32


def test_a_short_jwt_secret_fails_closed() -> None:
    """RFC 7518 §3.2: an HMAC key shorter than the hash output weakens HS256. PyJWT
    only warns; a signing key is not a place to accept a warning."""
    with pytest.raises(StartupConfigurationError, match="at least"):
        check_serving_configuration(Settings(app_env=AppEnv.local, jwt_secret="too-short"))


def test_is_production_reflects_the_environment() -> None:
    assert Settings(app_env=AppEnv.production).is_production
    assert not Settings(app_env=AppEnv.local).is_production


def test_configure_logging_installs_exactly_one_handler() -> None:
    import logging

    configure_logging("DEBUG")
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert root.level == logging.DEBUG
