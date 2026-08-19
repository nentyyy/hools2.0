"""Application settings.

Everything secret comes from the environment; nothing is ever hardcoded and the
bot token never leaves the backend/bot processes.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    # --- telegram ----------------------------------------------------------
    bot_token: str = ""
    bot_username: str = "gggram_bot"
    webapp_url: str = "http://localhost:5173"
    telegram_webhook_secret: str = ""
    init_data_ttl: int = 86400  # seconds an initData signature stays valid

    # --- storage -----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://gg:gg@localhost:5432/gg"
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_statement_cache_size: int = 100  # set 0 behind pgbouncer/Neon pooler
    redis_url: str = "redis://localhost:6379/0"

    # --- auth --------------------------------------------------------------
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_ttl: int = 60 * 60 * 24 * 7
    internal_api_token: str = "change-me-internal"
    cron_secret: str = "change-me-cron"
    admin_telegram_ids: list[int] = Field(default_factory=list)

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

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def sqlalchemy_url(self) -> str:
        """Normalise common Postgres URLs to the asyncpg driver."""
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.admin_telegram_ids


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
