"""Liveness and readiness probes.

Both are deliberately free of case data: they report process and dependency state
only, so they are safe to expose to the platform's probe without authentication.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.db.session import database_is_reachable

router = APIRouter(tags=["health"])


class Health(BaseModel):
    """Process-level health. No dependency checks."""

    status: str


class Readiness(BaseModel):
    """Dependency-level readiness."""

    status: str
    database: str


@router.get("/healthz", response_model=Health)
async def healthz() -> Health:
    """Liveness: the process is up and serving. Never touches a dependency."""
    return Health(status="ok")


@router.get("/readyz", response_model=Readiness)
async def readyz(response: Response) -> Readiness:
    """Readiness: the process can serve real traffic.

    Returns 503 when a dependency is unavailable so the platform stops routing to
    this replica rather than serving errors from it.
    """
    reachable = await database_is_reachable()
    if not reachable:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return Readiness(status="degraded", database="unreachable")
    return Readiness(status="ok", database="ok")
