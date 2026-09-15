from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

import logging

logger = logging.getLogger("app.database")

settings = get_settings()

# echo=True logs generated SQL — handy in dev, worth turning off in prod
# via environment/settings later.
engine = create_async_engine(
    settings.database_url,
    echo=settings.environment == "development",
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class all ORM models inherit from."""

    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a request-scoped async DB session.
    Automatically rolls back any pending transaction if an unhandled exception occurs.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as exc:
            logger.warning("Rolling back active DB transaction due to exception: %s", exc)
            if session.is_active:
                await session.rollback()
            raise
        finally:
            await session.close()
