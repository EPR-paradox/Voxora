"""CORS: only the local Expo dev origins may drive the API from a browser (design §3.2, §12).

The web preview of the mobile app is cross-origin, so without this the browser blocks every call
while a phone works fine — a difference worth a test, because it is invisible from the device.
"""

from __future__ import annotations

from conftest import ApiHarness

ALLOWED_ORIGIN = "http://localhost:8081"


async def test_allowed_origin_sees_the_cors_header(api: ApiHarness) -> None:
    response = await api.client.get("/api/v1/scenarios", headers={"Origin": ALLOWED_ORIGIN})

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN


async def test_other_origin_is_not_granted_access(api: ApiHarness) -> None:
    response = await api.client.get(
        "/api/v1/scenarios", headers={"Origin": "https://example.invalid"}
    )

    assert "access-control-allow-origin" not in response.headers


async def test_preflight_for_a_json_post_is_answered(api: ApiHarness) -> None:
    response = await api.client.options(
        "/api/v1/practice/sessions",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN
    assert "POST" in response.headers.get("access-control-allow-methods", "")
