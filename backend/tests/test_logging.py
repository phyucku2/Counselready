"""Request logging must stay free of case-identifying material (CLAUDE.md §3)."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.logging import (
    REQUEST_ID_HEADER,
    UNMATCHED_ROUTE,
    JsonFormatter,
    RequestLoggingMiddleware,
)

CASE_ID = "11111111-2222-3333-4444-555555555555"


@pytest.fixture()
def app() -> FastAPI:
    application = FastAPI()
    application.add_middleware(RequestLoggingMiddleware)

    @application.get("/cases/{case_id}")
    async def read_case(case_id: str) -> dict[str, str]:
        return {"case_id": case_id}

    @application.get("/boom")
    async def boom() -> None:
        raise RuntimeError("document text that must never be logged")

    return application


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_the_route_template_is_logged_not_the_populated_path(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """A raw path embeds the case id. The template must be logged instead."""
    with caplog.at_level(logging.INFO, logger="counselready.request"):
        assert client.get(f"/cases/{CASE_ID}").status_code == 200

    context = _only_request_context(caplog)
    assert context["route"] == "/cases/{case_id}"
    assert CASE_ID not in json.dumps(context)


def test_an_unhandled_exception_still_logs_one_correlated_line(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """A 500 that skips the response path must not skip the log line."""
    with caplog.at_level(logging.INFO, logger="counselready.request"):
        assert client.get("/boom").status_code == 500

    context = _only_request_context(caplog)
    assert context["status"] == 500
    assert context["route"] == "/boom"
    assert context["request_id"]


def test_the_exception_message_never_reaches_the_log(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """Exception text can carry document content; the log is built from a fixed
    field set, so it must not appear."""
    with caplog.at_level(logging.INFO, logger="counselready.request"):
        client.get("/boom")

    assert "document text that must never be logged" not in json.dumps(
        _only_request_context(caplog)
    )


def test_an_inbound_request_id_is_honored_and_echoed(client: TestClient) -> None:
    response = client.get(f"/cases/{CASE_ID}", headers={REQUEST_ID_HEADER: "abc123"})
    assert response.headers[REQUEST_ID_HEADER] == "abc123"


def test_a_request_id_is_generated_when_the_client_sends_none(client: TestClient) -> None:
    response = client.get(f"/cases/{CASE_ID}")
    assert response.headers[REQUEST_ID_HEADER]


def test_an_unmatched_path_logs_the_sentinel(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="counselready.request"):
        assert client.get("/no-such-route").status_code == 404

    assert _only_request_context(caplog)["route"] == UNMATCHED_ROUTE


def test_the_formatter_emits_single_line_json_with_the_context_merged() -> None:
    record = logging.LogRecord(
        name="counselready.request",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="http_request",
        args=(),
        exc_info=None,
    )
    record.context = {"status": 200}  # type: ignore[attr-defined]

    rendered = JsonFormatter().format(record)

    assert "\n" not in rendered
    assert json.loads(rendered) == {
        "level": "INFO",
        "logger": "counselready.request",
        "event": "http_request",
        "status": 200,
    }


def test_the_formatter_ignores_a_non_mapping_context() -> None:
    record = logging.LogRecord(
        name="counselready.request",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="http_request",
        args=(),
        exc_info=None,
    )
    record.context = "not-a-mapping"  # type: ignore[attr-defined]

    assert json.loads(JsonFormatter().format(record))["event"] == "http_request"


def _only_request_context(caplog: pytest.LogCaptureFixture) -> dict[str, object]:
    records = [r for r in caplog.records if r.name == "counselready.request"]
    assert len(records) == 1, f"expected exactly one request log line, got {len(records)}"
    context = records[0].context  # type: ignore[attr-defined]
    assert isinstance(context, dict)
    return context
