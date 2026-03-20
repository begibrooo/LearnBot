"""
Admin Content Management
─────────────────────────
Full inline button UI for managing:
  • Categories  — add, list, delete, toggle VIP
  • Levels      — add, list, delete, toggle VIP
  • Lessons     — add, list, delete, view detail
No text commands needed — everything via buttons.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import settings
from database.content import (
    get_categories, get_levels, get_lessons, get_lesson, get_level, get_category,
    add_category, add_level, add_lesson,
    delete_category, delete_level, delete_lesson,
    update_category, update_level, update_lesson,
)
from keyboards.admin import admin_content_kb, back_admin_kb
from keyboards.user import cancel_kb

router = Router()
logger = logging.getLogger(__name__)


def is_admin(uid): return uid in settings.admin_id_list


# ══════════════════════════════════════════════
#  CATEGORIES
# ══════════════════════════════════════════════

def cats_list_kb(cats: list) -> InlineKeyboardMarkup:
    rows = []
    for c in cats:
        vip = "👑" if c["is_vip"] else ""
        rows.append([
            InlineKeyboardButton(
                text=f"{c['emoji']} {c['name']} {vip}",
                callback_data=f"cat_detail:{c['id']}"
            ),
            InlineKeyboardButton(text="🗑 Delete", callback_data=f"cat_del:{c['id']}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ Add Category", callback_data="adm:add_cat")])
    rows.append([InlineKeyboardButton(text="◀️ Back", callback_data="adm:content")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cat_detail_kb(cat_id: int, is_vip: bool) -> InlineKeyboardMarkup:
    vip_label = "❌ Remove VIP" if is_vip else "👑 Make VIP"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=vip_label, callback_data=f"cat_vip:{cat_id}")],
        [InlineKeyboardButton(text="📖 View Levels", callback_data=f"lvl_list:{cat_id}")],
        [InlineKeyboardButton(text="🗑 Delete Category", callback_data=f"cat_del:{cat_id}")],
        [InlineKeyboardButton(text="◀️ Back", callback_data="adm:list_cats")],
    ])


@router.callback_query(F.data == "adm:list_cats")
async def adm_list_cats(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    cats = await get_categories()
    if not cats:
        await call.answer("No categories yet.", show_alert=True)
        await call.message.edit_text(
            "📚 <b>Categories</b>\n\nNo categories yet.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Add Category", callback_data="adm:add_cat")],
                [InlineKeyboardButton(text="◀️ Back", callback_data="adm:content")],
            ])
        )
        return
    await call.message.edit_text(
        f"📚 <b>Categories</b>  ({len(cats)} total)\n\nTap to manage, 🗑 to delete:",
        reply_markup=cats_list_kb(cats)
    )
    await call.answer()


@router.callback_query(F.data.startswith("cat_detail:"))
async def cat_detail(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    cat_id = int(call.data.split(":")[1])
    cat = await get_category(cat_id)
    if not cat:
        await call.answer("Not found.", show_alert=True); return
    levels = await get_levels(cat_id)
    await call.message.edit_text(
        f"📚 <b>{cat['emoji']} {cat['name']}</b>\n\n"
        f"VIP: {'👑 Yes' if cat['is_vip'] else 'No'}\n"
        f"Levels: <b>{len(levels)}</b>",
        reply_markup=cat_detail_kb(cat_id, bool(cat["is_vip"]))
    )
    await call.answer()


@router.callback_query(F.data.startswith("cat_vip:"))
async def cat_toggle_vip(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    cat_id = int(call.data.split(":")[1])
    cat = await get_category(cat_id)
    if not cat: await call.answer("Not found.", show_alert=True); return
    new_vip = 0 if cat["is_vip"] else 1
    await update_category(cat_id, is_vip=new_vip)
    await call.answer("👑 VIP enabled!" if new_vip else "VIP removed.", show_alert=True)
    cat = await get_category(cat_id)
    levels = await get_levels(cat_id)
    await call.message.edit_text(
        f"📚 <b>{cat['emoji']} {cat['name']}</b>\n\n"
        f"VIP: {'👑 Yes' if cat['is_vip'] else 'No'}\n"
        f"Levels: <b>{len(levels)}</b>",
        reply_markup=cat_detail_kb(cat_id, bool(cat["is_vip"]))
    )


@router.callback_query(F.data.startswith("cat_del:"))
async def cat_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    cat_id = int(call.data.split(":")[1])
    cat = await get_category(cat_id)
    if not cat: await call.answer("Not found.", show_alert=True); return
    await call.message.edit_text(
        f"⚠️ <b>Delete category?</b>\n\n"
        f"📚 <b>{cat['name']}</b>\n\n"
        f"This will also delete ALL levels and lessons inside it!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Yes, Delete", callback_data=f"cat_del_confirm:{cat_id}"),
                InlineKeyboardButton(text="❌ Cancel", callback_data="adm:list_cats"),
            ]
        ])
    )
    await call.answer()


@router.callback_query(F.data.startswith("cat_del_confirm:"))
async def cat_delete_confirm(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    cat_id = int(call.data.split(":")[1])
    cat = await get_category(cat_id)
    name = cat["name"] if cat else str(cat_id)
    await delete_category(cat_id)
    await call.answer(f"✅ '{name}' deleted.", show_alert=True)
    cats = await get_categories()
    await call.message.edit_text(
        f"📚 <b>Categories</b>  ({len(cats)} total)",
        reply_markup=cats_list_kb(cats)
    )


# ── ADD CATEGORY ──────────────────────────────

class CatState(StatesGroup):
    name  = State()
    emoji = State()
    is_vip = State()


@router.callback_query(F.data == "adm:add_cat")
async def adm_add_cat(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(CatState.name)
    await call.message.edit_text("📚 <b>Add Category — 1/3</b>\n\nEnter category <b>name</b>:", reply_markup=cancel_kb())
    await call.answer()


@router.message(CatState.name)
async def cat_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.update_data(name=message.text.strip())
    await state.set_state(CatState.emoji)
    await message.answer("📚 <b>Add Category — 2/3</b>\n\nSend an <b>emoji</b> for this category (or - to skip):", reply_markup=cancel_kb())


@router.message(CatState.emoji)
async def cat_emoji(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    emoji = "📚" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(emoji=emoji)
    await state.set_state(CatState.is_vip)
    await message.answer(
        "📚 <b>Add Category — 3/3</b>\n\nMake this a <b>VIP category</b>?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="👑 Yes, VIP", callback_data="cat_new_vip:1"),
            InlineKeyboardButton(text="🆓 No, Free", callback_data="cat_new_vip:0"),
        ]])
    )


@router.callback_query(F.data.startswith("cat_new_vip:"))
async def cat_new_vip(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    is_vip = int(call.data.split(":")[1])
    data = await state.get_data()
    await state.clear()
    cat_id = await add_category(data["name"], emoji=data.get("emoji","📚"), is_vip=is_vip)
    await call.message.edit_text(
        f"✅ <b>Category created!</b>\n\n"
        f"{data.get('emoji','📚')} <b>{data['name']}</b>\n"
        f"VIP: {'👑 Yes' if is_vip else 'No'}\n"
        f"ID: <code>{cat_id}</code>",
        reply_markup=back_admin_kb("list_cats")
    )
    await call.answer()


# ══════════════════════════════════════════════
#  LEVELS
# ══════════════════════════════════════════════

def lvls_list_kb(levels: list, cat_id: int) -> InlineKeyboardMarkup:
    rows = []
    for lv in levels:
        vip = "👑" if lv["is_vip"] else ""
        rows.append([
            InlineKeyboardButton(
                text=f"{lv['emoji']} {lv['name']} {vip}",
                callback_data=f"lvl_detail:{lv['id']}"
            ),
            InlineKeyboardButton(text="🗑 Delete", callback_data=f"lvl_del:{lv['id']}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ Add Level", callback_data=f"lvl_add:{cat_id}")])
    rows.append([InlineKeyboardButton(text="◀️ Back", callback_data=f"cat_detail:{cat_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def lvl_detail_kb(lvl_id: int, cat_id: int, is_vip: bool) -> InlineKeyboardMarkup:
    vip_label = "❌ Remove VIP" if is_vip else "👑 Make VIP"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=vip_label, callback_data=f"lvl_vip:{lvl_id}")],
        [InlineKeyboardButton(text="📝 View Lessons", callback_data=f"les_list:{lvl_id}")],
        [InlineKeyboardButton(text="🗑 Delete Level", callback_data=f"lvl_del:{lvl_id}")],
        [InlineKeyboardButton(text="◀️ Back", callback_data=f"lvl_list:{cat_id}")],
    ])


@router.callback_query(F.data == "adm:list_lvls")
async def adm_list_lvls_all(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    cats = await get_categories()
    rows = []
    for c in cats:
        lvls = await get_levels(c["id"])
        if lvls:
            rows.append([InlineKeyboardButton(
                text=f"📚 {c['name']} ({len(lvls)} levels)",
                callback_data=f"lvl_list:{c['id']}"
            )])
    if not rows:
        await call.answer("No levels yet.", show_alert=True); return
    rows.append([InlineKeyboardButton(text="◀️ Back", callback_data="adm:content")])
    await call.message.edit_text(
        "📖 <b>Levels</b> — Pick a category:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await call.answer()


@router.callback_query(F.data.startswith("lvl_list:"))
async def lvl_list(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    cat_id = int(call.data.split(":")[1])
    cat    = await get_category(cat_id)
    levels = await get_levels(cat_id)
    if not levels:
        await call.message.edit_text(
            f"📖 <b>{cat['name'] if cat else ''}</b> — No levels yet.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Add Level", callback_data=f"lvl_add:{cat_id}")],
                [InlineKeyboardButton(text="◀️ Back", callback_data=f"cat_detail:{cat_id}")],
            ])
        )
        await call.answer(); return
    cat_name = cat["name"] if cat else ""
    await call.message.edit_text(
        f"📖 <b>{cat_name}</b> — Levels ({len(levels)})\n\nTap to manage, 🗑 to delete:",
        reply_markup=lvls_list_kb(levels, cat_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("lvl_detail:"))
async def lvl_detail(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    lvl_id = int(call.data.split(":")[1])
    lv     = await get_level(lvl_id)
    if not lv: await call.answer("Not found.", show_alert=True); return
    lessons = await get_lessons(lvl_id)
    await call.message.edit_text(
        f"📖 <b>{lv['emoji']} {lv['name']}</b>\n\n"
        f"VIP: {'👑 Yes' if lv['is_vip'] else 'No'}\n"
        f"Lessons: <b>{len(lessons)}</b>",
        reply_markup=lvl_detail_kb(lvl_id, lv["category_id"], bool(lv["is_vip"]))
    )
    await call.answer()


@router.callback_query(F.data.startswith("lvl_vip:"))
async def lvl_toggle_vip(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    lvl_id = int(call.data.split(":")[1])
    lv = await get_level(lvl_id)
    if not lv: await call.answer("Not found.", show_alert=True); return
    new_vip = 0 if lv["is_vip"] else 1
    await update_level(lvl_id, is_vip=new_vip)
    await call.answer("👑 VIP enabled!" if new_vip else "VIP removed.", show_alert=True)
    lv = await get_level(lvl_id)
    lessons = await get_lessons(lvl_id)
    await call.message.edit_text(
        f"📖 <b>{lv['emoji']} {lv['name']}</b>\n\n"
        f"VIP: {'👑 Yes' if lv['is_vip'] else 'No'}\n"
        f"Lessons: <b>{len(lessons)}</b>",
        reply_markup=lvl_detail_kb(lvl_id, lv["category_id"], bool(lv["is_vip"]))
    )


@router.callback_query(F.data.startswith("lvl_del:"))
async def lvl_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    lvl_id = int(call.data.split(":")[1])
    lv = await get_level(lvl_id)
    if not lv: await call.answer("Not found.", show_alert=True); return
    await call.message.edit_text(
        f"⚠️ <b>Delete level?</b>\n\n"
        f"📖 <b>{lv['name']}</b>\n\n"
        f"This will also delete ALL lessons inside it!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🗑 Yes, Delete", callback_data=f"lvl_del_confirm:{lvl_id}:{lv['category_id']}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data=f"lvl_list:{lv['category_id']}"),
        ]])
    )
    await call.answer()


@router.callback_query(F.data.startswith("lvl_del_confirm:"))
async def lvl_delete_confirm(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    parts  = call.data.split(":")
    lvl_id = int(parts[1])
    cat_id = int(parts[2])
    lv     = await get_level(lvl_id)
    name   = lv["name"] if lv else str(lvl_id)
    await delete_level(lvl_id)
    await call.answer(f"✅ '{name}' deleted.", show_alert=True)
    levels = await get_levels(cat_id)
    cat    = await get_category(cat_id)
    cat_name = cat["name"] if cat else ""
    await call.message.edit_text(
        f"📖 <b>{cat_name}</b> — Levels ({len(levels)})",
        reply_markup=lvls_list_kb(levels, cat_id)
    )


# ── ADD LEVEL ─────────────────────────────────

class LvlState(StatesGroup):
    cat_id = State()
    name   = State()
    emoji  = State()
    is_vip = State()


@router.callback_query(F.data == "adm:add_lvl")
async def adm_add_lvl_pick_cat(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    cats = await get_categories()
    if not cats:
        await call.answer("Add a category first!", show_alert=True); return
    rows = [[InlineKeyboardButton(text=f"{c['emoji']} {c['name']}", callback_data=f"lvl_add:{c['id']}")]
            for c in cats]
    rows.append([InlineKeyboardButton(text="❌ Cancel", callback_data="adm:content")])
    await call.message.edit_text("📖 <b>Add Level</b>\n\nSelect category:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()


@router.callback_query(F.data.startswith("lvl_add:"))
async def lvl_add_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    cat_id = int(call.data.split(":")[1])
    await state.update_data(cat_id=cat_id)
    await state.set_state(LvlState.name)
    await call.message.edit_text("📖 <b>Add Level — 1/3</b>\n\nEnter level <b>name</b>:", reply_markup=cancel_kb())
    await call.answer()


@router.message(LvlState.name)
async def lvl_name(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.update_data(name=message.text.strip())
    await state.set_state(LvlState.emoji)
    await message.answer("📖 <b>Add Level — 2/3</b>\n\nSend an <b>emoji</b> (or - to skip):", reply_markup=cancel_kb())


@router.message(LvlState.emoji)
async def lvl_emoji(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    emoji = "📖" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(emoji=emoji)
    await state.set_state(LvlState.is_vip)
    await message.answer(
        "📖 <b>Add Level — 3/3</b>\n\nMake this a <b>VIP level</b>?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="👑 Yes, VIP", callback_data="lvl_new_vip:1"),
            InlineKeyboardButton(text="🆓 No, Free", callback_data="lvl_new_vip:0"),
        ]])
    )


@router.callback_query(F.data.startswith("lvl_new_vip:"))
async def lvl_new_vip(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    is_vip = int(call.data.split(":")[1])
    data   = await state.get_data()
    await state.clear()
    lvl_id = await add_level(data["cat_id"], data["name"], emoji=data.get("emoji","📖"), is_vip=is_vip)
    await call.message.edit_text(
        f"✅ <b>Level created!</b>\n\n"
        f"{data.get('emoji','📖')} <b>{data['name']}</b>\n"
        f"VIP: {'👑 Yes' if is_vip else 'No'}\n"
        f"ID: <code>{lvl_id}</code>",
        reply_markup=back_admin_kb(f"lvl_list:{data['cat_id']}")
    )
    await call.answer()


# ══════════════════════════════════════════════
#  LESSONS
# ══════════════════════════════════════════════

def les_list_kb(lessons: list, lvl_id: int) -> InlineKeyboardMarkup:
    rows = []
    for les in lessons:
        icon = "✅" if les["is_free"] else ("👑" if les["is_vip"] else "🔒")
        title = les["title"][:30] + ("…" if len(les["title"]) > 30 else "")
        rows.append([
            InlineKeyboardButton(text=f"{icon} {title}", callback_data=f"les_detail:{les['id']}"),
            InlineKeyboardButton(text="🗑", callback_data=f"les_del:{les['id']}:{lvl_id}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ Add Lesson", callback_data=f"les_add:{lvl_id}")])
    rows.append([InlineKeyboardButton(text="◀️ Back", callback_data=f"lvl_detail:{lvl_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def les_detail_kb(les_id: int, lvl_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Delete Lesson", callback_data=f"les_del:{les_id}:{lvl_id}")],
        [InlineKeyboardButton(text="◀️ Back", callback_data=f"les_list:{lvl_id}")],
    ])


@router.callback_query(F.data == "adm:list_les")
async def adm_list_les_pick(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    cats = await get_categories()
    rows = []
    for c in cats:
        rows.append([InlineKeyboardButton(text=f"📚 {c['name']}", callback_data=f"les_list_cat:{c['id']}")])
    if not rows:
        await call.answer("No content yet.", show_alert=True); return
    rows.append([InlineKeyboardButton(text="◀️ Back", callback_data="adm:content")])
    await call.message.edit_text("📝 <b>Lessons</b> — Pick a category:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()


@router.callback_query(F.data.startswith("les_list_cat:"))
async def les_list_cat(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    cat_id = int(call.data.split(":")[1])
    cat    = await get_category(cat_id)
    levels = await get_levels(cat_id)
    rows   = []
    for lv in levels:
        lessons = await get_lessons(lv["id"])
        rows.append([InlineKeyboardButton(
            text=f"📖 {lv['name']} ({len(lessons)} lessons)",
            callback_data=f"les_list:{lv['id']}"
        )])
    if not rows:
        await call.answer("No levels in this category.", show_alert=True); return
    rows.append([InlineKeyboardButton(text="◀️ Back", callback_data="adm:list_les")])
    cat_name = cat["name"] if cat else ""
    await call.message.edit_text(
        f"📝 <b>{cat_name}</b> — Pick a level:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await call.answer()


@router.callback_query(F.data.startswith("les_list:"))
async def les_list(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    lvl_id  = int(call.data.split(":")[1])
    lv      = await get_level(lvl_id)
    lessons = await get_lessons(lvl_id)
    lv_name = lv["name"] if lv else ""
    if not lessons:
        await call.message.edit_text(
            f"📝 <b>{lv_name}</b> — No lessons yet.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Add Lesson", callback_data=f"les_add:{lvl_id}")],
                [InlineKeyboardButton(text="◀️ Back", callback_data=f"lvl_detail:{lvl_id}")],
            ])
        )
        await call.answer(); return
    await call.message.edit_text(
        f"📝 <b>{lv_name}</b> — Lessons ({len(lessons)})\n\nTap to view, 🗑 to delete:",
        reply_markup=les_list_kb(lessons, lvl_id)
    )
    await call.answer()


@router.callback_query(F.data.startswith("les_detail:"))
async def les_detail(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    les_id = int(call.data.split(":")[1])
    les    = await get_lesson(les_id)
    if not les: await call.answer("Not found.", show_alert=True); return
    lv = await get_level(les["level_id"])
    status = "✅ Free" if les["is_free"] else ("👑 VIP" if les["is_vip"] else "🔒 Locked")
    await call.message.edit_text(
        f"📝 <b>{les['title']}</b>\n\n"
        f"Status: {status}\n"
        f"Type: {les['content_type']}\n"
        f"Views: {les.get('view_count', 0)}\n"
        f"Level: {lv['name'] if lv else '—'}\n"
        f"Code: <code>{les.get('unlock_code') or '—'}</code>\n"
        f"Description: {les.get('description') or '—'}",
        reply_markup=les_detail_kb(les_id, les["level_id"])
    )
    await call.answer()


@router.callback_query(F.data.startswith("les_del:"))
async def les_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    parts  = call.data.split(":")
    les_id = int(parts[1])
    lvl_id = int(parts[2])
    les    = await get_lesson(les_id)
    if not les: await call.answer("Not found.", show_alert=True); return
    await call.message.edit_text(
        f"⚠️ <b>Delete lesson?</b>\n\n"
        f"📝 <b>{les['title']}</b>\n\n"
        f"This cannot be undone.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🗑 Yes, Delete", callback_data=f"les_del_confirm:{les_id}:{lvl_id}"),
            InlineKeyboardButton(text="❌ Cancel", callback_data=f"les_list:{lvl_id}"),
        ]])
    )
    await call.answer()


@router.callback_query(F.data.startswith("les_del_confirm:"))
async def les_delete_confirm(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    parts  = call.data.split(":")
    les_id = int(parts[1])
    lvl_id = int(parts[2])
    les    = await get_lesson(les_id)
    name   = les["title"] if les else str(les_id)
    await delete_lesson(les_id)
    await call.answer(f"✅ '{name}' deleted.", show_alert=True)
    lessons = await get_lessons(lvl_id)
    lv      = await get_level(lvl_id)
    lv_name = lv["name"] if lv else ""
    await call.message.edit_text(
        f"📝 <b>{lv_name}</b> — Lessons ({len(lessons)})",
        reply_markup=les_list_kb(lessons, lvl_id)
    )


# ── ADD LESSON ────────────────────────────────

class LesState(StatesGroup):
    lvl_id      = State()
    title       = State()
    description = State()
    code        = State()
    is_free     = State()
    is_vip      = State()
    content     = State()


@router.callback_query(F.data == "adm:add_les")
async def adm_add_les_pick(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    cats = await get_categories()
    if not cats:
        await call.answer("Add a category first!", show_alert=True); return
    rows = [[InlineKeyboardButton(text=f"📚 {c['name']}", callback_data=f"les_add_cat:{c['id']}")]
            for c in cats]
    rows.append([InlineKeyboardButton(text="❌ Cancel", callback_data="adm:content")])
    await call.message.edit_text("📝 <b>Add Lesson</b>\n\nSelect category:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()


@router.callback_query(F.data.startswith("les_add_cat:"))
async def les_add_cat(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    cat_id = int(call.data.split(":")[1])
    levels = await get_levels(cat_id)
    if not levels:
        await call.answer("Add a level first!", show_alert=True); return
    rows = [[InlineKeyboardButton(text=f"📖 {lv['name']}", callback_data=f"les_add:{lv['id']}")]
            for lv in levels]
    rows.append([InlineKeyboardButton(text="❌ Cancel", callback_data="adm:content")])
    await call.message.edit_text("📝 <b>Add Lesson</b>\n\nSelect level:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await call.answer()


@router.callback_query(F.data.startswith("les_add:"))
async def les_add_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    lvl_id = int(call.data.split(":")[1])
    await state.update_data(lvl_id=lvl_id)
    await state.set_state(LesState.title)
    await call.message.edit_text("📝 <b>Add Lesson — 1/6</b>\n\nEnter lesson <b>title</b>:", reply_markup=cancel_kb())
    await call.answer()


@router.message(LesState.title)
async def les_title(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    await state.update_data(title=message.text.strip())
    await state.set_state(LesState.description)
    await message.answer("📝 <b>Add Lesson — 2/6</b>\n\nEnter <b>description</b> (or - to skip):", reply_markup=cancel_kb())


@router.message(LesState.description)
async def les_desc(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    desc = None if message.text.strip() == "-" else message.text.strip()
    await state.update_data(description=desc)
    await state.set_state(LesState.code)
    await message.answer("📝 <b>Add Lesson — 3/6</b>\n\nEnter <b>unlock code</b> (or - for none):", reply_markup=cancel_kb())


@router.message(LesState.code)
async def les_code(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    code = None if message.text.strip() == "-" else message.text.strip()
    await state.update_data(code=code)
    await state.set_state(LesState.is_free)
    await message.answer(
        "📝 <b>Add Lesson — 4/6</b>\n\nIs this a <b>free</b> lesson?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Yes, Free", callback_data="les_new_free:1"),
            InlineKeyboardButton(text="🔒 No, Locked", callback_data="les_new_free:0"),
        ]])
    )


@router.callback_query(F.data.startswith("les_new_free:"))
async def les_new_free(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    is_free = int(call.data.split(":")[1])
    await state.update_data(is_free=is_free)
    await state.set_state(LesState.is_vip)
    await call.message.edit_text(
        "📝 <b>Add Lesson — 5/6</b>\n\nIs this a <b>VIP</b> lesson?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="👑 Yes, VIP", callback_data="les_new_vip:1"),
            InlineKeyboardButton(text="🆓 No", callback_data="les_new_vip:0"),
        ]])
    )
    await call.answer()


@router.callback_query(F.data.startswith("les_new_vip:"))
async def les_new_vip(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    is_vip = int(call.data.split(":")[1])
    await state.update_data(is_vip=is_vip)
    await state.set_state(LesState.content)
    await call.message.edit_text(
        "📝 <b>Add Lesson — 6/6</b>\n\n"
        "Now send the <b>lesson content</b>:\n\n"
        "• Forward a message from your channel, OR\n"
        "• Upload a file (video, doc, photo, audio...)",
        reply_markup=cancel_kb()
    )
    await call.answer()


@router.message(LesState.content)
async def les_content(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    await state.clear()

    content_type = "forward"
    file_id = msg_id = channel_id = None

    if message.forward_from_chat:
        content_type = "forward"
        msg_id       = message.forward_from_message_id
        channel_id   = str(message.forward_from_chat.id)
    elif message.video:        content_type = "video";      file_id = message.video.file_id
    elif message.document:     content_type = "document";   file_id = message.document.file_id
    elif message.photo:        content_type = "photo";      file_id = message.photo[-1].file_id
    elif message.audio:        content_type = "audio";      file_id = message.audio.file_id
    elif message.voice:        content_type = "voice";      file_id = message.voice.file_id
    elif message.video_note:   content_type = "video_note"; file_id = message.video_note.file_id
    elif message.animation:    content_type = "animation";  file_id = message.animation.file_id
    else:
        await message.answer("⚠️ Unsupported content type. Lesson not saved."); return

    les_id = await add_lesson(
        level_id=data["lvl_id"],
        title=data["title"],
        description=data.get("description"),
        content_type=content_type,
        file_id=file_id,
        message_id=msg_id,
        channel_id=channel_id,
        unlock_code=data.get("code"),
        is_free=data.get("is_free", 0),
        is_vip=data.get("is_vip", 0),
    )
    await message.answer(
        f"✅ <b>Lesson created!</b>\n\n"
        f"📝 <b>{data['title']}</b>\n"
        f"Type: {content_type}\n"
        f"Free: {'Yes' if data.get('is_free') else 'No'} | "
        f"VIP: {'Yes' if data.get('is_vip') else 'No'}\n"
        f"ID: <code>{les_id}</code>",
        reply_markup=back_admin_kb(f"les_list:{data['lvl_id']}")
    )
