"""Application factory and startup guards.

Deployment-context checks live here rather than in `Settings` (ADR-0003): this runs
only where the app actually serves, so migrations and scripts that hold a database URL
without serving-only configuration are unaffected.
"""

from __future__ import annotations

import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.cases import router as cases_router
from app.api.health import router as health_router
from app.api.mfa import router as mfa_router
from app.api.passkeys import router as passkeys_router
from app.core.config import Settings, settings
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.db.session import dispose_engine

logger = logging.getLogger("counselready.startup")

# RFC 7518 §3.2 requires an HMAC key at least as long as the hash output (32 bytes
# for SHA-256).
MIN_JWT_SECRET_LENGTH = 32


class StartupConfigurationError(RuntimeError):
    """Raised when the serving process is missing configuration it requires."""


def check_serving_configuration(config: Settings) -> None:
    """Fail closed on configuration that is unsafe to serve with.

    Scoped to the real hazards. A missing DATABASE_URL outside local development is
    fatal; locally it is allowed so the app boots for API-shape work before Postgres
    is running.
    """
    if config.app_env is not config.app_env.local and config.database_url is None:
        raise StartupConfigurationError(
            f"DATABASE_URL must be set when APP_ENV={config.app_env.value}"
        )
    if config.jwt_secret is not None and len(config.jwt_secret) < MIN_JWT_SECRET_LENGTH:
        # RFC 7518 §3.2: an HMAC key shorter than the hash output weakens HS256.
        # PyJWT only warns; a signing key is not a place to accept a warning.
        raise StartupConfigurationError(
            f"JWT_SECRET must be at least {MIN_JWT_SECRET_LENGTH} characters"
        )

    if config.app_env is not config.app_env.local and config.mfa_encryption_key is None:
        # MFA is a launch requirement (CLAUDE.md §3), so a deployment that cannot
        # store a TOTP secret safely is misconfigured, not merely limited.
        raise StartupConfigurationError(
            f"MFA_ENCRYPTION_KEY must be set when APP_ENV={config.app_env.value}"
        )

    if config.jwt_secret is None:
        if config.app_env is not config.app_env.local:
            raise StartupConfigurationError(
                f"JWT_SECRET must be set when APP_ENV={config.app_env.value}"
            )
        if config.web_concurrency > 1:
            # Each worker would mint its own ephemeral key, so a token signed by one
            # would be rejected by the next — an intermittent, baffling logout rather
            # than an honest failure. Refuse instead.
            raise StartupConfigurationError(
                "JWT_SECRET must be set when running more than one worker"
            )


def resolve_jwt_secret(config: Settings) -> str:
    """The signing key, or a fresh ephemeral one for single-process local work.

    An ephemeral key means every restart invalidates outstanding tokens, which is
    correct for development and is why it is refused everywhere else.
    """
    if config.jwt_secret is not None:
        return config.jwt_secret
    return secrets.token_urlsafe(32)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings.log_level)
    check_serving_configuration(settings)
    app.state.jwt_secret = resolve_jwt_secret(settings)
    logger.info(
        "startup",
        extra={
            "context": {
                "app_env": settings.app_env.value,
                # Whether a key was configured, never the key itself.
                "jwt_secret_configured": settings.jwt_secret is not None,
            }
        },
    )
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    application = FastAPI(
        title="CounselReady API",
        version="0.1.0",
        summary="Organize a family court file. Never advises, predicts, or interprets.",
        lifespan=lifespan,
    )
    # Registered last so it wraps everything: the request id must be resolved before
    # any downstream handler runs, and unhandled exceptions must still log a line.
    application.add_middleware(RequestLoggingMiddleware)
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(mfa_router)
    application.include_router(passkeys_router)
    application.include_router(cases_router)
    return application


app = create_app()
