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
