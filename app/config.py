from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, loaded from environment variables / .env file."""

    app_name: str = "Personal Expense Tracker API"
    app_version: str = "0.1.0"
    environment: str = "development"

    # Async SQLAlchemy needs the `+asyncpg` driver in the URL.
    # Format: postgresql+asyncpg://<user>:<password>@<host>:<port>/<db>
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/expense_tracker"

    # JWT settings — override all three in production via environment variables.
    # Generate a strong secret_key with: python -c "import secrets; print(secrets.token_hex(32))"
    secret_key: str = "changeme-generate-a-real-key-before-deploying"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # External Exchange Rate Service settings
    exchange_rate_api_url: str = "https://open.er-api.com/v6/latest"
    exchange_rate_cache_ttl_seconds: int = 3600

    # Logging settings
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "console"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
