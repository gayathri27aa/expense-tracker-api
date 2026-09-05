from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user
from app.models.category import Category
from app.models.transaction import Transaction
from app.models.user import User
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
