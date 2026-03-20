import logging
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import settings
from database.content import (
    get_categories, get_levels, get_lessons, get_lesson, get_level,
    is_lesson_unlocked, unlock_lesson, get_user_unlocked_lessons,
    increment_view, get_attempts, record_wrong_attempt, reset_attempts
)
from database.users import get_user, use_free_pass, check_vip_validity, increment_vip_lessons_used
from database.analytics import log_action
from keyboards.user import (
    categories_kb, levels_kb, lessons_kb,
    lesson_detail_kb, cancel_kb, back_to_menu_kb, main_menu_kb
)
from utils.helpers import send_lesson_content

router = Router()
logger = logging.getLogger(__name__)


class LessonStates(StatesGroup):
    waiting_code = State()


# ─── BROWSE ALL MATERIALS ─────────────────────────────────────

@router.message(F.text == "📚 All Materials")
async def all_materials(message: Message):
    cats = await get_categories()
    if not cats:
        await message.answer("📭 No categories available yet. Check back soon!")
        return
    await message.answer(
        "📚 <b>All Materials</b>\n\nChoose a category:",
        reply_markup=categories_kb(cats)
    )


@router.callback_query(F.data.startswith("cat:"))
async def show_levels(call: CallbackQuery, state: FSMContext):
    cat_id = int(call.data.split(":")[1])
    levels = await get_levels(cat_id)
    if not levels:
        await call.answer("📭 No levels in this category yet.", show_alert=True)
        return
    await state.update_data(current_cat_id=cat_id)
    await call.message.edit_text(
        "📖 <b>Select a level:</b>",
        reply_markup=levels_kb(levels, cat_id)
    )
    await call.answer()


@router.callback_query(F.data == "back_cat")
async def back_to_categories(call: CallbackQuery):
    cats = await get_categories()
    if not cats:
        await call.answer("No categories.", show_alert=True)
        return
    await call.message.edit_text(
        "📚 <b>All Materials</b>\n\nChoose a category:",
        reply_markup=categories_kb(cats)
    )
    await call.answer()


@router.callback_query(F.data.startswith("lvl:"))
async def show_lessons(call: CallbackQuery, state: FSMContext):
    level_id = int(call.data.split(":")[1])
    lessons = await get_lessons(level_id)
    await state.update_data(current_level_id=level_id)
    if not lessons:
        await call.answer("📭 No lessons in this level yet.", show_alert=True)
        return
    unlocked = await get_user_unlocked_lessons(call.from_user.id)
    unlocked_ids = {l["id"] for l in unlocked}
    await call.message.edit_text(
        "📖 <b>Select a lesson:</b>",
        reply_markup=lessons_kb(lessons, level_id, unlocked_ids)
    )
    await call.answer()


@router.callback_query(F.data.startswith("back_lvl:"))
async def back_to_levels(call: CallbackQuery):
    level_id = int(call.data.split(":")[1])
    level = await get_level(level_id)
    if not level:
        await call.answer()
        return
    levels = await get_levels(level["category_id"])
    await call.message.edit_text(
        "📖 <b>Select a level:</b>",
        reply_markup=levels_kb(levels, level["category_id"])
    )
    await call.answer()


# ─── LESSON DETAIL ────────────────────────────────────────────

