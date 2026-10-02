"""Meeting mode's message identity rules (docs/meeting-mode-v0.1.md §3).

These are the assertions that would fail if the schema were built the obvious way: ``role IN
('user','assistant')`` plus ``UNIQUE(session_id, turn_index, role)`` allows exactly one AI reply per
turn, and a nullable ``speaker_key`` would let PostgreSQL treat learner rows as distinct (NULLs
are not equal), dropping the protection on the one row that must never be duplicated.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from conftest import ApiHarness, start_practice
from sqlalchemy.exc import IntegrityError

from app.db.models import Message


def _message(session_id: str, *, turn_index: int, seq: int, role: str, speaker_key: str) -> Message:
    return Message(
        id=uuid4(),
        session_id=UUID(session_id),
        turn_index=turn_index,
        seq=seq,
        role=role,
        speaker_key=speaker_key,
        content=f"{role}:{speaker_key or 'learner'}",
        status="completed",
    )


async def test_two_participants_can_speak_in_one_turn(api: ApiHarness) -> None:
    session_id = await start_practice(api)

    async with api.session_factory() as session:
        session.add_all(
            [
                _message(session_id, turn_index=1, seq=2, role="user", speaker_key=""),
                _message(session_id, turn_index=1, seq=3, role="assistant", speaker_key="eng_lead"),
                _message(session_id, turn_index=1, seq=4, role="assistant", speaker_key="pm"),
            ]
        )
        await session.commit()

    detail = await api.client.get(f"/api/v1/practice/sessions/{session_id}")

    assert detail.status_code == 200
    messages = detail.json()["messages"]
    # The opening line was written by the service for turn 0, so the meeting turn follows it.
    assert [(m["turn_index"], m["role"]) for m in messages] == [
        (0, "assistant"),
        (1, "user"),
        (1, "assistant"),
        (1, "assistant"),
    ]
    assert [m["content"] for m in messages[2:]] == ["assistant:eng_lead", "assistant:pm"]


async def test_one_participant_cannot_speak_twice_in_the_same_turn(api: ApiHarness) -> None:
    session_id = await start_practice(api)

    async with api.session_factory() as session:
        session.add_all(
            [
                _message(session_id, turn_index=1, seq=2, role="assistant", speaker_key="eng_lead"),
                _message(session_id, turn_index=1, seq=3, role="assistant", speaker_key="eng_lead"),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_a_learner_turn_still_holds_exactly_one_message(api: ApiHarness) -> None:
    """Why `speaker_key` is '' and not NULL: a nullable column would not be compared at all."""
    session_id = await start_practice(api)

    async with api.session_factory() as session:
        session.add_all(
            [
                _message(session_id, turn_index=1, seq=2, role="user", speaker_key=""),
                _message(session_id, turn_index=1, seq=3, role="user", speaker_key=""),
            ]
        )
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_the_same_learner_message_id_cannot_be_stored_twice(api: ApiHarness) -> None:
    session_id = await start_practice(api)
    client_message_id = uuid4()

    async with api.session_factory() as session:
        first = _message(session_id, turn_index=1, seq=2, role="user", speaker_key="")
        first.client_message_id = client_message_id
        session.add(first)
        await session.commit()

    async with api.session_factory() as session:
        replay = _message(session_id, turn_index=2, seq=3, role="user", speaker_key="")
        replay.client_message_id = client_message_id
        session.add(replay)
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_display_order_must_be_positive(api: ApiHarness) -> None:
    session_id = await start_practice(api)

    async with api.session_factory() as session:
        session.add(_message(session_id, turn_index=1, seq=0, role="user", speaker_key=""))
        with pytest.raises(IntegrityError):
            await session.commit()
