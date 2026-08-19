"""User-facing copy, kept out of the handlers."""

from __future__ import annotations

from gg_bot.config import settings

WELCOME = (
    "<b>gg.gram</b> — games, PvP and giveaways inside Telegram.\n\n"
    "🎮 <b>Solo modes</b> — Plinko, Upgrade, Lucky Buy, Hi-Lo, Ice Arena\n"
    "⚔️ <b>PvP</b> — put GG in the pot, your share is your chance\n"
    "🎁 <b>Giveaways</b> — free entries, real prizes\n\n"
    "GG is the in-app currency. Top it up with Telegram Stars, and every round is "
    "resolved on our servers with a provably fair seed you can verify.\n\n"
    "Tap the button below to start playing."
)

HELP = (
    "<b>Commands</b>\n"
    "/start — open the app\n"
    "/profile — your level, stats and referral link\n"
    "/games — all game modes\n"
    "/giveaways — giveaways running right now\n"
    "/balance — your GG balance and top-up options\n"
    "/paysupport — payment and refund help\n"
    "/help — this message\n\n"
    "<b>How the games work</b>\n"
    "Every result is computed by the server from a seed pair you can check "
    "afterwards. The app only shows what the server decided — it never rolls anything itself."
)

BANNED = "Your account is restricted. Contact support if you think this is a mistake."

BACKEND_DOWN = "We can't reach the game server right now. Please try again in a minute."


def profile(data: dict) -> str:
    level = data["level"]
    stats = data["stats"]
    return (
        f"👤 <b>{data['name']}</b>\n"
        f"Level {level['level']} · {level['xp_into_level']}/{level['xp_next_level'] - level['xp_current_level']} XP\n\n"
        f"💰 Balance: <b>{data['balance']} GG</b>\n"
        f"⚔️ PvP: {stats['pvp_wins']} wins / {stats['pvp_games']} games\n"
        f"🎲 Solo: {stats['solo_wins']} wins / {stats['solo_games']} games\n"
        f"📈 Total earned: {stats['total_earned']} GG\n"
        f"⭐ Stars spent: {stats['stars_spent']}\n\n"
        f"🤝 Referral link:\n{data['referral_link']}\n"
        f"Referral earnings: {stats['referral_earnings']} GG"
    )


def balance(data: dict) -> str:
    return (
        f"💰 Your balance: <b>{data['balance']} GG</b>\n\n"
        "Top up with Telegram Stars — GG is credited the moment the payment is confirmed."
    )


def giveaways(items: list[dict]) -> str:
    if not items:
        return "🎁 No giveaways are running right now. Check back soon!"
    lines = ["🎁 <b>Live giveaways</b>\n"]
    for item in items:
        prize = f"{item['prize_value']} GG" if item["prize_type"] == "gg" else item["prize_type"]
        entry = "free entry" if not item["entry_cost"] else f"{item['entry_cost']} GG entry"
        lines.append(
            f"• <b>{item['title']}</b> — {prize}\n"
            f"  {item['participants_count']} participants · {entry}"
        )
    lines.append("\nOpen the app to join.")
    return "\n".join(lines)


PAY_SUPPORT = (
    "<b>Payment support</b>\n\n"
    "GG is an in-app currency used for games inside this Mini App. Top-ups are paid with "
    "Telegram Stars (XTR) and credited automatically once Telegram confirms the payment.\n\n"
    "<b>GG did not arrive?</b>\n"
    "Send us the transaction id from Telegram (Settings → My Stars → the purchase) and we will "
    "check it. Payments are matched by their charge id, so nothing gets lost.\n\n"
    "<b>Refunds</b>\n"
    "Stars purchases can be refunded through Telegram while the topped-up GG has not been spent. "
    "Reply here with your transaction id to request a refund — we process it with Telegram's "
    "official refund mechanism and the Stars go back to your Telegram balance.\n\n"
    f"Support contact: @{settings.bot_username}"
)


def payment_confirmed(gg: int, balance: int, charge_id: str) -> str:
    return (
        f"✅ <b>Payment confirmed</b>\n\n"
        f"+{gg} GG credited. New balance: <b>{balance} GG</b>\n"
        f"Transaction id: <code>{charge_id}</code>\n\n"
        "Keep this id — you'll need it if you ever request a refund."
    )