@router.callback_query(F.data.startswith("les:"))
async def lesson_detail(call: CallbackQuery, state: FSMContext):
    lesson_id = int(call.data.split(":")[1])
    lesson = await get_lesson(lesson_id)
    if not lesson:
        await call.answer("Lesson not found.", show_alert=True)
        return
    await state.update_data(current_lesson_id=lesson_id)
    user = await get_user(call.from_user.id)
    is_free = bool(lesson.get("is_free"))
    is_vip = bool(lesson.get("is_vip"))
    is_unlocked = await is_lesson_unlocked(call.from_user.id, lesson_id)

    # Check VIP validity (auto-revokes if expired/limit hit)
    user_is_vip = await check_vip_validity(call.from_user.id)
    if is_vip and not user_is_vip and not is_unlocked:
        await call.message.edit_text(
            f"👑 <b>{lesson['title']}</b>\n\n"
            f"{lesson.get('description') or ''}\n\n"
            f"🔒 This is a <b>VIP lesson</b>. Upgrade to VIP to unlock it.",
            reply_markup=back_to_menu_kb()
        )
        await call.answer()
        return

    lock_status = "✅ Free" if is_free else ("🔓 Unlocked" if is_unlocked else "🔒 Locked")
    passes = user.get("free_passes", 0) if user else 0
    await call.message.edit_text(
        f"📖 <b>{lesson['title']}</b>\n\n"
        f"{lesson.get('description') or '—'}\n\n"
        f"Status: {lock_status}"
        + (f"\n🎫 Your free passes: <b>{passes}</b>" if not is_free and not is_unlocked else ""),
        reply_markup=lesson_detail_kb(lesson_id, is_unlocked, is_free, is_vip)
    )
    await call.answer()


@router.callback_query(F.data.startswith("back_les:"))
async def back_to_lesson_list(call: CallbackQuery):
    lesson_id = int(call.data.split(":")[1])
    lesson = await get_lesson(lesson_id)
    if not lesson:
        await call.answer()
        return
    level = await get_level(lesson["level_id"])
    if not level:
        await call.answer()
        return
    lessons = await get_lessons(level["id"])
    unlocked = await get_user_unlocked_lessons(call.from_user.id)
    unlocked_ids = {l["id"] for l in unlocked}
    await call.message.edit_text(
        "📖 <b>Select a lesson:</b>",
        reply_markup=lessons_kb(lessons, level["id"], unlocked_ids)
    )
    await call.answer()


# ─── OPEN LESSON ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("open:"))
async def open_lesson(call: CallbackQuery, bot: Bot):
    lesson_id = int(call.data.split(":")[1])
    lesson = await get_lesson(lesson_id)
    if not lesson:
        await call.answer("Lesson not found.", show_alert=True)
        return

    is_free = bool(lesson.get("is_free"))
    is_unlocked = await is_lesson_unlocked(call.from_user.id, lesson_id)

    if not is_free and not is_unlocked:
        await call.answer("🔒 This lesson is locked.", show_alert=True)
        return

    await call.answer("⏳ Loading lesson...")
    await call.message.answer(f"📖 <b>{lesson['title']}</b>")
    success = await send_lesson_content(bot, call.from_user.id, lesson)
    if success:
        await increment_view(lesson_id)
        await log_action(call.from_user.id, "open_lesson", str(lesson_id))
        # Track VIP lesson usage
        if lesson.get("is_vip"):
            await increment_vip_lessons_used(call.from_user.id)
            # Check if VIP just expired
            still_vip = await check_vip_validity(call.from_user.id)
            if not still_vip:
                await bot.send_message(
                    call.from_user.id,
                    "ℹ️ <b>Your VIP access has expired</b>\n\n"
                    "You used all your VIP lesson allowance.\n"
                    "Contact admin or earn more invites to get VIP again!"
                )
        # Ask for rating
        from handlers.feedback import rating_kb
        await bot.send_message(
            call.from_user.id,
            "⭐ <b>Rate this lesson:</b>",
            reply_markup=rating_kb(lesson_id)
        )


# ─── ENTER CODE ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("code:"))
async def ask_for_code(call: CallbackQuery, state: FSMContext):
    lesson_id = int(call.data.split(":")[1])

    attempt_rec = await get_attempts(call.from_user.id, lesson_id)
    if attempt_rec and attempt_rec.get("locked_until"):
        try:
            locked_until = datetime.fromisoformat(attempt_rec["locked_until"])
            if datetime.now() < locked_until:
                remaining = int((locked_until - datetime.now()).total_seconds() / 60) + 1
                await call.answer(
                    f"⏳ Too many wrong attempts. Try again in {remaining} min.",
                    show_alert=True
                )
                return
            else:
                await reset_attempts(call.from_user.id, lesson_id)
        except Exception:
            pass

    await state.set_state(LessonStates.waiting_code)
    await state.update_data(unlock_lesson_id=lesson_id)
    await call.message.edit_text(
        "🔑 <b>Enter the unlock code:</b>\n\n"
        f"<i>You have {settings.MAX_WRONG_ATTEMPTS} attempts before a {settings.LOCKOUT_MINUTES}-minute lockout.</i>",
        reply_markup=cancel_kb()
    )
    await call.answer()


