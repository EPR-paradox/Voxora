from uuid import UUID

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "voxora-api"
    app_env: str = "local"
    app_version: str = "0.1.0"
    database_url: str = "postgresql+asyncpg://voxora:voxora_dev_only@localhost:5432/voxora"
    local_user_id: UUID = UUID("10000000-0000-4000-8000-000000000001")
    api_access_token: SecretStr | None = None
    max_user_message_chars: int = 4000
    max_context_messages: int = 24
    log_level: str = "INFO"

    # Roleplay provider. ``mock`` keeps tests and offline development free of external
    # calls; ``openai_compatible`` targets any /chat/completions endpoint (DeepSeek by
    # default, other vendors by changing ``ai_base_url`` and ``ai_model``).
    ai_provider: str = "mock"
    ai_base_url: str = "https://api.deepseek.com/v1"
    ai_api_key: SecretStr | None = None
    ai_model: str = ""
    ai_timeout_seconds: float = 30.0
    ai_max_tokens: int = 400
    ai_json_mode: bool = True

    # Evaluation is a separate provider with its own limits (design §8.6): it returns a structured
    # document rather than one spoken turn, so it needs a longer budget and its own timeout.
    ai_evaluation_timeout_seconds: float = 60.0
    # Measured against deepseek-flash: one report costs ~2000-2200 completion tokens, roughly half
    # of it reasoning tokens that emit no visible output, and the split moves between calls. A
    # budget near the average yields an empty or truncated answer, so the default keeps headroom.
    ai_evaluation_max_tokens: int = 4000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
