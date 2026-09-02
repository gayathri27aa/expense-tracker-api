# Personal Expense Tracker — API Design

This document defines the entities, request/response contracts, and REST
endpoint plan for the expense tracker API, before implementation begins.

## 1. Scope

A single-user-per-account expense tracker where a user can:
- Manage categories (e.g. Food, Rent, Salary)
- Record transactions (expenses and income) against a category
- Retrieve summaries/totals for reporting

Multi-user support is included from the start (via a `User` entity + auth)
so the data model doesn't need reshaping later, even though auth
implementation itself may land in a later milestone.

## 2. Entities & relationships

```
User (1) ──< (many) Category
User (1) ──< (many) Transaction
Category (1) ──< (many) Transaction
```

- A `Category` belongs to one `User`.
- A `Transaction` belongs to one `User` and references one `Category`.
- Deleting a `Category` that has transactions is restricted (see §6).

### 2.1 User

| Field | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| email | str | Unique, required |
| hashed_password | str | Never exposed in responses |
| full_name | str \| null | Optional |
| created_at | datetime | Server-set |

### 2.2 Category

| Field | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| user_id | UUID | FK → User |
| name | str | Required, unique per user |
| type | enum: `expense` \| `income` | Determines which transactions can use it |
| color | str \| null | Hex code for UI, optional |
| icon | str \| null | Icon identifier, optional |
| created_at | datetime | Server-set |

### 2.3 Transaction

| Field | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| user_id | UUID | FK → User |
| category_id | UUID | FK → Category |
| type | enum: `expense` \| `income` | Must match the category's type |
| amount | decimal | Positive value; sign is implied by `type` |
| currency | str | ISO 4217 code, e.g. `INR`, `USD` (default from user/account settings) |
| description | str \| null | Optional free text |
| payment_method | str \| null | e.g. `cash`, `card`, `upi` — optional |
| transaction_date | date | When the transaction occurred (not `created_at`) |
| created_at | datetime | Server-set |
| updated_at | datetime | Server-set, updated on edit |

## 3. Request / response contracts

Shown as Pydantic-style schemas — these map directly to the models
implemented in the next milestone.

### 3.1 Category

```python
class CategoryType(str, Enum):
    expense = "expense"
    income = "income"

class CategoryCreate(BaseModel):
    name: str
    type: CategoryType
    color: str | None = None
    icon: str | None = None

class CategoryUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    icon: str | None = None
    # type is immutable after creation — see §6

class CategoryResponse(BaseModel):
    id: UUID
    name: str
    type: CategoryType
    color: str | None
    icon: str | None
    created_at: datetime
```

### 3.2 Transaction

```python
class TransactionCreate(BaseModel):
    category_id: UUID
    type: CategoryType
    amount: Decimal = Field(gt=0)
    currency: str = "INR"
    description: str | None = None
    payment_method: str | None = None
    transaction_date: date

class TransactionUpdate(BaseModel):
    category_id: UUID | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = None
    description: str | None = None
    payment_method: str | None = None
    transaction_date: date | None = None

class TransactionResponse(BaseModel):
    id: UUID
    category: CategoryResponse   # nested, not just category_id
    type: CategoryType
    amount: Decimal
    currency: str
    description: str | None
    payment_method: str | None
    transaction_date: date
    created_at: datetime
    updated_at: datetime
```

### 3.3 Summary

```python
class CategoryTotal(BaseModel):
    category_id: UUID
    category_name: str
    total: Decimal

class SummaryResponse(BaseModel):
    period_start: date
    period_end: date
    total_income: Decimal
    total_expense: Decimal
    net: Decimal
    by_category: list[CategoryTotal]
```

### 3.4 Error format

All errors follow FastAPI's default shape for consistency:

```json
{ "detail": "Category not found" }
```

Validation errors (422) use FastAPI's default structured format
(`detail: [{loc, msg, type}]`) without modification.

## 4. REST endpoint plan

### 4.1 Auth (future milestone, listed for completeness)

| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Create a user account |
| POST | `/auth/login` | Exchange credentials for a JWT |

### 4.2 Categories

| Method | Path | Request body | Response | Notes |
|---|---|---|---|---|
| GET | `/categories` | — | `list[CategoryResponse]` | Query param `type` to filter |
| POST | `/categories` | `CategoryCreate` | `CategoryResponse` (201) | |
| GET | `/categories/{id}` | — | `CategoryResponse` | 404 if not found / not owned |
| PATCH | `/categories/{id}` | `CategoryUpdate` | `CategoryResponse` | |
| DELETE | `/categories/{id}` | — | 204 | 409 if category has transactions |

### 4.3 Transactions

| Method | Path | Request body | Response | Notes |
|---|---|---|---|---|
| GET | `/transactions` | — | `list[TransactionResponse]` (paginated) | Filters: see §5 |
| POST | `/transactions` | `TransactionCreate` | `TransactionResponse` (201) | |
| GET | `/transactions/{id}` | — | `TransactionResponse` | 404 if not found / not owned |
| PATCH | `/transactions/{id}` | `TransactionUpdate` | `TransactionResponse` | |
| DELETE | `/transactions/{id}` | — | 204 | |

### 4.4 Reporting

| Method | Path | Response | Notes |
|---|---|---|---|
| GET | `/transactions/summary` | `SummaryResponse` | Query params `period_start`, `period_end` (defaults to current month) |

### 4.5 System

| Method | Path | Response | Notes |
|---|---|---|---|
| GET | `/` | Service info | Already implemented |
| GET | `/health` | Liveness status | Already implemented |

## 5. Query conventions (list endpoints)

Applied to `GET /transactions` (and extendable to others later):

| Param | Type | Example | Meaning |
|---|---|---|---|
| `type` | enum | `?type=expense` | Filter by expense/income |
| `category_id` | UUID | `?category_id=...` | Filter by category |
| `date_from` / `date_to` | date | `?date_from=2026-08-01&date_to=2026-08-31` | Inclusive range on `transaction_date` |
| `min_amount` / `max_amount` | decimal | `?min_amount=100` | Amount range |
| `page` / `page_size` | int | `?page=1&page_size=20` | Pagination (default `page_size=20`, max `100`) |
| `sort` | str | `?sort=-transaction_date` | `-` prefix = descending; default `-transaction_date` |

List responses are wrapped for pagination metadata:

```python
class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
```

## 6. Business rules to enforce at the API layer

1. A transaction's `type` must match its category's `type` (can't log an
   expense against an income category) → 400 if mismatched.
2. A category cannot be deleted while transactions reference it → 409;
   the client must reassign or delete those transactions first.
3. `Category.type` is immutable after creation, since changing it would
   retroactively misclassify existing transactions.
4. All list/detail/update/delete operations are scoped to the
   authenticated user — a user can never see or modify another user's
   categories or transactions (404, not 403, to avoid leaking existence).
5. `amount` is always stored positive; `type` carries the sign semantics.

## 7. Status code summary

| Code | Used for |
|---|---|
| 200 | Successful GET / PATCH |
| 201 | Successful POST (resource created) |
| 204 | Successful DELETE |
| 400 | Business-rule violation (e.g. type mismatch) |
| 401 | Missing/invalid auth |
| 404 | Resource not found or not owned by the caller |
| 409 | Conflict (e.g. deleting a category still in use) |
| 422 | Validation error (FastAPI default) |

## 8. Out of scope for this milestone

- Multi-currency conversion/aggregation (currency is stored, not converted)
- Budgets / spending limits per category
- Recurring transactions
- Attachments/receipts
- Shared/family accounts

These are natural extensions once the core model above is implemented and
stable.
