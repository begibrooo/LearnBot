"""
Achievement & Badge System — 100 Badges
────────────────────────────────────────
Badges split into:
  • VISIBLE (10 badges, shown always, ordered by difficulty, first 7 for all users,
    last 3 are hard/special)
  • HIDDEN (90 badges, shown in profile ONLY after earning — surprise discovery)

VIP-exclusive badges: silver/gold border shown in UI.
Top Badgers leaderboard: sorted by badge count, best badge shown.
"""
import logging
import aiosqlite
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from database.db import DB_PATH
from config import settings

router = Router()
logger = logging.getLogger(__name__)

# ─── BADGE DEFINITIONS ────────────────────────────────────────
# Each badge: key → {icon, name, desc, tier, hidden, vip_only, condition_desc}
# tier: 1=easy … 5=legendary

BADGES = {
    # ── VISIBLE (always shown, 10 badges ordered difficulty 1→5) ──────────────
    "newcomer":       {"icon":"🌱","name":"Newcomer",        "desc":"Joined LearnBot",                  "tier":1,"hidden":False,"vip_only":False},
    "first_lesson":   {"icon":"📖","name":"First Lesson",    "desc":"Unlocked your first lesson",       "tier":1,"hidden":False,"vip_only":False},
    "quiz_starter":   {"icon":"🧩","name":"Quiz Starter",    "desc":"Answered 5 quiz questions",        "tier":2,"hidden":False,"vip_only":False},
    "week_warrior":   {"icon":"🔥","name":"Week Warrior",    "desc":"7-day check-in streak",            "tier":2,"hidden":False,"vip_only":False},
    "graduate":       {"icon":"🎓","name":"Graduate",        "desc":"Unlocked 10 lessons",              "tier":3,"hidden":False,"vip_only":False},
    "connector":      {"icon":"👥","name":"Connector",       "desc":"Invited 5 friends",                "tier":3,"hidden":False,"vip_only":False},
    "quiz_master":    {"icon":"🧠","name":"Quiz Master",     "desc":"20 correct quiz answers",          "tier":3,"hidden":False,"vip_only":False},
    "diamond":        {"icon":"💎","name":"Diamond",         "desc":"Unlocked 50 lessons",              "tier":4,"hidden":False,"vip_only":False},
    "champion":       {"icon":"🏆","name":"Champion",        "desc":"Top 3 on the invite leaderboard",  "tier":5,"hidden":False,"vip_only":False},
    "vip_legend":     {"icon":"👑","name":"VIP Legend",      "desc":"Achieved VIP status",              "tier":5,"hidden":False,"vip_only":True},

    # ── HIDDEN — general progression ──────────────────────────────────────────
    "early_bird":     {"icon":"🐦","name":"Early Bird",      "desc":"Checked in before 8am",            "tier":1,"hidden":True,"vip_only":False},
    "night_owl":      {"icon":"🦉","name":"Night Owl",       "desc":"Opened the bot after midnight",    "tier":1,"hidden":True,"vip_only":False},
    "speed_reader":   {"icon":"⚡","name":"Speed Reader",    "desc":"Opened 3 lessons in one day",      "tier":2,"hidden":True,"vip_only":False},
    "bookworm":       {"icon":"📚","name":"Bookworm",        "desc":"Unlocked 25 lessons",              "tier":2,"hidden":True,"vip_only":False},
    "insatiable":     {"icon":"🍽️","name":"Insatiable",     "desc":"Unlocked 100 lessons",             "tier":4,"hidden":True,"vip_only":False},
    "streak_14":      {"icon":"🔥","name":"Fortnight Fire",  "desc":"14-day streak",                    "tier":3,"hidden":True,"vip_only":False},
    "streak_30":      {"icon":"🌋","name":"Volcano",         "desc":"30-day streak",                    "tier":4,"hidden":True,"vip_only":False},
    "streak_100":     {"icon":"☀️","name":"Solar",           "desc":"100-day streak",                   "tier":5,"hidden":True,"vip_only":False},
    "quiz_10":        {"icon":"✅","name":"Quiz Pro",        "desc":"10 correct quiz answers",          "tier":2,"hidden":True,"vip_only":False},
    "quiz_50":        {"icon":"🎯","name":"Sharpshooter",    "desc":"50 correct quiz answers",          "tier":3,"hidden":True,"vip_only":False},
    "quiz_100":       {"icon":"🏹","name":"Archer",          "desc":"100 correct quiz answers",         "tier":4,"hidden":True,"vip_only":False},
    "quiz_perfect5":  {"icon":"⭐","name":"Flawless 5",      "desc":"5 correct in a row without wrong", "tier":3,"hidden":True,"vip_only":False},
    "quiz_perfect10": {"icon":"🌟","name":"Perfect 10",      "desc":"10 correct in a row",              "tier":4,"hidden":True,"vip_only":False},
    "invite_10":      {"icon":"🔗","name":"Network Node",    "desc":"Invited 10 friends",               "tier":2,"hidden":True,"vip_only":False},
    "invite_25":      {"icon":"🕸️","name":"Spider",         "desc":"Invited 25 friends",               "tier":3,"hidden":True,"vip_only":False},
    "invite_50":      {"icon":"🚀","name":"Rocket",          "desc":"Invited 50 friends",               "tier":4,"hidden":True,"vip_only":False},
    "invite_100":     {"icon":"🛸","name":"Warp Speed",      "desc":"Invited 100 friends",              "tier":5,"hidden":True,"vip_only":False},
    "promo_used":     {"icon":"🎟️","name":"Deal Hunter",    "desc":"Used your first promo code",       "tier":1,"hidden":True,"vip_only":False},
    "promo_5":        {"icon":"🛒","name":"Bargain King",    "desc":"Used 5 promo codes",               "tier":2,"hidden":True,"vip_only":False},
    "rated_5":        {"icon":"⭐","name":"Critic",          "desc":"Rated 5 lessons",                  "tier":1,"hidden":True,"vip_only":False},
    "rated_20":       {"icon":"🎬","name":"Director",        "desc":"Rated 20 lessons",                 "tier":2,"hidden":True,"vip_only":False},
    "support_sent":   {"icon":"📩","name":"Helper",          "desc":"Sent a support message",           "tier":1,"hidden":True,"vip_only":False},
    "note_saved":     {"icon":"📝","name":"Notekeeper",      "desc":"Saved your first note",            "tier":1,"hidden":True,"vip_only":False},
    "notes_10":       {"icon":"📔","name":"Journalist",      "desc":"Saved 10 notes",                   "tier":2,"hidden":True,"vip_only":False},
    "pass_earner":    {"icon":"🎫","name":"Pass Earner",     "desc":"Earned your first free pass",      "tier":1,"hidden":True,"vip_only":False},
    "pass_10":        {"icon":"🎟️","name":"Pass Collector", "desc":"Collected 10 free passes",         "tier":2,"hidden":True,"vip_only":False},
    "challenge_done": {"icon":"⚡","name":"Challenger",      "desc":"Completed a daily challenge",      "tier":1,"hidden":True,"vip_only":False},
    "challenge_7":    {"icon":"🗓️","name":"Consistent",     "desc":"Completed 7 daily challenges",     "tier":3,"hidden":True,"vip_only":False},
    "checkin_3":      {"icon":"📅","name":"Regular",         "desc":"3-day check-in streak",            "tier":1,"hidden":True,"vip_only":False},
    "checkin_50":     {"icon":"🗝️","name":"Keymaster",      "desc":"50 total check-ins",               "tier":3,"hidden":True,"vip_only":False},
    "checkin_200":    {"icon":"🏛️","name":"Pillar",         "desc":"200 total check-ins",              "tier":5,"hidden":True,"vip_only":False},
    "first_quiz":     {"icon":"🎲","name":"Roll the Dice",   "desc":"Answered your first quiz",         "tier":1,"hidden":True,"vip_only":False},
    "search_used":    {"icon":"🔍","name":"Explorer",        "desc":"Used the lesson search",           "tier":1,"hidden":True,"vip_only":False},
    "badge_5":        {"icon":"🥉","name":"Badge Bronze",    "desc":"Earned 5 badges",                  "tier":2,"hidden":True,"vip_only":False},
    "badge_15":       {"icon":"🥈","name":"Badge Silver",    "desc":"Earned 15 badges",                 "tier":3,"hidden":True,"vip_only":False},
    "badge_30":       {"icon":"🥇","name":"Badge Gold",      "desc":"Earned 30 badges",                 "tier":4,"hidden":True,"vip_only":False},
    "badge_50":       {"icon":"🏅","name":"Badge Master",    "desc":"Earned 50 badges",                 "tier":5,"hidden":True,"vip_only":False},

    # ── HIDDEN — VIP / Premium ─────────────────────────────────────────────────
    "vip_first":      {"icon":"👑","name":"VIP Initiate",    "desc":"First VIP lesson opened",          "tier":3,"hidden":True,"vip_only":True},
    "vip_5":          {"icon":"💫","name":"VIP Scholar",     "desc":"5 VIP lessons opened",             "tier":3,"hidden":True,"vip_only":True},
    "vip_20":         {"icon":"✨","name":"VIP Master",      "desc":"20 VIP lessons opened",            "tier":4,"hidden":True,"vip_only":True},
    "vip_all":        {"icon":"🌠","name":"VIP Completionist","desc":"All VIP lessons unlocked",        "tier":5,"hidden":True,"vip_only":True},

    # ── HIDDEN — Social / Fun ──────────────────────────────────────────────────
    "lonely_start":   {"icon":"🌅","name":"First Light",     "desc":"Used the bot for 30 days",         "tier":2,"hidden":True,"vip_only":False},
    "social_10":      {"icon":"🤝","name":"Handshaker",      "desc":"10 friends used your invite link", "tier":2,"hidden":True,"vip_only":False},
    "top_1":          {"icon":"🥇","name":"Legend #1",       "desc":"Reached #1 on leaderboard",        "tier":5,"hidden":True,"vip_only":False},
    "top_10":         {"icon":"🏅","name":"Top 10",          "desc":"Reached top 10 on leaderboard",    "tier":3,"hidden":True,"vip_only":False},
    "comeback":       {"icon":"🔄","name":"Comeback Kid",    "desc":"Returned after 7 days away",       "tier":2,"hidden":True,"vip_only":False},
    "marathon":       {"icon":"🏃","name":"Marathon",        "desc":"Used bot for 90 consecutive days", "tier":5,"hidden":True,"vip_only":False},
    "multi_cat":      {"icon":"🗂️","name":"Multitasker",    "desc":"Unlocked lessons in 3 categories", "tier":2,"hidden":True,"vip_only":False},
    "all_free":       {"icon":"🎁","name":"Free Seeker",     "desc":"Opened all free lessons",          "tier":3,"hidden":True,"vip_only":False},
    "level_clear":    {"icon":"🎮","name":"Level Clear",     "desc":"Unlocked all lessons in a level",  "tier":3,"hidden":True,"vip_only":False},
    "cat_master":     {"icon":"🗺️","name":"Category Master","desc":"Unlocked all lessons in a category","tier":4,"hidden":True,"vip_only":False},
    "midnight_quiz":  {"icon":"🌙","name":"Night Quiz",      "desc":"Answered a quiz at midnight",      "tier":2,"hidden":True,"vip_only":False},
    "weekend_hero":   {"icon":"🎉","name":"Weekend Hero",    "desc":"Checked in on 4 weekends",         "tier":2,"hidden":True,"vip_only":False},
    "monday_start":   {"icon":"💼","name":"Monday Grind",    "desc":"Checked in every Monday for a month","tier":3,"hidden":True,"vip_only":False},
    "daily_learner":  {"icon":"📆","name":"Daily Learner",   "desc":"Opened a lesson every day for 7 days","tier":3,"hidden":True,"vip_only":False},
    "review_king":    {"icon":"👁️","name":"Review King",    "desc":"Reviewed 30 lessons",              "tier":3,"hidden":True,"vip_only":False},
    "answer_all":     {"icon":"🗂️","name":"Answer All",     "desc":"Answered every available quiz",    "tier":4,"hidden":True,"vip_only":False},
    "perfect_week":   {"icon":"🌈","name":"Perfect Week",    "desc":"Check-in, quiz, lesson every day for 7 days","tier":4,"hidden":True,"vip_only":False},
    "silent_scholar": {"icon":"🤫","name":"Silent Scholar",  "desc":"No wrong quiz answers in a week",  "tier":3,"hidden":True,"vip_only":False},
    "speed_5":        {"icon":"🏎️","name":"Speed 5",        "desc":"Completed 5 lessons in one day",   "tier":3,"hidden":True,"vip_only":False},
    "deep_dive":      {"icon":"🤿","name":"Deep Dive",       "desc":"Spent 30+ days on one category",   "tier":3,"hidden":True,"vip_only":False},
    "curiosity":      {"icon":"🔭","name":"Curious Mind",    "desc":"Opened 3 different categories",    "tier":2,"hidden":True,"vip_only":False},
    "centurion":      {"icon":"💯","name":"Centurion",       "desc":"100 total quiz answers",           "tier":3,"hidden":True,"vip_only":False},
    "double_century": {"icon":"2️⃣","name":"Double Century","desc":"200 total quiz answers",            "tier":4,"hidden":True,"vip_only":False},
    "quiz_streak_3":  {"icon":"3️⃣","name":"Hat Trick",      "desc":"3 correct quiz answers in a row",  "tier":1,"hidden":True,"vip_only":False},
    "quiz_streak_7":  {"icon":"7️⃣","name":"Lucky Seven",    "desc":"7 correct quiz answers in a row",  "tier":3,"hidden":True,"vip_only":False},
    "free_pass_used": {"icon":"🎫","name":"Free Spirit",     "desc":"Used your first free pass",        "tier":1,"hidden":True,"vip_only":False},
    "free_pass_10":   {"icon":"🎪","name":"Passmaster",      "desc":"Used 10 free passes",              "tier":2,"hidden":True,"vip_only":False},
    "first_checkin":  {"icon":"✅","name":"First Step",      "desc":"First ever check-in",              "tier":1,"hidden":True,"vip_only":False},
    "referral_first": {"icon":"👋","name":"Recruiter",       "desc":"Invited your first friend",        "tier":1,"hidden":True,"vip_only":False},
    "secret_1":       {"icon":"🔐","name":"???",             "desc":"???",                              "tier":5,"hidden":True,"vip_only":False},
    "secret_2":       {"icon":"🔐","name":"???",             "desc":"???",                              "tier":5,"hidden":True,"vip_only":False},
    "secret_3":       {"icon":"🔐","name":"???",             "desc":"???",                              "tier":5,"hidden":True,"vip_only":False},

    # ── HIDDEN — Tier 5 Legendary (very hard) ──────────────────────────────────
    "the_one":        {"icon":"🌌","name":"The One",         "desc":"Earned 75+ badges",                "tier":5,"hidden":True,"vip_only":False},
    "completionist":  {"icon":"🎖️","name":"Completionist",  "desc":"Earned ALL non-secret badges",     "tier":5,"hidden":True,"vip_only":False},
    "year_one":       {"icon":"🎂","name":"Year One",        "desc":"Used LearnBot for 365 days",       "tier":5,"hidden":True,"vip_only":False},
    "leaderboard_god":{"icon":"⚡","name":"Leaderboard God", "desc":"#1 on leaderboard for 4 weeks",    "tier":5,"hidden":True,"vip_only":False},
    "perfect_month":  {"icon":"🌙","name":"Perfect Month",   "desc":"Completed every challenge in a month","tier":5,"hidden":True,"vip_only":False},
    "quiz_god":       {"icon":"🧬","name":"Quiz God",        "desc":"500 correct quiz answers",         "tier":5,"hidden":True,"vip_only":False},
    "ultimate_inviter":{"icon":"🌐","name":"Global Reach",   "desc":"Invited 500 friends",              "tier":5,"hidden":True,"vip_only":False},
    "all_categories": {"icon":"🏰","name":"Grand Master",    "desc":"Completed all available categories","tier":5,"hidden":True,"vip_only":False},
    "unstoppable":    {"icon":"🦾","name":"Unstoppable",     "desc":"365-day streak",                   "tier":5,"hidden":True,"vip_only":False},
    "the_legend":     {"icon":"🌠","name":"The Legend",      "desc":"All badges earned",                "tier":5,"hidden":True,"vip_only":False},
}

