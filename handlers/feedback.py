"""
Lesson Feedback & Ratings
After opening a lesson, user can rate it 1-5 ⭐
Admin can see average ratings per lesson.
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import aiosqlite
from database.db import DB_PATH
from config import settings

router = Router()


def is_admin(uid): return uid in settings.admin_id_list


async def _ensure_ratings_table():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS lesson_ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                lesson_id INTEGER NOT NULL,
                rating INTEGER NOT NULL,
                rated_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, lesson_id)
            )
        """)
        await db.commit()


async def save_rating(user_id: int, lesson_id: int, rating: int):
    await _ensure_ratings_table()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO lesson_ratings (user_id, lesson_id, rating) VALUES (?,?,?)",
            (user_id, lesson_id, rating)
        )
        await db.commit()


async def get_lesson_rating(lesson_id: int) -> dict:
    await _ensure_ratings_table()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT COUNT(*) as cnt, AVG(rating) as avg FROM lesson_ratings WHERE lesson_id=?",
            (lesson_id,)
        ) as cur:
            row = await cur.fetchone()
        return {"count": row["cnt"] or 0, "avg": round(row["avg"] or 0, 1)}


async def get_top_rated_lessons(limit: int = 5) -> list:
    await _ensure_ratings_table()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT l.title, AVG(r.rating) as avg_rating, COUNT(r.id) as votes
               FROM lesson_ratings r
               JOIN lessons l ON l.id = r.lesson_id
               GROUP BY r.lesson_id
               ORDER BY avg_rating DESC, votes DESC
               LIMIT ?""",
            (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


def rating_kb(lesson_id: int) -> InlineKeyboardMarkup:
    stars = ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=s, callback_data=f"rate:{lesson_id}:{i+1}")
        for i, s in enumerate(stars)
    ]])


@router.callback_query(F.data.startswith("rate:"))
async def handle_rating(call: CallbackQuery):
    _, lesson_id_str, rating_str = call.data.split(":")
    lesson_id = int(lesson_id_str)
    rating    = int(rating_str)

    await save_rating(call.from_user.id, lesson_id, rating)
    stats = await get_lesson_rating(lesson_id)
    stars = "⭐" * rating

    await call.answer(
        f"{stars} Rating saved!\n"
        f"Avg: {stats['avg']}⭐ ({stats['count']} votes)",
        show_alert=True
    )
