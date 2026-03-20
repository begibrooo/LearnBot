import logging
from aiogram import Router, Bot, F
from aiogram.types import CallbackQuery
from database.users import get_user
from utils.helpers import check_subscriptions, subscription_kb
from keyboards.user import main_menu_kb

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "check_sub")
async def check_sub_callback(call: CallbackQuery, bot: Bot):
    missing = await check_subscriptions(bot, call.from_user.id)
    if missing:
        await call.answer("❌ You haven't subscribed to all channels yet!", show_alert=True)
        await call.message.edit_text(
            "📢 <b>Please subscribe to all channels first:</b>",
            reply_markup=subscription_kb(missing)
        )
        return

    user = await get_user(call.from_user.id)
    name = (user and user.get("full_name")) or "there"
    await call.message.delete()
    await call.message.answer(
        f"✅ <b>All done, {name}!</b>\n\nWelcome to <b>LearnBot</b> 🎓",
        reply_markup=main_menu_kb()
    )


@router.callback_query(F.data == "noop")
async def noop_callback(call: CallbackQuery):
    await call.answer("⚠️ No join link available. Ask admin to re-add this channel with an invite link.", show_alert=True)


@router.callback_query(F.data == "channel_fix_needed")
async def channel_fix_needed(call: CallbackQuery):
    await call.answer(
        "⚠️ This channel has no join link yet.\n\nAsk the admin to run /fix_channels to repair it.",
        show_alert=True
    )
