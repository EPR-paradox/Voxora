"""Review item endpoints (design §7.10, §14.2 #8)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import httpx
from conftest import ApiHarness, send_learner_turn, start_practice
from sqlalchemy import select

from app.db.models import PracticeSession, ReviewItem, Scenario, User


async def _create(api: ApiHarness, session_id: str, **overrides) -> httpx.Response:
    body = {
        "source_session_id": session_id,
        "item_type": "expression",
        "original_text": "The precision becomes bad.",
        "target_text": "The measurement precision has degraded.",
        "explanation": "Use a precise noun phrase and the verb degrade.",
    }
    body.update(overrides)
    response = await api.client.post("/api/v1/review-items", json=body)
    return response


async def test_create_review_item_returns_201(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    due = datetime.now(timezone.utc) + timedelta(days=1)

    response = await _create(api, session_id, due_at=due.isoformat())

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "new"
    assert payload["success_count"] == 0
    assert payload["failure_count"] == 0
    assert payload["item_type"] == "expression"
    assert payload["source_session_id"] == session_id


async def test_create_with_unknown_item_type_is_rejected(api: ApiHarness) -> None:
    session_id = await start_practice(api)

    response = await _create(api, session_id, item_type="vocabulary")

    assert response.status_code == 422


async def test_create_with_blank_target_text_is_rejected(api: ApiHarness) -> None:
    session_id = await start_practice(api)

    response = await _create(api, session_id, target_text="   ")

    assert response.status_code == 422


async def test_create_requires_an_owned_source_session(api: ApiHarness) -> None:
    other_user = User(id=uuid4(), status="active")
    async with api.session_factory() as session:
        session.add(other_user)
        await session.flush()
        scenario_id = await session.scalar(select(Scenario.id).limit(1))
        foreign = PracticeSession(
            id=uuid4(),
            user_id=other_user.id,
            scenario_id=scenario_id,
            scenario_version=1,
            scenario_snapshot={"id": str(scenario_id), "title": "Foreign"},
            status="active",
            input_mode="text",
            turn_count=0,
        )
        session.add(foreign)
        await session.commit()
        foreign_id = str(foreign.id)

    response = await _create(api, foreign_id)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


async def test_create_with_message_from_another_session_is_rejected(api: ApiHarness) -> None:
    first = await start_practice(api)
    second = await start_practice(api)
    await send_learner_turn(api, second)
    detail = await api.client.get(f"/api/v1/practice/sessions/{second}")
    message_id = detail.json()["messages"][1]["id"]

    response = await _create(api, first, source_message_id=message_id)

    assert response.status_code == 404


async def test_list_returns_newest_first_and_is_filterable_by_status(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    first = (await _create(api, session_id, target_text="first")).json()
    second = (await _create(api, session_id, target_text="second")).json()
    await api.client.patch(f"/api/v1/review-items/{first['id']}", json={"status": "mastered"})

    everything = await api.client.get("/api/v1/review-items")
    only_new = await api.client.get("/api/v1/review-items", params={"status": "new"})
    only_mastered = await api.client.get("/api/v1/review-items", params={"status": "mastered"})

    assert everything.json()["total"] == 2
    assert [item["id"] for item in only_new.json()["items"]] == [second["id"]]
    assert [item["id"] for item in only_mastered.json()["items"]] == [first["id"]]


async def test_list_orders_dated_items_first_and_filters_by_due_before(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    now = datetime.now(timezone.utc)
    soon = (await _create(api, session_id, target_text="soon", due_at=now.isoformat())).json()
    later = (
        await _create(
            api, session_id, target_text="later", due_at=(now + timedelta(days=5)).isoformat()
        )
    ).json()
    undated = (await _create(api, session_id, target_text="undated")).json()

    everything = await api.client.get("/api/v1/review-items")
    due_soon = await api.client.get(
        "/api/v1/review-items", params={"due_before": (now + timedelta(days=1)).isoformat()}
    )

    assert [item["id"] for item in everything.json()["items"]] == [
        soon["id"],
        later["id"],
        undated["id"],
    ]
    assert [item["id"] for item in due_soon.json()["items"]] == [soon["id"]]


async def test_patch_updates_review_results(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    item = (await _create(api, session_id)).json()

    response = await api.client.patch(
        f"/api/v1/review-items/{item['id']}",
        json={"status": "reviewing", "success_count": 2, "failure_count": 1},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "reviewing"
    assert payload["success_count"] == 2
    assert payload["failure_count"] == 1
    assert payload["target_text"] == item["target_text"], "content fields stay untouched"


async def test_patch_can_clear_the_due_date(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    item = (
        await _create(
            api, session_id, due_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        )
    ).json()

    response = await api.client.patch(f"/api/v1/review-items/{item['id']}", json={"due_at": None})

    assert response.status_code == 200
    assert response.json()["due_at"] is None


async def test_patch_ignores_ownership_fields(api: ApiHarness) -> None:
    """Ownership is not writable through the API, however it is spelled in the request (§7.10)."""
    session_id = await start_practice(api)
    item = (await _create(api, session_id)).json()
    async with api.session_factory() as session:
        before = await session.get(ReviewItem, UUID(item["id"]))
        owner_before, source_before = before.user_id, before.source_session_id

    response = await api.client.patch(
        f"/api/v1/review-items/{item['id']}",
        json={"user_id": str(uuid4()), "source_session_id": str(uuid4()), "status": "archived"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "archived"
    async with api.session_factory() as session:
        stored = await session.get(ReviewItem, UUID(item["id"]))
        assert stored.user_id == owner_before
        assert stored.source_session_id == source_before


async def test_patch_unknown_item_is_404(api: ApiHarness) -> None:
    response = await api.client.patch(
        f"/api/v1/review-items/{uuid4()}", json={"status": "mastered"}
    )

    assert response.status_code == 404


async def test_patch_rejects_negative_counts(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    item = (await _create(api, session_id)).json()

    response = await api.client.patch(
        f"/api/v1/review-items/{item['id']}", json={"success_count": -1}
    )

    assert response.status_code == 422


async def test_patch_rejects_invalid_status(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    item = (await _create(api, session_id)).json()

    response = await api.client.patch(f"/api/v1/review-items/{item['id']}", json={"status": "done"})

    assert response.status_code == 422
