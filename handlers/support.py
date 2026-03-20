import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import settings
from database.analytics import save_support_ticket, get_ticket_by_message
from keyboards.user import cancel_kb, main_menu_kb

router = Router()
logger = logging.getLogger(__name__)


class SupportState(StatesGroup):
    waiting_message = State()


@router.message(F.text == "✍️ Support")
async def support_prompt(message: Message, state: FSMContext):
    await state.set_state(SupportState.waiting_message)
    await message.answer(
        "✍️ <b>Contact Support</b>\n\n"
        "Send your message, photo, video, or document.\n"
        "Our team will get back to you as soon as possible.",
        reply_markup=cancel_kb()
    )


@router.message(SupportState.waiting_message)
async def forward_to_admins(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user = message.from_user
    header = (
        f"📩 <b>Support Request</b>\n"
        f"👤 {user.full_name} ({('@' + user.username) if user.username else '—'}) | ID: <code>{user.id}</code>"
    )

    sent_ids = []
    for admin_id in settings.admin_id_list:
        try:
            info_msg = await bot.send_message(admin_id, header)
            fwd = await message.forward(admin_id)
            sent_ids.append(fwd.message_id)
        except Exception as e:
            logger.warning(f"Could not forward to admin {admin_id}: {e}")

    if sent_ids:
        await save_support_ticket(user.id, sent_ids[0])

    await message.answer(
        "✅ <b>Your message has been sent!</b>\n\nWe'll reply soon.",
        reply_markup=main_menu_kb()
    )


# ─── ADMIN REPLY ──────────────────────────────────────────────

@router.message(F.reply_to_message & F.from_user.id.in_(settings.admin_id_list))
async def admin_reply_to_user(message: Message, bot: Bot):
    replied_to = message.reply_to_message
    if not replied_to:
        return

    ticket = await get_ticket_by_message(replied_to.message_id)
    if not ticket:
        return

    target_user_id = ticket["user_id"]
    try:
        await bot.send_message(
            target_user_id,
            f"📬 <b>Reply from Support:</b>\n\n{message.text or message.caption or '(media)'}"
        )
        if message.photo:
            await bot.send_photo(target_user_id, message.photo[-1].file_id)
        elif message.document:
            await bot.send_document(target_user_id, message.document.file_id)
        elif message.video:
            await bot.send_video(target_user_id, message.video.file_id)
        await message.reply("✅ Reply sent to user.")
    except Exception as e:
        await message.reply(f"❌ Could not send reply: {e}")
