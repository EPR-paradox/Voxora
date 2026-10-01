from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "voxora-api"
    app_env: str = "local"
    app_version: str = "0.1.0"
    database_url: str = "postgresql+asyncpg://voxora:voxora_dev_only@localhost:5432/voxora"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
