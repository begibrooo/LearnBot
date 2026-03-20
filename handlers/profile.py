from aiogram import Router, F
from aiogram.types import Message
from database.users import get_user
from database.content import get_user_unlocked_lessons

router = Router()


@router.message(F.text == "👤 Profile")
async def profile_handler(message: Message):
    user = await get_user(message.from_user.id)
    if not user:
        await message.answer("User not found.")
        return

    unlocked = await get_user_unlocked_lessons(message.from_user.id)
    vip_badge = "👑 VIP" if user.get("is_vip") else "🆓 Free"
    name = user.get("full_name") or "Unknown"
    username = f"@{user['username']}" if user.get("username") else "—"

    await message.answer(
        f"👤 <b>My Profile</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 Name: <b>{name}</b>\n"
        f"🔗 Username: {username}\n"
        f"🆔 ID: <code>{user['tg_id']}</code>\n"
        f"💎 Status: <b>{vip_badge}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📖 Unlocked Lessons: <b>{len(unlocked)}</b>\n"
        f"🎫 Free Passes: <b>{user.get('free_passes', 0)}</b>\n"
        f"👥 Invites: <b>{user.get('invites_count', 0)}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📅 Joined: <i>{str(user.get('created_at', ''))[:10]}</i>"
    )
