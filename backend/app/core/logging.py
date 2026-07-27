"""Structured, document-text-free request logging.

CLAUDE.md §3: logs carry route *templates* and fixed vocabularies only — never a raw
path (it embeds case and document ids), never a query string, body, or header, and
never any text extracted from a user's documents. Everything emitted here is drawn
from a closed set of fields.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

REQUEST_ID_HEADER = "X-Request-ID"
UNMATCHED_ROUTE = "__unmatched__"

logger = logging.getLogger("counselready.request")


class JsonFormatter(logging.Formatter):
    """Renders records as single-line JSON with a stable key set."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        extra = getattr(record, "context", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload, sort_keys=True)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON formatter on a single stdout handler (Twelve-Factor)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


def route_template(request: Request) -> str:
    """The matched route's path template, or a fixed sentinel.

    Returning the template rather than `request.url.path` is what keeps case and
    document identifiers out of logs and, later, out of metric labels.
    """
    route = request.scope.get("route")
    if isinstance(route, Route):
        return route.path
    return UNMATCHED_ROUTE


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Outermost middleware: one log line per request, including failures.

    The request id is resolved *before* calling downstream and stashed on
    `request.state`, so an unhandled exception still produces a line that correlates
    with whatever the error seam reports later.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:
            self._log(request, request_id, status=500, started=started)
            raise

        self._log(request, request_id, status=response.status_code, started=started)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @staticmethod
    def _log(request: Request, request_id: str, *, status: int, started: float) -> None:
        logger.info(
            "http_request",
            extra={
                "context": {
                    "request_id": request_id,
                    "method": request.method,
                    "route": route_template(request),
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            },
        )
