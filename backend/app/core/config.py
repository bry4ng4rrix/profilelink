from functools import cached_property
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str
    ip_hash_key: str
    revalidate_secret: str
    frontend_origin: str = "http://localhost:3000"
    frontend_internal_url: str = "http://localhost:3000"
    api_public_url: str = "http://localhost:8000"
    cookie_domain: str | None = None
    media_dir: Path = Path("media")
    registration_token: str | None = None  # empty: the /register page does not exist

    @field_validator("registration_token")
    @classmethod
    def _strong_or_empty(cls, value: str | None) -> str | None:
        if value and len(value) < 32:
            raise ValueError("REGISTRATION_TOKEN needs at least 32 characters")
        return value or None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @cached_property
    def site_domain(self) -> str:
        return urlsplit(self.frontend_origin).hostname or ""


settings = Settings()
