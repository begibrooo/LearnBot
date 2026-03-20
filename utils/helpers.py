import logging
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest
from database.analytics import get_required_channels
from utils.safe_chat import safe_get_chat_member

logger = logging.getLogger(__name__)


# ─── SUBSCRIPTION CHECK ───────────────────────────────────────

async def check_subscriptions(bot: Bot, user_id: int) -> list[dict]:
    """Returns list of channels user is NOT subscribed to."""
    channels = await get_required_channels()
    not_subscribed = []
    for ch in channels:
        status = await safe_get_chat_member(bot, ch["channel_id"], user_id)
        if status in ("left", "kicked", "banned"):
            not_subscribed.append(ch)
    return not_subscribed


def _channel_url(ch: dict) -> str:
    """
    Build the correct join URL for a channel.
    Priority:
      1. invite_link  (t.me/+ or t.me/joinchat)     → always use it directly
      2. username field                               → t.me/username
      3. channel_id starts with @                    → t.me/username
      4. channel_id is numeric + channel_type=public → CANNOT build URL, needs fix
    NEVER return t.me/c/<numeric> — that is a message-preview link, not a join link,
    and causes "no Telegram account" errors.
    """
    invite = (ch.get("invite_link") or "").strip()
    cid    = str(ch.get("channel_id") or "").strip()
    uname  = (ch.get("username") or "").strip().lstrip("@")

    # 1. Valid invite link (private or public join links)
    if invite and "t.me/" in invite:
        return invite

    # 2. Username stored in the username column
    if uname:
        return f"https://t.me/{uname}"

    # 3. channel_id is already @username
    if cid.startswith("@"):
        return f"https://t.me/{cid.lstrip('@')}"

    # 4. Numeric ID only — we have NO valid URL
    # Return empty: the button will show "⚠️ fix this channel" instead of crashing
    return ""


def subscription_kb(channels: list) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        title = (ch.get("title") or ch.get("channel_id") or "Channel")[:40]
        ctype = ch.get("channel_type") or "public"
        url   = _channel_url(ch)
        icon  = "🔒" if ctype == "private" else "📢"

        if url:
            rows.append([InlineKeyboardButton(text=f"{icon} {title}", url=url)])
        else:
            # No valid URL — tell admin to fix via /fix_channels
            rows.append([InlineKeyboardButton(
                text=f"⚠️ {title} — run /fix_channels",
                callback_data="channel_fix_needed"
            )])

    rows.append([InlineKeyboardButton(text="✅ I've Subscribed", callback_data="check_sub")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ─── CONTENT DELIVERY ─────────────────────────────────────────

async def send_lesson_content(bot: Bot, chat_id: int, lesson: dict) -> bool:
    try:
        ctype = lesson.get("content_type", "forward")
        if ctype == "forward" and lesson.get("message_id") and lesson.get("channel_id"):
            await bot.forward_message(
                chat_id=chat_id,
                from_chat_id=lesson["channel_id"],
                message_id=lesson["message_id"]
            )
            return True

        fid = lesson.get("file_id")
        if not fid:
            await bot.send_message(chat_id, "⚠️ Content not available yet.")
            return False

        caption = lesson.get("description") or ""
        if   ctype == "video":      await bot.send_video(chat_id, fid, caption=caption)
        elif ctype == "document":   await bot.send_document(chat_id, fid, caption=caption)
        elif ctype == "photo":      await bot.send_photo(chat_id, fid, caption=caption)
        elif ctype == "audio":      await bot.send_audio(chat_id, fid, caption=caption)
        elif ctype == "voice":      await bot.send_voice(chat_id, fid, caption=caption)
        elif ctype == "video_note": await bot.send_video_note(chat_id, fid)
        elif ctype == "animation":  await bot.send_animation(chat_id, fid, caption=caption)
        else:                       await bot.send_document(chat_id, fid, caption=caption)
        return True

    except TelegramBadRequest as e:
        logger.error(f"send_lesson_content TelegramBadRequest: {e}")
        await bot.send_message(chat_id, "⚠️ Error delivering content. Please contact support.")
        return False
    except Exception as e:
        logger.error(f"send_lesson_content error: {e}")
        return False


async def send_promo_file(bot: Bot, chat_id: int, promo: dict) -> bool:
    try:
        fid     = promo.get("file_id")
        ftype   = promo.get("file_type", "document")
        caption = promo.get("file_caption") or ""
        if not fid:
            return False
        if   ftype == "video": await bot.send_video(chat_id, fid, caption=caption)
        elif ftype == "photo": await bot.send_photo(chat_id, fid, caption=caption)
        elif ftype == "audio": await bot.send_audio(chat_id, fid, caption=caption)
        else:                  await bot.send_document(chat_id, fid, caption=caption)
        return True
    except Exception as e:
        logger.error(f"send_promo_file error: {e}")
        return False


# ─── FORMATTING ───────────────────────────────────────────────

def safe_username(username) -> str:
    return f"@{username}" if username else "—"

def fmt_user(user: dict) -> str:
    vip = " 👑" if user.get("is_vip") else ""
    return f"<b>{user.get('full_name') or 'Unknown'}</b>{vip} ({safe_username(user.get('username'))})"

def fmt_lesson(lesson: dict) -> str:
    lock = "✅ Free" if lesson.get("is_free") else ("👑 VIP" if lesson.get("is_vip") else "🔒 Locked")
    return (
        f"<b>{lesson['title']}</b>\n"
        f"{lesson.get('description') or ''}\n"
        f"Status: {lock} | Views: {lesson.get('view_count', 0)}"
    )

def paginate(items: list, page: int, per_page: int = 8) -> tuple[list, int]:
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    return items[start:start + per_page], total_pages
