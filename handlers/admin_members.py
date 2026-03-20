"""
Admin Members Panel
─────────────────────────────────────────────
Full member browser with search, filters, 
export, and bulk actions. Accessible via
the Admin Panel → 👥 Users → 📋 All Users.
"""
import logging
import aiosqlite
from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import settings
from database.db import DB_PATH
from database.users import get_user, add_free_pass, update_user, revoke_vip
from keyboards.admin import back_admin_kb
from keyboards.user import cancel_kb

router = Router()
logger = logging.getLogger(__name__)
PER_PAGE = 8


def is_admin(uid): return uid in settings.admin_id_list


# ─── DB helpers ───────────────────────────────────────────────

async def search_users(query: str, page: int = 0) -> tuple[list, int]:
    q = f"%{query}%"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT COUNT(*) as c FROM users "
            "WHERE full_name LIKE ? OR username LIKE ? OR tg_id LIKE ?",
            (q, q, q)
        ) as cur:
            total = (await cur.fetchone())["c"]
        async with db.execute(
            "SELECT tg_id, full_name, username, is_vip, is_banned, "
            "free_passes, invites_count, created_at, last_seen "
            "FROM users WHERE full_name LIKE ? OR username LIKE ? OR tg_id LIKE ? "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (q, q, q, PER_PAGE, page * PER_PAGE)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    return rows, total


async def get_members_page(
    page: int, filter_type: str = "all"
) -> tuple[list, int]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        where = {
            "all":    "",
            "vip":    "WHERE is_vip=1",
            "banned": "WHERE is_banned=1",
            "active": "WHERE is_banned=0",
            "new":    "WHERE date(created_at) = date('now')",
        }.get(filter_type, "")
        async with db.execute(f"SELECT COUNT(*) as c FROM users {where}") as cur:
            total = (await cur.fetchone())["c"]
        async with db.execute(
            f"SELECT tg_id, full_name, username, is_vip, is_banned, "
            f"free_passes, invites_count, streak_days, created_at, last_seen "
            f"FROM users {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (PER_PAGE, page * PER_PAGE)
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    return rows, total


async def get_user_activity_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) as c FROM users WHERE date(last_seen)=date('now')") as cur:
            active_today = (await cur.fetchone())["c"]
        async with db.execute("SELECT COUNT(*) as c FROM users WHERE date(last_seen)>=date('now','-7 days')") as cur:
            active_week = (await cur.fetchone())["c"]
        async with db.execute("SELECT COUNT(*) as c FROM users WHERE streak_days>=7") as cur:
            streak_7 = (await cur.fetchone())["c"]
        async with db.execute("SELECT AVG(invites_count) as avg FROM users") as cur:
            avg_inv = round((await cur.fetchone())["avg"] or 0, 1)
        async with db.execute("SELECT COUNT(*) as c FROM user_lessons") as cur:
            total_unlocks = (await cur.fetchone())["c"]
    return {
        "active_today": active_today,
        "active_week":  active_week,
        "streak_7":     streak_7,
        "avg_invites":  avg_inv,
        "total_unlocks": total_unlocks,
    }


# ─── Keyboards ────────────────────────────────────────────────

FILTERS = [
    ("👥 All",    "all"),
    ("👑 VIP",    "vip"),
    ("🚫 Banned", "banned"),
    ("✅ Active", "active"),
    ("🆕 Today",  "new"),
]


def members_filter_kb(current: str) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text=f"{'●' if c == current else '○'} {label}",
            callback_data=f"mbr:filter:{c}:0"
        )
        for label, c in FILTERS
    ]


