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
- `POST /api/v1/practice/sessions/{session_id}/finish` — ends the session and generates its evaluation. Idempotent; a failed report is reported in the body (`evaluation_status`/`error_code`), not as a transport error.
- `GET /api/v1/practice/sessions/{session_id}/evaluation` — reads the report (202 while it is still processing, 404 before it exists).
- `POST /api/v1/practice/sessions/{session_id}/evaluation/retry` — re-runs a failed report on the same row.
- `GET`/`POST /api/v1/review-items` plus `PATCH /api/v1/review-items/{item_id}` — the review list. Only status, due date and practice counts are writable.

Roleplay and evaluation run on separate pluggable providers, both selected by `AI_PROVIDER`:

- `mock` (default) — deterministic `FakeRoleplayProvider`; tests and offline development never call an external API.
- `openai_compatible` — real calls to any `/chat/completions` endpoint (DeepSeek by default; point `AI_BASE_URL`/`AI_MODEL` at another vendor). Startup fails fast when `AI_MODEL` or `AI_API_KEY` is missing, and the system prompt is built from the scenario snapshot without `target_expressions`/`evaluation_rubric`, so the roleplay partner never sees what the learner is graded on.

Evaluation has its own budget and timeout (`AI_EVALUATION_TIMEOUT_SECONDS`, `AI_EVALUATION_MAX_TOKENS`): one structured report costs far more completion tokens than one spoken turn, and `deepseek-flash` spends about half of them on internal reasoning that never reaches the output, so a budget near the average yields an empty or truncated report. Empty or unusable answers are retried once inside the provider (timeouts are not), and the report is validated before it is stored: every piece of evidence must quote the learner's own turns, and a report with nothing attributable to the learner is rejected rather than saved.

OpenAPI UI: `http://localhost:8000/docs`.

## Mobile app

```bash
cd apps/mobile
npm install
npm run web        # browser preview on http://localhost:8081
npm start          # Expo dev server for Expo Go on a phone
npm run typecheck
```

Screens live in `app/` (Expo Router) and everything else in `src/` (`api`, `components`, `features`,
`storage`, `theme`). The client reads `EXPO_PUBLIC_API_BASE_URL`; without it, Android falls back to
`10.0.2.2:8000` (emulator to host) and everything else to `127.0.0.1:8000`. A physical phone needs the dev
machine's LAN address in `apps/mobile/.env.local`, and the backend then needs `API_ACCESS_TOKEN` set,
because requests from non-loopback clients must carry `Authorization: Bearer <token>`.

The browser preview is cross-origin, so the backend allows the Expo dev-server origins through
`CORS_ALLOW_ORIGINS` (local development origins only).

### Running on a physical phone

1. Bind the API to the LAN: `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
2. Set `API_ACCESS_TOKEN` in `backend/.env`. Loopback clients are exempt from it, a phone is not
   (§3.1), so without this every request from the device comes back 401.
3. Put the dev machine's LAN address and the *same* token in `apps/mobile/.env.local`:

   ```dotenv
   EXPO_PUBLIC_API_BASE_URL=http://192.168.1.6:8000/api/v1
   EXPO_PUBLIC_API_ACCESS_TOKEN=<same token as the backend>
   ```

4. `cd apps/mobile && npm start`, then open `exp://<lan-ip>:8081` in Expo Go (or scan the QR code).
5. If Expo Go hangs, it is usually the host firewall. Allow that subnet only:

   ```bash
   sudo ufw allow from 192.168.1.0/24 to any port 8081 proto tcp
   sudo ufw allow from 192.168.1.0/24 to any port 8000 proto tcp
   ```

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
