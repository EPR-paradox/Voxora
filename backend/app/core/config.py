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
    # The Expo dev server serves the web preview from another origin, so previews need CORS. Only
    # local development origins are listed: a loopback API that is token-free for local clients
    # (§3.2) must not be reachable from an arbitrary page the learner happens to have open.
    cors_allow_origins: list[str] = [
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://localhost:19006",
        "http://127.0.0.1:19006",
    ]
    max_context_messages: int = 24
    log_level: str = "INFO"

    # Roleplay provider. ``mock`` keeps tests and offline development free of external calls;
    # ``openai_compatible`` targets any /chat/completions endpoint (DeepSeek by default, other
    # vendors by changing ``ai_base_url`` and ``ai_model``).
    ai_provider: str = "mock"
    ai_base_url: str = "https://api.deepseek.com/v1"
    ai_api_key: SecretStr | None = None
    ai_model: str = ""
    ai_timeout_seconds: float = 30.0
    # One spoken turn is ~50-150 completion tokens, and deepseek-flash spends the rest of the budget
    # on internal reasoning whose length is wildly unstable (measured: 0 to 1627 characters for
    # the same prompt). 400 tokens truncated ~1 call in 10 into an empty answer; 1000 leaves room
    # without costing anything when unused, because tokens never generated are never billed.
    ai_max_tokens: int = 1000
    ai_json_mode: bool = True
    # A meeting answers with a short script of 1-3 voices in one call, which costs more completion
    # tokens than a single spoken turn; deepseek-flash also spends roughly half of them on reasoning
    # that never reaches the output. Initial value, to be pinned by measurement in Phase 6
    # (docs/meeting-mode-v0.1.md §5).
    ai_meeting_max_tokens: int = 1200

    # Evaluation is a separate provider with its own limits (design §8.6): it returns a structured
    # document rather than one spoken turn, so it needs a longer budget and its own timeout.
    ai_evaluation_timeout_seconds: float = 60.0
    # Measured against deepseek-flash: one report costs ~2000-2200 completion tokens, roughly half
    # of it reasoning tokens that emit no visible output, and the split moves between calls. A
    # budget near the average yields an empty or truncated answer, so the default keeps headroom.
    ai_evaluation_max_tokens: int = 4000

    # Speech-to-text (design §8.6, §7.11). ``mock`` keeps tests and offline development free of
    # model downloads; ``faster_whisper`` runs on this machine — GPU when the libraries are present,
    # CPU int8 otherwise.
    speech_provider: str = "mock"
    speech_model: str = "small.en"
    speech_device: str = "auto"  # auto | cpu | cuda
    speech_compute_type: str = "int8"
    # Transcription must NOT reuse ``ai_timeout_seconds``: a 300 s clip takes minutes to decode on
    # the CPU fallback path, so a 30 s budget is a guaranteed 504 (§8.6). Pinned by measurement: a
    # 313 s clip takes 26.9 s on the CPU int8 path (11.6x realtime), leaving ~6.7x headroom at 180
    # s.
    speech_timeout_seconds: float = 180.0
    speech_max_seconds: int = 300
    speech_max_bytes: int = 32 * 1024 * 1024
    # §7.11 rule 3: m4a/AAC is what the phone records; the rest are here so a shared file works too.
    speech_allowed_content_types: list[str] = [
        "audio/m4a",
        "audio/x-m4a",
        "audio/mp4",
        "audio/aac",
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/ogg",
    ]

    # Text-to-speech (design §8.6, docs/meeting-mode-v0.1.md §9). ``mock`` keeps the phone playable
    # without any network; ``edge_tts`` is a keyless cloud voice service, verified reachable from
    # this machine without a proxy. The audio is never stored (§9.2), so there is no cache to
    # configure.
    speech_synthesis_provider: str = "mock"
    # Synthesis is the opposite shape of a transcription: a meeting-length line comes back in a few
    # hundred milliseconds, so this budget only has to cover a stalled websocket.
    speech_synthesis_timeout_seconds: float = 30.0
    # A meeting turn is capped at 60 words by the prompt, which lands well under 500 characters; the
    # ceiling is here so a runaway client cannot make the server speak a novel.
    speech_synthesis_max_chars: int = 1000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
