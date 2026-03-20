"""
Daily Challenge System
Every day at midnight a new challenge is set.
First N users to complete it win free passes.
Admin can set challenges from the panel.

Challenge types:
  • quiz      — answer 3 quiz questions correctly
  • lesson    — open a specific lesson
  • checkin   — check in today
  • invite    — invite 1 new friend today
"""
import asyncio
import logging
import aiosqlite
from datetime import datetime, date
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import DB_PATH
from database.users import get_all_users, add_free_pass
from config import settings
from keyboards.user import main_menu_kb, cancel_kb

router = Router()
logger = logging.getLogger(__name__)


def is_admin(uid): return uid in settings.admin_id_list


# ─── DB ───────────────────────────────────────────────────────

async def _ensure_tables():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS daily_challenges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                challenge_date TEXT UNIQUE NOT NULL,
                type TEXT NOT NULL,
                description TEXT NOT NULL,
                target_value INTEGER DEFAULT 1,
                reward_passes INTEGER DEFAULT 1,
                winner_limit INTEGER DEFAULT 10,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS challenge_completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                challenge_id INTEGER NOT NULL,
                completed_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, challenge_id)
            );
        """)
        await db.commit()


async def get_today_challenge() -> dict | None:
    await _ensure_tables()
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM daily_challenges WHERE challenge_date=?", (today,)
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


async def has_completed(user_id: int, challenge_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM challenge_completions WHERE user_id=? AND challenge_id=?",
            (user_id, challenge_id)
        ) as cur:
            return await cur.fetchone() is not None


async def get_completion_count(challenge_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT COUNT(*) as c FROM challenge_completions WHERE challenge_id=?", (challenge_id,)
        ) as cur:
            return (await cur.fetchone())["c"]


async def complete_challenge(user_id: int, challenge_id: int) -> bool:
    """Mark challenge complete. Returns True if newly completed."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO challenge_completions (user_id, challenge_id) VALUES (?,?)",
                (user_id, challenge_id)
            )
            await db.commit()
            return True
        except Exception:
            return False


async def create_challenge(
    challenge_date: str, ctype: str, description: str,
    target: int, reward: int, winner_limit: int
) -> int:
    await _ensure_tables()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT OR REPLACE INTO daily_challenges "
            "(challenge_date, type, description, target_value, reward_passes, winner_limit) "
            "VALUES (?,?,?,?,?,?)",
            (challenge_date, ctype, description, target, reward, winner_limit)
        )
        await db.commit()
        return cur.lastrowid


# ─── User: view + complete ─────────────────────────────────────

@router.message(Command("challenge"))
@router.message(F.text == "⚡ Challenge")
async def show_challenge(message: Message):
    ch = await get_today_challenge()
    if not ch:
        await message.answer(
            "📭 <b>No challenge today!</b>\n\n"
            "Check back tomorrow or ask the admin to set one."
        )
        return

    done       = await has_completed(message.from_user.id, ch["id"])
    completions = await get_completion_count(ch["id"])
    spots_left  = max(0, ch["winner_limit"] - completions)

    status = "✅ <b>You completed this challenge!</b>" if done else "⏳ <b>Not completed yet</b>"
    reward_line = f"🎫 Reward: <b>{ch['reward_passes']} Free Pass{'es' if ch['reward_passes']>1 else ''}</b>"
    limit_line  = f"🏁 Winners so far: <b>{completions}/{ch['winner_limit']}</b>"
    spots_line  = f"⚡ Spots remaining: <b>{spots_left}</b>" if spots_left > 0 else "🚫 <b>All spots claimed!</b>"

    kb = None
    if not done and spots_left > 0:
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Mark as Complete", callback_data=f"chall:complete:{ch['id']}")
        ]])

    await message.answer(
        f"⚡ <b>Daily Challenge</b>  —  {ch['challenge_date']}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>{ch['description']}</b>\n\n"
        f"{reward_line}\n"
        f"{limit_line}\n"
        f"{spots_line}\n\n"
        f"{status}",
        reply_markup=kb
    )


