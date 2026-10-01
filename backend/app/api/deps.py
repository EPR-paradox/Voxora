from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def get_database_health(request: Request) -> str:
    engine = request.app.state.database_engine
    try:
        async with engine.connect() as connection:
            await connection.exec_driver_sql("SELECT 1")
    except SQLAlchemyError:
        return "unavailable"
    return "ok"


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session:
        yield session
