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

The PostgreSQL credentials in `.env.example` are development-only. Practice API access from loopback is allowed in local mode; non-loopback clients must send `Authorization: Bearer <API_ACCESS_TOKEN>` using a secret configured in `backend/.env`. This shared token is only a local-development guard, not production user authentication. Do not expose this MVP publicly; public or multi-user deployment still requires full authentication and per-user ownership checks.

## Implemented API

- `GET /api/v1/health` — checks PostgreSQL and returns a request ID.
- `GET /api/v1/scenarios` — lists published scenarios; supports `category`, `industry_segment`, `role`, `difficulty`, `limit`, and `offset` filters.
- `GET /api/v1/scenarios/{scenario_id}` — reads a published scenario's public details. Internal roleplay instructions and evaluation rubric are not returned.
- `POST /api/v1/practice/sessions` — starts a text session, snapshots the scenario and saves the opening line.
- `POST /api/v1/practice/sessions/{session_id}/messages` — sends a text turn with idempotent retry handling.
- `GET /api/v1/practice/sessions/{session_id}` — restores session state and its message history.

Roleplay runs on a pluggable provider chosen by `AI_PROVIDER`:

- `mock` (default) — deterministic `FakeRoleplayProvider`; tests and offline development never call an external API.
- `openai_compatible` — real calls to any `/chat/completions` endpoint (DeepSeek by default; point `AI_BASE_URL`/`AI_MODEL` at another vendor). Startup fails fast when `AI_MODEL` or `AI_API_KEY` is missing, and the system prompt is built from the scenario snapshot without `target_expressions`/`evaluation_rubric`, so the roleplay partner never sees what the learner is graded on.

OpenAPI UI: `http://localhost:8000/docs`.

## Debugging in PyCharm

Run configuration type **Python** (not the FastAPI template):

- **Module name**: `uvicorn`
- **Parameters**: `app.main:app --host 127.0.0.1 --port 8000`
- **Working directory**: `backend/` — `settings` reads `.env` relative to the working directory, so a different cwd silently falls back to defaults
- **Interpreter**: the project venv

Do not add `--reload` while debugging: the reloader forks a child process and the debugger only stays attached to the parent, so breakpoints never fire.

For logic-level debugging, use a **pytest** run configuration instead. The test suite runs entirely on temporary SQLite databases, so no PostgreSQL is needed; breakpoints in `app/services/` and `app/api/` work out of the box.

## Development checks

Run from `backend/`:

```bash
pytest
ruff check app alembic tests
ruff format --check app alembic tests
alembic check
```

Apply schema changes with Alembic migrations; the app does not create or alter database tables at startup. Re-run `python -m app.db.seed` to safely update the bundled practice scenario.
