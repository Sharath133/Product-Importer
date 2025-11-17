from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: str = "development"
    secret_key: str = "change-me"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/product_importer"
    # Prefer 127.0.0.1 to avoid potential IPv6 localhost quirks on Windows/Docker
    redis_url: str = "redis://127.0.0.1:6379/0"
    allowed_origins: List[str] = ["*"]

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _coerce_allowed_origins(cls, value):
        """
        Allow ALLOWED_ORIGINS to be supplied as either a JSON list or a simple
        comma-separated string (e.g. "*", "https://a.com,https://b.com").
        """
        if value is None:
            return ["*"]

        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return ["*"]
            return [item.strip() for item in stripped.split(",") if item.strip()]

        return value


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()

