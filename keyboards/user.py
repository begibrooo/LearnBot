from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def main_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.row(KeyboardButton(text="📚 All Materials"), KeyboardButton(text="📖 My Lessons"))
    kb.row(KeyboardButton(text="👤 Profile"),       KeyboardButton(text="🔍 Search"))
    kb.row(KeyboardButton(text="🎟 Promo Code"),    KeyboardButton(text="👥 Invite Friends"))
    kb.row(KeyboardButton(text="🏆 Leaderboard"),   KeyboardButton(text="✍️ Support"))
    kb.row(KeyboardButton(text="✅ Check-in"),      KeyboardButton(text="🧠 Quiz"))
    kb.row(KeyboardButton(text="📊 My Stats"),          KeyboardButton(text="📋 Help"))
    kb.row(KeyboardButton(text="🏅 Badges"),            KeyboardButton(text="⚡ Challenge"))
    kb.row(KeyboardButton(text="🤖 AI Chat"),             KeyboardButton(text="🎮 Play Games"))
    return kb.as_markup(resize_keyboard=True)


def categories_kb(categories: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        vip = " 👑" if cat["is_vip"] else ""
        builder.button(text=f"{cat['emoji']} {cat['name']}{vip}", callback_data=f"cat:{cat['id']}")
    builder.adjust(2)
    return builder.as_markup()


def levels_kb(levels: list, cat_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for lvl in levels:
        vip = " 👑" if lvl["is_vip"] else ""
        builder.button(text=f"{lvl['emoji']} {lvl['name']}{vip}", callback_data=f"lvl:{lvl['id']}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data="back_cat"))
    return builder.as_markup()


def lessons_kb(lessons: list, level_id: int, unlocked_ids: set) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for les in lessons:
        icon = "✅" if (les["is_free"] or les["id"] in unlocked_ids) else ("👑" if les["is_vip"] else "🔒")
        builder.button(text=f"{icon} {les['title']}", callback_data=f"les:{les['id']}")
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="◀️ Back", callback_data=f"back_lvl:{level_id}"))
    return builder.as_markup()


def lesson_detail_kb(lesson_id: int, is_unlocked: bool, is_free: bool, is_vip: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if is_free or is_unlocked:
        builder.button(text="▶️ Open Lesson", callback_data=f"open:{lesson_id}")
    else:
        builder.button(text="🔑 Enter Code",    callback_data=f"code:{lesson_id}")
        builder.button(text="🎫 Use Free Pass", callback_data=f"freepass:{lesson_id}")
    builder.button(text="◀️ Back", callback_data=f"back_les:{lesson_id}")
    builder.adjust(1)
    return builder.as_markup()


def confirm_kb(yes_cb: str, no_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Yes", callback_data=yes_cb),
        InlineKeyboardButton(text="❌ No",  callback_data=no_cb),
    ]])


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Cancel", callback_data="cancel")
    ]])


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🏠 Main Menu", callback_data="main_menu")
    ]])


# ─── STYLED ACTION BUTTONS (screenshot style) ─────────────────
#
# Produces rows like:
#   [ ⚡ Pul ishlash 💰          ] [ ↗ ]
#   [ 💰 Ovoz berish 📦          ] [ ↗ ]
#   [ 🎁 Sovgani olish 🎁        ] [ ↗ ]
#
# Each item: (label, callback_data_or_url)
# If target starts with "http" → URL button; otherwise → callback button.

def action_buttons_kb(buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = []
    for label, target in buttons:
        is_url = target.startswith("http://") or target.startswith("https://")
        if is_url:
            main_btn  = InlineKeyboardButton(text=label,  url=target)
            arrow_btn = InlineKeyboardButton(text="↗",    url=target)
        else:
            main_btn  = InlineKeyboardButton(text=label,  callback_data=target)
            arrow_btn = InlineKeyboardButton(text="↗",    callback_data=target)
        rows.append([main_btn, arrow_btn])
    return InlineKeyboardMarkup(inline_keyboard=rows)
