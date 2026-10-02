from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.ai.roleplay import FakeRoleplayProvider
from app.core.config import settings
from app.db.base import Base
from app.db.models import Scenario, User
from app.main import create_app


@pytest.fixture
async def practice_client(tmp_path) -> AsyncIterator[AsyncClient]:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'practice.db'}"
    engine = create_async_engine(database_url)

    @event.listens_for(engine.sync_engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(User(id=settings.local_user_id, status="active"))
        scenario = Scenario(
            slug="practice-project",
            title="Explain a software project",
            summary="Describe your project clearly.",
            category="interview",
            industry_segment="equipment",
            companies=["KLA"],
            roles=["metrology_software_engineer"],
            difficulty=2,
            situation="An interviewer asks about your project.",
            ai_character={"name": "Interviewer", "title": "Manager"},
            user_objective="Explain your role and a challenge.",
            target_skills=["project_explanation"],
            target_expressions=[],
            roleplay_instructions="Ask one follow-up question at a time.",
            evaluation_rubric={"version": "v1"},
            estimated_minutes=10,
            status="published",
        )
        session.add(scenario)
        await session.commit()

    app = create_app(database_url=database_url, roleplay_provider=FakeRoleplayProvider())
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    await engine.dispose()


async def create_session(client: AsyncClient) -> str:
    scenarios = await client.get("/api/v1/scenarios")
    scenario_id = scenarios.json()["items"][0]["id"]
    response = await client.post(
        "/api/v1/practice/sessions",
        json={"scenario_id": scenario_id, "input_mode": "text"},
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.asyncio
async def test_create_session_saves_snapshot_and_opening_message(
    practice_client: AsyncClient,
) -> None:
    scenarios = await practice_client.get("/api/v1/scenarios")
    scenario_id = scenarios.json()["items"][0]["id"]

    response = await practice_client.post(
        "/api/v1/practice/sessions",
        json={"scenario_id": scenario_id, "input_mode": "text"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["scenario"]["id"] == scenario_id
    assert payload["status"] == "active"
    assert payload["input_mode"] == "text"
    assert payload["messages"] == [
        {
            "id": payload["messages"][0]["id"],
            "turn_index": 0,
            "seq": 1,
            "role": "assistant",
            "speaker_key": "interviewer",
            "speaker": {"key": "interviewer", "name": "Interviewer", "title": "Manager"},
            "content": "Could you briefly introduce the project and your role in it?",
            "status": "completed",
        }
    ]

    detail = await practice_client.get(f"/api/v1/practice/sessions/{payload['id']}")
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) == 1
    assert "roleplay_instructions" not in detail.text


@pytest.mark.asyncio
async def test_message_retry_is_idempotent_and_trims_content(
    practice_client: AsyncClient,
) -> None:
    session_id = await create_session(practice_client)
    payload = {
        "client_message_id": str(uuid4()),
        "content": "  I built a measurement pipeline.  ",
    }

    first = await practice_client.post(
        f"/api/v1/practice/sessions/{session_id}/messages", json=payload
    )
    retry = await practice_client.post(
        f"/api/v1/practice/sessions/{session_id}/messages", json=payload
    )
    history = await practice_client.get(f"/api/v1/practice/sessions/{session_id}")

    assert first.status_code == 201
    assert retry.status_code == 200
    assert retry.json() == first.json()
    assert first.json()["user_message"]["content"] == "I built a measurement pipeline."
    # One reply from the single participant, always in a list (§7.6).
    assert [message["turn_index"] for message in first.json()["assistant_messages"]] == [1]
    assert [message["speaker_key"] for message in first.json()["assistant_messages"]] == [
        "interviewer"
    ]
    assert first.json()["session_status"] == "active"
    assert len(history.json()["messages"]) == 3
    assert history.json()["participants"] == [
        {"key": "interviewer", "name": "Interviewer", "title": "Manager"}
    ]


@pytest.mark.asyncio
async def test_message_rejects_blank_content(practice_client: AsyncClient) -> None:
    session_id = await create_session(practice_client)

    response = await practice_client.post(
        f"/api/v1/practice/sessions/{session_id}/messages",
        json={"client_message_id": str(uuid4()), "content": "   "},
    )

    assert response.status_code == 422
