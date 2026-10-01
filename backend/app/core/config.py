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
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
