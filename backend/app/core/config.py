"""Application configuration.

Deliberately free of fail-fast validators: a config-time guard fires in *every*
context that imports this module, including Alembic and one-off scripts that
legitimately hold a database URL without any serving-only secret. Deployment-context
checks belong in the application lifespan (see `app.main`), which only runs where the
app actually serves.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppEnv(StrEnum):
    """Deployment context. Drives guards applied at startup, never at import."""

    local = "local"
    staging = "staging"
    production = "production"


class Settings(BaseSettings):
    """Runtime settings, read from the environment or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: AppEnv = AppEnv.local
    log_level: str = "INFO"

    # Unset in unit tests and in contexts that never touch the database.
    database_url: str | None = None

    # Signs access tokens. Unset is tolerated only for single-process local work,
    # where the lifespan mints an ephemeral key; see `resolve_jwt_secret`.
    jwt_secret: str | None = None

    # Fernet key encrypting TOTP secrets at rest. Without it, MFA enrolment is
    # refused rather than storing a secret in the clear.
    mfa_encryption_key: str | None = None

    # Number of serving worker processes. Read by the lifespan guard.
    web_concurrency: int = 1

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.production


settings = Settings()
