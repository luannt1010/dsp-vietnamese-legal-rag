"""Request correlation and timing without logging question or source content."""

import logging
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.api.exception_handlers import unexpected_error


logger = logging.getLogger(__name__)


class RequestContextMiddleware:
    """Generate server-owned IDs and preserve ASGI cancellation semantics."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = perf_counter()
        status_code = 500
        response_started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_started = True
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["Cache-Control"] = "no-store"
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception as exc:
            if response_started:
                raise  # A response already on the wire cannot be replaced.
            # Handle before the outer CORS middleware so frontend callers
            # can read 500 errors as well as successful responses.
            response = await unexpected_error(Request(scope), exc)
            await response(scope, receive, send_with_headers)
        finally:
            # Use the route template, never query strings or arbitrary URLs.
            route = scope.get("route")
            logger.info(
                "http_request request_id=%s method=%s route=%s status=%s duration_ms=%.2f",
                request_id, scope["method"], getattr(route, "path", "unmatched"),
                status_code, (perf_counter() - started) * 1000,
            )
