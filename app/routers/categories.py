from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.category import Category
from app.models.enums import TransactionType
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryResponse

router = APIRouter(prefix="/categories", tags=["categories"])


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Category:
    category = Category(
        user_id=current_user.id,
        name=payload.name,
        type=payload.type,
        color=payload.color,
        icon=payload.icon,
    )
    db.add(category)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A category named '{payload.name}' already exists.",
        )
    await db.refresh(category)
    return category


@router.get("", response_model=list[CategoryResponse])
async def list_categories(
    type: Annotated[
        TransactionType | None,
        Query(description="Filter categories by type (expense or income)"),
    ] = None,
    page: Annotated[
        int | None,
        Query(ge=1, description="Optional page number (1-indexed)"),
    ] = None,
    page_size: Annotated[
        int | None,
        Query(ge=1, le=100, description="Optional items per page (max 100)"),
    ] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Category]:
    """
    List categories belonging to the authenticated user.
    Optionally filter by category type (expense/income).
    Guarantees stable ordering (alphabetical by name, tie-break by ID).
    Supports optional pagination via page and page_size.
    """
    stmt = select(Category).where(Category.user_id == current_user.id)

    if type is not None:
        stmt = stmt.where(Category.type == type)

    # Stable deterministic ordering: sort by name ascending, break ties with UUID
    stmt = stmt.order_by(Category.name.asc(), Category.id.asc())

    if page is not None and page_size is not None:
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    elif page_size is not None:
        stmt = stmt.limit(page_size)

    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{id}", response_model=CategoryResponse)
async def get_category(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Category:
    """
    Retrieve details for a single category by ID.
    Returns 404 if the category does not exist or does not belong to the user.
    """
    category = await db.get(Category, id)

    if category is None or category.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found.",
        )

    return category
