from functools import lru_cache
from typing import List

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


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()

