from functools import lru_cache
from ipaddress import ip_network
from typing import Literal

from pydantic import Field, SecretStr, field_validator
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
    metrics_token: SecretStr = SecretStr("")
    demo_mode: bool = True
    schema_bootstrap: bool = True
    product_mode: Literal["retail", "pharmacy"] = "pharmacy"
    pharmacy_demo_minute: int | None = Field(default=None, ge=0, le=1439)
    voice_enabled: bool = True
    voice_executable: str = ".local/voice/whisper.cpp/build/bin/whisper-cli"
    voice_model: str = ".local/voice/ggml-tiny.en.bin"
    tts_python: str = ".local/voice/tts-venv/bin/python"
    tts_model: str = ".local/voice/tts-model"
    auth_mode: Literal["demo", "oidc"] = "demo"
    public_base_url: str = "http://127.0.0.1:8510"
    oidc_issuer: str = "http://127.0.0.1:8850/realms/commerce"
    oidc_client_id: str = "commerce-web"
    oidc_client_secret: SecretStr = SecretStr("")
    oidc_api_audience: str = "commerce-api"
    session_ttl_seconds: int = Field(default=28800, ge=60, le=28800)
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
    model_budget_database_url: SecretStr | None = None
    max_daily_model_calls: int = Field(default=20, ge=1, le=100)
    max_model_calls_per_session: int = Field(default=4, ge=2, le=10)
    cookie_secure: bool = False
    trace_enabled: bool = True
    allowed_client_cidrs: list[str] = ["127.0.0.1/32", "::1/128"]

    @field_validator("allowed_client_cidrs")
    @classmethod
    def local_networks(cls, values):
        if not values or any(not ip_network(value).is_private for value in values):
            raise ValueError("Only explicit private or loopback client networks are supported")
        return values

    allowed_origins: list[str] = [
        "http://127.0.0.1:8510",
        "http://localhost:8510",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]

    def require_source_secrets(self) -> None:
        if len(self.source_token.get_secret_value()) < 32 or not self.demo_mode:
            raise ValueError("A source credential and local synthetic mode are required")

    def require_secrets(self) -> None:
        if len(self.signing_key.get_secret_value()) < 32:
            raise ValueError(
                "COMMERCE_SIGNING_KEY must contain at least 32 characters; run tools/dev.py init"
            )
        if len(self.source_token.get_secret_value()) < 32:
            raise ValueError("COMMERCE_SOURCE_TOKEN must contain at least 32 characters")
        if not self.demo_mode:
            raise ValueError(
                "This release supports local synthetic demonstrations only; public production operation is not enabled"
            )
        if self.auth_mode == "oidc" and len(self.oidc_client_secret.get_secret_value()) < 32:
            raise ValueError("Run tools/identity.py init to configure the local identity client")


@lru_cache
def get_settings() -> Settings:
    return Settings()
