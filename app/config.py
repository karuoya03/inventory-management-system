"""Typed application settings loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "Inventory Management System"
    environment: str = "development"
    debug: bool = False
    base_url: str = "http://localhost:8000"

    # Database
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "ims_user"
    db_password: str = ""
    db_name: str = "inventory_db"

    # Security — no default on secret_key so the app fails loudly if unset
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    cookie_secure: bool = False
    cookie_domain: str | None = None

    allowed_origins: str = "http://localhost:8000"

    @property
    def database_url(self) -> str:
        password = quote_plus(self.db_password)
        return (
            f"mysql+pymysql://{self.db_user}:{password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @property
    def origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()