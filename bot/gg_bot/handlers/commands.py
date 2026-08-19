"""Command handlers: /start, /profile, /games, /giveaways, /balance, /help."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from gg_bot import api, keyboards, texts

logger = logging.getLogger(__name__)
router = Router(name="commands")


async def _ensure(message: Message, start_param: str | None = None) -> dict | None:
    """Register the user (binding a referral deep link) before doing anything else."""
    user = message.from_user
    if user is None:
        return None
    try:
        data = await api.ensure_user(
            user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
            start_param=start_param,
        )
    except api.BackendError:
        await message.answer(texts.BACKEND_DOWN)
        return None

    if data.get("is_banned"):
        await message.answer(texts.BANNED)
        return None
    return data


@router.message(CommandStart())
async def start(message: Message, command: CommandObject) -> None:
    """`/start` and `/start ref_XXXX` — the referral is bound server side."""
    data = await _ensure(message, start_param=command.args)
    if data is None:
        return

    greeting = texts.WELCOME
    if data.get("created"):
        greeting += f"\n\n🎁 Welcome bonus credited: <b>{data['balance']} GG</b>"
    await message.answer(greeting, reply_markup=keyboards.main_menu())
    logger.info("start", extra={"user_id": message.from_user.id, "ref": command.args})


@router.message(Command("profile"))
async def profile(message: Message) -> None:
    data = await _ensure(message)
    if data is None:
        return
    await message.answer(texts.profile(data), reply_markup=keyboards.open_app("👤 Open profile", "/profile"))


@router.message(Command("games"))
async def games(message: Message) -> None:
    await message.answer(
        "🎮 <b>Game modes</b>\n\nEvery result is computed by the server — pick a mode to play.",
        reply_markup=keyboards.games_menu(),
    )


@router.message(Command("giveaways"))
async def giveaways(message: Message) -> None:
    try:
        data = await api.active_giveaways()
    except api.BackendError:
        await message.answer(texts.BACKEND_DOWN)
        return
    await message.answer(
        texts.giveaways(data["items"]),
        reply_markup=keyboards.open_app("🎁 Open giveaways", "/giveaways"),
    )


@router.message(Command("balance"))
async def balance(message: Message) -> None:
    data = await _ensure(message)
    if data is None:
        return
    try:
        config = await api.get_config()
    except api.BackendError:
        await message.answer(texts.BACKEND_DOWN)
        return
    await message.answer(texts.balance(data), reply_markup=keyboards.packages_menu(config["packages"]))


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(texts.HELP, reply_markup=keyboards.open_app())


@router.callback_query(F.data == "menu")
async def menu_callback(callback: CallbackQuery) -> None:
    await callback.message.edit_text(texts.WELCOME, reply_markup=keyboards.main_menu())
    await callback.answer()
