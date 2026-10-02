from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

from app.ai.roleplay import FakeRoleplayProvider
from app.api.deps import get_database_health
from app.main import create_app


async def request_health(database_health: str, headers: dict[str, str] | None = None):
    app = create_app()
    app.dependency_overrides[get_database_health] = lambda: database_health

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.get("/api/v1/health", headers=headers)


@pytest.mark.asyncio
async def test_health_returns_ok_when_database_is_healthy() -> None:
    response = await request_health("ok")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "ok",
        "version": "0.1.0",
    }


@pytest.mark.asyncio
async def test_health_returns_service_unavailable_when_database_is_down() -> None:
    response = await request_health("unavailable")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "service_unavailable",
            "message": "Database is unavailable.",
            "request_id": response.headers["x-request-id"],
            "details": {},
        }
    }


@pytest.mark.asyncio
async def test_health_generates_a_uuid_request_id() -> None:
    response = await request_health("ok")

    request_id = response.headers["x-request-id"]
    assert request_id == str(UUID(request_id))


@pytest.mark.asyncio
async def test_health_replaces_invalid_request_id() -> None:
    response = await request_health("ok", headers={"X-Request-ID": "not-a-uuid"})

    request_id = response.headers["x-request-id"]
    assert request_id == str(UUID(request_id))


class RefusingEngine:
    """An engine whose driver raises a bare ``OSError`` on connect, like asyncpg does."""

    def connect(self):
        raise ConnectionRefusedError(111, "Connection refused")


@pytest.mark.asyncio
async def test_health_reports_service_unavailable_on_driver_level_connect_failure() -> None:
    # Regression: SQLAlchemy does not wrap driver connect failures, so catching only
    # SQLAlchemyError turned an unreachable database into HTTP 500 instead of 503.
    app = create_app(database_url="sqlite+aiosqlite://", roleplay_provider=FakeRoleplayProvider())
    async with app.router.lifespan_context(app):
        app.state.database_engine = RefusingEngine()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