@router.callback_query(F.data.startswith("chall:complete:"))
async def complete_challenge_cb(call: CallbackQuery, bot: Bot):
    ch_id       = int(call.data.split(":")[2])
    ch          = await get_today_challenge()
    if not ch or ch["id"] != ch_id:
        await call.answer("Challenge expired.", show_alert=True); return

    completions = await get_completion_count(ch_id)
    if completions >= ch["winner_limit"]:
        await call.answer("🚫 All spots already claimed!", show_alert=True); return

    newly = await complete_challenge(call.from_user.id, ch_id)
    if not newly:
        await call.answer("You already completed this!", show_alert=True); return

    await add_free_pass(call.from_user.id, ch["reward_passes"])
    rank = completions + 1

    await call.answer(f"🎉 #{rank} — You earned {ch['reward_passes']} Free Pass(es)!", show_alert=True)
    await call.message.edit_text(
        f"✅ <b>Challenge Complete!</b>\n\n"
        f"<b>{ch['description']}</b>\n\n"
        f"🎫 <b>+{ch['reward_passes']} Free Pass{'es' if ch['reward_passes']>1 else ''}  earned!</b>\n"
        f"🏆 You were #{rank} to complete it!"
    )

    # Check for achievements
    from handlers.achievements import check_and_award
    await check_and_award(call.from_user.id, bot)


# ─── Admin: set challenge ──────────────────────────────────────

class ChallengeAdminState(StatesGroup):
    description = State()
    reward      = State()
    limit       = State()
    date        = State()


@router.callback_query(F.data == "adm:set_challenge")
async def adm_set_challenge(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(ChallengeAdminState.description)
    await call.message.edit_text(
        "⚡ <b>Set Daily Challenge</b>\n\n"
        "Enter the challenge <b>description</b>:\n\n"
        "Examples:\n"
        "• Answer 3 quiz questions correctly\n"
        "• Open any lesson today\n"
        "• Invite 1 friend to the bot\n"
        "• Complete your daily check-in",
        reply_markup=cancel_kb()
    )
    await call.answer()


@router.message(ChallengeAdminState.description)
async def chall_desc(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.update_data(description=message.text.strip())
    await state.set_state(ChallengeAdminState.reward)
    await message.answer("How many <b>Free Passes</b> as reward? (1-5):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="1", callback_data="challrew:1"),
        InlineKeyboardButton(text="2", callback_data="challrew:2"),
        InlineKeyboardButton(text="3", callback_data="challrew:3"),
    ]]))


@router.callback_query(F.data.startswith("challrew:"))
async def chall_reward(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    reward = int(call.data.split(":")[1])
    await state.update_data(reward=reward)
    await state.set_state(ChallengeAdminState.limit)
    await call.message.edit_text(
        "How many <b>winners</b> (spots)?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="10",  callback_data="challlim:10"),
            InlineKeyboardButton(text="25",  callback_data="challlim:25"),
            InlineKeyboardButton(text="50",  callback_data="challlim:50"),
            InlineKeyboardButton(text="100", callback_data="challlim:100"),
        ]])
    )
    await call.answer()


@router.callback_query(F.data.startswith("challlim:"))
async def chall_limit(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    limit = int(call.data.split(":")[1])
    data  = await state.get_data()
    await state.clear()

    today = date.today().isoformat()
    ch_id = await create_challenge(today, "manual", data["description"], 1, data["reward"], limit)

    # Announce to all users
    users = await get_all_users()
    announcement = (
        f"⚡ <b>Daily Challenge!</b>\n\n"
        f"<b>{data['description']}</b>\n\n"
        f"🎫 Reward: <b>{data['reward']} Free Pass{'es' if data['reward']>1 else ''}</b>\n"
        f"🏁 First <b>{limit}</b> to complete win!\n\n"
        f"Tap /challenge to participate!"
    )
    sent = 0
    for uid in users[:500]:   # cap broadcast
        try:
            await call.bot.send_message(uid, announcement)
            sent += 1
        except Exception:
            pass
        if sent % 25 == 0:
            await asyncio.sleep(1)

    await call.message.edit_text(
        f"✅ <b>Challenge set and announced!</b>\n\n"
        f"📢 Sent to {sent} users.\n"
        f"Challenge ID: <code>{ch_id}</code>"
    )
    await call.answer()
