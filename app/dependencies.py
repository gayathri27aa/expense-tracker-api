"""
Real JWT-based get_current_user dependency.

Replaces the previous demo-user stub. Routers are unchanged — they still
call `Depends(get_current_user)` and receive a `User` ORM object, so the
swap is completely transparent to all existing endpoint code.
"""

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import decode_access_token
from app.database import get_db
from app.models.user import User

# The tokenUrl tells Swagger UI where to POST credentials for the
# "Authorize" button — it does not change any routing behaviour.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency that validates the Bearer JWT and returns the
    corresponding User from the database.

    Raises 401 Unauthorized when:
      - the Authorization header is missing (handled by OAuth2PasswordBearer)
      - the token is expired, tampered, or otherwise invalid
      - the encoded user UUID does not correspond to any row in the DB
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exc

    sub: str | None = payload.get("sub")
    if sub is None:
        raise credentials_exc

    try:
        user_id = uuid.UUID(sub)
    except ValueError:
        raise credentials_exc

    user = await db.get(User, user_id)
    if user is None:
        raise credentials_exc

    return user


# ---------------------------------------------------------------------------
# Exchange Rate Service dependency
# ---------------------------------------------------------------------------
# A single shared instance is used across all requests: it holds the TTL
# cache, so re-creating it on every request would defeat the caching purpose.

from app.services.exchange_rate import ExchangeRateService  # noqa: E402

_exchange_rate_service = ExchangeRateService()


def get_exchange_rate_service() -> ExchangeRateService:
    """FastAPI dependency that returns the shared ExchangeRateService instance."""
    return _exchange_rate_service
