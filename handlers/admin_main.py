from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from config import settings
from database.users import get_user_stats
from database.content import get_content_stats
from keyboards.admin import (
    admin_main_kb, admin_content_kb, admin_promo_kb,
    admin_users_kb, admin_settings_kb
)

router = Router()


def is_admin(uid): return uid in settings.admin_id_list


@router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id): return
    await _send_admin_home(message.answer)


@router.callback_query(F.data == "adm:main")
async def adm_main(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Unauthorized", show_alert=True); return
    text, kb = await _admin_home_args()
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


async def _admin_home_args():
    u   = await get_user_stats()
    c   = await get_content_stats()
    now = datetime.now().strftime("%d %b %Y  %H:%M")
    text = (
        f"⚙️ <b>Admin Panel</b>\n"
        f"<i>{now}</i>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>{u['total']}</b> users  "
        f"🆕 <b>{u['new_today']}</b> today  "
        f"👑 <b>{u['vip']}</b> VIP  "
        f"🚫 <b>{u['banned']}</b> banned\n"
        f"📚 <b>{c['categories']}</b> cats  "
        f"📝 <b>{c['lessons']}</b> lessons  "
        f"👁 <b>{c['total_views']}</b> views"
    )
    return text, admin_main_kb()


async def _send_admin_home(answer_fn):
    text, kb = await _admin_home_args()
    await answer_fn(text, reply_markup=kb)


@router.callback_query(F.data == "adm:content")
async def adm_content(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text("📚 <b>Content Management</b>", reply_markup=admin_content_kb())
    await call.answer()


@router.callback_query(F.data == "adm:promos")
async def adm_promos(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text("🎟 <b>Promo Codes</b>", reply_markup=admin_promo_kb())
    await call.answer()


@router.callback_query(F.data == "adm:users")
async def adm_users(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text("👥 <b>User Management</b>", reply_markup=admin_users_kb())
    await call.answer()


@router.callback_query(F.data == "adm:settings")
async def adm_settings(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    await call.message.edit_text("⚙️ <b>Settings</b>", reply_markup=admin_settings_kb())
    await call.answer()


@router.callback_query(F.data == "adm:fix_channels_btn")
async def adm_fix_channels(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id): return
    from database.analytics import get_required_channels, add_required_channel
    from utils.safe_chat import safe_get_chat
    channels = await get_required_channels()
    if not channels:
        await call.answer("No channels saved.", show_alert=True); return
    report = "🔧 <b>Channel Fix Report</b>\n\n"
    for ch in channels:
        cid   = ch["channel_id"]
        uname = ch.get("username") or ""
        link  = ch.get("invite_link") or ""
        # Already has a working URL?
        if (link and "t.me/" in link) or (uname) or cid.startswith("@"):
            report += f"✅ <code>{cid}</code> — OK\n"
            continue
        # Try to fetch username via raw API
        try:
            chat     = await safe_get_chat(bot, cid)
            fetched_uname = chat.get("username") or ""
            # For public channels: derive link from username
            new_link = link or (f"https://t.me/{fetched_uname}" if fetched_uname else None)
            ctype    = ch.get("channel_type", "public")
            await add_required_channel(
                channel_id=cid,
                title=chat["title"],
                channel_type=ctype,
                invite_link=new_link,
                username=fetched_uname,
            )
            if fetched_uname:
                report += f"✅ <code>{cid}</code> → @{fetched_uname}\n"
            elif new_link:
                report += f"✅ <code>{cid}</code> → link saved\n"
            else:
                report += f"⚠️ <code>{cid}</code> — no username found, set invite link manually\n"
        except Exception as e:
            report += f"❌ <code>{cid}</code> — {str(e)[:60]}\n"
    report += "\n<i>Run /fix_channels to fix remaining issues.</i>"
    await call.message.edit_text(report, reply_markup=admin_settings_kb())
    await call.answer()


@router.message(F.text.startswith("/fix_channels"))
async def fix_channels_cmd(message: Message, bot: Bot):
    if not is_admin(message.from_user.id): return
    from database.analytics import get_required_channels, add_required_channel
    from utils.safe_chat import safe_get_chat
    channels = await get_required_channels()
    if not channels:
        await message.answer("No channels saved."); return
    report = "🔧 <b>Channel Fix Report</b>\n\n"
    for ch in channels:
        cid   = ch["channel_id"]
        uname = ch.get("username") or ""
        link  = ch.get("invite_link") or ""
        if (link and "t.me/" in link) or uname or cid.startswith("@"):
            report += f"✅ <code>{cid}</code> — OK\n"
            continue
        try:
            chat          = await safe_get_chat(bot, cid)
            fetched_uname = chat.get("username") or ""
            new_link      = link or (f"https://t.me/{fetched_uname}" if fetched_uname else None)
            await add_required_channel(
                channel_id=cid,
                title=chat["title"],
                channel_type=ch.get("channel_type","public"),
                invite_link=new_link,
                username=fetched_uname,
            )
            report += f"✅ <code>{cid}</code> → {'@'+fetched_uname if fetched_uname else new_link or 'no URL'}\n"
        except Exception as e:
            report += f"❌ <code>{cid}</code> — {str(e)[:60]}\n"
    await message.answer(report)


@router.callback_query(F.data == "adm:bot_info")
async def adm_bot_info(call: CallbackQuery, bot: Bot):
    if not is_admin(call.from_user.id): return
    me = await bot.get_me()
    await call.message.edit_text(
        f"🤖 <b>Bot Info</b>\n\n"
        f"Name: <b>{me.full_name}</b>\n"
        f"Username: @{me.username}\n"
        f"ID: <code>{me.id}</code>",
        reply_markup=admin_settings_kb()
    )
    await call.answer()


@router.callback_query(F.data == "adm:analytics")
async def adm_analytics(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    u   = await get_user_stats()
    c   = await get_content_stats()
    now = datetime.now().strftime("%d %b %Y, %H:%M")
    await call.message.edit_text(
        f"📊 <b>Analytics</b>\n<i>{now}</i>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>Users</b>\n"
        f"  Total: <b>{u['total']}</b>  Today: <b>{u['new_today']}</b>\n"
        f"  VIP: <b>{u['vip']}</b>  Banned: <b>{u['banned']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"<b>Content</b>\n"
        f"  📚 {c['categories']} categories\n"
        f"  📖 {c['levels']} levels\n"
        f"  📝 {c['lessons']} lessons\n"
        f"  👁 {c['total_views']} total views",
        reply_markup=admin_main_kb()
    )
    await call.answer()


@router.callback_query(F.data == "adm:most_viewed")
async def adm_most_viewed(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    import aiosqlite
    from database.db import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT title, view_count FROM lessons ORDER BY view_count DESC LIMIT 10"
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    text = "🔥 <b>Most Viewed Lessons</b>\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. <b>{r['title']}</b> — {r['view_count']} views\n"
    await call.message.edit_text(text or "No data yet.", reply_markup=admin_content_kb())
    await call.answer()


@router.callback_query(F.data == "adm:top_rated")
async def adm_top_rated(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    import aiosqlite
    from database.db import DB_PATH
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT l.title, ROUND(AVG(r.rating),1) as avg, COUNT(r.id) as votes
               FROM lesson_ratings r JOIN lessons l ON l.id=r.lesson_id
               GROUP BY r.lesson_id ORDER BY avg DESC LIMIT 10"""
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]
    text = "⭐ <b>Top Rated Lessons</b>\n\n"
    for i, r in enumerate(rows, 1):
        stars = "⭐" * round(r["avg"])
        text += f"{i}. <b>{r['title']}</b>\n   {stars} {r['avg']} ({r['votes']} votes)\n"
    await call.message.edit_text(text or "No ratings yet.", reply_markup=admin_content_kb())
    await call.answer()
