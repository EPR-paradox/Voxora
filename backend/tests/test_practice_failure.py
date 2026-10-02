from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.ai.roleplay import RoleplayProvider, RoleplayTurn
from app.core.config import settings
from app.db.base import Base
from app.db.models import Message, PracticeSession, Scenario, User
from app.services.practice import PracticeError, send_practice_message


class FailOnceProvider:
    def __init__(self, session_factory, session_id) -> None:
        self.calls = 0
        self.session_factory = session_factory
        self.session_id = session_id

    async def opening_turns(self, scenario: dict) -> list[RoleplayTurn]:
        return [RoleplayTurn(speaker_key="interviewer", content="Tell me about your project.")]

    async def reply(
        self, scenario: dict, history: list[dict], user_message: str
    ) -> list[RoleplayTurn]:
        async with self.session_factory() as session:
            practice_session = await session.get(PracticeSession, self.session_id)
            pending_message = await session.scalar(
                select(Message).where(
                    Message.session_id == self.session_id,
                    Message.status == "pending",
                    Message.role == "user",
                )
            )
            assert practice_session is not None
            assert pending_message is not None
            assert practice_session.processing_turn_id == pending_message.id
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError
        return [RoleplayTurn(speaker_key="interviewer", content="What was the main challenge?")]


@pytest.mark.asyncio
async def test_failed_turn_releases_lock_and_next_message_uses_next_index(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'retry.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    session_id = uuid4()
    scenario_id = uuid4()
    now = datetime.now(timezone.utc)
    async with session_factory() as session:
        session.add(User(id=settings.local_user_id, status="active"))
        session.add(
            Scenario(
                id=scenario_id,
                slug="failure-test",
                title="Failure test",
                summary="Scenario used to test provider retries.",
                category="interview",
                companies=[],
                roles=[],
                difficulty=1,
                situation="Interview situation.",
                ai_character={"name": "Interviewer"},
                user_objective="Explain your work.",
                target_skills=[],
                target_expressions=[],
                roleplay_instructions="Ask a follow-up.",
                evaluation_rubric={"version": "v1"},
                estimated_minutes=5,
                status="published",
            )
        )
        await session.flush()
        session.add(
            PracticeSession(
                id=session_id,
                user_id=settings.local_user_id,
                scenario_id=scenario_id,
                scenario_version=1,
                scenario_snapshot={"id": str(scenario_id), "title": "Failure test"},
                status="active",
                input_mode="text",
                turn_count=0,
                last_activity_at=now,
                started_at=now,
            )
        )
        await session.flush()
        session.add(
            Message(
                id=uuid4(),
                session_id=session_id,
                turn_index=0,
                seq=1,
                role="assistant",
                content="Tell me about your project.",
                status="completed",
            )
        )
        await session.commit()

    provider: RoleplayProvider = FailOnceProvider(session_factory, session_id)
    first_client_id = uuid4()
    async with session_factory() as session:
        with pytest.raises(PracticeError) as failure:
            await send_practice_message(
                session,
                session_id=session_id,
                client_message_id=first_client_id,
                content="I built a measurement pipeline.",
                provider=provider,
            )
        assert failure.value.status_code == 504

    async with session_factory() as session:
        practice_session = await session.get(PracticeSession, session_id)
        failed_message = await session.scalar(
            select(Message).where(Message.client_message_id == first_client_id)
        )
        assert practice_session is not None
        assert practice_session.processing_turn_id is None
        assert practice_session.turn_count == 1
        assert failed_message is not None
        assert failed_message.status == "failed"

    async with session_factory() as session:
        practice_session, user_message, assistant_messages, replayed = await send_practice_message(
            session,
            session_id=session_id,
            client_message_id=uuid4(),
            content="Let me try a different answer.",
            provider=provider,
        )
        assert replayed is False
        assert user_message.turn_index == 2
        assert [message.turn_index for message in assistant_messages] == [2]
        assert [message.speaker_key for message in assistant_messages] == ["interviewer"]

    await engine.dispose()
