from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COMMERCE_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://commerce:local-demo-only@127.0.0.1:55439/commerce"
    simulator_database_url: str = (
        "postgresql+psycopg://commerce:local-demo-only@127.0.0.1:55439/commerce_sources"
    )
    simulator_url: str = "http://127.0.0.1:8511"
    signing_key: SecretStr = SecretStr("")
    source_token: SecretStr = SecretStr("")
    demo_mode: bool = True
    model_provider: Literal["baseline", "codex"] = "baseline"
    codex_bin: str = "codex"
    codex_model: str | None = None
    model_timeout_seconds: int = Field(default=120, ge=5, le=300)
    quote_ttl_seconds: int = Field(default=300, ge=1, le=3600)
    worker_enabled: bool = True
    worker_poll_seconds: float = 0.5
    job_lease_seconds: int = 360
    max_job_attempts: int = 50
    max_active_sessions_per_user: int = Field(default=5, ge=1, le=50)
    max_daily_model_calls: int = Field(default=20, ge=1, le=100)
    max_model_calls_per_session: int = Field(default=4, ge=2, le=10)
    cookie_secure: bool = False
    trace_enabled: bool = True
    allowed_origins: list[str] = [
        "http://127.0.0.1:8510",
        "http://localhost:8510",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]

    def require_secrets(self) -> None:
        if len(self.signing_key.get_secret_value()) < 32:
            raise ValueError(
                "COMMERCE_SIGNING_KEY must contain at least 32 characters; run tools/dev.py init"
            )
        if len(self.source_token.get_secret_value()) < 32:
            raise ValueError("COMMERCE_SOURCE_TOKEN must contain at least 32 characters")
        if not self.demo_mode:
            raise ValueError(
                "This release supports local synthetic demonstrations only; production identity is not configured"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
