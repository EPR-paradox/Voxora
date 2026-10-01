import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from starlette.requests import Request

from app.api.deps import PracticeAccessError, require_practice_access
from app.core.config import settings
from app.main import create_app


def make_request(host: str, authorization: str | None = None) -> Request:
    headers = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "headers": headers,
            "client": (host, 12345),
        }
    )


def test_loopback_client_can_access_local_practice_api() -> None:
    assert require_practice_access(make_request("127.0.0.1")) is None


def test_remote_client_without_token_is_rejected() -> None:
    with pytest.raises(PracticeAccessError):
        require_practice_access(make_request("192.168.1.50"))


def test_remote_client_with_configured_token_is_allowed(monkeypatch) -> None:
    monkeypatch.setattr(settings, "api_access_token", SecretStr("test-only-token"))

    assert require_practice_access(make_request("192.168.1.50", "Bearer test-only-token")) is None


def test_app_refuses_nonlocal_mode_without_full_auth(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")

    with pytest.raises(RuntimeError, match="full user authentication"):
        create_app()


@pytest.mark.asyncio
async def test_non_loopback_practice_request_returns_standard_401_error() -> None:
    app = create_app(database_url="sqlite+aiosqlite://")
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, client=("192.168.1.50", 12345)),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/v1/practice/sessions",
                json={
                    "scenario_id": "00000000-0000-0000-0000-000000000001",
                    "input_mode": "text",
                },
            )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"
    assert response.headers["x-request-id"] == response.json()["error"]["request_id"]
