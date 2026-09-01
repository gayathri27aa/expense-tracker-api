# Personal Expense Tracker API

A FastAPI backend for tracking personal income and expenses.

## Project structure

```
expense-tracker-api/
├── app/
│   ├── __init__.py
│   ├── config.py      # Settings (env-driven)
│   └── main.py         # FastAPI app + routes
├── venv/                # Virtual environment (not committed)
├── requirements.txt
├── .env.example
└── .gitignore
```

## Setup

```bash
cd expense-tracker-api

# Create and activate the virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy env template and adjust as needed
cp .env.example .env
```

## Run

```bash
uvicorn app.main:app --reload
```

The API will be available at http://127.0.0.1:8000

- Interactive docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

## Next steps

This scaffold currently exposes only the root and health endpoints. Natural
next additions:
- SQLAlchemy models for `Expense`, `Category`, `User`
- Pydantic schemas for request/response validation
- CRUD routers under `/expenses`, `/categories`
- Auth (e.g. JWT) if the API needs per-user data
- Alembic for database migrations
