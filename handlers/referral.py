from aiogram import Router, F, Bot
from aiogram.types import Message
from database.users import get_user
from config import settings

router = Router()


@router.message(F.text == "👥 Invite Friends")
async def invite_friends(message: Message, bot: Bot):
    user = await get_user(message.from_user.id)
    invites = user.get("invites_count", 0) if user else 0
    passes = user.get("free_passes", 0) if user else 0
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start={message.from_user.id}"
    needed = settings.INVITES_PER_FREE_PASS - (invites % settings.INVITES_PER_FREE_PASS)
    if needed == settings.INVITES_PER_FREE_PASS:
        needed = 0

    await message.answer(
        f"👥 <b>Invite Friends</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🔗 Your invite link:\n<code>{link}</code>\n\n"
        f"📊 Total invites: <b>{invites}</b>\n"
        f"🎫 Free Passes earned: <b>{passes}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🎁 Every <b>{settings.INVITES_PER_FREE_PASS}</b> invites = <b>1 Free Pass</b>\n"
        + (f"⏳ <b>{settings.INVITES_PER_FREE_PASS - (invites % settings.INVITES_PER_FREE_PASS)}</b> more invite(s) until your next Free Pass!"
           if invites % settings.INVITES_PER_FREE_PASS != 0 else
           f"🎉 Keep inviting to earn more passes!")
    )
