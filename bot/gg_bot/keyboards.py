"""Inline keyboards. Mini App buttons carry a deep path so a command can open
the exact screen it talks about."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from gg_bot.config import settings


def webapp_url(path: str = "/") -> str:
    base = settings.webapp_url.rstrip("/")
    return f"{base}/#{path}" if path and path != "/" else base


def open_app(text: str = "🎮 Open gg.gram", path: str = "/") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=webapp_url(path)))]]
    )


def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Play", web_app=WebAppInfo(url=webapp_url("/")))],
            [
                InlineKeyboardButton(text="⚔️ PvP", web_app=WebAppInfo(url=webapp_url("/pvp"))),
                InlineKeyboardButton(text="🎲 Solo", web_app=WebAppInfo(url=webapp_url("/solo"))),
            ],
            [
                InlineKeyboardButton(text="🎁 Giveaways", web_app=WebAppInfo(url=webapp_url("/giveaways"))),
                InlineKeyboardButton(text="👤 Profile", web_app=WebAppInfo(url=webapp_url("/profile"))),
            ],
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
    rows = [
        [InlineKeyboardButton(text=title, web_app=WebAppInfo(url=webapp_url(path)))]
        for title, path in modes
    ]
    rows.insert(0, [InlineKeyboardButton(text="⚔️ PvP arena", web_app=WebAppInfo(url=webapp_url("/pvp")))])
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
