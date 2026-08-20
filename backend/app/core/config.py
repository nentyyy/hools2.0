"""Application settings.

Everything secret comes from the environment; nothing is ever hardcoded and the
bot token never leaves the backend/bot processes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

_DEFAULT_DATABASE_URL = "postgresql+asyncpg://gg:gg@localhost:5432/gg"
_DEFAULT_REDIS_URL = "redis://localhost:6379/0"
_DEFAULT_WEBAPP_URL = "http://localhost:5173"


@dataclass(frozen=True, slots=True)
class DatabaseOptions:
    url: str
    ssl_required: bool
    statement_cache_size: int


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- runtime -----------------------------------------------------------
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    api_prefix: str = "/api"
    # NoDecode: keep pydantic-settings from JSON-parsing the raw env value, so
    # the validator below can accept plain "a,b,c" as well as a JSON list.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])

    # --- telegram ----------------------------------------------------------
    bot_token: str = ""
    bot_username: str = "gggram_bot"
    webapp_url: str = _DEFAULT_WEBAPP_URL
    telegram_webhook_secret: str = ""
    init_data_ttl: int = 86400  # seconds an initData signature stays valid
    # Lets the Mini App be played in a plain browser through a guest account.
    # Off by default: with it on, anyone holding the URL can mint accounts.
    allow_browser_login: bool = False

    # --- storage -----------------------------------------------------------
    database_url: str = _DEFAULT_DATABASE_URL
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_statement_cache_size: int = 100  # set 0 behind pgbouncer/Neon pooler
    redis_url: str = _DEFAULT_REDIS_URL

    # --- auth --------------------------------------------------------------
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_ttl: int = 60 * 60 * 24 * 7
    internal_api_token: str = "change-me-internal"
    cron_secret: str = "change-me-cron"
    admin_telegram_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    # --- economy -----------------------------------------------------------
    pvp_rake_percent: float = 5.0
    pvp_min_bet: int = 10
    pvp_max_bet: int = 100_000
    pvp_countdown_seconds: int = 20
    pvp_spin_seconds: int = 6
    pvp_max_players: int = 12
    solo_min_bet: int = 10
    solo_max_bet: int = 50_000
    house_edge: float = 0.04
    referral_signup_bonus: int = 50
    referral_topup_percent: float = 10.0
    signup_bonus: int = 100

    # --- ton ---------------------------------------------------------------
    ton_manifest_url: str = ""
    ton_receiver_address: str = ""
    ton_api_base: str = "https://tonapi.io"
    ton_api_key: str = ""
    ton_network: str = "-239"  # mainnet workchain id used by TON Connect proofs

    # --- limits ------------------------------------------------------------
    rate_limit_default: str = "120/60"  # requests/seconds
    rate_limit_play: str = "30/60"
    rate_limit_auth: str = "20/60"

    @field_validator("admin_telegram_ids", "cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept `A,B,C`, a JSON list, or a bare single value from the env."""
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            if value.startswith("["):
                return value
            return [part.strip() for part in value.split(",") if part.strip()]
        if isinstance(value, (int, float)):
            return [value]
        return value

    @model_validator(mode="after")
    def _adopt_platform_urls(self) -> Settings:
        """Pick up the connection strings managed integrations provide.

        Adding Neon or Upstash from the Vercel marketplace injects its own
        variable names; honouring them means a deployment configured entirely
        from a phone needs no manual copying of secrets.
        """
        if not self.database_url or self.database_url == _DEFAULT_DATABASE_URL:
            for name in ("POSTGRES_URL", "POSTGRES_PRISMA_URL", "POSTGRES_URL_NON_POOLING", "NEON_DATABASE_URL"):
                value = os.getenv(name)
                if value:
                    self.database_url = value
                    break

        if not self.redis_url or self.redis_url == _DEFAULT_REDIS_URL:
            for name in ("KV_URL", "UPSTASH_REDIS_URL", "REDIS_TLS_URL"):
                value = os.getenv(name)
                if value:
                    self.redis_url = value
                    break

        # On Vercel the deployment host is known only after the first build, so
        # fall back to it rather than forcing a redeploy just to learn the URL.
        if not self.webapp_url or self.webapp_url == _DEFAULT_WEBAPP_URL:
            for name in ("VERCEL_PROJECT_PRODUCTION_URL", "VERCEL_URL"):
                value = os.getenv(name)
                if value:
                    self.webapp_url = value if value.startswith("http") else f"https://{value}"
                    break
        return self

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def database_options(self) -> DatabaseOptions:
        """Split a managed Postgres URL into something asyncpg accepts.

        Hosted providers hand out libpq-style URLs (`?sslmode=require`,
        `&channel_binding=require`, `?pgbouncer=true`). asyncpg does not
        understand those keywords and SQLAlchemy would pass them straight to
        `connect()`, so they are stripped here and translated into connect
        arguments instead.
        """
        url = self.database_url.strip()
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

        parsed = urlsplit(url)
        params = parse_qsl(parsed.query, keep_blank_values=True)

        ssl_required = False
        pooled = "pooler" in (parsed.hostname or "") or "pgbouncer" in (parsed.hostname or "")
        kept: list[tuple[str, str]] = []

        for key, value in params:
            lowered = key.lower()
            if lowered == "sslmode":
                ssl_required = value.lower() not in {"disable", "allow", "prefer"}
            elif lowered == "channel_binding":
                continue  # libpq only
            elif lowered == "pgbouncer":
                pooled = pooled or value.lower() in {"1", "true", "yes"}
            elif lowered in {"connect_timeout", "application_name", "options"}:
                continue  # supplied through connect_args instead
            else:
                kept.append((key, value))

        clean = urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, urlencode(kept), parsed.fragment)
        )

        # A transaction-mode pooler cannot keep prepared statements around.
        cache_size = 0 if pooled else self.db_statement_cache_size
        return DatabaseOptions(url=clean, ssl_required=ssl_required, statement_cache_size=cache_size)

    @property
    def sqlalchemy_url(self) -> str:
        """Connection URL with the asyncpg driver and no libpq-only parameters."""
        return self.database_options.url

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.admin_telegram_ids


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
