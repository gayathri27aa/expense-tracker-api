from datetime import date
from decimal import Decimal
from typing import Annotated
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.category import Category
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.common import Page
from app.schemas.transaction import TransactionCreate, TransactionResponse

router = APIRouter(prefix="/transactions", tags=["transactions"])


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    payload: TransactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Transaction:
    """
    Creates a transaction (expense or income entry).

    Validation, beyond the field-level checks Pydantic already applied
    (amount > 0, currency length, string lengths, etc.):
      - The referenced category must exist and belong to the caller
        (api-design.md §6 rule 4 — 404, not 403, so we don't leak
        existence of another user's category).
      - The transaction's `type` must match its category's `type`
        (api-design.md §6 rule 1 — 400 on mismatch).

    The write itself is transactional: nothing is staged with db.add()
    until both checks above pass, and if the final commit fails for any
    reason (e.g. a constraint SQLAlchemy didn't catch at the app layer),
    we roll back explicitly so no partial row is ever left behind.
    """
    category = await db.get(Category, payload.category_id)

    if category is None or category.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found.",
        )

    if category.type != payload.type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Transaction type '{payload.type.value}' does not match "
                f"category '{category.name}', which is type "
                f"'{category.type.value}'."
            ),
        )

    transaction = Transaction(
        user_id=current_user.id,
        category_id=payload.category_id,
        type=payload.type,
        amount=payload.amount,
        currency=payload.currency,
        description=payload.description,
        payment_method=payload.payment_method,
        transaction_date=payload.transaction_date,
    )
    db.add(transaction)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Could not create transaction — check the submitted data.",
        )

    # Re-fetch with the category eagerly loaded, since the response
    # schema nests the full CategoryResponse rather than just an id
    # (api-design.md §3.2), and the lazy-loaded relationship isn't safe
    # to access after commit on an async session without an explicit load.
    result = await db.execute(
        select(Transaction)
        .options(selectinload(Transaction.category))
        .where(Transaction.id == transaction.id)
    )
    return result.scalar_one()


@router.get("", response_model=Page[TransactionResponse])
async def list_transactions(
    type: Annotated[
        TransactionType | None,
        Query(description="Filter by transaction type (expense or income)"),
    ] = None,
    category_id: Annotated[
        uuid.UUID | None,
        Query(description="Filter by category ID"),
    ] = None,
    date_from: Annotated[
        date | None,
        Query(description="Filter from transaction date (inclusive, YYYY-MM-DD)"),
    ] = None,
    date_to: Annotated[
        date | None,
        Query(description="Filter to transaction date (inclusive, YYYY-MM-DD)"),
    ] = None,
    min_amount: Annotated[
        Decimal | None,
        Query(ge=0, description="Minimum transaction amount"),
    ] = None,
    max_amount: Annotated[
        Decimal | None,
        Query(ge=0, description="Maximum transaction amount"),
    ] = None,
    page: Annotated[
        int,
        Query(ge=1, description="Page number (1-indexed)"),
    ] = 1,
    page_size: Annotated[
        int,
        Query(ge=1, le=100, description="Items per page (maximum 100)"),
    ] = 20,
    sort: Annotated[
        str,
        Query(
            description="Sort field. Allowed: transaction_date, amount, created_at. Prefix '-' for descending."
        ),
    ] = "-transaction_date",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Page[TransactionResponse]:
    """
    List transactions belonging to the authenticated user with filtering,
    pagination, and deterministic stable sorting.
    """
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_from cannot be after date_to.",
        )

    if min_amount is not None and max_amount is not None and min_amount > max_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="min_amount cannot be greater than max_amount.",
        )

    filters = [Transaction.user_id == current_user.id]

    if type is not None:
        filters.append(Transaction.type == type)
    if category_id is not None:
        filters.append(Transaction.category_id == category_id)
    if date_from is not None:
        filters.append(Transaction.transaction_date >= date_from)
    if date_to is not None:
        filters.append(Transaction.transaction_date <= date_to)
    if min_amount is not None:
        filters.append(Transaction.amount >= min_amount)
    if max_amount is not None:
        filters.append(Transaction.amount <= max_amount)

    # Sort parsing and validation
    descending = sort.startswith("-")
    sort_field = sort[1:] if (descending or sort.startswith("+")) else sort

    sort_field_map = {
        "transaction_date": Transaction.transaction_date,
        "amount": Transaction.amount,
        "created_at": Transaction.created_at,
    }

    column = sort_field_map.get(sort_field)
    if column is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid sort field '{sort_field}'. Allowed fields: {', '.join(sort_field_map.keys())}.",
        )

    # Deterministic stable ordering: sort by requested column, then break ties
    # with created_at (if not already primary) and finally the unique primary key (id).
    order_by_clauses = []
    if descending:
        order_by_clauses.append(column.desc())
        if sort_field != "created_at":
            order_by_clauses.append(Transaction.created_at.desc())
        order_by_clauses.append(Transaction.id.desc())
    else:
        order_by_clauses.append(column.asc())
        if sort_field != "created_at":
            order_by_clauses.append(Transaction.created_at.asc())
        order_by_clauses.append(Transaction.id.asc())

    # Total count for pagination metadata
    count_query = select(func.count()).select_from(Transaction).where(*filters)
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Paginated rows query with eager-loaded Category
    items_query = (
        select(Transaction)
        .options(selectinload(Transaction.category))
        .where(*filters)
        .order_by(*order_by_clauses)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items_result = await db.execute(items_query)
    items = items_result.scalars().all()

    return Page(
        items=list(items),
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{id}", response_model=TransactionResponse)
async def get_transaction(
    id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Transaction:
    """
    Retrieve details for a single transaction by ID.
    Returns 404 if the transaction does not exist or does not belong to the user.
    """
    query = (
        select(Transaction)
        .options(selectinload(Transaction.category))
        .where(
            Transaction.id == id,
            Transaction.user_id == current_user.id,
        )
    )
    result = await db.execute(query)
    transaction = result.scalar_one_or_none()

    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found.",
        )

    return transaction
