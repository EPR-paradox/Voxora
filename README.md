# Voxora

Backend foundation for the Voxora semiconductor-English practice app.

## Local setup

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
cd ..
docker compose -f infra/docker-compose.yml up -d postgres
cd backend
alembic upgrade head
python -m app.db.seed
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The local PostgreSQL credentials in `.env.example` are development-only. This MVP has no user authentication; do not expose it to a public network.

## Implemented API

- `GET /api/v1/health` — checks PostgreSQL and returns a request ID.
- `GET /api/v1/scenarios` — lists published scenarios; supports `category`, `industry_segment`, `role`, `difficulty`, `limit`, and `offset` filters.
- `GET /api/v1/scenarios/{scenario_id}` — reads a published scenario's public details. Internal roleplay instructions and evaluation rubric are not returned.

OpenAPI UI: `http://localhost:8000/docs`.

## Development checks

Run from `backend/`:

```bash
pytest
ruff check app alembic tests
ruff format --check app alembic tests
alembic check
```

Apply schema changes with Alembic migrations; the app does not create or alter database tables at startup. Re-run `python -m app.db.seed` to safely update the bundled practice scenario.
