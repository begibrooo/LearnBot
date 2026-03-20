"""
User Stats & Progress Dashboard
/stats   — full personal stats card
/help    — show all available commands
/top     — leaderboard shortcut
"""
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database.users import get_user, get_leaderboard
from database.content import get_user_unlocked_lessons, get_categories, get_lessons, get_levels
from handlers.checkin import get_streak
import aiosqlite
from database.db import DB_PATH

router = Router()


async def get_quiz_stats(tg_id: int) -> dict:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT COUNT(*) as total, SUM(is_correct) as correct "
                "FROM quiz_answers WHERE user_id=?", (tg_id,)
            ) as cur:
                row = await cur.fetchone()
            return {"total": row["total"] or 0, "correct": int(row["correct"] or 0)}
    except Exception:
        return {"total": 0, "correct": 0}


async def get_total_lessons() -> int:
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT COUNT(*) as c FROM lessons") as cur:
                return (await cur.fetchone())["c"]
    except Exception:
        return 0


def _progress_bar(done: int, total: int, width: int = 10) -> str:
    if total == 0:
        return "░" * width + " 0%"
    pct     = done / total
    filled  = int(pct * width)
    bar     = "█" * filled + "░" * (width - filled)
    return f"{bar} {int(pct * 100)}%"


@router.message(Command("stats"))
@router.message(F.text == "📊 My Stats")
async def user_stats(message: Message):
    uid      = message.from_user.id
    user     = await get_user(uid)
    if not user:
        await message.answer("User not found.")
        return

    unlocked     = await get_user_unlocked_lessons(uid)
    total_lessons = await get_total_lessons()
    streak_data  = await get_streak(uid)
    quiz_data    = await get_quiz_stats(uid)
    streak       = streak_data.get("streak_days") or 0
    total_ci     = streak_data.get("total_checkins") or 0
    quiz_total   = quiz_data["total"]
    quiz_correct = quiz_data["correct"]
    quiz_pct     = int(quiz_correct / quiz_total * 100) if quiz_total else 0

    lesson_bar   = _progress_bar(len(unlocked), total_lessons)
    vip_badge    = "👑 VIP" if user.get("is_vip") else "🆓 Free"

    fire = "🔥" * min(streak // 7 + 1, 5) if streak else ""

    await message.answer(
        f"📊 <b>My Learning Stats</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>{user.get('full_name') or 'User'}</b>  {vip_badge}\n\n"
        f"📖 <b>Lessons</b>\n"
        f"   Unlocked: <b>{len(unlocked)}</b> / {total_lessons}\n"
        f"   <code>{lesson_bar}</code>\n\n"
        f"🔥 <b>Streak</b>\n"
        f"   Current: <b>{streak} days</b> {fire}\n"
        f"   Total check-ins: <b>{total_ci}</b>\n\n"
        f"🧠 <b>Quiz</b>\n"
        f"   Answered: <b>{quiz_total}</b>\n"
        f"   Correct: <b>{quiz_correct}</b> ({quiz_pct}%)\n\n"
        f"🎫 <b>Free Passes:</b> {user.get('free_passes', 0)}\n"
        f"👥 <b>Invites:</b> {user.get('invites_count', 0)}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )


@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "📋 <b>Available Commands</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "<b>📚 Learning</b>\n"
        "/start — main menu\n"
        "/checkin — daily check-in & streak\n"
        "/quiz — get a random quiz question\n"
        "/stats — your full learning stats\n\n"
        "<b>📝 Notes</b>\n"
        "/note &lt;text&gt; — save a note\n"
        "/notes — view your notes\n"
        "/clearnotes — delete all notes\n\n"
        "<b>🏆 Social</b>\n"
        "/top — invite leaderboard\n\n"
        "<b>⚙️ Admin only</b>\n"
        "/admin — admin panel\n"
        "/action_msg — create styled broadcast\n"
        "/test_friday — test Friday reward\n"
        "/fix_channels — repair channel links\n"
        "/readd_channel — fix a channel's invite link\n"
        "/add_quiz — add a quiz question\n"
        "/list_quizzes — list all quizzes\n"
        "/del_quiz &lt;id&gt; — delete a quiz\n"
        "━━━━━━━━━━━━━━━━━━"
    )


@router.message(Command("top"))
async def top_cmd(message: Message):
    top = await get_leaderboard(10)
    if not top:
        await message.answer("🏆 No data yet.")
        return
    medals = ["🥇", "🥈", "🥉"]
    text = "🏆 <b>Top Inviters</b>\n━━━━━━━━━━━━━━━━━━\n"
    for i, u in enumerate(top):
        medal = medals[i] if i < 3 else f"{i+1}."
        name  = u.get("full_name") or "Anonymous"
        text += f"{medal} <b>{name}</b> — {u.get('invites_count', 0)} invites\n"
    await message.answer(text)


@router.message(F.text == "⭐ Top Lessons")
@router.message(Command("top_lessons"))
async def top_lessons(message: Message):
    from handlers.feedback import get_top_rated_lessons
    top = await get_top_rated_lessons(5)
    if not top:
        await message.answer("📭 No lesson ratings yet. Open some lessons and rate them!")
        return
    text = "⭐ <b>Top Rated Lessons</b>\n━━━━━━━━━━━━━━━━━━\n\n"
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i, l in enumerate(top):
        stars = "⭐" * round(l["avg_rating"])
        text += f"{medals[i]} <b>{l['title']}</b>\n   {stars} {l['avg_rating']}/5  ({l['votes']} votes)\n\n"
    await message.answer(text)
