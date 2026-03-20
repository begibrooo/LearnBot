from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


# ════════════════════════════════════════════
#  MAIN ADMIN PANEL  —  categorised sections
# ════════════════════════════════════════════

def admin_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Content",      callback_data="adm:content"),
         InlineKeyboardButton(text="👥 Members",      callback_data="mbr:filter:all:0")],
        [InlineKeyboardButton(text="🎟 Promos",       callback_data="adm:promos"),
         InlineKeyboardButton(text="🧠 Quizzes",      callback_data="adm:quiz")],
        [InlineKeyboardButton(text="📢 Broadcast",    callback_data="adm:broadcast"),
         InlineKeyboardButton(text="📡 Channels",     callback_data="adm:channels")],
        [InlineKeyboardButton(text="🎁 Rewards",      callback_data="adm:rewards"),
         InlineKeyboardButton(text="⚡ Challenge",    callback_data="adm:set_challenge")],
        [InlineKeyboardButton(text="📊 Analytics",    callback_data="adm:analytics"),
         InlineKeyboardButton(text="⚙️ Settings",     callback_data="adm:settings")],
        [InlineKeyboardButton(text="🎮 Games",         callback_data="adm:games")],
    ])


# ════════════════════════════════
#  CONTENT
# ════════════════════════════════

def admin_content_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Category",    callback_data="adm:add_cat"),
         InlineKeyboardButton(text="📋 Categories",     callback_data="adm:list_cats")],
        [InlineKeyboardButton(text="➕ Add Level",       callback_data="adm:add_lvl"),
         InlineKeyboardButton(text="📋 Levels",         callback_data="adm:list_lvls")],
        [InlineKeyboardButton(text="➕ Add Lesson",      callback_data="adm:add_les"),
         InlineKeyboardButton(text="📋 Lessons",        callback_data="adm:list_les")],
        [InlineKeyboardButton(text="⭐ Top Rated",      callback_data="adm:top_rated"),
         InlineKeyboardButton(text="🔥 Most Viewed",    callback_data="adm:most_viewed")],
        [InlineKeyboardButton(text="◀️ Back",            callback_data="adm:main")],
    ])


def admin_content_kb_inline() -> InlineKeyboardMarkup:
    """Same as admin_content_kb — alias for back buttons."""
    return admin_content_kb()


# ════════════════════════════════
#  USERS
# ════════════════════════════════

def admin_users_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 All Members",     callback_data="mbr:filter:all:0"),
         InlineKeyboardButton(text="👑 VIP Users",       callback_data="mbr:filter:vip:0")],
        [InlineKeyboardButton(text="🚫 Banned Users",    callback_data="adm:banned_users"),
         InlineKeyboardButton(text="🔍 Find User",       callback_data="adm:lookup_user")],
        [InlineKeyboardButton(text="🎫 Give Pass",       callback_data="adm:give_pass"),
         InlineKeyboardButton(text="👑 Grant VIP",       callback_data="adm:grant_vip")],
        [InlineKeyboardButton(text="❌ Revoke VIP",      callback_data="adm:revoke_vip"),
         InlineKeyboardButton(text="🚫 Ban User",        callback_data="adm:ban_user")],
        [InlineKeyboardButton(text="✅ Unban User",      callback_data="adm:unban_user"),
         InlineKeyboardButton(text="📊 Stats",           callback_data="adm:user_stats")],
        [InlineKeyboardButton(text="◀️ Back",            callback_data="adm:main")],
    ])


# ════════════════════════════════
#  PROMOS
# ════════════════════════════════

def admin_promo_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Create Promo",   callback_data="adm:create_promo"),
         InlineKeyboardButton(text="📋 List Promos",   callback_data="adm:list_promos")],
        [InlineKeyboardButton(text="◀️ Back",           callback_data="adm:main")],
    ])


# ════════════════════════════════
#  SETTINGS
# ════════════════════════════════

def admin_settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔧 Fix Channel Links",  callback_data="adm:fix_channels_btn")],
        [InlineKeyboardButton(text="📋 Re-add Channel",     callback_data="adm:readd_channel_btn")],
        [InlineKeyboardButton(text="📝 Bot Info",           callback_data="adm:bot_info")],
        [InlineKeyboardButton(text="◀️ Back",               callback_data="adm:main")],
    ])


# ════════════════════════════════
#  PROMO CREATION
# ════════════════════════════════

def promo_type_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🎫 Free Pass",     callback_data="promo_type:free_pass")
    builder.button(text="🔓 Lesson Unlock", callback_data="promo_type:lesson_unlock")
    builder.button(text="📁 File Reward",   callback_data="promo_type:file_reward")
    builder.button(text="❌ Cancel",        callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


def promo_expiry_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="1 hour",    callback_data="promo_exp:1h")
    builder.button(text="1 day",     callback_data="promo_exp:1d")
    builder.button(text="1 week",    callback_data="promo_exp:1w")
    builder.button(text="1 month",   callback_data="promo_exp:1mo")
    builder.button(text="No expiry", callback_data="promo_exp:none")
    builder.button(text="❌ Cancel",  callback_data="cancel")
    builder.adjust(2)
    return builder.as_markup()


def back_admin_kb(section: str = "main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◀️ Back", callback_data=f"adm:{section}")
    ]])
