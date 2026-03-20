"""
Admin — User Management
• Browse ALL users (paginated, 10 per page)
• Filter: VIP users / Banned users
• Per-user card: full info + quick action buttons
• Grant VIP with lesson limit (e.g. 10 lessons) or time expiry
• Revoke VIP with one tap
• Ban / Unban
• Give free passes
• Lookup by Telegram ID
"""
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import settings
from database.users import (
    get_user, update_user, add_free_pass, get_user_stats,
    get_all_users_paginated, get_vip_users,
    grant_vip, revoke_vip, check_vip_validity
)
from database.content import get_user_unlocked_lessons
from keyboards.admin import admin_users_kb, back_admin_kb
from keyboards.user import cancel_kb

router = Router()
logger = logging.getLogger(__name__)
PER_PAGE = 10


def is_admin(uid): return uid in settings.admin_id_list


# ─── KEYBOARDS ────────────────────────────────────────────────

def user_card_kb(uid: int, is_vip: bool, is_banned: bool) -> InlineKeyboardMarkup:
    rows = []
    if is_vip:
        rows.append([InlineKeyboardButton(text="❌ Revoke VIP",   callback_data=f"usr:revoke_vip:{uid}")])
    else:
        rows.append([InlineKeyboardButton(text="👑 Grant VIP",    callback_data=f"usr:grant_vip:{uid}")])
    rows.append([
        InlineKeyboardButton(text="🎫 +1 Pass",   callback_data=f"usr:give_pass:{uid}"),
        InlineKeyboardButton(text="🎫 +5 Passes", callback_data=f"usr:give_5pass:{uid}"),
    ])
    if is_banned:
        rows.append([InlineKeyboardButton(text="✅ Unban",         callback_data=f"usr:unban:{uid}")])
    else:
        rows.append([InlineKeyboardButton(text="🚫 Ban",           callback_data=f"usr:ban:{uid}")])
    rows.append([InlineKeyboardButton(text="◀️ Back to list",      callback_data="adm:users")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def paginate_kb(page: int, total: int, base_cb: str) -> list:
    pages = (total + PER_PAGE - 1) // PER_PAGE
    row = []
    if page > 0:
        row.append(InlineKeyboardButton(text="◀️", callback_data=f"{base_cb}:{page-1}"))
    row.append(InlineKeyboardButton(text=f"{page+1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        row.append(InlineKeyboardButton(text="▶️", callback_data=f"{base_cb}:{page+1}"))
    return row


def _user_line(u: dict) -> str:
    name   = u.get("full_name") or "—"
    uname  = f"@{u['username']}" if u.get("username") else ""
    badges = ""
    if u.get("is_vip"):    badges += " 👑"
    if u.get("is_banned"): badges += " 🚫"
    return f"{name} {uname}{badges}"


def _vip_status(u: dict) -> str:
    if not u.get("is_vip"):
        return "🆓 Free"
    limit  = u.get("vip_lesson_limit") or 0
    used   = u.get("vip_lessons_used") or 0
    exp    = u.get("vip_expires_at")
    parts  = ["👑 VIP"]
    if limit > 0:
        parts.append(f"({used}/{limit} lessons)")
    if exp:
        try:
            dt = datetime.fromisoformat(exp)
            parts.append(f"exp: {dt.strftime('%d %b %Y')}")
        except Exception:
            pass
    return " ".join(parts)


# ─── ALL USERS LIST ───────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:all_users:"))
async def adm_all_users(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    page = int(call.data.split(":")[-1])
    users, total = await get_all_users_paginated(page, PER_PAGE)
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)

    text = f"👥 <b>All Users</b>  ({total} total)  —  Page {page+1}/{pages}\n\n"
    rows = []
    for u in users:
        line = _user_line(u)
        rows.append([InlineKeyboardButton(
            text=line[:48],
            callback_data=f"usr:card:{u['tg_id']}"
        )])

    nav = paginate_kb(page, total, "adm:all_users")
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="◀️ Back", callback_data="adm:users")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()


# ─── VIP USERS LIST ───────────────────────────────────────────

@router.callback_query(F.data == "adm:vip_users")
async def adm_vip_users(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    users = await get_vip_users()
    if not users:
        await call.answer("No VIP users.", show_alert=True)
        return

    rows = []
    for u in users:
        name    = u.get("full_name") or "—"
        limit   = u.get("vip_lesson_limit") or 0
        used    = u.get("vip_lessons_used") or 0
        suffix  = f" ({used}/{limit})" if limit > 0 else " (∞)"
        rows.append([
            InlineKeyboardButton(text=f"👑 {name}{suffix}", callback_data=f"usr:card:{u['tg_id']}"),
            InlineKeyboardButton(text="❌",                  callback_data=f"usr:revoke_vip:{u['tg_id']}"),
        ])
    rows.append([InlineKeyboardButton(text="◀️ Back", callback_data="adm:users")])

    await call.message.edit_text(
        f"👑 <b>VIP Users</b>  ({len(users)} total)\n\n"
        f"Tap ❌ to revoke VIP. Tap name for full profile.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await call.answer()


# ─── BANNED USERS ─────────────────────────────────────────────

@router.callback_query(F.data == "adm:banned_users")
async def adm_banned_users(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    users, total = await get_all_users_paginated(0, 20, filter_banned=True)
    if not users:
        await call.answer("No banned users.", show_alert=True)
        return
    rows = []
    for u in users:
        name = u.get("full_name") or "—"
        rows.append([
            InlineKeyboardButton(text=f"🚫 {name}", callback_data=f"usr:card:{u['tg_id']}"),
            InlineKeyboardButton(text="✅ Unban",   callback_data=f"usr:unban:{u['tg_id']}"),
        ])
    rows.append([InlineKeyboardButton(text="◀️ Back", callback_data="adm:users")])
    await call.message.edit_text(
        f"🚫 <b>Banned Users</b>  ({total} total)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await call.answer()


# ─── USER CARD ────────────────────────────────────────────────

@router.callback_query(F.data.startswith("usr:card:"))
async def user_card(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    uid  = int(call.data.split(":")[-1])
    user = await get_user(uid)
    if not user:
        await call.answer("User not found.", show_alert=True)
        return

    unlocked = await get_user_unlocked_lessons(uid)
    vip_line = _vip_status(user)
    banned   = "🚫 Banned" if user.get("is_banned") else "✅ Active"
    uname    = f"@{user['username']}" if user.get("username") else "—"

    await call.message.edit_text(
        f"👤 <b>User Profile</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Name:     <b>{user.get('full_name') or '—'}</b>\n"
        f"Username: {uname}\n"
        f"ID:       <code>{uid}</code>\n"
        f"Status:   {vip_line}\n"
        f"Account:  {banned}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📖 Lessons:  <b>{len(unlocked)}</b>\n"
        f"🎫 Passes:   <b>{user.get('free_passes', 0)}</b>\n"
        f"👥 Invites:  <b>{user.get('invites_count', 0)}</b>\n"
        f"🔥 Streak:   <b>{user.get('streak_days', 0)} days</b>\n"
        f"📅 Joined:   <i>{str(user.get('created_at', ''))[:10]}</i>\n"
        f"🕐 Last seen: <i>{str(user.get('last_seen', ''))[:10]}</i>",
        reply_markup=user_card_kb(uid, bool(user.get("is_vip")), bool(user.get("is_banned")))
    )
    await call.answer()


# ─── QUICK ACTIONS FROM CARD ──────────────────────────────────

@router.callback_query(F.data.startswith("usr:give_pass:"))
async def usr_give_pass(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.split(":")[-1])
    await add_free_pass(uid, 1)
    await call.answer("✅ +1 Free Pass given.", show_alert=True)
    try: await bot.send_message(uid, "🎫 You received <b>1 Free Pass</b> from an admin!")
    except Exception: pass


@router.callback_query(F.data.startswith("usr:give_5pass:"))
async def usr_give_5pass(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.split(":")[-1])
    await add_free_pass(uid, 5)
    await call.answer("✅ +5 Free Passes given.", show_alert=True)
    try: await bot.send_message(uid, "🎫 You received <b>5 Free Passes</b> from an admin! 🎉")
    except Exception: pass


@router.callback_query(F.data.startswith("usr:ban:"))
async def usr_ban(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.split(":")[-1])
    await update_user(uid, is_banned=1)
    await call.answer("🚫 User banned.", show_alert=True)
    await adm_refresh_card(call, uid)


@router.callback_query(F.data.startswith("usr:unban:"))
async def usr_unban(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.split(":")[-1])
    await update_user(uid, is_banned=0)
    await call.answer("✅ User unbanned.", show_alert=True)
    await adm_refresh_card(call, uid)


@router.callback_query(F.data.startswith("usr:revoke_vip:"))
async def usr_revoke_vip(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.split(":")[-1])
    await revoke_vip(uid, reason="admin_revoked", revoked_by=call.from_user.id)
    await call.answer("✅ VIP revoked.", show_alert=True)
    try:
        await bot.send_message(uid, "ℹ️ Your <b>VIP status</b> has been removed by an admin.")
    except Exception: pass
    await adm_refresh_card(call, uid)


async def adm_refresh_card(call: CallbackQuery, uid: int):
    user     = await get_user(uid)
    if not user: return
    unlocked = await get_user_unlocked_lessons(uid)
    vip_line = _vip_status(user)
    banned   = "🚫 Banned" if user.get("is_banned") else "✅ Active"
    uname    = f"@{user['username']}" if user.get("username") else "—"
    await call.message.edit_text(
        f"👤 <b>User Profile</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Name:     <b>{user.get('full_name') or '—'}</b>\n"
        f"Username: {uname}\n"
        f"ID:       <code>{uid}</code>\n"
        f"Status:   {vip_line}\n"
        f"Account:  {banned}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📖 Lessons: <b>{len(unlocked)}</b>  🎫 Passes: <b>{user.get('free_passes',0)}</b>",
        reply_markup=user_card_kb(uid, bool(user.get("is_vip")), bool(user.get("is_banned")))
    )


# ─── GRANT VIP WIZARD ─────────────────────────────────────────

class VipGrantState(StatesGroup):
    choosing_limit = State()
    custom_limit   = State()
    choosing_expiry = State()


@router.callback_query(F.data.startswith("usr:grant_vip:"))
async def usr_grant_vip_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    uid = int(call.data.split(":")[-1])
    await state.update_data(vip_uid=uid)
    await state.set_state(VipGrantState.choosing_limit)
    await call.message.edit_text(
        "👑 <b>Grant VIP</b>\n\n"
        "How many VIP lessons should this user get?\n"
        "<i>(VIP expires automatically after N lessons are unlocked)</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="5 lessons",   callback_data="viplimit:5"),
             InlineKeyboardButton(text="10 lessons",  callback_data="viplimit:10")],
            [InlineKeyboardButton(text="20 lessons",  callback_data="viplimit:20"),
             InlineKeyboardButton(text="50 lessons",  callback_data="viplimit:50")],
            [InlineKeyboardButton(text="♾ Unlimited", callback_data="viplimit:0")],
            [InlineKeyboardButton(text="✏️ Custom",    callback_data="viplimit:custom")],
            [InlineKeyboardButton(text="❌ Cancel",    callback_data="adm:users")],
        ])
    )
    await call.answer()


@router.callback_query(F.data.startswith("viplimit:"))
async def vip_limit_selected(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    val = call.data.split(":")[1]
    if val == "custom":
        await state.set_state(VipGrantState.custom_limit)
        await call.message.edit_text(
            "✏️ Enter the <b>exact number</b> of lessons:", reply_markup=cancel_kb()
        )
    else:
        await state.update_data(vip_limit=int(val))
        await state.set_state(VipGrantState.choosing_expiry)
        await _ask_vip_expiry(call)
    await call.answer()


@router.message(VipGrantState.custom_limit)
async def vip_custom_limit(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try:
        n = int(message.text.strip())
        if n < 0: raise ValueError
    except ValueError:
        await message.answer("❌ Enter a positive number:"); return
    await state.update_data(vip_limit=n)
    await state.set_state(VipGrantState.choosing_expiry)
    await message.answer(
        "⏰ Set a <b>time expiry</b> as well?",
        reply_markup=_vip_expiry_kb()
    )


async def _ask_vip_expiry(call: CallbackQuery):
    await call.message.edit_text(
        "⏰ Set a <b>time expiry</b> as well?\n"
        "<i>VIP will also expire when the time runs out, regardless of lesson count.</i>",
        reply_markup=_vip_expiry_kb()
    )


def _vip_expiry_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 week",   callback_data="vipexp:1w"),
         InlineKeyboardButton(text="1 month",  callback_data="vipexp:1mo")],
        [InlineKeyboardButton(text="3 months", callback_data="vipexp:3mo"),
         InlineKeyboardButton(text="1 year",   callback_data="vipexp:1y")],
        [InlineKeyboardButton(text="No time limit", callback_data="vipexp:none")],
        [InlineKeyboardButton(text="❌ Cancel",      callback_data="adm:users")],
    ])


@router.callback_query(F.data.startswith("vipexp:"))
async def vip_expiry_selected(call: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(call.from_user.id): return
    val  = call.data.split(":")[1]
    data = await state.get_data()
    uid  = data.get("vip_uid")
    limit = data.get("vip_limit", 0)
    await state.clear()

    now = datetime.now()
    exp_map = {"1w": timedelta(weeks=1), "1mo": timedelta(days=30),
               "3mo": timedelta(days=90), "1y": timedelta(days=365)}
    expires_at = (now + exp_map[val]).isoformat() if val in exp_map else None

    await grant_vip(uid, lesson_limit=limit, expires_at=expires_at,
                    granted_by=call.from_user.id, reason="admin_grant")

    user = await get_user(uid)
    name = (user or {}).get("full_name") or str(uid)
    limit_txt = f"{limit} lessons" if limit > 0 else "unlimited"
    exp_txt   = expires_at[:10] if expires_at else "no time limit"

    await call.message.edit_text(
        f"✅ <b>VIP granted to {name}!</b>\n\n"
        f"Lesson limit: <b>{limit_txt}</b>\n"
        f"Expires: <b>{exp_txt}</b>",
        reply_markup=back_admin_kb("users")
    )
    try:
        msg = (
            f"👑 <b>You now have VIP access!</b>\n\n"
            f"🎓 Lesson allowance: <b>{limit_txt}</b>\n"
            f"⏰ Valid until: <b>{exp_txt}</b>\n\n"
            f"Enjoy exclusive content!"
        )
        await bot.send_message(uid, msg)
    except Exception: pass
    await call.answer()


# ─── STATS + LOOKUP + GIVE PASS (from menu) ───────────────────

class UserSearchState(StatesGroup):
    waiting_id = State()
    give_pass_id = State()
    give_pass_amount = State()


@router.callback_query(F.data == "adm:lookup_user")
async def adm_lookup(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(UserSearchState.waiting_id)
    await call.message.edit_text("🔍 Send the user's <b>Telegram ID</b>:", reply_markup=cancel_kb())
    await call.answer()


@router.message(UserSearchState.waiting_id)
async def lookup_id_received(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.clear()
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid ID.", reply_markup=admin_users_kb()); return
    user = await get_user(uid)
    if not user:
        await message.answer(f"❌ No user with ID <code>{uid}</code>.", reply_markup=admin_users_kb())
        return
    unlocked = await get_user_unlocked_lessons(uid)
    vip_line = _vip_status(user)
    banned   = "🚫 Banned" if user.get("is_banned") else "✅ Active"
    uname    = f"@{user['username']}" if user.get("username") else "—"
    await message.answer(
        f"🔍 <b>User Found</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Name:    <b>{user.get('full_name') or '—'}</b>\n"
        f"User:    {uname}\n"
        f"ID:      <code>{uid}</code>\n"
        f"Status:  {vip_line}\n"
        f"Account: {banned}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📖 Lessons: <b>{len(unlocked)}</b>  🎫 Passes: <b>{user.get('free_passes',0)}</b>\n"
        f"👥 Invites: <b>{user.get('invites_count',0)}</b>  🔥 Streak: <b>{user.get('streak_days',0)}d</b>",
        reply_markup=user_card_kb(uid, bool(user.get("is_vip")), bool(user.get("is_banned")))
    )


@router.callback_query(F.data == "adm:give_pass")
async def adm_give_pass(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(UserSearchState.give_pass_id)
    await call.message.edit_text("🎫 Send the <b>Telegram ID</b> to give a pass:", reply_markup=cancel_kb())
    await call.answer()


@router.message(UserSearchState.give_pass_id)
async def give_pass_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try:
        uid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Invalid ID."); return
    await state.update_data(pass_uid=uid)
    await state.set_state(UserSearchState.give_pass_amount)
    await message.answer(
        "How many passes?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="1", callback_data="pass_amt:1"),
            InlineKeyboardButton(text="3", callback_data="pass_amt:3"),
            InlineKeyboardButton(text="5", callback_data="pass_amt:5"),
            InlineKeyboardButton(text="10",callback_data="pass_amt:10"),
        ]])
    )


@router.callback_query(F.data.startswith("pass_amt:"))
async def give_pass_amount(call: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(call.from_user.id): return
    data   = await state.get_data()
    uid    = data.get("pass_uid")
    amount = int(call.data.split(":")[1])
    await state.clear()
    if not uid:
        await call.answer("Session expired.", show_alert=True); return
    await add_free_pass(uid, amount)
    await call.answer(f"✅ {amount} pass(es) given.", show_alert=True)
    try:
        await bot.send_message(uid, f"🎫 You received <b>{amount} Free Pass{'es' if amount>1 else ''}</b> from an admin!")
    except Exception: pass
    await call.message.edit_text(f"✅ Done. {amount} pass(es) → <code>{uid}</code>", reply_markup=back_admin_kb("users"))


@router.callback_query(F.data == "adm:grant_vip")
async def adm_grant_vip_from_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(UserSearchState.waiting_id)
    await state.update_data(_next_action="grant_vip")
    await call.message.edit_text("👑 Send the <b>Telegram ID</b> to grant VIP:", reply_markup=cancel_kb())
    await call.answer()


@router.callback_query(F.data == "adm:revoke_vip")
async def adm_revoke_vip_from_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(UserSearchState.waiting_id)
    await state.update_data(_next_action="revoke_vip")
    await call.message.edit_text("❌ Send the <b>Telegram ID</b> to revoke VIP:", reply_markup=cancel_kb())
    await call.answer()


@router.callback_query(F.data == "adm:ban_user")
async def adm_ban_from_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(UserSearchState.waiting_id)
    await state.update_data(_next_action="ban")
    await call.message.edit_text("🚫 Send the <b>Telegram ID</b> to ban:", reply_markup=cancel_kb())
    await call.answer()


@router.callback_query(F.data == "adm:unban_user")
async def adm_unban_from_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(UserSearchState.waiting_id)
    await state.update_data(_next_action="unban")
    await call.message.edit_text("✅ Send the <b>Telegram ID</b> to unban:", reply_markup=cancel_kb())
    await call.answer()


@router.callback_query(F.data == "adm:user_stats")
async def adm_user_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    s = await get_user_stats()
    await call.message.edit_text(
        f"📊 <b>User Statistics</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👥 Total:      <b>{s['total']}</b>\n"
        f"🆕 New today:  <b>{s['new_today']}</b>\n"
        f"👑 VIP:        <b>{s['vip']}</b>\n"
        f"🚫 Banned:     <b>{s['banned']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━",
        reply_markup=back_admin_kb("users")
    )
    await call.answer()
