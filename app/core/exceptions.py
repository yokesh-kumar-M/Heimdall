from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class HeimdallError(Exception):
    """Base class for Heimdall gateway errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_type: str = "heimdall_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class UpstreamTimeoutError(HeimdallError):
    status_code = status.HTTP_504_GATEWAY_TIMEOUT
    error_type = "upstream_timeout"


class UpstreamConnectionError(HeimdallError):
    status_code = status.HTTP_502_BAD_GATEWAY
    error_type = "upstream_unreachable"


class UpstreamProtocolError(HeimdallError):
    status_code = status.HTTP_502_BAD_GATEWAY
    error_type = "upstream_protocol_error"


class InvalidRequestError(HeimdallError):
    status_code = status.HTTP_400_BAD_REQUEST
    error_type = "invalid_request"


def _payload(exc: HeimdallError) -> dict[str, Any]:
    body: dict[str, Any] = {
        "error": {
            "type": exc.error_type,
            "message": exc.message,
        }
    }
    if exc.details:
        body["error"]["details"] = exc.details
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HeimdallError)
    async def _handle_heimdall_error(_: Request, exc: HeimdallError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=_payload(exc))
