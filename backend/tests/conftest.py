"""Shared fixtures: a real ASGI app on a temporary SQLite database with fake AI providers.

The harness keeps the shape of a production request path (router -> service -> ORM) while removing
both external dependencies, which is what the design asks of every test below the API layer (§4.2,
§14.1).
"""

from __future__ import annotations

import itertools
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.ai.evaluation import EvaluationProvider, FakeEvaluationProvider
from app.ai.roleplay import FakeRoleplayProvider, RoleplayProvider
from app.ai.speech import FakeSpeechProvider, SpeechProvider
from app.core.config import settings
from app.db.base import Base
from app.db.models import Scenario, User
from app.main import create_app

LEARNER_TURN = (
    "I built a measurement pipeline for overlay metrology and cut the cycle time by half."
)


@dataclass
class ApiHarness:
    client: AsyncClient
    session_factory: async_sessionmaker[AsyncSession]


def build_scenario(**overrides) -> Scenario:
    values = {
        "slug": "evaluation-project",
        "title": "Explain a metrology project",
        "summary": "Describe your project clearly.",
        "category": "interview",
        "industry_segment": "equipment",
        "companies": [],
        "roles": [],
        "difficulty": 2,
        "situation": "An interviewer asks about your project.",
        "ai_character": {"name": "Interviewer", "title": "Manager"},
        "user_objective": "Explain your role and a challenge.",
        "target_skills": ["project_explanation"],
        "target_expressions": [],
        "roleplay_instructions": "Ask one follow-up question at a time.",
        "evaluation_rubric": {"version": "english-communication-v1"},
        "estimated_minutes": 10,
        "status": "published",
    }
    values.update(overrides)
    return Scenario(**values)


@asynccontextmanager
async def build_harness(
    database_url: str,
    *,
    roleplay_provider: RoleplayProvider | None = None,
    evaluation_provider: EvaluationProvider | None = None,
    speech_provider: SpeechProvider | None = None,
    client_address: tuple[str, int] = ("127.0.0.1", 12345),
) -> AsyncIterator[ApiHarness]:
    engine = create_async_engine(database_url)

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        session.add(User(id=settings.local_user_id, status="active"))
        session.add(build_scenario())
        await session.commit()

    app = create_app(
        database_url=database_url,
        roleplay_provider=roleplay_provider or FakeRoleplayProvider(),
        evaluation_provider=evaluation_provider or FakeEvaluationProvider(),
        speech_provider=speech_provider or FakeSpeechProvider(),
    )
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app, client=client_address)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield ApiHarness(client=client, session_factory=session_factory)
    await engine.dispose()


@pytest.fixture
async def api(tmp_path) -> AsyncIterator[ApiHarness]:
    async with build_harness(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}") as harness:
        yield harness


@pytest.fixture
def build_api(tmp_path):
    """Factory for tests that need their own fake providers; each call gets its own database."""
    counter = itertools.count()

    @asynccontextmanager
    async def _build(
        *, roleplay_provider=None, evaluation_provider=None, speech_provider=None
    ) -> AsyncIterator[ApiHarness]:
        url = f"sqlite+aiosqlite:///{tmp_path / f'api-{next(counter)}.db'}"
        async with build_harness(
            url,
            roleplay_provider=roleplay_provider,
            evaluation_provider=evaluation_provider,
            speech_provider=speech_provider,
        ) as harness:
            yield harness

    return _build


async def start_practice(api: ApiHarness) -> str:
    """Create a session through the API and return its id."""
    scenarios = await api.client.get("/api/v1/scenarios")
    scenario_id = scenarios.json()["items"][0]["id"]
    response = await api.client.post(
        "/api/v1/practice/sessions",
        json={"scenario_id": scenario_id, "input_mode": "text"},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def send_learner_turn(api: ApiHarness, session_id: str, content: str = LEARNER_TURN) -> None:
    response = await api.client.post(
        f"/api/v1/practice/sessions/{session_id}/messages",
        json={"client_message_id": str(uuid4()), "content": content},
    )
    assert response.status_code == 201
