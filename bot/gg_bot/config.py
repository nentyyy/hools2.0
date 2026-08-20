"""Bot settings. The token lives here and in the backend only — never in the
frontend bundle."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_DEFAULT_BACKEND_URL = "http://localhost:8000"
_DEFAULT_WEBAPP_URL = "http://localhost:5173"


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    bot_token: str = ""
    bot_username: str = "gggram_bot"
    webapp_url: str = _DEFAULT_WEBAPP_URL

    # The bot owns no database: everything goes through the backend's internal API.
    backend_url: str = _DEFAULT_BACKEND_URL
    api_prefix: str = "/api"
    internal_api_token: str = "change-me-internal"

    telegram_webhook_secret: str = ""
    # NoDecode: pydantic-settings would otherwise try to JSON-parse the raw env
    # value, which fails for the documented "1,2,3" form and takes the whole bot
    # down at import time.
    admin_telegram_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    log_level: str = "INFO"
    environment: str = "development"
    request_timeout: float = 15.0

    @field_validator("admin_telegram_ids", mode="before")
    @classmethod
    def _parse_ids(cls, value: object) -> object:
        """Accept `1,2,3`, a JSON list, or a single bare id."""
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            if value.startswith("["):
                # NoDecode stops pydantic-settings from doing this for us.
                return json.loads(value)
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, int):
            return [value]
        return value

    @field_validator("bot_username", mode="before")
    @classmethod
    def _clean_username(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().strip("<>").lstrip("@").strip()
        return value

    @property
    def internal_base(self) -> str:
        return f"{self.backend_url.rstrip('/')}{self.api_prefix}"

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.admin_telegram_ids


@lru_cache
def get_settings() -> BotSettings:
    settings = BotSettings()
    # A separate bot process on a managed host has no localhost backend to call,
    # and Telegram refuses a Mini App button that is not HTTPS — so both URLs
    # fall back to the deployment's own address when left at their local values.
    deployment = next(
        (
            os.getenv(name)
            for name in ("VERCEL_PROJECT_PRODUCTION_URL", "VERCEL_URL")
            if os.getenv(name)
        ),
        None,
    )
    if deployment and not deployment.startswith("http"):
        deployment = f"https://{deployment}"

    if deployment and settings.backend_url == _DEFAULT_BACKEND_URL:
        settings.backend_url = deployment
    if deployment and settings.webapp_url == _DEFAULT_WEBAPP_URL:
        settings.webapp_url = deployment
    return settings


settings = get_settings()
