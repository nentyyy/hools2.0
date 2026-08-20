"""Inline keyboards. Mini App buttons carry a deep path so a command can open
the exact screen it talks about."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from gg_bot.config import settings


def webapp_url(path: str = "/") -> str:
    base = settings.webapp_url.rstrip("/")
    return f"{base}/#{path}" if path and path != "/" else base


def _mini_app_available() -> bool:
    """Telegram only accepts HTTPS for Mini App buttons."""
    return settings.webapp_url.startswith("https://")


def app_button(text: str, path: str = "/") -> InlineKeyboardButton:
    """A Mini App button where Telegram allows one, a plain link otherwise.

    Without this a misconfigured WEBAPP_URL makes every keyboard rejected by the
    Bot API, and the user just sees "something went wrong".
    """
    url = webapp_url(path)
    if _mini_app_available():
        return InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))
    return InlineKeyboardButton(text=text, url=url)


def open_app(text: str = "🎮 Open gg.gram", path: str = "/") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[app_button(text, path)]])


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [app_button("🎮 Play", "/")],
            [app_button("⚔️ PvP", "/pvp"), app_button("🎲 Solo", "/solo")],
            [app_button("🎁 Giveaways", "/giveaways"), app_button("👤 Profile", "/profile")],
            [InlineKeyboardButton(text="⭐ Top up GG", callback_data="topup")],
        ]
    )


def games_menu() -> InlineKeyboardMarkup:
    modes = [
        ("🟣 Plinko", "/solo/plinko"),
        ("🔺 Upgrade", "/solo/upgrade"),
        ("🎁 Lucky Buy", "/shop"),
        ("🃏 Hi-Lo", "/solo/hi-lo"),
        ("🧊 Ice Arena", "/solo/ice-arena"),
    ]
    rows = [[app_button(title, path)] for title, path in modes]
    rows.insert(0, [app_button("⚔️ PvP arena", "/pvp")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def packages_menu(packages: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{p['total_gg']} GG — ⭐ {p['stars']}", callback_data=f"buy:{p['code']}"
            )
        ]
        for p in packages
    ]
    rows.append([InlineKeyboardButton(text="↩️ Back", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pay_button(invoice_link: str, stars: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"⭐ Pay {stars} Stars", url=invoice_link)],
            [InlineKeyboardButton(text="↩️ Back", callback_data="topup")],
        ]
    )
