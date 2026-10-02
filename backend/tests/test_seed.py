import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.base import Base
from app.db.models import Scenario, User
from app.db.seed import SCENARIO_SEEDS, seed_local_user, seed_scenarios


@pytest.mark.asyncio
async def test_seed_scenarios_is_idempotent(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'seed.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await seed_scenarios(session)
        await seed_scenarios(session)
        await session.commit()

        count = await session.scalar(select(func.count()).select_from(Scenario))
        assert count == len(SCENARIO_SEEDS)

        first = await session.scalar(
            select(Scenario).where(Scenario.slug == SCENARIO_SEEDS[0]["slug"])
        )
        assert first is not None
        assert first.status == "published"

    await engine.dispose()


@pytest.mark.asyncio
async def test_seed_local_user_is_idempotent(tmp_path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'local-user.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await seed_local_user(session)
        await seed_local_user(session)
        await session.commit()

        count = await session.scalar(select(func.count()).select_from(User))
        user = await session.get(User, settings.local_user_id)
        assert count == 1
        assert user is not None
        assert user.status == "active"

    await engine.dispose()


@pytest.mark.asyncio
async def test_seeded_meetings_get_a_validated_cast_and_a_display_name(tmp_path) -> None:
    """A meeting seed carries its cast, and the legacy `ai_character` mirrors the first one."""
    from app.scenario_cast import scenario_cast

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'seed-meeting.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await seed_scenarios(session)
        await session.commit()

        meeting = await session.scalar(
            select(Scenario).where(Scenario.slug == "design-review-scope-01")
        )
        assert meeting is not None
        assert meeting.cast is not None
        assert [participant["key"] for participant in meeting.cast] == ["eng_lead", "pm", "qa"]
        # Voice belongs to the speech-output phase; the seed must not pretend otherwise.
        assert all(participant["voice"] is None for participant in meeting.cast)
        # ai_character is NOT NULL and predates meeting mode, so it stays populated.
        assert meeting.ai_character["name"] == "Dana Whitfield"
        assert len(scenario_cast({"cast": meeting.cast})) == 3

        single = await session.scalar(
            select(Scenario).where(Scenario.slug == "metrology-project-explanation-01")
        )
        assert single is not None
        assert single.cast is None

    await engine.dispose()
