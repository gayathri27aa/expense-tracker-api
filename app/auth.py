import bcrypt
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import get_settings


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain* (bcrypt truncates to 72 bytes)."""
    # bcrypt requires bytes; max input length for bcrypt is 72 bytes
    pwd_bytes = plain.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches the stored *hashed* password."""
    pwd_bytes = plain.encode("utf-8")[:72]
    hashed_bytes = hashed.encode("utf-8")
    try:
        return bcrypt.checkpw(pwd_bytes, hashed_bytes)
    except (ValueError, TypeError):
        return False


def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Encode *data* as a signed JWT.

    The token always carries a ``sub`` claim (the user's UUID as a string)
    and an ``exp`` claim set to now + *expires_delta* (or the configured
    default when *expires_delta* is None).
    """
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict | None:
    """
    Decode and verify a JWT.  Returns the payload dict on success,
    or None if the token is invalid, expired, or tampered with.
    """
    settings = get_settings()
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None