VISIBLE_BADGES = [k for k, v in BADGES.items() if not v["hidden"]]
TIER_COLORS = {1:"⬜",2:"🟩",3:"🟦",4:"🟪",5:"🔶"}  # visual tier indicator


# ─── DB ───────────────────────────────────────────────────────

async def _ensure_table():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_badges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                badge_key TEXT NOT NULL,
                earned_at TEXT DEFAULT (datetime('now')),
                UNIQUE(user_id, badge_key)
            )
        """)
        await db.commit()


async def get_user_badges(tg_id: int) -> list[str]:
    await _ensure_table()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT badge_key FROM user_badges WHERE user_id=? ORDER BY earned_at", (tg_id,)
        ) as cur:
            return [r["badge_key"] for r in await cur.fetchall()]


async def award_badge(tg_id: int, badge_key: str, bot: Bot) -> bool:
    """Award badge, notify user. Returns True if newly awarded."""
    if badge_key not in BADGES:
        return False
    await _ensure_table()
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO user_badges (user_id, badge_key) VALUES (?,?)",
                (tg_id, badge_key)
            )
            await db.commit()
        except Exception:
            return False

    badge = BADGES[badge_key]
    icon  = badge["icon"]
    name  = badge["name"]
    desc  = badge["desc"]
    tier  = badge["tier"]
    tier_label = ["","Common","Uncommon","Rare","Epic","Legendary"][tier]
    # Don't spoil secret badges
    if name == "???":
        name = "Secret Badge"
        desc = "You discovered a secret!"

    try:
        await bot.send_message(
            tg_id,
            f"🏅 <b>New Badge!</b>\n\n"
            f"{TIER_COLORS[tier]} <b>{tier_label}</b>\n"
            f"{icon} <b>{name}</b>\n"
            f"<i>{desc}</i>\n\n"
            f"Check all your badges: /badges"
        )
    except Exception:
        pass

    # Check badge-count badges recursively (avoid infinite loop)
    if badge_key not in ("badge_5","badge_15","badge_30","badge_50","the_one","completionist","the_legend"):
        badges_now = await get_user_badges(tg_id)
        count = len(badges_now)
        for threshold, key in [(5,"badge_5"),(15,"badge_15"),(30,"badge_30"),(50,"badge_50"),(75,"the_one")]:
            if count >= threshold:
                await award_badge(tg_id, key, bot)
    return True


async def check_and_award(tg_id: int, bot: Bot):
    """Check all conditions and award any newly earned badges."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE tg_id=?", (tg_id,)) as cur:
            user = await cur.fetchone()
        if not user:
            return
        user = dict(user)

        async with db.execute("SELECT COUNT(*) as c FROM user_lessons WHERE user_id=?", (tg_id,)) as cur:
            lessons = (await cur.fetchone())["c"]
        async with db.execute("SELECT COUNT(*) as c, SUM(is_correct) as corr FROM quiz_answers WHERE user_id=?", (tg_id,)) as cur:
            qrow = await cur.fetchone()
        async with db.execute("SELECT COUNT(*) as c FROM lesson_ratings WHERE user_id=?", (tg_id,)) as cur:
            ratings = (await cur.fetchone())["c"]
        async with db.execute("SELECT COUNT(DISTINCT level_id) as c FROM user_lessons ul JOIN lessons l ON l.id=ul.lesson_id WHERE ul.user_id=?", (tg_id,)) as cur:
            levels_touched = (await cur.fetchone())["c"]

    quiz_total   = qrow["c"] or 0
    quiz_correct = int(qrow["corr"] or 0)
    streak       = user.get("streak_days") or 0
    total_ci     = user.get("total_checkins") or 0
    invites      = user.get("invites_count") or 0
    is_vip       = bool(user.get("is_vip"))
    vip_used     = user.get("vip_lessons_used") or 0

    # Core visible badges
    await award_badge(tg_id, "newcomer", bot)
    if lessons >= 1:   await award_badge(tg_id, "first_lesson", bot)
    if quiz_total >= 5: await award_badge(tg_id, "quiz_starter", bot)
    if streak >= 7:    await award_badge(tg_id, "week_warrior", bot)
    if lessons >= 10:  await award_badge(tg_id, "graduate", bot)
    if invites >= 5:   await award_badge(tg_id, "connector", bot)
    if quiz_correct >= 20: await award_badge(tg_id, "quiz_master", bot)
    if lessons >= 50:  await award_badge(tg_id, "diamond", bot)
    if is_vip:         await award_badge(tg_id, "vip_legend", bot)

    # Hidden — lessons
    if lessons >= 25:  await award_badge(tg_id, "bookworm", bot)
    if lessons >= 100: await award_badge(tg_id, "insatiable", bot)

    # Hidden — streaks
    if streak >= 3:    await award_badge(tg_id, "checkin_3", bot)
    if streak >= 14:   await award_badge(tg_id, "streak_14", bot)
    if streak >= 30:   await award_badge(tg_id, "streak_30", bot)
    if streak >= 100:  await award_badge(tg_id, "streak_100", bot)
    if total_ci >= 1:  await award_badge(tg_id, "first_checkin", bot)
    if total_ci >= 50: await award_badge(tg_id, "checkin_50", bot)
    if total_ci >= 200: await award_badge(tg_id, "checkin_200", bot)

    # Hidden — quiz
    if quiz_total >= 1:   await award_badge(tg_id, "first_quiz", bot)
    if quiz_correct >= 10: await award_badge(tg_id, "quiz_10", bot)
    if quiz_correct >= 50: await award_badge(tg_id, "quiz_50", bot)
    if quiz_correct >= 100: await award_badge(tg_id, "quiz_100", bot)
    if quiz_correct >= 500: await award_badge(tg_id, "quiz_god", bot)
    if quiz_total >= 100:  await award_badge(tg_id, "centurion", bot)
    if quiz_total >= 200:  await award_badge(tg_id, "double_century", bot)

    # Hidden — invites
    if invites >= 1:   await award_badge(tg_id, "referral_first", bot)
    if invites >= 10:  await award_badge(tg_id, "invite_10", bot)
    if invites >= 25:  await award_badge(tg_id, "invite_25", bot)
    if invites >= 50:  await award_badge(tg_id, "invite_50", bot)
    if invites >= 100: await award_badge(tg_id, "invite_100", bot)
    if invites >= 500: await award_badge(tg_id, "ultimate_inviter", bot)

    # Hidden — ratings
    if ratings >= 5:  await award_badge(tg_id, "rated_5", bot)
    if ratings >= 20: await award_badge(tg_id, "rated_20", bot)
    if ratings >= 30: await award_badge(tg_id, "review_king", bot)

    # Hidden — categories/levels
    if levels_touched >= 3: await award_badge(tg_id, "curiosity", bot)

    # VIP hidden
    if is_vip and vip_used >= 1:  await award_badge(tg_id, "vip_first", bot)
    if is_vip and vip_used >= 5:  await award_badge(tg_id, "vip_5", bot)
    if is_vip and vip_used >= 20: await award_badge(tg_id, "vip_20", bot)

    # Social/leaderboard
    leaderboard = await _get_leaderboard_rank(tg_id)
    if leaderboard <= 3:  await award_badge(tg_id, "champion", bot)
    if leaderboard == 1:  await award_badge(tg_id, "top_1", bot)
    if leaderboard <= 10: await award_badge(tg_id, "top_10", bot)


