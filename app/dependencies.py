"""
TEMPORARY: Auth is a future milestone (see api-design.md §4.1) and hasn't
been implemented yet. Every transaction/category still needs a real
user_id to satisfy the foreign key, so this dependency fetches — or
creates, on first call — a single demo user and returns it.

Swap this for real JWT-based auth later without touching any router code:
routers depend on `get_current_user` and only care that it returns a
`User`, not how that user was determined.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Depends

from app.database import get_db
from app.models.user import User

_DEMO_USER_EMAIL = "demo@expensetracker.local"


async def get_current_user(db: AsyncSession = Depends(get_db)) -> User:
    result = await db.execute(select(User).where(User.email == _DEMO_USER_EMAIL))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            email=_DEMO_USER_EMAIL,
            hashed_password="not-a-real-hash--auth-not-yet-implemented",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user
