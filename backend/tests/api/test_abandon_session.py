"""Closing a session nobody spoke in (design §7.15).

The bug these tests exist for: a listening-only session could be opened and never closed. `finish`
builds a report, a report needs learner turns, and a listener has none — so the way out has to be a
distinct ending that produces no report rather than a fake one.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from conftest import ApiHarness, build_scenario

MEETING_CAST = [
    {"key": "algo_lead", "name": "Dr. Nadia Farrow", "title": "Algorithms Lead"},
    {"key": "sw_eng", "name": "Tobias Lang", "title": "Software Engineer"},
]


async def open_meeting(api: ApiHarness) -> dict:
    async with api.session_factory() as session:
        scenario = build_scenario(slug="tech-sync-01", title="Technical sync", cast=MEETING_CAST)
        session.add(scenario)
        await session.commit()
        scenario_id = str(scenario.id)
    response = await api.client.post(
        "/api/v1/practice/sessions", json={"scenario_id": scenario_id, "input_mode": "text"}
    )
    assert response.status_code == 201
    return response.json()


async def test_a_silent_session_can_be_closed(api: ApiHarness) -> None:
    """Listening and then leaving is a legitimate session; it must not be a trap."""
    session = await open_meeting(api)

    response = await api.client.post(f"/api/v1/practice/sessions/{session['id']}/abandon")

    assert response.status_code == 200
    assert response.json() == {"status": "abandoned"}
    detail = await api.client.get(f"/api/v1/practice/sessions/{session['id']}")
    assert detail.json()["status"] == "abandoned"


async def test_abandoning_twice_is_the_same_answer(api: ApiHarness) -> None:
    session = await open_meeting(api)

    first = await api.client.post(f"/api/v1/practice/sessions/{session['id']}/abandon")
    second = await api.client.post(f"/api/v1/practice/sessions/{session['id']}/abandon")

    assert (first.status_code, second.status_code) == (200, 200)
    assert first.json() == second.json()


async def test_a_session_with_learner_turns_is_not_abandoned(api: ApiHarness) -> None:
    """Throwing away real turns would destroy a report the learner can still have; say so
    instead."""
    session = await open_meeting(api)
    sent = await api.client.post(
        f"/api/v1/practice/sessions/{session['id']}/messages",
        json={
            "content": "I'd like to see the residual split by field.",
            "client_message_id": str(uuid4()),
        },
    )
    assert sent.status_code == 201

    response = await api.client.post(f"/api/v1/practice/sessions/{session['id']}/abandon")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_has_user_turns"


async def test_a_completed_session_is_not_abandoned(api: ApiHarness) -> None:
    session = await open_meeting(api)
    session_id = session["id"]
    await api.client.post(
        f"/api/v1/practice/sessions/{session_id}/messages",
        json={
            "content": "Two weeks, if we keep the calibration pass.",
            "client_message_id": str(uuid4()),
        },
    )
    finished = await api.client.post(
        f"/api/v1/practice/sessions/{session_id}/finish", json={"client_finish_id": str(uuid4())}
    )
    assert finished.status_code == 200

    response = await api.client.post(f"/api/v1/practice/sessions/{session_id}/abandon")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_not_active"


async def test_an_unknown_session_cannot_be_abandoned(api: ApiHarness) -> None:
    response = await api.client.post(f"/api/v1/practice/sessions/{uuid4()}/abandon")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


async def test_abandoning_a_finished_session_keeps_its_report(api: ApiHarness) -> None:
    """The ending that exists for listeners must not be a back door around the report."""
    session = await open_meeting(api)
    session_id = session["id"]
    await api.client.post(
        f"/api/v1/practice/sessions/{session_id}/messages",
        json={
            "content": "Two weeks, if we keep the calibration pass.",
            "client_message_id": str(uuid4()),
        },
    )
    await api.client.post(
        f"/api/v1/practice/sessions/{session_id}/finish", json={"client_finish_id": str(uuid4())}
    )

    await api.client.post(f"/api/v1/practice/sessions/{session_id}/abandon")

    evaluation = await api.client.get(f"/api/v1/practice/sessions/{session_id}/evaluation")
    assert evaluation.status_code == 200
    assert evaluation.json()["evaluation_status"] == "completed"
    async with api.session_factory() as db:
        from app.db.models import PracticeSession

        row = await db.get(PracticeSession, UUID(session_id))
        assert row.status == "completed"
