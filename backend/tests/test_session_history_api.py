"""The learner's practice history endpoint (design §7.7, §10.1 "最近练习")."""

from __future__ import annotations

from uuid import UUID, uuid4

from conftest import ApiHarness, send_learner_turn, start_practice
from sqlalchemy import select

from app.db.models import PracticeSession, Scenario, User


async def test_history_is_empty_before_the_first_practice(api: ApiHarness) -> None:
    response = await api.client.get("/api/v1/practice/sessions")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


async def test_history_lists_newest_activity_first(api: ApiHarness) -> None:
    older = await start_practice(api)
    newer = await start_practice(api)
    await send_learner_turn(api, older)  # activity moves, creation order no longer decides

    response = await api.client.get("/api/v1/practice/sessions")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [older, newer]
    assert payload["total"] == 2
    assert payload["items"][0]["turn_count"] == 1


async def test_history_carries_the_evaluation_status(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    await send_learner_turn(api, session_id)
    await api.client.post(f"/api/v1/practice/sessions/{session_id}/finish", json={})

    response = await api.client.get("/api/v1/practice/sessions")

    item = response.json()["items"][0]
    assert item["status"] == "completed"
    assert item["evaluation_status"] == "completed"
    assert item["completed_at"] is not None


async def test_history_shows_a_session_without_an_evaluation_as_null(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    await send_learner_turn(api, session_id)

    response = await api.client.get("/api/v1/practice/sessions")

    item = response.json()["items"][0]
    assert item["id"] == session_id
    assert item["status"] == "active"
    assert item["evaluation_status"] is None


async def test_history_filters_by_status(api: ApiHarness) -> None:
    active = await start_practice(api)
    finished = await start_practice(api)
    await send_learner_turn(api, finished)
    await api.client.post(f"/api/v1/practice/sessions/{finished}/finish", json={})

    only_active = await api.client.get("/api/v1/practice/sessions", params={"status": "active"})
    only_finished = await api.client.get(
        "/api/v1/practice/sessions", params={"status": "completed"}
    )

    assert [item["id"] for item in only_active.json()["items"]] == [active]
    assert [item["id"] for item in only_finished.json()["items"]] == [finished]
    assert only_active.json()["total"] == 1


async def test_history_rejects_an_unknown_status(api: ApiHarness) -> None:
    response = await api.client.get("/api/v1/practice/sessions", params={"status": "nonsense"})

    assert response.status_code == 422


async def test_history_paginates(api: ApiHarness) -> None:
    ids = [await start_practice(api) for _ in range(3)]

    first_page = await api.client.get("/api/v1/practice/sessions", params={"limit": 2})
    second_page = await api.client.get(
        "/api/v1/practice/sessions", params={"limit": 2, "offset": 2}
    )

    collected = [item["id"] for item in first_page.json()["items"]] + [
        item["id"] for item in second_page.json()["items"]
    ]

    assert first_page.json()["total"] == 3
    assert len(first_page.json()["items"]) == 2
    assert len(second_page.json()["items"]) == 1
    assert set(collected) == set(ids)


async def test_history_is_scoped_to_the_local_user(api: ApiHarness) -> None:
    """Somebody else's session must not appear, and must not be countable either."""
    other_user = User(id=uuid4(), status="active")
    async with api.session_factory() as session:
        session.add(other_user)
        await session.flush()
        scenario_id = await session.scalar(select(Scenario.id).limit(1))
        session.add(
            PracticeSession(
                id=uuid4(),
                user_id=other_user.id,
                scenario_id=scenario_id,
                scenario_version=1,
                scenario_snapshot={"id": str(scenario_id), "title": "Foreign"},
                status="active",
                input_mode="text",
                turn_count=0,
            )
        )
        await session.commit()

    response = await api.client.get("/api/v1/practice/sessions")

    assert response.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}


async def test_history_uses_the_snapshot_title_not_the_current_scenario(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    async with api.session_factory() as session:
        practice_session = await session.get(PracticeSession, UUID(session_id))
        practice_session.scenario_snapshot = {
            **practice_session.scenario_snapshot,
            "title": "Explain a metrology project (old title)",
        }
        await session.commit()

    response = await api.client.get("/api/v1/practice/sessions")

    assert response.json()["items"][0]["scenario"]["title"] == (
        "Explain a metrology project (old title)"
    )
