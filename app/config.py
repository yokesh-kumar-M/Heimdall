from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    upstream_base_url: str = Field(
        default="https://api.openai.com/v1",
        description="OpenAI-compatible base URL the proxy forwards to.",
    )
    upstream_api_key: str = Field(
        default="",
        description="Optional fallback API key used when the client request "
        "does not provide an Authorization header.",
    )

    http_connect_timeout: float = 10.0
    http_read_timeout: float = 120.0
    http_total_timeout: float = 180.0

    host: str = "0.0.0.0"
    port: int = 8000

    log_level: str = "INFO"

    # ---- Phase 3: Semantic layer (Llama Guard 3) ----
    semantic_enabled: bool = True
    semantic_base_url: str = "http://localhost:11434/v1"
    semantic_model: str = "llama-guard3"
    semantic_api_key: str = ""
    semantic_fail_closed: bool = False
    semantic_timeout: float = 15.0

    # ---- Phase 4: Telemetry ----
    telemetry_db_path: str = "telemetry/heimdall.sqlite3"

    # ---- Phase 3: Policy Manager ----
    # Number of false-positive feedbacks before a rule is auto-suppressed.
    # Set to 0 to disable auto-suppress entirely.
    policy_default_fp_threshold: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
