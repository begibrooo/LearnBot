from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.promos import validate_promo, use_promo
from database.content import unlock_lesson
from database.users import add_free_pass
from database.analytics import log_action
from utils.helpers import send_promo_file
from keyboards.user import cancel_kb, main_menu_kb

router = Router()


class PromoState(StatesGroup):
    waiting_code = State()


@router.message(F.text == "🎟 Promo Code")
async def promo_prompt(message: Message, state: FSMContext):
    await state.set_state(PromoState.waiting_code)
    await message.answer(
        "🎟 <b>Enter your promo code:</b>",
        reply_markup=cancel_kb()
    )


@router.message(PromoState.waiting_code)
async def process_promo(message: Message, state: FSMContext, bot: Bot):
    code = message.text.strip()
    await state.clear()

    promo, err = await validate_promo(code)
    if not promo:
        msgs = {
            "not_found": "❌ <b>Invalid promo code.</b>",
            "expired": "⌛ <b>This promo code has expired.</b>",
            "limit_reached": "🚫 <b>This promo code has reached its usage limit.</b>",
        }
        await message.answer(msgs.get(err, "❌ Invalid code."), reply_markup=main_menu_kb())
        return

    success, reason = await use_promo(message.from_user.id, promo["id"])
    if not success:
        await message.answer("⚠️ You've already used this promo code.", reply_markup=main_menu_kb())
        return

    ptype = promo["promo_type"]
    if ptype == "free_pass":
        passes = promo.get("free_passes") or 1
        await add_free_pass(message.from_user.id, passes)
        await message.answer(
            f"🎉 <b>Promo activated!</b>\n\n🎫 You received <b>{passes} Free Pass(es)</b>!",
            reply_markup=main_menu_kb()
        )

    elif ptype == "lesson_unlock":
        lesson_id = promo.get("lesson_id")
        if lesson_id:
            await unlock_lesson(message.from_user.id, lesson_id)
            await message.answer(
                f"🎉 <b>Promo activated!</b>\n\n🔓 Lesson unlocked!",
                reply_markup=main_menu_kb()
            )
        else:
            await message.answer("⚠️ Promo has no lesson assigned.", reply_markup=main_menu_kb())

    elif ptype == "file_reward":
        await message.answer("🎉 <b>Promo activated!</b> Here's your reward:", reply_markup=main_menu_kb())
        await send_promo_file(bot, message.from_user.id, promo)

    await log_action(message.from_user.id, "promo_used", code)
