import ipaddress
import secrets
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.evaluation import EvaluationProvider
from app.ai.roleplay import RoleplayProvider
from app.ai.speech import SpeechProvider
from app.ai.speech_synthesis import SpeechSynthesisProvider
from app.core.config import settings


@dataclass
class PracticeAccessError(Exception):
    status_code: int = 401
    code: str = "authentication_required"
    message: str = "A valid practice API token is required from non-loopback clients."


async def get_database_health(request: Request) -> str:
    engine = request.app.state.database_engine
    try:
        async with engine.connect() as connection:
            await connection.exec_driver_sql("SELECT 1")
    except (SQLAlchemyError, OSError):
        # SQLAlchemy does not wrap driver-level connect failures: asyncpg raises a bare
        # ConnectionRefusedError (an OSError) when the server is down. Catching only
        # SQLAlchemyError lets that escape as HTTP 500 instead of the 503 contract.
        return "unavailable"
    return "ok"


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    async with session_factory() as session:
        yield session


def get_roleplay_provider(request: Request) -> RoleplayProvider:
    return request.app.state.roleplay_provider


def get_evaluation_provider(request: Request) -> EvaluationProvider:
    return request.app.state.evaluation_provider


def get_speech_provider(request: Request) -> SpeechProvider:
    return request.app.state.speech_provider


def get_speech_synthesis_provider(request: Request) -> SpeechSynthesisProvider:
    return request.app.state.speech_synthesis_provider


def require_practice_access(request: Request) -> None:
    client_host = request.client.host if request.client is not None else ""
    try:
        is_loopback = ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        is_loopback = False

    if settings.app_env == "local" and is_loopback:
        return

    configured_token = (
        settings.api_access_token.get_secret_value() if settings.api_access_token else ""
    )
    authorization = request.headers.get("Authorization", "")
    if configured_token and secrets.compare_digest(authorization, f"Bearer {configured_token}"):
        return
    raise PracticeAccessError()
