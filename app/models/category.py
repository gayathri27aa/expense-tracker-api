import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import TransactionType


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        # A category name only needs to be unique within a single user's
        # set of categories, not globally.
        UniqueConstraint("user_id", "name", name="uq_category_user_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[TransactionType] = mapped_column(
        SAEnum(TransactionType, name="category_type"), nullable=False
    )
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)  # e.g. "#FF5733"
    icon: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="categories")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="category"
    )

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name!r} type={self.type}>"
