"""
Structured logging module for Personal Expense Tracker API.

Provides JSON formatting for production log management systems and structured text
formatting for local development, with contextvars support for request correlation IDs.
"""

from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import sys
from typing import Any

from app.config import get_settings

# Context variable for thread/task local request tracing ID
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_object: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        req_id = request_id_ctx.get()
        if req_id:
            log_object["request_id"] = req_id

        # Attach custom extra fields passed during logger calls
        extra_fields = ("request_id", "method", "path", "status_code", "duration_ms", "client_ip")
        for field in extra_fields:
            if hasattr(record, field):
                log_object[field] = getattr(record, field)

        if record.exc_info:
            log_object["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_object, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Formats log records into human-readable text for console debugging."""

    def format(self, record: logging.LogRecord) -> str:
        req_id = request_id_ctx.get()
        prefix = f"[{req_id}] " if req_id else ""
        time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        msg = f"{time_str} [{record.levelname}] {record.name}: {prefix}{record.getMessage()}"
        if record.exc_info:
            msg += f"\n{self.formatException(record.exc_info)}"
        return msg


def setup_logging() -> None:
    """Configures application-wide logging handlers and formatters."""
    settings = get_settings()

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Clear existing handlers to prevent duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if settings.log_format.lower() == "json" or settings.environment == "production":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(ConsoleFormatter())

    root_logger.addHandler(handler)

    # Adjust third-party loggers verbosity
    logging.getLogger("uvicorn.access").handlers = []
    logging.getLogger("uvicorn.access").propagate = True
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
