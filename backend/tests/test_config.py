"""Configuration normalisation.

Managed platforms hand out connection strings in shapes asyncpg cannot consume
directly, and inject their own variable names. Getting this wrong is a
deployment that dies on the first query, so it is pinned down here.
"""

import pytest

from app.core.config import Settings


def _settings(**env) -> Settings:
    import os

    saved = {k: os.environ.get(k) for k in env}
    os.environ.update({k: v for k, v in env.items() if v is not None})
    for key, value in env.items():
        if value is None:
            os.environ.pop(key, None)
    try:
        return Settings(_env_file=None)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_libpq_parameters_are_translated_for_asyncpg():
    settings = _settings(
        DATABASE_URL="postgresql://u:p@ep-x-123.eu-central-1.aws.neon.tech/db"
        "?sslmode=require&channel_binding=require"
    )
    options = settings.database_options

    assert options.url.startswith("postgresql+asyncpg://")
    assert "sslmode" not in options.url
    assert "channel_binding" not in options.url
    assert options.ssl_required is True


def test_pooled_host_disables_the_statement_cache():
    pooled = _settings(DATABASE_URL="postgresql://u:p@ep-x-123-pooler.neon.tech/db").database_options
    direct = _settings(DATABASE_URL="postgresql://u:p@db.internal:5432/db").database_options

    # Prepared statements break behind a transaction-mode pooler.
    assert pooled.statement_cache_size == 0
    assert direct.statement_cache_size > 0


def test_postgres_scheme_variants_are_accepted():
    assert _settings(DATABASE_URL="postgres://u:p@h/db").database_options.url.startswith(
        "postgresql+asyncpg://"
    )


def test_platform_variables_are_adopted():
    settings = _settings(
        DATABASE_URL=None,
        REDIS_URL=None,
        WEBAPP_URL=None,
        POSTGRES_URL="postgresql://u:p@neon/db",
        KV_URL="rediss://default:pw@upstash:6379",
        VERCEL_URL="gg-gram-abc.vercel.app",
    )
    assert settings.database_url == "postgresql://u:p@neon/db"
    assert settings.redis_url.startswith("rediss://")
    assert settings.webapp_url == "https://gg-gram-abc.vercel.app"


def test_explicit_values_win_over_platform_defaults():
    settings = _settings(
        DATABASE_URL="postgresql://mine:pw@myhost/db",
        POSTGRES_URL="postgresql://theirs:pw@neon/db",
        WEBAPP_URL="https://custom.example",
        VERCEL_URL="gg-gram-abc.vercel.app",
    )
    assert "mine" in settings.database_url
    assert settings.webapp_url == "https://custom.example"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("5794472585", [5794472585]), ("1,2,3", [1, 2, 3]), ("[7, 8]", [7, 8]), ("", [])],
)
def test_admin_ids_parse_from_every_documented_form(raw, expected):
    assert _settings(ADMIN_TELEGRAM_IDS=raw).admin_telegram_ids == expected


def test_bot_username_is_cleaned():
    # The value pasted from the template keeps its placeholder brackets.
    assert _settings(BOT_USERNAME="<GGGgrambot").bot_username == "GGGgrambot"
    assert _settings(BOT_USERNAME="@gg_bot ").bot_username == "gg_bot"
