from aiogram import Router, F
from aiogram.types import Message
from database.users import get_leaderboard

router = Router()

MEDALS = ["🥇", "🥈", "🥉"]


@router.message(F.text == "🏆 Leaderboard")
async def leaderboard(message: Message):
    top = await get_leaderboard(10)
    if not top:
        await message.answer("🏆 <b>Leaderboard</b>\n\nNo data yet. Be the first!")
        return

    text = "🏆 <b>Top Inviters</b>\n━━━━━━━━━━━━━━━━━━\n"
    for i, u in enumerate(top):
        medal = MEDALS[i] if i < 3 else f"{i+1}."
        name = u.get("full_name") or "Anonymous"
        uname = f"@{u['username']}" if u.get("username") else ""
        invites = u.get("invites_count", 0)
        highlight = "<b>" if i < 3 else ""
        end = "</b>" if i < 3 else ""
        text += f"{medal} {highlight}{name}{end} {uname} — <b>{invites}</b> invites\n"

    await message.answer(text)
