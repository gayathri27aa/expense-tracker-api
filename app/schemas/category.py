import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TransactionType

# Loose hex color check, e.g. "#FF5733". Optional field, so None is fine too.
_HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: TransactionType
    color: str | None = Field(default=None, pattern=_HEX_COLOR_PATTERN)
    icon: str | None = Field(default=None, max_length=50)


class CategoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: TransactionType
    color: str | None
    icon: str | None
    created_at: datetime
