"""
Request logging and correlation ID middleware.
"""

import logging
import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.logging_config import request_id_ctx

logger = logging.getLogger("app.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware that:
    1. Extracts or generates an X-Request-ID header for correlation.
    2. Binds request_id to contextvars context for downstream loggers.
    3. Logs HTTP request path, method, status code, and latency.
    4. Attaches X-Request-ID to outgoing response headers.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        token = request_id_ctx.set(request_id)
        start_time = time.monotonic()

        client_ip = request.client.host if request.client else "unknown"

        try:
            response = await call_next(request)
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)

            response.headers["X-Request-ID"] = request_id

            logger.info(
                "%s %s -> %d (%.2fms)",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                },
            )
            return response
        except Exception as exc:
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            logger.error(
                "Unhandled error during request %s %s (%.2fms): %s",
                request.method,
                request.url.path,
                duration_ms,
                exc,
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                },
                exc_info=True,
            )
            raise
        finally:
            request_id_ctx.reset(token)
