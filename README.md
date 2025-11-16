
## Getting Started
```bash
# 1. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r backend/requirements.txt

# 3. Copy environment template
cp .env.example .env  # update values as needed

# 4. Run database migrations (optional - app will create tables on startup if not using Alembic)
cd backend
alembic upgrade head
cd ..
```

> **Note:** Create `.env` with at least `DATABASE_URL`, `REDIS_URL`, and `SECRET_KEY`. See [Environment Variables](#environment-variables).

## Running Locally
Open two terminals after activating the virtual environment.

**API & Frontend (served by FastAPI static mount)**:
```bash
uvicorn backend.app.main:app --reload --port 8000
```

**Background worker (imports + webhooks)**:
```bash
dramatiq backend.app.tasks --processes 1 --threads 4
```

Access the UI at http://localhost:8000 (the SPA is served from `frontend/` by FastAPI static route; see deployment instructions if serving via CDN or reverse proxy).

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | Async SQLAlchemy DSN | `postgresql+asyncpg://user:pass@localhost:5432/product_importer` |
| `REDIS_URL` | Redis connection string for Dramatiq & progress | `redis://localhost:6379/0` |
| `SECRET_KEY` | Used for sessions / crypto hooks | `change-this-secret` |
| `ALLOWED_ORIGINS` | JSON array or comma-separated origins for CORS | `["http://localhost:3000"]` or `*` |
| `ENVIRONMENT` | Optional toggle for metrics/logging | `development` |

`config.py` loads values via `pydantic-settings`, with `.env` support.
