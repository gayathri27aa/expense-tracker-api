import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TransactionType
from app.schemas.category import CategoryResponse


class TransactionCreate(BaseModel):
    category_id: uuid.UUID
    type: TransactionType
    # amount is always stored/sent positive — `type` carries the sign
    # semantics (see api-design.md §2.3 / §6). Upper bound guards against
    # accidental typos (e.g. an extra zero) more than any real business
    # limit.
    amount: Decimal = Field(gt=0, le=Decimal("999999999.99"), decimal_places=2)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    description: str | None = Field(default=None, max_length=500)
    payment_method: str | None = Field(default=None, max_length=50)
    transaction_date: date


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: CategoryResponse
    type: TransactionType
    amount: Decimal
    currency: str
    description: str | None
    payment_method: str | None
    transaction_date: date
    created_at: datetime
    updated_at: datetime
