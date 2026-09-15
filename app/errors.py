"""
Centralized error handling and exception mapping module.

Guarantees consistent JSON error responses across all API endpoints without leaking internal
stack traces to clients while logging detailed diagnostics on the server.
"""

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError

logger = logging.getLogger("app.errors")


class AppException(Exception):
    """Base application exception for domain logic errors."""

    def __init__(
        self,
        detail: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.detail = detail
        self.status_code = status_code
        self.headers = headers
        super().__init__(detail)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    logger.warning("Application exception on %s %s: %s", request.method, request.url.path, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if exc.status_code >= 500:
        logger.error(
            "HTTP %d error on %s %s: %s",
            exc.status_code,
            request.method,
            request.url.path,
            exc.detail,
        )
    else:
        logger.info(
            "HTTP %d response on %s %s: %s",
            exc.status_code,
            request.method,
            request.url.path,
            exc.detail,
        )

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning("Request validation failed on %s %s: %s", request.method, request.url.path, exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )


async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.error("Database exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)

    if isinstance(exc, IntegrityError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "Database conflict — integrity constraint violated."},
        )
    elif isinstance(exc, DBAPIError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "Database operation failed. Please try again later."},
        )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Database error occurred."},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.critical("Unhandled unexpected error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error."},
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Registers custom exception handlers on the FastAPI application instance."""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
