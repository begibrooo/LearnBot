"""
Daily Check-in & Streak System
Users tap /checkin (or the button) once per day.
- Day 1-6:   +0 bonus
- Day 7:     🎫 1 Free Pass  (weekly streak reward)
- Day 14:    🎫 2 Free Passes
- Day 30:    🎫 3 Free Passes + 👑 VIP for 1 week (admin configurable)
Streak resets if user misses a day.
"""
from datetime import datetime, date, timedelta
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import aiosqlite
from database.db import DB_PATH
from database.users import get_user, add_free_pass, update_user
from keyboards.user import main_menu_kb
from handlers.achievements import check_and_award

router = Router()

STREAK_REWARDS = {
    7:  {"passes": 1, "msg": "🎫 You earned <b>1 Free Pass</b> for a 7-day streak!"},
    14: {"passes": 2, "msg": "🎫 You earned <b>2 Free Passes</b> for a 14-day streak!"},
    30: {"passes": 3, "msg": "🎫 You earned <b>3 Free Passes</b> for a 30-day streak! 🔥"},
}


async def get_streak(tg_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT streak_days, last_checkin, total_checkins FROM users WHERE tg_id=?", (tg_id,)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return {"streak_days": 0, "last_checkin": None, "total_checkins": 0}
            return dict(row)


async def do_checkin(tg_id: int) -> dict:
    """Returns result dict: {success, streak, reward_msg, already_done}"""
    today = date.today()
    data  = await get_streak(tg_id)
    last  = data["last_checkin"]
    streak = data["streak_days"] or 0
    total  = data["total_checkins"] or 0

    if last:
        last_date = date.fromisoformat(last)
        if last_date == today:
            return {"success": False, "already_done": True, "streak": streak, "total": total}
        elif last_date == today - timedelta(days=1):
            streak += 1   # consecutive day
        else:
            streak = 1    # streak broken

    else:
        streak = 1

    total += 1
    reward_msg = None

    # Give reward if milestone hit
    if streak in STREAK_REWARDS:
        reward = STREAK_REWARDS[streak]
        await add_free_pass(tg_id, reward["passes"])
        reward_msg = reward["msg"]

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET streak_days=?, last_checkin=?, total_checkins=? WHERE tg_id=?",
            (streak, today.isoformat(), total, tg_id)
        )
        await db.commit()

    return {"success": True, "already_done": False, "streak": streak, "total": total, "reward_msg": reward_msg}


def checkin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Daily Check-in", callback_data="do_checkin")
    ]])


@router.message(Command("checkin"))
@router.message(F.text == "✅ Check-in")
async def checkin_cmd(message: Message, bot: Bot):
    result = await do_checkin(message.from_user.id)
    await _send_checkin_result(message.answer, result)


@router.callback_query(F.data == "do_checkin")
async def checkin_callback(call: CallbackQuery, bot: Bot):
    result = await do_checkin(call.from_user.id)
    await call.answer()
    await _send_checkin_result(call.message.answer, result)
    await check_and_award(call.from_user.id, bot)


async def _send_checkin_result(answer_fn, result: dict):
    streak  = result["streak"]
    total   = result["total"]
    fire    = "🔥" * min(streak // 7 + 1, 5)

    if result.get("already_done"):
        next_checkin = (date.today() + timedelta(days=1)).strftime("%d %b")
        await answer_fn(
            f"⏳ <b>Already checked in today!</b>\n\n"
            f"🔥 Current streak: <b>{streak} days</b>\n"
            f"📅 Next check-in: <b>{next_checkin}</b>"
        )
        return

    # Progress bar to next milestone
    milestones = sorted(STREAK_REWARDS.keys())
    next_ms    = next((m for m in milestones if m > streak), milestones[-1] + 7)
    prev_ms    = max((m for m in milestones if m <= streak), default=0)
    prog_total = next_ms - prev_ms
    prog_done  = streak - prev_ms
    bar_filled = int(prog_done / prog_total * 10)
    bar        = "█" * bar_filled + "░" * (10 - bar_filled)

    reward_line = f"\n\n{result['reward_msg']}" if result.get("reward_msg") else ""
    next_reward = STREAK_REWARDS.get(next_ms, {}).get("msg", "")
    next_hint   = f"\n🎯 <b>{next_ms - streak}</b> more days → {next_reward[:40]}..." if next_ms - streak > 0 and next_reward else ""

    await answer_fn(
        f"✅ <b>Check-in successful!</b> {fire}\n\n"
        f"🔥 Streak: <b>{streak} days</b>\n"
        f"📊 Total check-ins: <b>{total}</b>\n\n"
        f"<code>[{bar}]</code> {streak}/{next_ms}"
        f"{reward_line}{next_hint}"
    )
