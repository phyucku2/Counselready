"""Application factory and startup guards.

Deployment-context checks live here rather than in `Settings` (ADR-0003): this runs
only where the app actually serves, so migrations and scripts that hold a database URL
without serving-only configuration are unaffected.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.core.config import Settings, settings
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.db.session import dispose_engine

logger = logging.getLogger("counselready.startup")


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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings.log_level)
    check_serving_configuration(settings)
    logger.info(
        "startup",
        extra={"context": {"app_env": settings.app_env.value}},
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
    return application


app = create_app()
