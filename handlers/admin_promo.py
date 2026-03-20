import secrets
import logging
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import settings
from database.promos import create_promo, get_all_promos, delete_promo
from keyboards.admin import admin_promo_kb, promo_type_kb, promo_expiry_kb
from keyboards.user import cancel_kb

router = Router()
logger = logging.getLogger(__name__)


def is_admin(uid): return uid in settings.admin_id_list


class PromoAdminState(StatesGroup):
    promo_type = State()
    promo_code = State()
    promo_passes = State()
    promo_lesson_id = State()
    promo_file = State()
    promo_expiry = State()
    promo_max_uses = State()


@router.callback_query(F.data == "adm:create_promo")
async def adm_create_promo(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(PromoAdminState.promo_type)
    await call.message.edit_text("🎟 <b>Create Promo Code</b>\n\nSelect promo type:", reply_markup=promo_type_kb())
    await call.answer()


@router.callback_query(F.data.startswith("promo_type:"))
async def promo_type_selected(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    ptype = call.data.split(":")[1]
    await state.update_data(promo_type=ptype)
    await state.set_state(PromoAdminState.promo_code)
    auto = secrets.token_hex(4).upper()
    await call.message.edit_text(
        f"Type: <b>{ptype}</b>\n\nEnter custom code or send '-' to auto-generate.\n"
        f"<i>Auto suggestion: <code>{auto}</code></i>",
        reply_markup=cancel_kb()
    )
    await state.update_data(auto_code=auto)
    await call.answer()


@router.message(PromoAdminState.promo_code)
async def promo_code_received(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    data = await state.get_data()
    code = data["auto_code"] if message.text.strip() == "-" else message.text.strip().upper()
    await state.update_data(promo_code=code)
    ptype = data["promo_type"]

    if ptype == "free_pass":
        await state.set_state(PromoAdminState.promo_passes)
        await message.answer(f"Code: <code>{code}</code>\n\nHow many free passes? (e.g. 1):", reply_markup=cancel_kb())
    elif ptype == "lesson_unlock":
        await state.set_state(PromoAdminState.promo_lesson_id)
        await message.answer(f"Code: <code>{code}</code>\n\nEnter Lesson ID to unlock:", reply_markup=cancel_kb())
    elif ptype == "file_reward":
        await state.set_state(PromoAdminState.promo_file)
        await message.answer(f"Code: <code>{code}</code>\n\nUpload the reward file:", reply_markup=cancel_kb())


@router.message(PromoAdminState.promo_passes)
async def promo_passes_received(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try:
        passes = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Enter a number:")
        return
    await state.update_data(promo_passes=passes)
    await state.set_state(PromoAdminState.promo_expiry)
    await message.answer("Set expiry:", reply_markup=promo_expiry_kb())


@router.message(PromoAdminState.promo_lesson_id)
async def promo_lesson_received(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    try:
        lid = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Enter a valid lesson ID:")
        return
    await state.update_data(promo_lesson_id=lid)
    await state.set_state(PromoAdminState.promo_expiry)
    await message.answer("Set expiry:", reply_markup=promo_expiry_kb())


@router.message(PromoAdminState.promo_file)
async def promo_file_received(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    file_id = None
    file_type = "document"
    if message.video:
        file_id = message.video.file_id; file_type = "video"
    elif message.document:
        file_id = message.document.file_id; file_type = "document"
    elif message.photo:
        file_id = message.photo[-1].file_id; file_type = "photo"
    elif message.audio:
        file_id = message.audio.file_id; file_type = "audio"
    if not file_id:
        await message.answer("⚠️ Please send a valid file.")
        return
    await state.update_data(promo_file_id=file_id, promo_file_type=file_type,
                            promo_file_caption=message.caption or "")
    await state.set_state(PromoAdminState.promo_expiry)
    await message.answer("Set expiry:", reply_markup=promo_expiry_kb())


@router.callback_query(F.data.startswith("promo_exp:"))
async def promo_expiry_selected(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    exp_key = call.data.split(":")[1]
    now = datetime.now()
    expires_at = None
    if exp_key == "1h":   expires_at = (now + timedelta(hours=1)).isoformat()
    elif exp_key == "1d": expires_at = (now + timedelta(days=1)).isoformat()
    elif exp_key == "1w": expires_at = (now + timedelta(weeks=1)).isoformat()
    elif exp_key == "1mo":expires_at = (now + timedelta(days=30)).isoformat()
    await state.update_data(promo_expires_at=expires_at)
    await state.set_state(PromoAdminState.promo_max_uses)
    await call.message.edit_text(
        "Max uses? (e.g. 100) or send '-' for unlimited:",
        reply_markup=cancel_kb()
    )
    await call.answer()


@router.message(PromoAdminState.promo_max_uses)
async def promo_max_uses_received(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id): return
    max_uses = None
    if message.text.strip() != "-":
        try:
            max_uses = int(message.text.strip())
        except ValueError:
            await message.answer("❌ Enter a number or '-':")
            return
    data = await state.get_data()
    await state.clear()

    await create_promo(
        code=data["promo_code"],
        promo_type=data["promo_type"],
        free_passes=data.get("promo_passes", 0),
        lesson_id=data.get("promo_lesson_id"),
        file_id=data.get("promo_file_id"),
        file_type=data.get("promo_file_type"),
        file_caption=data.get("promo_file_caption"),
        max_uses=max_uses,
        expires_at=data.get("promo_expires_at"),
    )
    await message.answer(
        f"✅ <b>Promo created!</b>\n\n"
        f"Code: <code>{data['promo_code']}</code>\n"
        f"Type: {data['promo_type']}\n"
        f"Max uses: {max_uses or '∞'}\n"
        f"Expires: {data.get('promo_expires_at') or 'Never'}",
        reply_markup=admin_promo_kb()
    )


@router.callback_query(F.data == "adm:list_promos")
async def adm_list_promos(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    promos = await get_all_promos()
    if not promos:
        await call.answer("No promos yet.", show_alert=True)
        return
    text = "🎟 <b>Promo Codes:</b>\n\n"
    for p in promos[:20]:
        status = "✅" if (not p["expires_at"] or datetime.fromisoformat(p["expires_at"]) > datetime.now()) else "❌"
        text += (
            f"{status} <code>{p['code']}</code> — {p['promo_type']}\n"
            f"  Uses: {p['uses_count']}/{p['max_uses'] or '∞'}  "
            f"Exp: {str(p['expires_at'] or 'Never')[:10]}\n"
        )
    text += "\n<i>To delete: /del_promo &lt;id&gt;</i>"
    await call.message.edit_text(text, reply_markup=admin_promo_kb())
    await call.answer()


@router.message(F.text.startswith("/del_promo"))
async def del_promo(message: Message):
    if not is_admin(message.from_user.id): return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Usage: /del_promo <id>")
        return
    await delete_promo(int(parts[1]))
    await message.answer(f"✅ Promo {parts[1]} deleted.")
