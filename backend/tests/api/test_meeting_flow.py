"""One learner turn, several AI speakers (docs/meeting-mode-v0.1.md §6, §7.6).

The API contract is the part that has to hold: the reply is always a list, every voice gets its own
row with its own sequence number, and a replay hands back exactly what the learner already saw.
"""

from __future__ import annotations

from uuid import uuid4

from conftest import ApiHarness, build_scenario, display_fields

from app.ai.voices import VOICE_CATALOG

MEETING_CAST = [
    {"key": "eng_lead", "name": "Dana Whitfield", "title": "Engineering Lead"},
    {"key": "pm", "name": "Marco Ruiz", "title": "Product Manager"},
]


async def meeting_scenario(api: ApiHarness) -> str:
    """Seed a second scenario with a cast, next to the single-character one the harness creates."""
    async with api.session_factory() as session:
        scenario = build_scenario(
            slug="design-review-01",
            title="Technical design review",
            cast=MEETING_CAST,
        )
        session.add(scenario)
        await session.commit()
        return str(scenario.id)


async def open_meeting(api: ApiHarness) -> dict:
    scenario_id = await meeting_scenario(api)
    response = await api.client.post(
        "/api/v1/practice/sessions",
        json={"scenario_id": scenario_id, "input_mode": "text"},
    )
    assert response.status_code == 201
    return response.json()


async def test_the_opening_can_hold_two_voices(api: ApiHarness) -> None:
    payload = await open_meeting(api)

    assert [participant["key"] for participant in payload["participants"]] == ["eng_lead", "pm"]
    assert [message["speaker_key"] for message in payload["messages"]] == ["eng_lead", "pm"]
    speaker = payload["messages"][0]["speaker"]
    assert display_fields(speaker) == {
        "key": "eng_lead",
        "name": "Dana Whitfield",
        "title": "Engineering Lead",
    }
    # Each speaker carries the voice to be read aloud with, and it is one the catalog knows (§9).
    assert speaker["voice"] in VOICE_CATALOG
    assert len({participant["voice"] for participant in payload["participants"]}) == 2
    assert all(message["turn_index"] == 0 for message in payload["messages"])


async def test_a_turn_writes_one_row_per_speaker_in_order(api: ApiHarness) -> None:
    session_id = (await open_meeting(api))["id"]

    response = await api.client.post(
        f"/api/v1/practice/sessions/{session_id}/messages",
        json={"client_message_id": str(uuid4()), "content": "We can ship the parser first."},
    )
    detail = await api.client.get(f"/api/v1/practice/sessions/{session_id}")

    assert response.status_code == 201
    replies = response.json()["assistant_messages"]
    assert [message["speaker_key"] for message in replies] == ["eng_lead", "pm"]
    assert all(message["turn_index"] == 1 for message in replies)

    messages = detail.json()["messages"]
    assert [(message["turn_index"], message["speaker_key"]) for message in messages] == [
        (0, "eng_lead"),
        (0, "pm"),
        (1, ""),  # the learner
        (1, "eng_lead"),
        (1, "pm"),
    ]
    # Display order is the sequence, not the timestamp: every row one turn writes shares now().
    assert [message["seq"] for message in messages] == [1, 2, 3, 4, 5]


async def test_replay_hands_back_the_same_voices(api: ApiHarness) -> None:
    session_id = (await open_meeting(api))["id"]
    body = {"client_message_id": str(uuid4()), "content": "The estimate holds."}

    first = await api.client.post(f"/api/v1/practice/sessions/{session_id}/messages", json=body)
    replayed = await api.client.post(f"/api/v1/practice/sessions/{session_id}/messages", json=body)
    detail = await api.client.get(f"/api/v1/practice/sessions/{session_id}")

    assert first.status_code == 201
    assert replayed.status_code == 200
    assert replayed.json() == first.json()
    # No second copy of the turn: two openings, one learner line, two replies.
    assert len(detail.json()["messages"]) == 5


async def test_scenario_detail_publishes_the_cast(api: ApiHarness) -> None:
    scenario_id = await meeting_scenario(api)

    detail = await api.client.get(f"/api/v1/scenarios/{scenario_id}")

    assert detail.status_code == 200
    assert [display_fields(item) for item in detail.json()["cast"]] == MEETING_CAST
    assert all(item["voice"] in VOICE_CATALOG for item in detail.json()["cast"])


async def test_a_single_character_scenario_reports_one_participant(api: ApiHarness) -> None:
    """The old shape still works: one voice, one row, participants listing that one person."""
    scenarios = await api.client.get("/api/v1/scenarios")
    single_id = scenarios.json()["items"][0]["id"]

    created = await api.client.post(
        "/api/v1/practice/sessions", json={"scenario_id": single_id, "input_mode": "text"}
    )
    turn = await api.client.post(
        f"/api/v1/practice/sessions/{created.json()['id']}/messages",
        json={"client_message_id": str(uuid4()), "content": "I built a measurement pipeline."},
    )

    assert [participant["key"] for participant in created.json()["participants"]] == ["interviewer"]
    replies = turn.json()["assistant_messages"]
    assert [message["speaker_key"] for message in replies] == ["interviewer"]
