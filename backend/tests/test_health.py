"""Health and readiness probes."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def test_healthz_is_ok_without_any_dependency(client: TestClient) -> None:
    """Liveness must not depend on the database — a degraded dependency must not
    make the platform kill an otherwise-healthy replica."""
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_reports_503_when_the_database_is_unreachable(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Readiness fails closed so the platform stops routing to this replica."""
    monkeypatch.setattr("app.api.health.database_is_reachable", _unreachable)
    response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unreachable"}


def test_readyz_reports_ok_when_the_database_answers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.health.database_is_reachable", _reachable)
    response = client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def _unreachable() -> bool:
    return False


async def _reachable() -> bool:
    return True