async def _get_leaderboard_rank(tg_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT COUNT(*)+1 as rank FROM users WHERE invites_count > "
            "(SELECT invites_count FROM users WHERE tg_id=?)", (tg_id,)
        ) as cur:
            row = await cur.fetchone()
            return row["rank"] if row else 9999


# ─── Leaderboard ──────────────────────────────────────────────

async def get_top_badgers(limit: int = 10) -> list[dict]:
    """Return top users by badge count, with their best badge."""
    await _ensure_table()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT ub.user_id, COUNT(ub.badge_key) as badge_count,
               u.full_name, u.username,
               GROUP_CONCAT(ub.badge_key) as all_badges
               FROM user_badges ub
               JOIN users u ON u.tg_id = ub.user_id
               GROUP BY ub.user_id
               ORDER BY badge_count DESC
               LIMIT ?""",
            (limit,)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    result = []
    for r in rows:
        # Find best badge (highest tier)
        keys   = r["all_badges"].split(",") if r["all_badges"] else []
        best   = max(keys, key=lambda k: BADGES.get(k, {}).get("tier", 0), default=None)
        b_info = BADGES.get(best, {}) if best else {}
        result.append({
            "user_id":    r["user_id"],
            "full_name":  r["full_name"] or "Unknown",
            "username":   r["username"],
            "badge_count":r["badge_count"],
            "best_badge": best,
            "best_icon":  b_info.get("icon","🏅"),
            "best_name":  b_info.get("name","—"),
            "best_tier":  b_info.get("tier",1),
        })
    return result


# ─── Handlers ─────────────────────────────────────────────────

@router.message(Command("badges"))
@router.message(F.text == "🏅 Badges")
async def show_badges(message: Message, bot: Bot = None):
    tg_id  = message.from_user.id
    if bot:
        await check_and_award(tg_id, bot)
    earned = set(await get_user_badges(tg_id))
    total_all = len(BADGES)
    count     = len(earned)

    # Section 1: Visible badges (always shown, sorted by tier)
    visible_lines = []
    for key in VISIBLE_BADGES:
        b = BADGES[key]
        if key in earned:
            tier_dot = TIER_COLORS[b["tier"]]
            vip_tag  = " 👑" if b["vip_only"] else ""
            visible_lines.append(f"{b['icon']} <b>{b['name']}</b>{vip_tag} {tier_dot}")
        else:
            visible_lines.append(f"🔒 <i>{b['name']}</i>")

    # Section 2: Earned hidden badges
    earned_hidden = [k for k in earned if BADGES.get(k,{}).get("hidden")]
    hidden_lines  = []
    for key in earned_hidden:
        b = BADGES.get(key,{})
        if b.get("name") == "???":
            hidden_lines.append(f"🔐 <b>Secret Badge</b>")
        else:
            tier_dot = TIER_COLORS.get(b.get("tier",1),"")
            hidden_lines.append(f"{b.get('icon','🏅')} <b>{b.get('name','')}</b> {tier_dot}")

    text = (
        f"🏅 <b>My Badges</b>  {count}/{total_all}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Achievements</b>\n" +
        "\n".join(visible_lines)
    )
    if hidden_lines:
        text += f"\n\n<b>Discovered ({len(earned_hidden)} hidden)</b>\n" + "\n".join(hidden_lines)
    else:
        text += f"\n\n<i>🔍 {total_all - len(VISIBLE_BADGES)} hidden badges to discover...</i>"

    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🏆 Top Badgers", callback_data="badges:top"),
        ]])
    )


@router.callback_query(F.data == "badges:top")
async def show_top_badgers(call: CallbackQuery):
    top = await get_top_badgers(10)
    if not top:
        await call.answer("No badge data yet.", show_alert=True)
        return

    medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    text   = "🏆 <b>Top Badgers</b>\n━━━━━━━━━━━━━━━━━━\n\n"

    for i, u in enumerate(top):
        medal    = medals[i] if i < len(medals) else f"{i+1}."
        name     = u["full_name"][:18]
        uname    = f"@{u['username']}" if u.get("username") else ""
        b_icon   = u["best_icon"]
        b_name   = u["best_name"]
        tier_dot = TIER_COLORS.get(u["best_tier"], "")
        text += (
            f"{medal} <b>{name}</b> {uname}\n"
            f"   {b_icon} <i>{b_name}</i> {tier_dot}  —  <b>{u['badge_count']}</b> badges\n\n"
        )

    await call.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ My Badges", callback_data="badges:mine"),
        ]])
    )
    await call.answer()


@router.callback_query(F.data == "badges:mine")
async def back_to_my_badges(call: CallbackQuery, bot: Bot):
    # Re-trigger show_badges as a message
    await call.answer()
    earned = set(await get_user_badges(call.from_user.id))
    count  = len(earned)
    total  = len(BADGES)
    visible_lines = []
    for key in VISIBLE_BADGES:
        b = BADGES[key]
        if key in earned:
            tier_dot = TIER_COLORS[b["tier"]]
            vip_tag  = " 👑" if b["vip_only"] else ""
            visible_lines.append(f"{b['icon']} <b>{b['name']}</b>{vip_tag} {tier_dot}")
        else:
            visible_lines.append(f"🔒 <i>{b['name']}</i>")
    earned_hidden = [k for k in earned if BADGES.get(k,{}).get("hidden")]
    hidden_lines  = [
        f"🔐 <b>Secret Badge</b>" if BADGES.get(k,{}).get("name") == "???"
        else f"{BADGES.get(k,{}).get('icon','🏅')} <b>{BADGES.get(k,{}).get('name','')}</b>"
        for k in earned_hidden
    ]
    text = (
        f"🏅 <b>My Badges</b>  {count}/{total}\n━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Achievements</b>\n" + "\n".join(visible_lines)
    )
    if hidden_lines:
        text += f"\n\n<b>Discovered ({len(earned_hidden)} hidden)</b>\n" + "\n".join(hidden_lines)
    else:
        text += f"\n\n<i>🔍 {total - len(VISIBLE_BADGES)} hidden badges to discover...</i>"
    await call.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🏆 Top Badgers", callback_data="badges:top"),
        ]])
    )