def members_list_kb(
    users: list, page: int, total: int, filter_type: str
) -> InlineKeyboardMarkup:
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    rows = []

    # Filter bar
    rows.append(members_filter_kb(filter_type))

    # User rows
    for u in users:
        name  = (u.get("full_name") or "Unknown")[:22]
        badge = ("👑" if u.get("is_vip") else "") + ("🚫" if u.get("is_banned") else "")
        rows.append([InlineKeyboardButton(
            text=f"{badge} {name}  ({u['tg_id']})",
            callback_data=f"mbr:card:{u['tg_id']}:{filter_type}:{page}"
        )])

    # Pagination
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"mbr:filter:{filter_type}:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"mbr:filter:{filter_type}:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([
        InlineKeyboardButton(text="🔍 Search", callback_data="mbr:search"),
        InlineKeyboardButton(text="📊 Activity", callback_data="mbr:activity"),
    ])
    rows.append([InlineKeyboardButton(text="◀️ Back", callback_data="adm:users")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def member_card_kb(uid: int, is_vip: bool, is_banned: bool, back_filter: str, back_page: int) -> InlineKeyboardMarkup:
    back_cb = f"mbr:filter:{back_filter}:{back_page}"
    rows = []
    if is_vip:
        rows.append([InlineKeyboardButton(text="❌ Revoke VIP",   callback_data=f"mbr:act:revoke_vip:{uid}")])
    else:
        rows.append([InlineKeyboardButton(text="👑 Grant VIP (10 lessons)", callback_data=f"mbr:act:grant_vip:{uid}")])
    rows.append([
        InlineKeyboardButton(text="🎫 +1 Pass",   callback_data=f"mbr:act:pass1:{uid}"),
        InlineKeyboardButton(text="🎫 +5 Passes", callback_data=f"mbr:act:pass5:{uid}"),
    ])
    if is_banned:
        rows.append([InlineKeyboardButton(text="✅ Unban",  callback_data=f"mbr:act:unban:{uid}")])
    else:
        rows.append([InlineKeyboardButton(text="🚫 Ban",    callback_data=f"mbr:act:ban:{uid}")])
    rows.append([InlineKeyboardButton(text="💬 Send Message", callback_data=f"mbr:act:msg:{uid}")])
    rows.append([InlineKeyboardButton(text="◀️ Back to list", callback_data=back_cb)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── Handlers ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("mbr:filter:"))
async def members_list(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    _, _, filter_type, page_str = call.data.split(":")
    page  = int(page_str)
    users, total = await get_members_page(page, filter_type)
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)

    label = next((l for l, c in FILTERS if c == filter_type), "All")
    text  = (
        f"👥 <b>Members — {label}</b>  "
        f"({total} total, page {page+1}/{pages})\n\n"
        f"Tap a name to open their profile."
    )
    await call.message.edit_text(text, reply_markup=members_list_kb(users, page, total, filter_type))
    await call.answer()


@router.callback_query(F.data.startswith("mbr:card:"))
async def member_card(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    parts       = call.data.split(":")
    uid         = int(parts[2])
    back_filter = parts[3] if len(parts) > 3 else "all"
    back_page   = int(parts[4]) if len(parts) > 4 else 0

    user = await get_user(uid)
    if not user:
        await call.answer("User not found.", show_alert=True); return

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT COUNT(*) as c FROM user_lessons WHERE user_id=?", (uid,)
        ) as cur:
            lessons = (await cur.fetchone())["c"]
        async with db.execute(
            "SELECT COUNT(*) as c, SUM(is_correct) as correct FROM quiz_answers WHERE user_id=?", (uid,)
        ) as cur:
            qrow = await cur.fetchone()
        async with db.execute(
            "SELECT COUNT(*) as c FROM lesson_ratings WHERE user_id=?", (uid,)
        ) as cur:
            ratings = (await cur.fetchone())["c"]

    quiz_total   = qrow["c"] or 0
    quiz_correct = int(qrow["correct"] or 0)
    quiz_pct     = f"{int(quiz_correct/quiz_total*100)}%" if quiz_total else "—"
    vip_info     = "👑 VIP" if user.get("is_vip") else "🆓 Free"
    if user.get("is_vip"):
        limit = user.get("vip_lesson_limit") or 0
        used  = user.get("vip_lessons_used") or 0
        vip_info += f" ({used}/{limit if limit else '∞'} VIP lessons)"
    uname  = f"@{user['username']}" if user.get("username") else "—"
    streak = user.get("streak_days") or 0
    fire   = "🔥" * min(streak // 7 + 1, 5) if streak else ""

    await call.message.edit_text(
        f"👤 <b>Member Profile</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Name:     <b>{user.get('full_name') or '—'}</b>\n"
        f"Username: {uname}\n"
        f"ID:       <code>{uid}</code>\n"
        f"Status:   {vip_info}\n"
        f"Account:  {'🚫 Banned' if user.get('is_banned') else '✅ Active'}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📖 Lessons:    <b>{lessons}</b>\n"
        f"🎫 Passes:     <b>{user.get('free_passes', 0)}</b>\n"
        f"👥 Invites:    <b>{user.get('invites_count', 0)}</b>\n"
        f"🔥 Streak:     <b>{streak} days</b> {fire}\n"
        f"🧠 Quiz:       <b>{quiz_correct}/{quiz_total}</b> correct ({quiz_pct})\n"
        f"⭐ Ratings:    <b>{ratings}</b> given\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📅 Joined:  <i>{str(user.get('created_at',''))[:10]}</i>\n"
        f"🕐 Seen:    <i>{str(user.get('last_seen',''))[:10]}</i>",
        reply_markup=member_card_kb(uid, bool(user.get("is_vip")), bool(user.get("is_banned")), back_filter, back_page)
    )
    await call.answer()


# ─── Quick actions ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("mbr:act:"))
async def member_action(call: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(call.from_user.id): return
    parts  = call.data.split(":")
    action = parts[2]
    uid    = int(parts[3])

    if action == "pass1":
        await add_free_pass(uid, 1)
        await call.answer("✅ +1 Free Pass given.", show_alert=True)
        try: await bot.send_message(uid, "🎫 You received <b>1 Free Pass</b> from an admin!")
        except Exception: pass

    elif action == "pass5":
        await add_free_pass(uid, 5)
        await call.answer("✅ +5 Free Passes given.", show_alert=True)
        try: await bot.send_message(uid, "🎫 You received <b>5 Free Passes</b> from an admin! 🎉")
        except Exception: pass

    elif action == "ban":
        await update_user(uid, is_banned=1)
        await call.answer("🚫 Banned.", show_alert=True)

    elif action == "unban":
        await update_user(uid, is_banned=0)
        await call.answer("✅ Unbanned.", show_alert=True)

    elif action == "revoke_vip":
        await revoke_vip(uid, reason="admin_revoked", revoked_by=call.from_user.id)
        await call.answer("✅ VIP revoked.", show_alert=True)
        try: await bot.send_message(uid, "ℹ️ Your <b>VIP access</b> has been removed by an admin.")
        except Exception: pass

    elif action == "grant_vip":
        from database.users import grant_vip
        await grant_vip(uid, lesson_limit=10, granted_by=call.from_user.id, reason="admin_quick_grant")
        await call.answer("👑 VIP (10 lessons) granted.", show_alert=True)
        try: await bot.send_message(uid, "👑 <b>VIP access granted!</b>\n\n🎓 You get <b>10 VIP lessons</b>. Enjoy!")
        except Exception: pass

    elif action == "msg":
        await state.set_state(MemberMsgState.waiting_text)
        await state.update_data(msg_target_uid=uid)
        await call.message.edit_text(
            f"💬 <b>Send message to user <code>{uid}</code></b>\n\nType your message:",
            reply_markup=cancel_kb()
        )
        await call.answer()
        return

    # Refresh card after action
    user = await get_user(uid)
    if user:
        await call.message.edit_reply_markup(
            reply_markup=member_card_kb(uid, bool(user.get("is_vip")), bool(user.get("is_banned")), "all", 0)
        )


# ─── Send DM to specific user ─────────────────────────────────

class MemberMsgState(StatesGroup):
    waiting_text = State()


@router.message(MemberMsgState.waiting_text)
async def member_msg_send(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    uid  = data.get("msg_target_uid")
    await state.clear()
    if not uid:
        await message.answer("❌ Session expired."); return
    try:
        await bot.send_message(
            uid,
            f"📬 <b>Message from Admin:</b>\n\n{message.text or message.caption or '(media)'}",
            parse_mode="HTML"
        )
        if message.photo:
            await bot.send_photo(uid, message.photo[-1].file_id)
        elif message.document:
            await bot.send_document(uid, message.document.file_id)
        elif message.video:
            await bot.send_video(uid, message.video.file_id)
        await message.answer(f"✅ Message sent to <code>{uid}</code>.", reply_markup=back_admin_kb("users"))
    except Exception as e:
        await message.answer(f"❌ Could not send: {e}", reply_markup=back_admin_kb("users"))


# ─── Search ───────────────────────────────────────────────────

class MemberSearchState(StatesGroup):
    waiting_query = State()


@router.callback_query(F.data == "mbr:search")
async def member_search_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(MemberSearchState.waiting_query)
    await call.message.edit_text(
        "🔍 <b>Search Members</b>\n\n"
        "Send a name, @username, or Telegram ID:",
        reply_markup=cancel_kb()
    )
    await call.answer()


@router.message(MemberSearchState.waiting_query)
async def member_search_results(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()
    q     = message.text.strip()
    users, total = await search_users(q)

    if not users:
        await message.answer(f"😔 No users found for <b>{q}</b>.", reply_markup=back_admin_kb("users"))
        return

    rows = []
    for u in users:
        name  = (u.get("full_name") or "Unknown")[:22]
        badge = ("👑" if u.get("is_vip") else "") + ("🚫" if u.get("is_banned") else "")
        rows.append([InlineKeyboardButton(
            text=f"{badge} {name}  ({u['tg_id']})",
            callback_data=f"mbr:card:{u['tg_id']}:all:0"
        )])
    rows.append([InlineKeyboardButton(text="◀️ Back", callback_data="adm:users")])
    await message.answer(
        f"🔍 <b>Search: {q}</b>  —  {total} result(s)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )


# ─── Activity stats ───────────────────────────────────────────

@router.callback_query(F.data == "mbr:activity")
async def member_activity(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    s = await get_user_activity_stats()
    await call.message.edit_text(
        f"📊 <b>Member Activity</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🟢 Active today:    <b>{s['active_today']}</b>\n"
        f"📅 Active this week: <b>{s['active_week']}</b>\n"
        f"🔥 Streak ≥7 days:  <b>{s['streak_7']}</b>\n"
        f"👥 Avg invites/user: <b>{s['avg_invites']}</b>\n"
        f"📖 Total unlocks:   <b>{s['total_unlocks']}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◀️ Back", callback_data="mbr:filter:all:0")
        ]])
    )
    await call.answer()
