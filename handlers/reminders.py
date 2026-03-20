"""
Smart Reminders
- Users who haven't opened the bot in 2+ days get a gentle nudge
- Remind users who have a free pass but haven't used it
- Admin can send scheduled reminders
Runs as a background task checking every 6 hours.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import settings
import aiosqlite
from database.db import DB_PATH

router = Router()
logger = logging.getLogger(__name__)

CHECK_INTERVAL_HOURS = 6


async def get_inactive_users(days: int = 2) -> list[dict]:
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT tg_id, full_name, free_passes FROM users "
            "WHERE is_banned=0 AND last_seen < ? AND last_seen IS NOT NULL",
            (cutoff,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_pass_holders() -> list[dict]:
    """Users with unused passes who haven't been seen recently."""
    cutoff = (datetime.now() - timedelta(days=1)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT tg_id, full_name, free_passes FROM users "
            "WHERE is_banned=0 AND free_passes > 0 AND last_seen < ?",
            (cutoff,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


COMEBACK_MESSAGES = [
    "👋 Hey {name}! We miss you 🥺\n\n📚 New lessons are waiting for you.\n🎫 Free passes: <b>{passes}</b>",
    "🔔 {name}, your learning streak is at risk!\n\n✅ Check in today to keep your streak alive.",
    "📖 {name}, knowledge doesn't wait!\n\n Come back and continue your journey. 🚀",
]

_msg_index = 0


async def reminder_loop(bot: Bot):
    """Background task — runs every 6 hours."""
    global _msg_index
    while True:
        await asyncio.sleep(CHECK_INTERVAL_HOURS * 3600)
        try:
            inactive = await get_inactive_users(days=2)
            notified = 0
            for u in inactive[:200]:   # cap at 200 per cycle
                name = u.get("full_name") or "friend"
                passes = u.get("free_passes", 0)
                template = COMEBACK_MESSAGES[_msg_index % len(COMEBACK_MESSAGES)]
                text = template.format(name=name, passes=passes)
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="🎓 Go to bot", callback_data="main_menu"),
                ]])
                try:
                    await bot.send_message(u["tg_id"], text, reply_markup=kb)
                    notified += 1
                except Exception:
                    pass
                await asyncio.sleep(0.05)
            _msg_index += 1
            if notified:
                logger.info(f"Reminders sent to {notified} inactive users.")
        except Exception as e:
            logger.error(f"Reminder loop error: {e}")
