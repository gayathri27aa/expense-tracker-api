import time

from fastapi import FastAPI

from app.config import get_settings

settings = get_settings()
_start_time = time.monotonic()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API for tracking personal income and expenses.",
)


@app.get("/", tags=["root"])
def read_root():
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }


@app.get("/health", tags=["health"])
def health_check():
    """Liveness/readiness probe endpoint."""
    return {
        "status": "ok",
        "environment": settings.environment,
        "uptime_seconds": round(time.monotonic() - _start_time, 2),
    }
