import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import settings
from database.users import get_all_users
from database.analytics import add_required_channel, remove_required_channel, get_required_channels
from keyboards.admin import admin_main_kb, back_admin_kb
from keyboards.user import cancel_kb
from utils.safe_chat import safe_get_chat

router = Router()
logger = logging.getLogger(__name__)


def is_admin(uid): return uid in settings.admin_id_list


# ─── STATES ───────────────────────────────────────────────────

class BroadcastState(StatesGroup):
    waiting_message = State()


class ChannelState(StatesGroup):
    choosing_type      = State()
    waiting_id         = State()   # step 1: @username or numeric ID
    waiting_invite     = State()   # step 2: invite link (both public & private)


class ReaddChannelState(StatesGroup):
    waiting_channel_id = State()
    waiting_new_link   = State()


# ─── KEYBOARDS ────────────────────────────────────────────────

def channel_type_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🌐 Public channel",  callback_data="chtype:public"),
            InlineKeyboardButton(text="🔒 Private channel", callback_data="chtype:private"),
        ],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="adm:channels")],
    ])


def skip_invite_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Skip (use username link)", callback_data="ch_skip_invite")],
        [InlineKeyboardButton(text="❌ Cancel",                   callback_data="adm:channels")],
    ])


def channels_manage_kb(channels: list) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        label = ch.get("title") or ch["channel_id"]
        icon  = "🔒" if ch.get("channel_type") == "private" else "🌐"
        has   = "✅" if ch.get("invite_link") else "⚠️"
        rows.append([
            InlineKeyboardButton(text=f"{icon} {has} {label}", callback_data=f"ch_info:{ch['channel_id']}"),
            InlineKeyboardButton(text="🗑",                     callback_data=f"ch_del:{ch['channel_id']}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ Add channel", callback_data="ch_add")])
    rows.append([InlineKeyboardButton(text="◀️ Back",        callback_data="adm:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def render_channels_panel(channels: list) -> str:
    if not channels:
        return (
            "📡 <b>Required Channels</b>\n\n"
            "<i>No channels added yet.</i>\n\n"
            "Users must join all listed channels before using the bot."
        )
    text = f"📡 <b>Required Channels</b>  ({len(channels)} total)\n\n"
    for ch in channels:
        icon  = "🔒" if ch.get("channel_type") == "private" else "🌐"
        title = ch.get("title") or "—"
        link  = ch.get("invite_link")
        link_status = f"🔗 <code>{link}</code>" if link else "⚠️ <i>No invite link — users can't join!</i>"
        text += f"{icon} <b>{title}</b>  <code>{ch['channel_id']}</code>\n   {link_status}\n\n"
    return text.rstrip()


# ─── CHANNEL PANEL ────────────────────────────────────────────

@router.callback_query(F.data == "adm:channels")
async def adm_channels(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.clear()
    channels = await get_required_channels()
    text = await render_channels_panel(channels)
    await call.message.edit_text(text, reply_markup=channels_manage_kb(channels))
    await call.answer()


@router.callback_query(F.data == "ch_add")
async def ch_add_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(ChannelState.choosing_type)
    await call.message.edit_text(
        "📡 <b>Add Required Channel</b>\n\n"
        "Choose the channel type:\n\n"
        "🌐 <b>Public</b> — has a <code>@username</code>\n"
        "🔒 <b>Private</b> — no username, invite-link only",
        reply_markup=channel_type_kb()
    )
    await call.answer()


# ─── UNIFIED STEP 1: channel ID ───────────────────────────────

@router.callback_query(F.data.startswith("chtype:"))
async def ch_type_selected(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    ctype = call.data.split(":")[1]   # "public" or "private"
    await state.update_data(ch_type=ctype)
    await state.set_state(ChannelState.waiting_id)

    if ctype == "public":
        await call.message.edit_text(
            "🌐 <b>Add Public Channel — Step 1 / 2</b>\n\n"
            "Send the channel <b>username</b> or <b>numeric ID</b>:\n\n"
            "• <code>@mychannel</code>\n"
            "• <code>-1001234567890</code>\n\n"
            "<i>The bot must be an admin in the channel.</i>",
            reply_markup=cancel_kb()
        )
    else:
        await call.message.edit_text(
            "🔒 <b>Add Private Channel — Step 1 / 2</b>\n\n"
            "Send the <b>numeric ID</b> of the private channel:\n\n"
            "• <code>-1001234567890</code>\n\n"
            "<i>Tip: forward a message from the channel to @userinfobot to get its ID.\n"
            "The bot must be an admin in the channel.</i>",
            reply_markup=cancel_kb()
        )
    await call.answer()


@router.message(ChannelState.waiting_id)
async def ch_id_received(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id): return
    cid = message.text.strip()
    data = await state.get_data()
    ctype = data.get("ch_type", "public")

    try:
        chat = await safe_get_chat(bot, cid)
    except Exception as e:
        await message.answer(
            f"❌ <b>Could not verify channel.</b>\n\n"
            f"<code>{e}</code>\n\n"
            f"• Make sure the bot is an admin\n"
            f"• Check the username / ID is correct",
            reply_markup=cancel_kb()
        )
        return

    fetched_username = chat.get("username") or ""
    # For public channels: store @username as the channel_id if available
    # This guarantees _channel_url() always builds a valid t.me/username link
    stored_id = f"@{fetched_username}" if fetched_username else str(chat["id"])
    await state.update_data(
        ch_id=stored_id,
        ch_numeric_id=str(chat["id"]),
        ch_title=chat["title"],
        ch_username=fetched_username,
    )
    await state.set_state(ChannelState.waiting_invite)

    # Step 2: ask for invite link
    if ctype == "public":
        username_hint = f"@{chat['username']}" if chat.get("username") else None
        skip_note = (
            f"\n\nOr tap <b>⏭ Skip</b> — users will be sent to <code>t.me/{chat['username']}</code>."
            if username_hint else ""
        )
        await message.answer(
            f"✅ Found: <b>{chat['title']}</b>\n\n"
            f"🌐 <b>Step 2 / 2 — Invite Link</b>\n\n"
            f"Send a custom <b>invite link</b> for this channel.\n"
            f"This is what users tap to join.\n\n"
            f"Example: <code>https://t.me/+AbCdEfGhIjKlMnOp</code>"
            f"{skip_note}",
            reply_markup=skip_invite_kb() if username_hint else cancel_kb()
        )
    else:
        await message.answer(
            f"✅ Found: <b>{chat['title']}</b>\n\n"
            f"🔒 <b>Step 2 / 2 — Invite Link</b>\n\n"
            f"Send the <b>invite link</b> so users can join this private channel.\n\n"
            f"Example: <code>https://t.me/+AbCdEfGhIjKlMnOp</code>\n\n"
            f"<i>Create one: Channel Settings → Invite Links → Create New Link</i>",
            reply_markup=cancel_kb()
        )


# ─── UNIFIED STEP 2: invite link ──────────────────────────────

@router.message(ChannelState.waiting_invite)
async def ch_invite_received(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    link = message.text.strip()

    if not (link.startswith("https://t.me/") or link.startswith("http://t.me/")):
        await message.answer(
            "❌ <b>Invalid link.</b>\n\n"
            "Must be a Telegram link starting with <code>https://t.me/</code>",
            reply_markup=cancel_kb()
        )
        return

    await _save_channel(message, state, link)


@router.callback_query(F.data == "ch_skip_invite")
async def ch_skip_invite(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    data = await state.get_data()
    username = (data.get("ch_username") or "").lstrip("@")
    # Build proper t.me link from username — this is a valid join link for public channels
    link = f"https://t.me/{username}" if username else None
    await _save_channel(call.message, state, link, answering_call=call)


async def _save_channel(msg, state: FSMContext, link: str | None, answering_call=None):
    data = await state.get_data()
    await state.clear()

    ch_id       = data["ch_id"]           # @username or numeric ID
    ch_numeric  = data.get("ch_numeric_id", ch_id)   # always numeric for getChatMember
    ch_title    = data["ch_title"]
    ch_uname    = (data.get("ch_username") or "").lstrip("@")
    ctype       = data.get("ch_type", "public")

    # Use numeric ID for getChatMember (required by Telegram),
    # but build join URL from username when available
    if not link and ch_uname:
        link = f"https://t.me/{ch_uname}"

    await add_required_channel(
        channel_id=ch_numeric,    # always store numeric ID for getChatMember
        title=ch_title,
        channel_type=ctype,
        invite_link=link,
        username=ch_uname,
    )

    icon = "🔒" if ctype == "private" else "🌐"
    link_line = f"🔗 <code>{link}</code>" if link else "⚠️ No invite link set"
    text = (
        f"✅ <b>Channel saved!</b>\n\n"
        f"{icon} <b>{ch_title}</b>\n"
        f"ID: <code>{ch_id}</code>\n"
        f"Type: {'Private' if ctype == 'private' else 'Public'}\n"
        f"{link_line}"
    )
    if answering_call:
        await answering_call.answer()
        await msg.edit_text(text, reply_markup=back_admin_kb("channels"))
    else:
        await msg.answer(text, reply_markup=back_admin_kb("channels"))


# ─── DELETE / INFO ────────────────────────────────────────────

@router.callback_query(F.data.startswith("ch_del:"))
async def ch_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    cid = call.data.split(":", 1)[1]
    await remove_required_channel(cid)
    await call.answer("✅ Channel removed.", show_alert=True)
    channels = await get_required_channels()
    text = await render_channels_panel(channels)
    await call.message.edit_text(text, reply_markup=channels_manage_kb(channels))


@router.callback_query(F.data.startswith("ch_info:"))
async def ch_info(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    cid = call.data.split(":", 1)[1]
    channels = await get_required_channels()
    ch = next((c for c in channels if c["channel_id"] == cid), None)
    if not ch:
        await call.answer("Not found.", show_alert=True)
        return
    ctype = ch.get("channel_type", "public")
    icon  = "🔒 Private" if ctype == "private" else "🌐 Public"
    info  = f"{icon}\n{ch.get('title') or '—'}\nID: {ch['channel_id']}"
    if ch.get("invite_link"):
        info += f"\n{ch['invite_link']}"
    await call.answer(info[:200], show_alert=True)


# ─── RE-ADD / FIX INVITE LINK ─────────────────────────────────

@router.message(F.text.startswith("/readd_channel"))
async def readd_channel_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    channels = await get_required_channels()
    if not channels:
        await message.answer("No channels saved yet.")
        return
    text = "🔧 <b>Fix channel invite link</b>\n\nSend the <b>channel ID</b> to fix:\n\n"
    for ch in channels:
        icon     = "🔒" if ch.get("channel_type") == "private" else "🌐"
        has_link = "✅" if ch.get("invite_link") else "❌ no link"
        text    += f"{icon} <code>{ch['channel_id']}</code> — {ch.get('title') or '—'} {has_link}\n"
    await state.set_state(ReaddChannelState.waiting_channel_id)
    await message.answer(text, reply_markup=cancel_kb())


@router.message(ReaddChannelState.waiting_channel_id)
async def readd_ch_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.update_data(readd_cid=message.text.strip())
    await state.set_state(ReaddChannelState.waiting_new_link)
    await message.answer(
        "Send the new <b>invite link</b>:\n\n"
        "Example: <code>https://t.me/+AbCdEfGhIjKlMnOp</code>\n\n"
        "Or send <code>-</code> to remove the invite link.",
        reply_markup=cancel_kb()
    )


@router.message(ReaddChannelState.waiting_new_link)
async def readd_ch_link(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    cid  = data["readd_cid"]
    link = message.text.strip()
    await state.clear()

    channels = await get_required_channels()
    ch = next((c for c in channels if c["channel_id"] == cid), None)
    if not ch:
        await message.answer(f"❌ Channel <code>{cid}</code> not found.", reply_markup=back_admin_kb("channels"))
        return

    new_link = None if link == "-" else link
    ctype = "private" if new_link and ("+" in new_link or "joinchat" in new_link) else ch.get("channel_type", "public")
    await add_required_channel(cid, ch.get("title"), ctype, new_link)
    await message.answer(
        f"✅ Updated!\n\n"
        f"Link: {f'<code>{new_link}</code>' if new_link else '<i>removed</i>'}",
        reply_markup=back_admin_kb("channels")
    )


# ─── BROADCAST ────────────────────────────────────────────────

@router.callback_query(F.data == "adm:broadcast")
async def adm_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(BroadcastState.waiting_message)
    users = await get_all_users()
    await call.message.edit_text(
        f"📢 <b>Broadcast Message</b>\n\n"
        f"Will be sent to <b>{len(users)}</b> active users.\n\n"
        f"Send any message — text (HTML), photo, video, document, or audio.",
        reply_markup=cancel_kb()
    )
    await call.answer()


@router.message(BroadcastState.waiting_message)
async def broadcast_message_received(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id): return
    await state.clear()
    users  = await get_all_users()
    total  = len(users)
    sent   = failed = 0
    status = await message.answer(f"📢 Sending to <b>{total}</b> users...")

    for i, uid in enumerate(users):
        try:
            if message.text:
                await bot.send_message(uid, message.text, parse_mode="HTML")
            elif message.photo:
                await bot.send_photo(uid, message.photo[-1].file_id, caption=message.caption or "", parse_mode="HTML")
            elif message.video:
                await bot.send_video(uid, message.video.file_id, caption=message.caption or "", parse_mode="HTML")
            elif message.document:
                await bot.send_document(uid, message.document.file_id, caption=message.caption or "", parse_mode="HTML")
            elif message.audio:
                await bot.send_audio(uid, message.audio.file_id, caption=message.caption or "", parse_mode="HTML")
            elif message.animation:
                await bot.send_animation(uid, message.animation.file_id, caption=message.caption or "", parse_mode="HTML")
            else:
                await message.forward(uid)
            sent += 1
        except Exception:
            failed += 1
        if (i + 1) % 25 == 0:
            await asyncio.sleep(1)
        if (i + 1) % 100 == 0:
            try:
                await status.edit_text(f"📢 Progress: <b>{i+1}/{total}</b>\n✅ {sent}  ❌ {failed}")
            except Exception:
                pass

    await status.edit_text(
        f"📢 <b>Broadcast complete!</b>\n\n"
        f"✅ Sent: <b>{sent}</b>\n"
        f"❌ Failed: <b>{failed}</b>\n"
        f"📊 Total: <b>{total}</b>"
    )


# ─── /fix_channels — auto-repair existing channels ────────────

@router.message(F.text.startswith("/fix_channels"))
async def fix_channels_cmd(message: Message, bot: Bot):
    """
    Admin utility: fetch username/title for all saved channels
    and update invite_link where it's still missing.
    Run once after upgrading to fix all old entries.
    """
    if not is_admin(message.from_user.id): return
    channels = await get_required_channels()
    if not channels:
        await message.answer("No channels saved.")
        return

    report = "🔧 <b>Channel fix report:</b>\n\n"
    for ch in channels:
        cid     = ch["channel_id"]
        has_inv = bool(ch.get("invite_link"))
        has_usr = bool(ch.get("username"))
        if has_inv and has_usr:
            report += f"✅ <code>{cid}</code> — already complete\n"
            continue
        try:
            chat = await safe_get_chat(bot, cid)
            uname = chat.get("username")
            # For public channels without invite link, derive URL from username
            new_link = ch.get("invite_link")
            if not new_link and uname:
                new_link = f"https://t.me/{uname}"
            await add_required_channel(
                channel_id=cid,
                title=chat["title"],
                channel_type=ch.get("channel_type", "public"),
                invite_link=new_link,
                username=uname,
            )
            report += (
                f"✅ <code>{cid}</code> — <b>{chat['title']}</b>\n"
                f"   link: <code>{new_link or '—'}</code>\n"
            )
        except Exception as e:
            report += f"❌ <code>{cid}</code> — {e}\n"

    await message.answer(report)
