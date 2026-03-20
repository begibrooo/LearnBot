import logging
from aiogram import Router, Bot
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from config import settings
from database.users import get_or_create_user, increment_invites, add_free_pass, get_user
from utils.helpers import check_subscriptions, subscription_kb
from keyboards.user import main_menu_kb

router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    args = message.text.split(maxsplit=1)
    referrer_id = None
    if len(args) > 1:
        try:
            referrer_id = int(args[1])
            if referrer_id == message.from_user.id:
                referrer_id = None
        except ValueError:
            referrer_id = None

    user = await get_or_create_user(
        tg_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        referred_by=referrer_id,
    )

    # Handle referral reward
    if referrer_id and user.get("referred_by") == referrer_id:
        referrer = await get_user(referrer_id)
        if referrer:
            new_invites = referrer["invites_count"] + 1
            await increment_invites(referrer_id)
            # Grant free pass every N invites
            if new_invites % settings.INVITES_PER_FREE_PASS == 0:
                await add_free_pass(referrer_id)
                try:
                    await bot.send_message(
                        referrer_id,
                        f"🎉 <b>Congrats!</b> You've invited {new_invites} friends!\n"
                        f"🎫 You've earned a <b>Free Pass</b>!"
                    )
                except Exception:
                    pass
            else:
                remaining = settings.INVITES_PER_FREE_PASS - (new_invites % settings.INVITES_PER_FREE_PASS)
                try:
                    await bot.send_message(
                        referrer_id,
                        f"👥 <b>New friend joined!</b> ({new_invites} total)\n"
                        f"🎫 {remaining} more invite(s) until your next Free Pass!"
                    )
                except Exception:
                    pass

    # Check subscriptions
    missing = await check_subscriptions(bot, message.from_user.id)
    if missing:
        await message.answer(
            "📢 <b>Please subscribe to our channels to use this bot:</b>",
            reply_markup=subscription_kb(missing)
        )
        return

    await send_welcome(message, user)


async def send_welcome(message: Message, user: dict):
    name = user.get("full_name") or "there"
    vip = " 👑" if user.get("is_vip") else ""
    await message.answer(
        f"👋 <b>Welcome, {name}{vip}!</b>\n\n"
        f"🎓 <b>LearnBot</b> — Your personal learning platform.\n\n"
        f"📚 Browse categories, unlock lessons, invite friends,\n"
        f"and track your progress — all in one place.\n\n"
        f"<i>Choose an option below to get started:</i>",
        reply_markup=main_menu_kb()
    )
