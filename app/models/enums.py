import enum


class TransactionType(str, enum.Enum):
    """Shared by Category and Transaction — a transaction's type must
    match its category's type (enforced at the API/service layer, not
    the DB, since cross-table checks aren't expressible as a simple
    CHECK constraint here)."""

    expense = "expense"
    income = "income"
