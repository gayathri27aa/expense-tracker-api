"""
Import every model here so SQLAlchemy's mapper can resolve the string-based
relationship() references between them (e.g. User -> "Category"), and so
Alembic's autogenerate sees the full metadata when this package is imported.
"""

from app.database import Base
from app.models.category import Category
from app.models.enums import TransactionType
from app.models.transaction import Transaction
from app.models.user import User

__all__ = ["Base", "User", "Category", "Transaction", "TransactionType"]
