"""Listening to a meeting without speaking (design §7.14).

The contract these tests protect:

- an advance adds a round of AI turns and **no learner turn**, and never moves ``turn_count``,
- the same request twice does not buy a second round of model calls,
- the ceiling is enforced by the server, not by the client's politeness,
- a session nobody spoke in still has nothing to evaluate: the honest answer, not a made-up report.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from conftest import ApiHarness, build_harness, build_scenario

from app.ai.roleplay import FakeRoleplayProvider, RoleplayProvider
from app.core.config import settings

MEETING_CAST = [
    {"key": "eng_lead", "name": "Dana Whitfield", "title": "Engineering Lead"},
    {"key": "pm", "name": "Marco Ruiz", "title": "Product Manager"},
]


class FailingRoleplayProvider(FakeRoleplayProvider):
    """Fails only on ``advance``, so the round the learner does speak in still works."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    async def advance(self, scenario, history):
        raise self.error


async def seed_meeting(api: ApiHarness, *, slug: str = "tech-review-01") -> str:
    async with api.session_factory() as session:
        scenario = build_scenario(slug=slug, title="Technical review", cast=MEETING_CAST)
        session.add(scenario)
        await session.commit()
        return str(scenario.id)


async def open_meeting(api: ApiHarness, *, slug: str = "tech-review-01") -> dict:
    scenario_id = await seed_meeting(api, slug=slug)
    response = await api.client.post(
        "/api/v1/practice/sessions", json={"scenario_id": scenario_id, "input_mode": "text"}
    )
    assert response.status_code == 201
    return response.json()


@asynccontextmanager
async def failing_harness(tmp_path, error: Exception):
    provider: RoleplayProvider = FailingRoleplayProvider(error)
    async with build_harness(
        f"sqlite+aiosqlite:///{tmp_path / f'advance-{type(error).__name__}.db'}",
        roleplay_provider=provider,
    ) as harness:
        yield harness


async def last_seq(session: dict) -> int:
    return max(message["seq"] for message in session["messages"])