@router.message(LessonStates.waiting_code)
async def process_code(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    lesson_id = data.get("unlock_lesson_id")
    if not lesson_id:
        await state.clear()
        return

    lesson = await get_lesson(lesson_id)
    if not lesson:
        await state.clear()
        return

    entered = message.text.strip()
    correct = (lesson.get("unlock_code") or "").strip()

    if correct and entered == correct:
        await unlock_lesson(message.from_user.id, lesson_id)
        await reset_attempts(message.from_user.id, lesson_id)
        await state.clear()
        await message.answer(
            f"✅ <b>Lesson unlocked!</b>\n\n📖 {lesson['title']}\n\nSending content...",
            reply_markup=main_menu_kb()
        )
        await send_lesson_content(bot, message.from_user.id, lesson)
        await increment_view(lesson_id)
        await log_action(message.from_user.id, "unlock_code", str(lesson_id))
    else:
        await record_wrong_attempt(
            message.from_user.id, lesson_id,
            settings.MAX_WRONG_ATTEMPTS, settings.LOCKOUT_MINUTES
        )
        rec = await get_attempts(message.from_user.id, lesson_id)
        attempts = rec["attempts"] if rec else 1
        remaining = settings.MAX_WRONG_ATTEMPTS - attempts
        if remaining <= 0:
            await state.clear()
            await message.answer(
                f"🚫 <b>Too many wrong attempts!</b>\n"
                f"⏳ Try again in {settings.LOCKOUT_MINUTES} minutes.",
                reply_markup=main_menu_kb()
            )
        else:
            await message.answer(
                f"❌ <b>Wrong code.</b> {remaining} attempt(s) remaining.",
                reply_markup=cancel_kb()
            )


# ─── FREE PASS UNLOCK ─────────────────────────────────────────

@router.callback_query(F.data.startswith("freepass:"))
async def use_free_pass_handler(call: CallbackQuery, bot: Bot):
    lesson_id = int(call.data.split(":")[1])
    lesson = await get_lesson(lesson_id)
    if not lesson:
        await call.answer("Lesson not found.", show_alert=True)
        return

    used = await use_free_pass(call.from_user.id)
    if not used:
        await call.answer("❌ You have no Free Passes left.", show_alert=True)
        return

    await unlock_lesson(call.from_user.id, lesson_id)
    await call.answer("✅ Free Pass used!")
    await call.message.edit_text(
        f"🎫 <b>Free Pass used!</b>\n\n📖 {lesson['title']}\n\nSending content..."
    )
    await send_lesson_content(bot, call.from_user.id, lesson)
    await increment_view(lesson_id)
    await log_action(call.from_user.id, "freepass_unlock", str(lesson_id))


# ─── MY LESSONS ───────────────────────────────────────────────

@router.message(F.text == "📖 My Lessons")
async def my_lessons(message: Message):
    lessons = await get_user_unlocked_lessons(message.from_user.id)
    if not lessons:
        await message.answer(
            "📭 <b>You haven't unlocked any lessons yet.</b>\n\n"
            "Browse <b>All Materials</b> and unlock your first lesson!"
        )
        return
    text = "📖 <b>My Unlocked Lessons:</b>\n\n"
    for i, les in enumerate(lessons[:20], 1):
        text += f"{i}. 📗 {les['title']}\n"
    if len(lessons) > 20:
        text += f"\n<i>...and {len(lessons) - 20} more</i>"
    await message.answer(text)


# ─── CANCEL — returns to main menu ────────────────────────────

@router.callback_query(F.data == "cancel")
async def cancel_action(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.answer(
        "🏠 <b>Main Menu</b>",
        reply_markup=main_menu_kb()
    )
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer()
