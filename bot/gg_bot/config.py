"""Bot settings. The token lives here and in the backend only — never in the
frontend bundle."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    bot_token: str = ""
    bot_username: str = "gggram_bot"
    webapp_url: str = "http://localhost:5173"

    # The bot owns no database: everything goes through the backend's internal API.
    backend_url: str = "http://localhost:8000"
    api_prefix: str = "/api"
    internal_api_token: str = "change-me-internal"

    telegram_webhook_secret: str = ""
    admin_telegram_ids: list[int] = Field(default_factory=list)

    log_level: str = "INFO"
    environment: str = "development"
    request_timeout: float = 15.0

    @property
    def internal_base(self) -> str:
        return f"{self.backend_url.rstrip('/')}{self.api_prefix}"

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.admin_telegram_ids


def _parse_list(raw: str | None) -> list[int]:
    if not raw:
        return []
    return [int(part) for part in raw.replace("[", "").replace("]", "").split(",") if part.strip().isdigit()]


@lru_cache
def get_settings() -> BotSettings:
    import os

    settings = BotSettings()
    if not settings.admin_telegram_ids:
        settings.admin_telegram_ids = _parse_list(os.getenv("ADMIN_TELEGRAM_IDS"))
    return settings


settings = get_settings()
