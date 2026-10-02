"""Every business route must demand the dev token from a non-loopback client (design §3.1).

A route that forgets the dependency is invisible from the device until something abuses it. The
earlier suite exercised `/practice/sessions` only, which is exactly how `/scenarios` shipped
wide open — so this walks the full route table instead of sampling it.
"""

from __future__ import annotations

import pytest
from conftest import build_harness

REMOTE_CLIENT = ("192.168.1.50", 12345)

PROTECTED_ROUTES = [
    ("GET", "/api/v1/scenarios"),
    ("GET", "/api/v1/scenarios/00000000-0000-0000-0000-000000000001"),
    ("GET", "/api/v1/practice/sessions"),
    ("POST", "/api/v1/practice/sessions"),
    ("GET", "/api/v1/practice/sessions/00000000-0000-0000-0000-000000000002"),
    ("POST", "/api/v1/practice/sessions/00000000-0000-0000-0000-000000000002/finish"),
    ("GET", "/api/v1/practice/sessions/00000000-0000-0000-0000-000000000002/evaluation"),
    (
        "POST",
        "/api/v1/practice/sessions/00000000-0000-0000-0000-000000000002/evaluation/retry",
    ),
    ("GET", "/api/v1/review-items"),
    ("GET", "/api/v1/review-items/00000000-0000-0000-0000-000000000003"),
    ("POST", "/api/v1/review-items"),
    ("PATCH", "/api/v1/review-items/00000000-0000-0000-0000-000000000003"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED_ROUTES)
async def test_remote_client_without_a_token_is_rejected_everywhere(method: str, path: str) -> None:
    async with build_harness("sqlite+aiosqlite://", client_address=REMOTE_CLIENT) as api:
        response = await api.client.request(method, path)

    assert response.status_code == 401, f"{method} {path} is reachable without a token"
    assert response.json()["error"]["code"] == "authentication_required"


async def test_health_stays_public_from_a_remote_client(tmp_path) -> None:
    """Health is a probe endpoint with no business data: monitoring must not need a credential."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'health.db'}"
    async with build_harness(url, client_address=REMOTE_CLIENT) as api:
        response = await api.client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_loopback_client_needs_no_token(tmp_path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'loopback.db'}"
    async with build_harness(url) as api:
        response = await api.client.get("/api/v1/scenarios")

    assert response.status_code == 200
