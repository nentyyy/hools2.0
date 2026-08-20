"""The bot's settings are parsed at import time.

A failure here does not raise a nice error: it stops the dispatcher from being
built at all, which takes down webhook handling and command registration. The
env formats the documentation promises are pinned down here.
"""

import os

import pytest

from gg_bot.config import BotSettings


def _settings(**env) -> BotSettings:
    saved = {k: os.environ.get(k) for k in env}
    for key, value in env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        return BotSettings(_env_file=None)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("5794472585", [5794472585]),
        ("1,2,3", [1, 2, 3]),
        ("[7, 8]", [7, 8]),
        ("", []),
    ],
)
def test_admin_ids_parse_from_every_documented_form(raw, expected):
    assert _settings(ADMIN_TELEGRAM_IDS=raw).admin_telegram_ids == expected


def test_bot_username_is_cleaned():
    assert _settings(BOT_USERNAME="<GGGgrambot").bot_username == "GGGgrambot"
    assert _settings(BOT_USERNAME="@gg_bot").bot_username == "gg_bot"


def test_dispatcher_builds_with_a_single_admin_id():
    # This is the exact shape that broke command registration in production.
    os.environ["ADMIN_TELEGRAM_IDS"] = "5794472585"
    from gg_bot.runtime import COMMANDS, get_dispatcher

    assert get_dispatcher() is not None
    assert {c.command for c in COMMANDS} >= {"start", "profile", "balance", "paysupport"}
