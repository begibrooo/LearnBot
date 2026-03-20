import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from keyboards.user import main_menu_kb
from utils.helpers import check_subscriptions, subscription_kb

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text == "🏠 Main Menu")
@router.callback_query(F.data == "main_menu")
async def main_menu(event, bot: Bot, state: FSMContext):
    await state.clear()
    if isinstance(event, CallbackQuery):
        await event.answer()
        msg = event.message
    else:
        msg = event

    missing = await check_subscriptions(bot, event.from_user.id)
    if missing:
        await msg.answer("📢 <b>Please subscribe first:</b>", reply_markup=subscription_kb(missing))
        return

    await msg.answer("🏠 <b>Main Menu</b> — Choose an option:", reply_markup=main_menu_kb())


@router.message(F.text == "📋 Help")
async def help_menu_btn(message: Message, state: FSMContext):
    from handlers.stats import help_cmd
    await help_cmd(message)


@router.message(F.text == "🏅 Badges")
async def badges_menu_btn(message: Message, state: FSMContext, bot: Bot):
    from handlers.achievements import show_badges
    await show_badges(message, bot)


@router.message(F.text == "⚡ Challenge")
async def challenge_menu_btn(message: Message, state: FSMContext):
    from handlers.daily_challenge import show_challenge
    await show_challenge(message)


@router.message(F.text == "🎮 Play Games")
async def games_menu_btn(message: Message, state: FSMContext):
    from config import settings
    webapp_url = settings.WEBAPP_URL
    if not webapp_url:
        await message.answer(
            "🎮 <b>Games are coming soon!</b>\n\n"
            "The admin is setting up the game platform. Check back soon!"
        )
        return
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    await message.answer(
        "🎮 <b>LearnBot Games</b>\n\n"
        "Play interactive games based on your lessons!\n\n"
        "• 🧠 Multiple choice quizzes\n"
        "• 🃏 Flashcard review\n"
        "• 🔗 Match the pairs\n"
        "• ✏️ Fill in the blank",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎮 Open Games", web_app={"url": webapp_url})
        ]])
    )
