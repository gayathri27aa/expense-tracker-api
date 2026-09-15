"""
Reliability test suite for error handling, structured logging, request correlation, and safe DB rollback.
"""

from unittest.mock import AsyncMock, patch

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError

from app.errors import (
    AppException,
    http_exception_handler,
    register_exception_handlers,
    sqlalchemy_exception_handler,
    unhandled_exception_handler,
)
from app.logging_config import JSONFormatter, setup_logging
from app.main import app
from app.middleware import RequestLoggingMiddleware


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_request_id_generated_when_missing(client):
    """Verify X-Request-ID is automatically generated and returned in response headers."""
    response = client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0


def test_request_id_preserved_when_supplied(client):
    """Verify custom X-Request-ID passed by client is preserved and returned."""
    custom_id = "trace-correlation-id-999"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_id


def test_404_error_response_format(client):
    """Verify standard detail shape for non-existent routes."""
    response = client.get("/non-existent-endpoint-xyz")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


def test_422_validation_error_response_format(client):
    """Verify invalid payloads return HTTP 422 with structured detail."""
    response = client.post("/auth/login", json={})
    assert response.status_code == 422
    data = response.json()
    assert "detail" in data
    assert isinstance(data["detail"], list)


def test_json_formatter():
    """Verify JSONFormatter formats LogRecord into valid JSON with expected fields."""
    import logging

    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test log message",
        args=(),
        exc_info=None,
    )
    record.status_code = 200
    record.duration_ms = 15.4

    output = formatter.format(record)
    import json
    data = json.loads(output)

    assert data["logger"] == "test_logger"
    assert data["level"] == "INFO"
    assert data["message"] == "Test log message"
    assert data["status_code"] == 200
    assert data["duration_ms"] == 15.4
    assert "timestamp" in data


def test_unhandled_exception_returns_500_without_leaking_details():
    """Verify unhandled internal errors return HTTP 500 without exposing stack details."""
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/error-trigger")
    def trigger_error():
        raise RuntimeError("Secret DB credentials leaked inside stack trace!")

    test_client = TestClient(test_app, raise_server_exceptions=False)
    response = test_client.get("/error-trigger")

    assert response.status_code == 500
    data = response.json()
    assert data == {"detail": "Internal server error."}
    assert "Secret DB credentials" not in response.text


def test_sqlalchemy_integrity_error_handler():
    """Verify IntegrityError maps to 409 Conflict with generic message."""
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/db-conflict")
    def trigger_integrity_error():
        raise IntegrityError("duplicate key value violates unique constraint", params={}, orig=Exception())

    test_client = TestClient(test_app, raise_server_exceptions=False)
    response = test_client.get("/db-conflict")

    assert response.status_code == 409
    data = response.json()
    assert "detail" in data
    assert data["detail"] == "Database conflict — integrity constraint violated."


def test_sqlalchemy_dbapi_error_handler():
    """Verify DBAPIError maps to 503 Service Unavailable."""
    test_app = FastAPI()
    register_exception_handlers(test_app)

    @test_app.get("/db-down")
    def trigger_db_error():
        raise DBAPIError("connection refused", params={}, orig=Exception())

    test_client = TestClient(test_app, raise_server_exceptions=False)
    response = test_client.get("/db-down")

    assert response.status_code == 503
    data = response.json()
    assert "detail" in data
    assert data["detail"] == "Database operation failed. Please try again later."


@pytest.mark.asyncio
async def test_database_get_db_rollback_on_exception():
    """Verify get_db session dependency performs rollback when exceptions occur."""
    from app.database import AsyncSessionLocal, get_db

    mock_session = AsyncMock()
    mock_session.is_active = True

    with patch("app.database.AsyncSessionLocal", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_session), __aexit__=AsyncMock())):
        gen = get_db()
        session = await gen.__anext__()
        assert session == mock_session

        with pytest.raises((ValueError, StopAsyncIteration)):
            await gen.athrow(ValueError("Test error during DB operation"))

        mock_session.rollback.assert_awaited_once()
        mock_session.close.assert_awaited_once()
