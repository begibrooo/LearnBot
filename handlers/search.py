from aiogram import Router, F
from aiogram.types import Message, InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.content import search_lessons, get_lesson, is_lesson_unlocked
from keyboards.user import cancel_kb, main_menu_kb, lesson_detail_kb
import hashlib

router = Router()


class SearchState(StatesGroup):
    waiting_query = State()


@router.message(F.text == "🔍 Search")
async def search_prompt(message: Message, state: FSMContext):
    await state.set_state(SearchState.waiting_query)
    await message.answer(
        "🔍 <b>Search Lessons</b>\n\nType a lesson name or keyword:",
        reply_markup=cancel_kb()
    )


@router.message(SearchState.waiting_query)
async def do_search(message: Message, state: FSMContext):
    query = message.text.strip()
    if not query:
        return
    await state.clear()
    results = await search_lessons(query)
    if not results:
        await message.answer(f"😔 No lessons found for <b>\"{query}\"</b>.")
        return

    text = f"🔍 <b>Results for \"{query}\":</b>\n\n"
    for les in results[:15]:
        lock = "✅" if les.get("is_free") else ("👑" if les.get("is_vip") else "🔒")
        text += f"{lock} <b>{les['title']}</b> — <i>{les.get('category_name', '')}</i>\n"
    if len(results) > 15:
        text += f"\n<i>Showing 15 of {len(results)} results. Be more specific.</i>"
    await message.answer(text)


@router.inline_query()
async def inline_search(query: InlineQuery):
    q = query.query.strip()
    if not q:
        await query.answer([], cache_time=5)
        return

    results_data = await search_lessons(q, limit=10)
    articles = []
    for les in results_data:
        lock = "✅ Free" if les.get("is_free") else ("👑 VIP" if les.get("is_vip") else "🔒 Locked")
        desc = les.get("description") or les.get("category_name") or ""
        uid = hashlib.md5(f"{les['id']}".encode()).hexdigest()
        articles.append(InlineQueryResultArticle(
            id=uid,
            title=les["title"],
            description=f"{lock} | {desc[:60]}",
            input_message_content=InputTextMessageContent(
                message_text=f"📖 <b>{les['title']}</b>\n{desc}",
            )
        ))
    await query.answer(articles, cache_time=10)
