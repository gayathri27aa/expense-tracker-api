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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
