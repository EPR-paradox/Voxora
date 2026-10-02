"""The app must build its roleplay provider from settings and own its lifecycle."""

import pytest

from app.ai.openai_compatible import OpenAICompatibleRoleplayProvider
from app.ai.roleplay import FakeRoleplayProvider
from app.core.config import Settings
from app.main import create_app


def real_provider_settings() -> Settings:
    return Settings(
        app_env="local",
        ai_provider="openai_compatible",
        ai_base_url="https://model.test/v1",
        ai_model="deepseek-chat",
        ai_api_key="test-key",
    )


@pytest.mark.asyncio
async def test_startup_builds_the_provider_from_settings(monkeypatch) -> None:
    monkeypatch.setattr("app.main.settings", real_provider_settings())
    app = create_app(database_url="sqlite+aiosqlite://")

    async with app.router.lifespan_context(app):
        assert isinstance(app.state.roleplay_provider, OpenAICompatibleRoleplayProvider)

    # The app owns the provider it created, so shutdown must release its HTTP client.
    assert app.state.roleplay_provider._client.is_closed


@pytest.mark.asyncio
async def test_startup_fails_when_provider_configuration_is_incomplete(monkeypatch) -> None:
    incomplete = real_provider_settings().model_copy(update={"ai_api_key": None})
    monkeypatch.setattr("app.main.settings", incomplete)
    app = create_app(database_url="sqlite+aiosqlite://")

    with pytest.raises(RuntimeError, match="AI_API_KEY must be set"):
        async with app.router.lifespan_context(app):
            pass


@pytest.mark.asyncio
async def test_injected_provider_is_used_as_is(monkeypatch) -> None:
    monkeypatch.setattr("app.main.settings", Settings(app_env="local", ai_provider="mock"))
    provider = FakeRoleplayProvider()
    app = create_app(database_url="sqlite+aiosqlite://", roleplay_provider=provider)

    async with app.router.lifespan_context(app):
        assert app.state.roleplay_provider is provider
