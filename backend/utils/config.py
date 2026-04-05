from __future__ import annotations

from functools import lru_cache
from typing import Literal, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="Criclytics AI")
    environment: str = Field(default="development")
    log_level: str = Field(default="INFO")
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_origin_regex: str = Field(
        default=r"^https?://(localhost|127\.0\.0\.1|\[::1\]|\[::\])(?::\d+)?$"
    )

    cache_backend: Literal["memory", "redis"] = Field(default="memory")
    redis_url: str = Field(default="redis://localhost:6379/0")
    cache_ttl_seconds: int = Field(default=180, ge=30, le=3600)
    cache_ttl_min_seconds: int = Field(default=30, ge=10, le=600)
    cache_ttl_max_seconds: int = Field(default=240, ge=30, le=3600)
    cache_namespace: str = Field(default="analysis-v3")

    rate_limit_requests: int = Field(default=30, ge=1, le=500)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    rate_limit_subnet_multiplier: int = Field(default=4, ge=1, le=20)
    request_timeout_seconds: int = Field(default=15, ge=1, le=120)
    max_request_body_bytes: int = Field(default=4096, ge=256, le=65536)
    trend_window_size: int = Field(default=5, ge=5, le=10)
    trend_ttl_seconds: int = Field(default=900, ge=60, le=3600)

    text_engine_model: str = Field(default="signal-synthesizer-v1")
    text_engine_seed: int = Field(default=7)

    total_overs_default: int = Field(default=20, ge=5, le=50)
    prompt_version: str = Field(default="insight-v2")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        enable_decoding=False,
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Union[str, list[str]]) -> list[str]:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            origins = [origin.strip() for origin in value.split(",") if origin.strip()]
            return origins or ["*"]
        return ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
