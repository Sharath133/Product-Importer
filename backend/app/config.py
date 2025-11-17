from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import List

from pydantic import computed_field
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
    database_url_raw: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/product_importer"
    # Prefer 127.0.0.1 to avoid potential IPv6 localhost quirks on Windows/Docker
    redis_url: str = "redis://127.0.0.1:6379/0"
    allowed_origins_raw: str = os.getenv("ALLOWED_ORIGINS", "*")

    @computed_field(return_type=List[str])
    @property
    def allowed_origins(self) -> List[str]:
        raw = (self.allowed_origins_raw or "*").strip()
        if not raw:
            return ["*"]
        if raw.startswith("[") and raw.endswith("]"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list) and parsed:
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in raw.split(",") if item.strip()] or ["*"]

    @computed_field(return_type=str)
    @property
    def database_url(self) -> str:
        url = self.database_url_raw.strip()
        if "+asyncpg" in url:
            return url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()

