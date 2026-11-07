"""Central HTTP errors with safe diagnostics and consistent correlation IDs."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from src.api.schemas.errors import ErrorDetail, ErrorResponse, ValidationIssue
from src.api.services.rag_service import ServiceBusyError, ServiceUnavailableError


logger = logging.getLogger(__name__)


def error_response(
    request: Request, status_code: int, code: str, message: str, *,
    issues: list[ValidationIssue] | None = None, headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = request.state.request_id
    body = ErrorResponse(
        request_id=request_id,
        error=ErrorDetail(code=code, message=message, issues=issues or []),
    )
    return JSONResponse(
        status_code=status_code, content=body.model_dump(mode="json"),
        headers={"X-Request-ID": request_id, "Cache-Control": "no-store", **(headers or {})},
    )


async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Pydantic's input/ctx can contain the question, arbitrary objects or secrets.
    issues = [ValidationIssue(location=list(error["loc"]), code=error["type"], message=error["msg"])
              for error in exc.errors()]
    return error_response(request, 422, "invalid_request", "Dữ liệu yêu cầu không hợp lệ.", issues=issues)


async def unavailable_error(request: Request, exc: ServiceUnavailableError) -> JSONResponse:
    busy = isinstance(exc, ServiceBusyError)
    return error_response(
        request, 503, "service_busy" if busy else "service_not_ready",
        "Hệ thống đang bận. Vui lòng thử lại sau." if busy else "Hệ thống chưa sẵn sàng nhận câu hỏi.",
        headers={"Retry-After": "1"},
    )


async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    return error_response(request, exc.status_code, f"http_{exc.status_code}",
                          "Yêu cầu HTTP không được hỗ trợ.", headers=exc.headers)


async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("rag_api_unexpected_error request_id=%s error_type=%s",
                 request.state.request_id, type(exc).__name__)
    logger.debug("rag_api_exception_details", exc_info=True)
    return error_response(request, 500, "internal_error", "Hệ thống gặp lỗi xử lý. Vui lòng thử lại sau.")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(ServiceUnavailableError, unavailable_error)
    app.add_exception_handler(HTTPException, http_error)