async def test_an_advance_adds_a_round_and_no_learner_turn(api: ApiHarness) -> None:
    session = await open_meeting(api)
    session_id = session["id"]
    before = await last_seq(session)

    response = await api.client.post(
        f"/api/v1/practice/sessions/{session_id}/advance", json={"after_seq": before}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["assistant_messages"], "the room has to say something"
    assert {message["speaker_key"] for message in payload["assistant_messages"]} <= {
        "eng_lead",
        "pm",
    }
    assert [message["seq"] for message in payload["assistant_messages"]] == list(
        range(before + 1, before + 1 + len(payload["assistant_messages"]))
    )

    detail = await api.client.get(f"/api/v1/practice/sessions/{session_id}")
    body = detail.json()
    # No learner row was created, and the learner's turn counter did not move: they said nothing.
    # (The create response has no turn_count; only the detail does, so read it there.)
    assert all(message["role"] == "assistant" for message in body["messages"])
    assert body["turn_count"] == 0


async def test_an_advance_opens_its_own_round(api: ApiHarness) -> None:
    """The unique key is (session, turn_index, role, speaker_key), so a repeat needs a new round."""
    session = await open_meeting(api)
    session_id = session["id"]
    before = await last_seq(session)

    first = await api.client.post(
        f"/api/v1/practice/sessions/{session_id}/advance", json={"after_seq": before}
    )
    seq_after_first = max(m["seq"] for m in first.json()["assistant_messages"])
    second = await api.client.post(
        f"/api/v1/practice/sessions/{session_id}/advance", json={"after_seq": seq_after_first}
    )

    assert second.status_code == 200
    detail = await api.client.get(f"/api/v1/practice/sessions/{session_id}")
    turns = {message["turn_index"] for message in detail.json()["messages"]}
    assert turns == {0, 1, 2}, "the opening is round 0; each advance is a round of its own"


async def test_the_same_position_is_not_advanced_twice(api: ApiHarness) -> None:
    """A retried request must not buy a second round of model calls."""
    session = await open_meeting(api)
    session_id = session["id"]
    before = await last_seq(session)
    body = {"after_seq": before}

    first = await api.client.post(f"/api/v1/practice/sessions/{session_id}/advance", json=body)
    replay = await api.client.post(f"/api/v1/practice/sessions/{session_id}/advance", json=body)

    assert replay.status_code == 200
    assert [m["id"] for m in replay.json()["assistant_messages"]] == [
        m["id"] for m in first.json()["assistant_messages"]
    ]
    detail = await api.client.get(f"/api/v1/practice/sessions/{session_id}")
    assert len(detail.json()["messages"]) == len(session["messages"]) + len(
        first.json()["assistant_messages"]
    )


async def test_the_budget_is_enforced_server_side(api: ApiHarness, monkeypatch) -> None:
    monkeypatch.setattr(settings, "meeting_max_advances", 2)
    session = await open_meeting(api)
    session_id = session["id"]
    cursor = await last_seq(session)

    remaining = []
    for _ in range(2):
        response = await api.client.post(
            f"/api/v1/practice/sessions/{session_id}/advance", json={"after_seq": cursor}
        )
        assert response.status_code == 200
        remaining.append(response.json()["advances_remaining"])
        cursor = max(m["seq"] for m in response.json()["assistant_messages"])

    exhausted = await api.client.post(
        f"/api/v1/practice/sessions/{session_id}/advance", json={"after_seq": cursor}
    )

    assert remaining == [1, 0], "the client is told how much listening is left"
    assert exhausted.status_code == 409
    assert exhausted.json()["error"]["code"] == "advance_limit_reached"


async def test_a_single_character_scenario_cannot_be_advanced(api: ApiHarness) -> None:
    """One other person has nobody to talk to; that would be a monologue, not a meeting."""
    scenarios = await api.client.get("/api/v1/scenarios")
    single_id = scenarios.json()["items"][0]["id"]
    created = await api.client.post(
        "/api/v1/practice/sessions", json={"scenario_id": single_id, "input_mode": "text"}
    )
    session_id = created.json()["id"]
    cursor = await last_seq(created.json())

    response = await api.client.post(
        f"/api/v1/practice/sessions/{session_id}/advance", json={"after_seq": cursor}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_is_not_a_meeting"


async def test_a_finished_session_cannot_be_advanced(api: ApiHarness) -> None:
    session = await open_meeting(api)
    session_id = session["id"]
    cursor = await last_seq(session)
    async with api.session_factory() as db, db.begin():
        from app.db.models import PracticeSession

        # The ORM wants a UUID, not the string the JSON response carried.
        row = await db.get(PracticeSession, UUID(session_id))
        row.status = "abandoned"

    response = await api.client.post(
        f"/api/v1/practice/sessions/{session_id}/advance", json={"after_seq": cursor}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "session_not_active"


async def test_a_provider_timeout_maps_to_504(tmp_path) -> None:
    async with failing_harness(tmp_path, TimeoutError("too slow")) as harness:
        session = await open_meeting(harness)
        response = await harness.client.post(
            f"/api/v1/practice/sessions/{session['id']}/advance",
            json={"after_seq": await last_seq(session)},
        )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "ai_provider_timeout"


async def test_a_provider_failure_maps_to_502(tmp_path) -> None:
    async with failing_harness(tmp_path, RuntimeError("model exploded")) as harness:
        session = await open_meeting(harness)
        response = await harness.client.post(
            f"/api/v1/practice/sessions/{session['id']}/advance",
            json={"after_seq": await last_seq(session)},
        )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "ai_provider_error"
    assert "/home/" not in response.text


async def test_a_listening_session_has_nothing_to_evaluate(api: ApiHarness) -> None:
    """The report is not faked for someone who never spoke: the existing gate says so."""
    session = await open_meeting(api)
    session_id = session["id"]
    cursor = await last_seq(session)
    for _ in range(2):
        advanced = await api.client.post(
            f"/api/v1/practice/sessions/{session_id}/advance", json={"after_seq": cursor}
        )
        cursor = max(m["seq"] for m in advanced.json()["assistant_messages"])

    finished = await api.client.post(
        f"/api/v1/practice/sessions/{session_id}/finish",
        json={"client_finish_id": str(uuid4())},
    )

    assert finished.status_code == 409
    assert finished.json()["error"]["code"] == "session_has_no_user_turns"
